"""
PDF Manipulation Utilities
Split, merge, remove pages, and reorder PDFs
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple, Optional
import logging
from logging_config import get_logger

logger = get_logger(__name__)


class PDFManipulator:
    """Utility class for PDF manipulation operations"""
    
    @staticmethod
    def get_page_count(pdf_path: Path) -> int:
        """Get total number of pages in PDF"""
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            logger.error(f"Failed to get page count: {e}")
            return 0
    
    @staticmethod
    def split_pdf(input_path: Path, output_dir: Path, ranges: List[Tuple[int, int]], 
                  base_name: str = None) -> List[Path]:
        """
        Split PDF into multiple files based on page ranges
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory to save split PDFs
            ranges: List of (start, end) page tuples (1-indexed, inclusive)
            base_name: Base name for output files (default: input filename)
            
        Returns:
            List of paths to created PDF files
        """
        try:
            doc = fitz.open(input_path)
            total_pages = len(doc)
            
            if base_name is None:
                base_name = input_path.stem
            
            output_files = []
            
            for idx, (start, end) in enumerate(ranges, 1):
                # Validate range
                if start < 1 or end > total_pages or start > end:
                    logger.warning(f"Invalid range {start}-{end}, skipping")
                    continue
                
                # Create new PDF with selected pages (convert to 0-indexed)
                output_pdf = fitz.open()
                output_pdf.insert_pdf(doc, from_page=start-1, to_page=end-1)
                
                # Save
                output_path = output_dir / f"{base_name}_part{idx}_pages{start}-{end}.pdf"
                output_pdf.save(output_path)
                output_pdf.close()
                
                output_files.append(output_path)
                logger.info(f"Created {output_path.name} (pages {start}-{end})")
            
            doc.close()
            return output_files
            
        except Exception as e:
            logger.error(f"Failed to split PDF: {e}")
            raise
    
    @staticmethod
    def remove_pages(input_path: Path, output_path: Path, 
                     pages_to_remove: List[int]) -> Path:
        """
        Remove specific pages from PDF
        
        Args:
            input_path: Path to input PDF
            output_path: Path to save output PDF
            pages_to_remove: List of page numbers to remove (1-indexed)
            
        Returns:
            Path to created PDF file
        """
        try:
            doc = fitz.open(input_path)
            total_pages = len(doc)
            
            # Convert to 0-indexed and sort in reverse (to delete from end)
            pages_to_remove_0idx = sorted([p-1 for p in pages_to_remove 
                                          if 1 <= p <= total_pages], reverse=True)
            
            # Delete pages
            for page_num in pages_to_remove_0idx:
                doc.delete_page(page_num)
            
            # Save
            doc.save(output_path)
            doc.close()
            
            logger.info(f"Removed {len(pages_to_remove_0idx)} pages, saved to {output_path.name}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to remove pages: {e}")
            raise
    
    @staticmethod
    def merge_pdfs(input_paths: List[Path], output_path: Path) -> Path:
        """
        Merge multiple PDFs into one
        
        Args:
            input_paths: List of PDF paths to merge
            output_path: Path to save merged PDF
            
        Returns:
            Path to created PDF file
        """
        try:
            output_pdf = fitz.open()
            
            for pdf_path in input_paths:
                doc = fitz.open(pdf_path)
                output_pdf.insert_pdf(doc)
                doc.close()
                logger.info(f"Merged {pdf_path.name}")
            
            output_pdf.save(output_path)
            output_pdf.close()
            
            logger.info(f"Created merged PDF: {output_path.name}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to merge PDFs: {e}")
            raise
    
    @staticmethod
    def extract_pages(input_path: Path, output_path: Path, 
                     pages: List[int]) -> Path:
        """
        Extract specific pages to new PDF
        
        Args:
            input_path: Path to input PDF
            output_path: Path to save output PDF
            pages: List of page numbers to extract (1-indexed)
            
        Returns:
            Path to created PDF file
        """
        try:
            doc = fitz.open(input_path)
            total_pages = len(doc)
            output_pdf = fitz.open()
            
            # Validate and convert to 0-indexed
            valid_pages = [p-1 for p in pages if 1 <= p <= total_pages]
            
            # Insert pages in order
            for page_num in valid_pages:
                output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            doc.close()
            output_pdf.save(output_path)
            output_pdf.close()
            
            logger.info(f"Extracted {len(valid_pages)} pages to {output_path.name}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to extract pages: {e}")
            raise
    
    @staticmethod
    def reorder_pages(input_path: Path, output_path: Path, 
                     new_order: List[int]) -> Path:
        """
        Reorder pages in PDF
        
        Args:
            input_path: Path to input PDF
            output_path: Path to save output PDF
            new_order: List of page numbers in desired order (1-indexed)
            
        Returns:
            Path to created PDF file
        """
        try:
            doc = fitz.open(input_path)
            total_pages = len(doc)
            output_pdf = fitz.open()
            
            # Validate and convert to 0-indexed
            valid_order = [p-1 for p in new_order if 1 <= p <= total_pages]
            
            # Insert pages in new order
            for page_num in valid_order:
                output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            doc.close()
            output_pdf.save(output_path)
            output_pdf.close()
            
            logger.info(f"Reordered {len(valid_order)} pages, saved to {output_path.name}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to reorder pages: {e}")
            raise
    
    @staticmethod
    def rotate_pages(input_path: Path, output_path: Path, 
                    pages: List[int], rotation: int) -> Path:
        """
        Rotate specific pages
        
        Args:
            input_path: Path to input PDF
            output_path: Path to save output PDF
            pages: List of page numbers to rotate (1-indexed, empty = all pages)
            rotation: Rotation angle (90, 180, 270)
            
        Returns:
            Path to created PDF file
        """
        try:
            doc = fitz.open(input_path)
            total_pages = len(doc)
            
            # If no pages specified, rotate all
            if not pages:
                pages = list(range(1, total_pages + 1))
            
            # Validate and convert to 0-indexed
            valid_pages = [p-1 for p in pages if 1 <= p <= total_pages]
            
            # Rotate pages
            for page_num in valid_pages:
                page = doc[page_num]
                page.set_rotation(rotation)
            
            doc.save(output_path)
            doc.close()
            
            logger.info(f"Rotated {len(valid_pages)} pages by {rotation}°, saved to {output_path.name}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to rotate pages: {e}")
            raise
    
    @staticmethod
    def get_pdf_info(pdf_path: Path) -> dict:
        """
        Get PDF metadata and information
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with PDF information
        """
        try:
            doc = fitz.open(pdf_path)
            
            info = {
                'page_count': len(doc),
                'title': doc.metadata.get('title', ''),
                'author': doc.metadata.get('author', ''),
                'subject': doc.metadata.get('subject', ''),
                'keywords': doc.metadata.get('keywords', ''),
                'creator': doc.metadata.get('creator', ''),
                'producer': doc.metadata.get('producer', ''),
                'creation_date': doc.metadata.get('creationDate', ''),
                'modification_date': doc.metadata.get('modDate', ''),
                'file_size': pdf_path.stat().st_size,
                'encrypted': doc.is_encrypted,
            }
            
            doc.close()
            return info
            
        except Exception as e:
            logger.error(f"Failed to get PDF info: {e}")
            return {}


def parse_page_ranges(range_str: str, total_pages: int) -> List[Tuple[int, int]]:
    """
    Parse page range string into list of (start, end) tuples
    
    Examples:
        "1-10" -> [(1, 10)]
        "1-5,10-15" -> [(1, 5), (10, 15)]
        "1-10,15,20-25" -> [(1, 10), (15, 15), (20, 25)]
    
    Args:
        range_str: Page range string
        total_pages: Total pages in PDF (for validation)
        
    Returns:
        List of (start, end) tuples
    """
    ranges = []
    
    for part in range_str.split(','):
        part = part.strip()
        
        if '-' in part:
            # Range like "1-10"
            start, end = part.split('-')
            start = int(start.strip())
            end = int(end.strip())
        else:
            # Single page like "5"
            start = end = int(part.strip())
        
        # Validate
        if start < 1 or end > total_pages or start > end:
            logger.warning(f"Invalid range {start}-{end}, skipping")
            continue
        
        ranges.append((start, end))
    
    return ranges


def parse_page_list(page_str: str, total_pages: int) -> List[int]:
    """
    Parse page list string into list of page numbers
    
    Examples:
        "1,2,3" -> [1, 2, 3]
        "1-5,10" -> [1, 2, 3, 4, 5, 10]
        "1-3,5-7" -> [1, 2, 3, 5, 6, 7]
    
    Args:
        page_str: Page list string
        total_pages: Total pages in PDF (for validation)
        
    Returns:
        List of page numbers
    """
    pages = []
    
    for part in page_str.split(','):
        part = part.strip()
        
        if '-' in part:
            # Range like "1-5"
            start, end = part.split('-')
            start = int(start.strip())
            end = int(end.strip())
            pages.extend(range(start, end + 1))
        else:
            # Single page
            pages.append(int(part.strip()))
    
    # Filter valid pages
    pages = [p for p in pages if 1 <= p <= total_pages]
    
    return pages


# Test functions
def test_pdf_manipulator():
    """Test PDF manipulation functions"""
    print("PDF Manipulator Test")
    print("=" * 50)
    
    # Test with a sample PDF (you'll need to provide one)
    test_pdf = Path("test.pdf")
    
    if not test_pdf.exists():
        print("❌ test.pdf not found")
        return
    
    manipulator = PDFManipulator()
    
    # Get info
    info = manipulator.get_pdf_info(test_pdf)
    print(f"\n📄 PDF Info:")
    print(f"   Pages: {info['page_count']}")
    print(f"   Title: {info['title']}")
    print(f"   Size: {info['file_size'] / 1024:.1f} KB")
    
    # Test page range parsing
    print(f"\n📋 Page Range Parsing:")
    ranges = parse_page_ranges("1-5,10-15,20", info['page_count'])
    print(f"   '1-5,10-15,20' -> {ranges}")
    
    pages = parse_page_list("1,2,3,10-12", info['page_count'])
    print(f"   '1,2,3,10-12' -> {pages}")
    
    print("\n✅ PDF Manipulator ready!")


if __name__ == "__main__":
    test_pdf_manipulator()
