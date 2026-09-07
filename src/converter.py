"""
Main PDF to EPUB Converter - Orchestrates the conversion process
"""
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from .pdf_processor import PDFProcessor
from .ocr_engine import OCREngine
from .text_cleaner import TextCleaner
from .epub_builder import EPUBBuilder
from .config import EPUB_LANGUAGE, EPUB_PUBLISHER

from .logging_config import get_logger
logger = get_logger(__name__)


class PDFToEPUBConverter:
    """Main converter class that orchestrates the PDF to EPUB conversion"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize converter
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.pdf_processor = None
        self.ocr_engine = OCREngine()
        self.text_cleaner = TextCleaner()
        
        logger.info("PDF to EPUB Converter initialized")
    
    def convert(
        self,
        pdf_path: str,
        output_path: str,
        title: Optional[str] = None,
        author: str = "Unknown",
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> str:
        """
        Convert PDF to EPUB
        
        Args:
            pdf_path: Path to input PDF file
            output_path: Path to output EPUB file
            title: Book title (uses PDF filename if not provided)
            author: Book author
            progress_callback: Optional callback(stage, current, total)
                stage: 'extract', 'ocr', 'clean', 'build'
                current: current item number
                total: total items
        
        Returns:
            Path to generated EPUB file
        """
        try:
            # Determine title from filename if not provided
            if title is None:
                title = Path(pdf_path).stem
            
            logger.info(f"Starting conversion: {pdf_path} -> {output_path}")
            logger.info(f"Title: {title}, Author: {author}")
            
            # Step 1: Extract pages from PDF
            logger.info("Step 1/4: Extracting pages from PDF...")
            self.pdf_processor = PDFProcessor(pdf_path)
            
            def extract_progress(current, total):
                if progress_callback:
                    progress_callback('extract', current, total)
            
            images = self.pdf_processor.extract_pages(progress_callback=extract_progress)
            logger.info(f"Extracted {len(images)} pages")
            
            # Step 2: OCR - Extract text from images
            logger.info("Step 2/4: Performing OCR on pages...")
            
            def ocr_progress(current, total):
                if progress_callback:
                    progress_callback('ocr', current, total)
            
            page_texts = self.ocr_engine.process_pages(images, progress_callback=ocr_progress)
            logger.info(f"OCR complete. Extracted text from {len(page_texts)} pages")
            
            # Step 3: Clean extracted text
            logger.info("Step 3/4: Cleaning extracted text...")
            if progress_callback:
                progress_callback('clean', 0, len(page_texts))
            
            cleaned_texts = self.text_cleaner.clean_pages(page_texts)
            
            if progress_callback:
                progress_callback('clean', len(page_texts), len(page_texts))
            
            logger.info("Text cleaning complete")
            
            # Step 4: Build EPUB
            logger.info("Step 4/4: Building EPUB file...")
            if progress_callback:
                progress_callback('build', 0, 1)
            
            epub_builder = EPUBBuilder(
                title=title,
                author=author,
                language=self.config.get('language', EPUB_LANGUAGE),
                publisher=self.config.get('publisher', EPUB_PUBLISHER)
            )
            
            # Add chapters from pages
            epub_builder.add_chapters_from_pages(
                cleaned_texts,
                pages_per_chapter=self.config.get('pages_per_chapter', 10)
            )
            
            # Add cover image if provided
            cover_image = self.config.get('cover_image')
            if cover_image and Path(cover_image).exists():
                epub_builder.add_cover_image(cover_image)
            
            # Build EPUB
            output_file = epub_builder.build(output_path)
            
            if progress_callback:
                progress_callback('build', 1, 1)
            
            logger.info(f"Conversion complete! EPUB saved to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            raise
    
    def convert_with_options(
        self,
        pdf_path: str,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Convert PDF to EPUB with custom options
        
        Args:
            pdf_path: Path to input PDF file
            options: Dictionary of conversion options
                - output_path: Output EPUB path (default: same as PDF with .epub)
                - title: Book title
                - author: Book author
                - language: Language code
                - publisher: Publisher name
                - pages_per_chapter: Pages per chapter
                - cover_image: Path to cover image
                - progress_callback: Progress callback function
        
        Returns:
            Path to generated EPUB file
        """
        options = options or {}
        
        # Determine output path
        output_path = options.get('output_path')
        if output_path is None:
            pdf_file = Path(pdf_path)
            output_path = pdf_file.with_suffix('.epub')
        
        # Update config with options
        self.config.update(options)
        
        # Convert
        return self.convert(
            pdf_path=pdf_path,
            output_path=str(output_path),
            title=options.get('title'),
            author=options.get('author', 'Unknown'),
            progress_callback=options.get('progress_callback')
        )
    
    def get_pdf_info(self, pdf_path: str) -> Dict[str, Any]:
        """
        Get information about PDF file
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Dictionary with PDF information
        """
        try:
            processor = PDFProcessor(pdf_path)
            images = processor.extract_pages()
            
            return {
                'path': pdf_path,
                'filename': Path(pdf_path).name,
                'page_count': len(images),
                'file_size': Path(pdf_path).stat().st_size,
            }
        except Exception as e:
            logger.error(f"Failed to get PDF info: {e}")
            return {
                'path': pdf_path,
                'error': str(e)
            }



