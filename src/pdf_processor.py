"""
PDF Processor - Extract pages from PDF and convert to images
"""
import logging
from pathlib import Path
from typing import List, Callable, Optional
from PIL import Image
import pytesseract

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

from .config import OCR_DPI, AUTO_ROTATE

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Extract PDF pages as images with auto-rotation support"""
    
    def __init__(self, pdf_path: str, dpi: int = OCR_DPI):
        """
        Initialize PDF processor
        
        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for image extraction (default: 300)
        """
        self.pdf_path = Path(pdf_path)
        self.dpi = dpi
        
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if convert_from_path is None:
            raise ImportError(
                "pdf2image is not installed. Install with: pip install pdf2image\n"
                "Also ensure poppler is installed on your system."
            )
    
    def extract_pages(
        self, 
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Image.Image]:
        """
        Extract all pages from PDF as images
        
        Args:
            progress_callback: Optional callback function(current_page, total_pages)
        
        Returns:
            List of PIL Image objects
        """
        logger.info(f"Extracting pages from {self.pdf_path} at {self.dpi} DPI")
        
        try:
            # Convert PDF to images
            images = convert_from_path(
                str(self.pdf_path),
                dpi=self.dpi,
                fmt='png',
                thread_count=4
            )
            
            logger.info(f"Extracted {len(images)} pages from PDF")
            
            # Auto-rotate if enabled
            if AUTO_ROTATE:
                logger.info("Auto-rotating pages...")
                rotated_images = []
                for i, image in enumerate(images):
                    rotated_image = self.auto_rotate_image(image)
                    rotated_images.append(rotated_image)
                    
                    if progress_callback:
                        progress_callback(i + 1, len(images))
                
                return rotated_images
            else:
                return images
                
        except Exception as e:
            logger.error(f"Error extracting pages: {e}")
            raise
    
    def auto_rotate_image(self, image: Image.Image) -> Image.Image:
        """
        Auto-detect and correct page rotation using Tesseract OSD
        
        Args:
            image: PIL Image object
        
        Returns:
            Rotated PIL Image object
        """
        try:
            # Use Tesseract's Orientation and Script Detection
            osd = pytesseract.image_to_osd(image)
            
            # Parse rotation angle from OSD output
            rotation_angle = 0
            for line in osd.split('\n'):
                if 'Rotate:' in line:
                    rotation_angle = int(line.split(':')[1].strip())
                    break
            
            # Rotate if needed
            if rotation_angle != 0:
                logger.debug(f"Rotating image by {rotation_angle} degrees")
                # Tesseract returns counter-clockwise rotation needed
                # PIL rotate() is counter-clockwise, so we use negative
                image = image.rotate(-rotation_angle, expand=True)
            
            return image
            
        except Exception as e:
            logger.warning(f"Auto-rotation failed: {e}. Using original orientation.")
            return image
    
    def save_images(
        self, 
        images: List[Image.Image], 
        output_dir: str,
        prefix: str = "page"
    ) -> List[Path]:
        """
        Save images to directory
        
        Args:
            images: List of PIL Images
            output_dir: Directory to save images
            prefix: Filename prefix
        
        Returns:
            List of saved image paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        for i, image in enumerate(images, start=1):
            filename = output_path / f"{prefix}_{i:04d}.png"
            image.save(filename, 'PNG')
            saved_paths.append(filename)
            logger.debug(f"Saved {filename}")
        
        logger.info(f"Saved {len(saved_paths)} images to {output_dir}")
        return saved_paths
