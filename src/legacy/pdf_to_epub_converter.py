"""
PDF to EPUB Converter - Core Module
Main conversion logic combining OCR, table detection, and EPUB generation
"""
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
import io
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import config
from ocr_processor import OCRProcessor
from table_detector import TableDetector
from epub_builder import EPUBBuilder

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PDFToEPUBConverter:
    """Convert scanned PDF to EPUB with OCR"""
    
    def __init__(self, language: str = None, dpi: int = None, 
                 detect_tables: bool = True, preserve_images: bool = True,
                 progress_callback: Optional[Callable[[str, int, int], None]] = None):
        """
        Initialize PDF to EPUB converter
        
        Args:
            language: OCR language code
            dpi: DPI for PDF to image conversion
            detect_tables: Whether to detect tables
            preserve_images: Whether to preserve images
            progress_callback: Optional callback function(stage, current, total)
        """
        self.language = language or config.DEFAULT_OCR_LANGUAGE
        self.dpi = dpi or config.DEFAULT_DPI
        self.detect_tables = detect_tables
        self.preserve_images = preserve_images
        self.progress_callback = progress_callback
        
        # Initialize processors
        self.ocr_processor = OCRProcessor(language=self.language)
        self.table_detector = TableDetector() if detect_tables else None
        
        logger.info(f"Converter initialized: language={self.language}, dpi={self.dpi}")
    
    def _update_progress(self, stage: str, current: int, total: int):
        """
        Update progress via callback
        
        Args:
            stage: Current stage description
            current: Current progress value
            total: Total progress value
        """
        if self.progress_callback:
            try:
                self.progress_callback(stage, current, total)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    def extract_images_from_pdf(self, pdf_path: Path) -> List[Image.Image]:
        """
        Convert PDF pages to images
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of PIL Images
        """
        try:
            self._update_progress("Converting PDF to images", 0, 100)
            logger.info(f"Converting PDF to images (DPI={self.dpi})...")
            
            images = convert_from_path(
                pdf_path,
                dpi=self.dpi,
                fmt=config.IMAGE_FORMAT
            )
            
            self._update_progress("Converting PDF to images", 100, 100)
            logger.info(f"Converted {len(images)} pages to images")
            return images
            
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            return []
    
    def extract_embedded_images(self, pdf_path: Path) -> List[Dict]:
        """
        Extract embedded images from PDF
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of dictionaries with image info
        """
        embedded_images = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Convert to PIL Image
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    embedded_images.append({
                        'page': page_num,
                        'index': img_index,
                        'image': image,
                        'ext': image_ext
                    })
            
            logger.info(f"Extracted {len(embedded_images)} embedded images")
            
        except Exception as e:
            logger.error(f"Failed to extract embedded images: {e}")
        
        return embedded_images
    
    def process_page(self, page_image: Image.Image, page_num: int, total_pages: int = 0) -> Dict:
        """
        Process a single page
        
        Args:
            page_image: PIL Image of page
            page_num: Page number
            total_pages: Total number of pages (for progress)
            
        Returns:
            Dictionary with processed content
        """
        if total_pages > 0:
            progress = int(20 + (page_num / total_pages) * 60)  # 20-80% range
            self._update_progress(f"Processing page {page_num + 1}/{total_pages}", progress, 100)
        
        logger.info(f"Processing page {page_num + 1}...")
        
        result = {
            'page_num': page_num,
            'text': '',
            'tables': [],
            'images': []
        }
        
        try:
            # Detect tables if enabled
            if self.detect_tables and self.table_detector:
                tables = self.table_detector.detect_tables(page_image)
                
                for table in tables:
                    # Extract table cells
                    cells = self.table_detector.extract_cells(
                        table['image'],
                        table['row_positions'],
                        table['col_positions']
                    )
                    
                    # OCR each cell
                    table_data = []
                    for row_cells in cells:
                        row_data = []
                        for cell_image in row_cells:
                            cell_text = self.ocr_processor.extract_text(cell_image)
                            row_data.append(cell_text.strip())
                        table_data.append(row_data)
                    
                    result['tables'].append({
                        'data': table_data,
                        'rows': table['rows'],
                        'cols': table['cols']
                    })
            
            # Extract text from entire page
            text = self.ocr_processor.extract_text(page_image)
            result['text'] = text
            
            # Preserve page image if requested
            if self.preserve_images:
                result['images'].append(page_image)
            
        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {e}")
        
        return result
    
    def process_pages_parallel(self, page_images: List[Image.Image]) -> List[Dict]:
        """
        Process multiple pages in parallel
        
        Args:
            page_images: List of page images
            
        Returns:
            List of processed page results
        """
        results = [None] * len(page_images)
        
        total_pages = len(page_images)
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_page = {
                executor.submit(self.process_page, img, i, total_pages): i 
                for i, img in enumerate(page_images)
            }
            
            # Collect results
            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    result = future.result()
                    results[page_num] = result
                except Exception as e:
                    logger.error(f"Page {page_num + 1} processing failed: {e}")
                    results[page_num] = {
                        'page_num': page_num,
                        'text': '',
                        'tables': [],
                        'images': []
                    }
        
        return results
    
    def build_epub(self, processed_pages: List[Dict], output_path: Path, 
                   title: str = None, author: str = None):
        """
        Build EPUB from processed pages
        
        Args:
            processed_pages: List of processed page results
            output_path: Path to save EPUB
            title: Book title
            author: Book author
        """
        self._update_progress("Building EPUB", 80, 100)
        logger.info("Building EPUB...")
        
        # Initialize EPUB builder
        builder = EPUBBuilder(
            title=title or config.EPUB_METADATA['title'],
            author=author or config.EPUB_METADATA['author'],
            language=self.language
        )
        
        # Add metadata
        builder.set_metadata(
            publisher=config.EPUB_METADATA['publisher'],
            date=None  # Will use current date
        )
        
        # Process each page
        for page_result in processed_pages:
            for i, table in enumerate(page_result['tables']):
                table_chapter = builder.create_table_chapter(
                    title=f"Table {page_num + 1}.{i + 1}",
                    table_data=table['data']
                )
                builder.add_chapter(table_chapter)
        
        # Build EPUB
        success = builder.build(output_path)
        
        if success:
            self._update_progress("EPUB created", 90, 100)
            logger.info(f"✓ EPUB created successfully: {output_path}")
        else:
            logger.error("✗ Failed to create EPUB")
        
        return success
    
    def convert(self, pdf_path: Path, output_path: Path, 
                title: str = None, author: str = None) -> bool:
        """
        Convert PDF to EPUB
        
        Args:
            pdf_path: Path to input PDF
            output_path: Path to output EPUB
            title: Book title
            author: Book author
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Starting conversion: {pdf_path}")
            
            # Verify Telugu support
            if not self.ocr_processor.verify_telugu_support():
                logger.warning("Telugu OCR support not verified!")
            
            # Convert PDF to images
            page_images = self.extract_images_from_pdf(pdf_path)
            
            if not page_images:
                logger.error("No pages extracted from PDF")
                return False
            
            # Process pages
            logger.info(f"Processing {len(page_images)} pages...")
            processed_pages = self.process_pages_parallel(page_images)
            
            # Build EPUB
            success = self.build_epub(processed_pages, output_path, title, author)
            
            # Cleanup
            if config.CLEANUP_TEMP_FILES:
                logger.info("Cleaning up temporary files...")
                # Add cleanup logic here if needed
            
            return success
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return False


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description='Convert scanned PDF to EPUB with Telugu OCR'
    )
    
    parser.add_argument('input', type=str, help='Input PDF file')
    parser.add_argument('output', type=str, help='Output EPUB file')
    parser.add_argument('--language', type=str, default='tel', 
                       help='OCR language code (default: tel)')
    parser.add_argument('--dpi', type=int, default=300,
                       help='DPI for PDF conversion (default: 300)')
    parser.add_argument('--no-tables', action='store_true',
                       help='Disable table detection')
    parser.add_argument('--no-images', action='store_true',
                       help='Do not preserve images')
    parser.add_argument('--title', type=str, help='Book title')
    parser.add_argument('--author', type=str, help='Book author')
    
    args = parser.parse_args()
    
    # Create converter
    converter = PDFToEPUBConverter(
        language=args.language,
        dpi=args.dpi,
        detect_tables=not args.no_tables,
        preserve_images=not args.no_images
    )
    
    # Convert
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
    
    success = converter.convert(
        input_path,
        output_path,
        title=args.title,
        author=args.author
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
