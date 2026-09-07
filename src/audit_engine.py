"""
Audit Engine
Compares current EPUB content against live PDF OCR to detect quality gaps.
"""
import logging
from pathlib import Path
from typing import List, Dict, Any

from epub_extractor import EPUBExtractor
from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
from page_complexity_analyzer import PageComplexityAnalyzer
import config

logger = logging.getLogger(__name__)

class AuditEngine:
    """Orchestrates the comparison between a PDF and an existing EPUB."""
    
    def __init__(self, pdf_path: Path, epub_path: Path):
        self.pdf_path = pdf_path
        self.epub_path = epub_path
        self.extractor = EPUBExtractor(epub_path)
        self.converter = OptimizedPDFToEPUBConverter(language=config.DEFAULT_OCR_LANGUAGE)
        self.audit_results = [] # List of discrepancy reports

    def run_audit(self, page_range: List[int] = None) -> List[Dict]:
        """
        Compare the existing EPUB text against new OCR results.
        
        Args:
            page_range: Optional filter for specific pages (1-indexed).
            
        Returns:
            List of discrepancy reports.
        """
        if not self.extractor.extract_all():
            return []
            
        # 1. Map EPUB chapters to PDF page ranges
        # Assumes 10 pages per chapter based on config.PAGES_PER_CHAPTER
        pages_per_chapter = config.PAGES_PER_CHAPTER
        
        results = []
        
        # We process pages in batches to match chapter structure
        # (Chapter 1 = Pages 1-10, Chapter 2 = Pages 11-20, etc.)
        for ch_idx, chapter in enumerate(self.extractor.chapters):
            # Calculate PDF page range for this chapter
            start_page = (ch_idx * pages_per_chapter) + 1
            end_page = start_page + pages_per_chapter - 1
            
            # If a specific page range was requested, skip if this chapter is outside it
            if page_range:
                if not any(start_page <= p <= end_page for p in page_range):
                    continue
            
            logger.info(f"Auditing Chapter {ch_idx + 1} (PDF Pages {start_page}-{end_page})")
            
            # 2. Get the "Ground Truth" line count from PDF images
            # This is the physical number of lines seen on the page
            import fitz
            doc = fitz.open(self.pdf_path)
            
            # Limit end_page to total PDF pages
            end_page = min(end_page, len(doc))
            
            for p_num in range(start_page, end_page + 1):
                if page_range and p_num not in page_range:
                    continue
                    
                # Load page image
                page = doc.load_page(p_num - 1)
                pix = page.get_pixmap(dpi=300)
                from PIL import Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Analyze page complexity and estimate lines
                analyzer = PageComplexityAnalyzer()
                analysis = analyzer.analyze(img)
                estimated_lines = analysis.get('estimated_lines', 0)
                
                # 3. Find the corresponding text segment in the EPUB chapter
                # For now, we estimate the "Page Block" within a chapter by splitting
                # proportionally. In a high-end implementation, we'd use fuzzy matching.
                blocks = chapter['text'].split("\n\n")
                # Approximate block for this page within the chapter
                # (10 pages per chapter, so we look at the corresponding 1/10th of blocks)
                start_block = (p_num - start_page) * max(1, len(blocks) // pages_per_chapter)
                end_block = start_block + max(1, len(blocks) // pages_per_chapter)
                epub_segment = "\n\n".join(blocks[start_block:end_block])
                
                actual_lines = analyzer.get_text_line_count(epub_segment)
                
                # 4. Detect Discrepancy
                # If EPUB has significantly fewer lines than the PDF image
                discrepancy = {
                    'page_num': p_num,
                    'estimated_lines': estimated_lines,
                    'epub_lines': actual_lines,
                    'epub_text': epub_segment,
                    'status': 'Match'
                }
                
                if estimated_lines > 5 and actual_lines < (estimated_lines * 0.7):
                    discrepancy['status'] = 'Discrepancy'
                    discrepancy['message'] = f"Missing lines detected: {actual_lines} in EPUB vs ~{estimated_lines} in PDF"
                    logger.warning(f"  ⚠️ DETECTED: Page {p_num} has a line count discrepancy")
                
                results.append(discrepancy)
            
            doc.close()
            
        self.audit_results = results
        return results

    def resolve_discrepancy(self, page_num: int) -> str:
        """
        Run high-accuracy Gemini OCR for a specific page to resolve a discrepancy.
        """
        import fitz
        doc = fitz.open(self.pdf_path)
        page = doc.load_page(page_num - 1)
        pix = page.get_pixmap(dpi=300)
        from PIL import Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Get Gemini processor
        gemini_processor = self.converter.adaptive_factory._get_cached_processor('gemini', self.converter.language)
        if not (gemini_processor and gemini_processor.is_available):
            return "Error: Gemini API not available for resolution"
            
        # Extract text via Gemini
        improved_text = gemini_processor.extract_text(img)
        doc.close()
        
        return improved_text
