"""
OCR Engine - Extract text from images using Tesseract
"""
import logging
from typing import List, Callable, Optional
from PIL import Image
import pytesseract
from joblib import Parallel, delayed

from .config import OCR_LANGUAGES, TESSERACT_CONFIG, PARALLEL_PROCESSING, NUM_WORKERS

logger = logging.getLogger(__name__)


class OCREngine:
    """Extract text from images using Tesseract OCR"""
    
    def __init__(self, languages: Optional[List[str]] = None):
        """
        Initialize OCR engine
        
        Args:
            languages: List of language codes (default: from config)
        """
        self.languages = languages or OCR_LANGUAGES
        self.lang_string = '+'.join(self.languages)
        logger.info(f"Initialized OCR engine with languages: {self.lang_string}")
    
    def extract_text(self, image: Image.Image) -> str:
        """
        Extract text from a single image
        
        Args:
            image: PIL Image object
        
        Returns:
            Extracted text as string
        """
        try:
            text = pytesseract.image_to_string(
                image,
                lang=self.lang_string,
                config=TESSERACT_CONFIG
            )
            return text
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""
    
    def extract_text_with_confidence(self, image: Image.Image) -> tuple[str, float]:
        """
        Extract text with confidence score
        
        Args:
            image: PIL Image object
        
        Returns:
            Tuple of (text, average_confidence)
        """
        try:
            data = pytesseract.image_to_data(
                image,
                lang=self.lang_string,
                config=TESSERACT_CONFIG,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text and calculate average confidence
            text_parts = []
            confidences = []
            
            for i, conf in enumerate(data['conf']):
                if conf != -1:  # -1 means no text detected
                    text = data['text'][i]
                    if text.strip():
                        text_parts.append(text)
                        confidences.append(conf)
            
            full_text = ' '.join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return full_text, avg_confidence
            
        except Exception as e:
            logger.error(f"OCR extraction with confidence failed: {e}")
            return "", 0.0
    
    def _process_single_page(self, image: Image.Image, page_num: int) -> tuple[int, str]:
        """
        Process a single page (for parallel processing)
        
        Args:
            image: PIL Image object
            page_num: Page number
        
        Returns:
            Tuple of (page_num, extracted_text)
        """
        logger.debug(f"Processing page {page_num}")
        text = self.extract_text(image)
        return page_num, text
    
    def process_pages(
        self,
        images: List[Image.Image],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[str]:
        """
        Process multiple pages and extract text
        
        Args:
            images: List of PIL Image objects
            progress_callback: Optional callback function(current_page, total_pages)
        
        Returns:
            List of extracted text strings (one per page)
        """
        total_pages = len(images)
        logger.info(f"Processing {total_pages} pages with OCR")
        
        if PARALLEL_PROCESSING and total_pages > 1:
            # Parallel processing
            logger.info(f"Using parallel processing with {NUM_WORKERS} workers")
            
            results = Parallel(n_jobs=NUM_WORKERS)(
                delayed(self._process_single_page)(img, i)
                for i, img in enumerate(images, start=1)
            )
            
            # Sort by page number and extract text
            results.sort(key=lambda x: x[0])
            texts = [text for _, text in results]
            
            if progress_callback:
                progress_callback(total_pages, total_pages)
        else:
            # Sequential processing
            texts = []
            for i, image in enumerate(images, start=1):
                text = self.extract_text(image)
                texts.append(text)
                
                if progress_callback:
                    progress_callback(i, total_pages)
                
                logger.debug(f"Processed page {i}/{total_pages}")
        
        logger.info(f"OCR processing complete. Extracted text from {len(texts)} pages")
        return texts
    
    def get_page_info(self, image: Image.Image) -> dict:
        """
        Get detailed information about text in image
        
        Args:
            image: PIL Image object
        
        Returns:
            Dictionary with text statistics
        """
        try:
            data = pytesseract.image_to_data(
                image,
                lang=self.lang_string,
                config=TESSERACT_CONFIG,
                output_type=pytesseract.Output.DICT
            )
            
            word_count = sum(1 for text in data['text'] if text.strip())
            confidences = [conf for conf in data['conf'] if conf != -1]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {
                'word_count': word_count,
                'avg_confidence': avg_confidence,
                'min_confidence': min(confidences) if confidences else 0.0,
                'max_confidence': max(confidences) if confidences else 0.0,
            }
        except Exception as e:
            logger.error(f"Failed to get page info: {e}")
            return {
                'word_count': 0,
                'avg_confidence': 0.0,
                'min_confidence': 0.0,
                'max_confidence': 0.0,
            }
