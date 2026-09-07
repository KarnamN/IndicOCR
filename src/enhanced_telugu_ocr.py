"""
Enhanced Telugu OCR Processor
Integrates EasyOCR and Tesseract with Telugu text processing (Vatulu & Guninthalu detection)
Intelligently selects OCR engine based on page complexity
"""

import logging
from typing import Dict, Optional, Tuple
from PIL import Image
import pytesseract
from pathlib import Path

# Import configuration
try:
    from config import (
        TESSERACT_PATH, TESSERACT_CONFIG, DEFAULT_OCR_LANGUAGE,
        EASYOCR_USE_GPU, EASYOCR_LANG, EASYOCR_MIN_SIZE,
        EASYOCR_TEXT_THRESHOLD, EASYOCR_LOW_TEXT, EASYOCR_LINK_THRESHOLD,
        EASYOCR_MAG_RATIO, ENABLE_TELUGU_PROCESSING, TELUGU_ENCODING_DIR,
        ANALYZE_VATULU, ANALYZE_GUNINTHALU, ADAPTIVE_SIMPLE_THRESHOLD,
        ADAPTIVE_COMPLEX_THRESHOLD, ENABLE_ADAPTIVE_OCR
    )
except ImportError:
    # Fallback defaults
    TESSERACT_PATH = 'tesseract'
    TESSERACT_CONFIG = '--oem 3 --psm 6'
    DEFAULT_OCR_LANGUAGE = 'tel+eng'
    EASYOCR_USE_GPU = False
    EASYOCR_LANG = 'te+en'
    EASYOCR_MIN_SIZE = 8
    EASYOCR_TEXT_THRESHOLD = 0.4
    EASYOCR_LOW_TEXT = 0.2
    EASYOCR_LINK_THRESHOLD = 0.15
    EASYOCR_MAG_RATIO = 2.0
    ENABLE_TELUGU_PROCESSING = True
    TELUGU_ENCODING_DIR = None
    ANALYZE_VATULU = True
    ANALYZE_GUNINTHALU = True
    ADAPTIVE_SIMPLE_THRESHOLD = 45
    ADAPTIVE_COMPLEX_THRESHOLD = 60
    ENABLE_ADAPTIVE_OCR = True

# Import Telugu text processor
try:
    from telugu_text_processor import TeluguTextProcessor
    TELUGU_PROCESSOR_AVAILABLE = True
except ImportError:
    TELUGU_PROCESSOR_AVAILABLE = False

# Import EasyOCR
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class EnhancedTeluguOCR:
    """
    Enhanced OCR processor with Telugu text analysis
    - Intelligently selects between EasyOCR and Tesseract based on page complexity
    - Enhances output with Vatulu and Guninthalu detection
    - Provides detailed text analysis and quality metrics
    """
    
    def __init__(self, encoding_dir: Optional[Path] = None):
        """
        Initialize Enhanced Telugu OCR
        
        Args:
            encoding_dir: Optional path to TeluguOCR encoding files
        """
        self.encoding_dir = encoding_dir or TELUGU_ENCODING_DIR
        
        # Initialize Telugu text processor
        if TELUGU_PROCESSOR_AVAILABLE and ENABLE_TELUGU_PROCESSING:
            self.telugu_processor = TeluguTextProcessor(encoding_dir=self.encoding_dir)
            logger.info("✅ Telugu text processor initialized")
        else:
            self.telugu_processor = None
            logger.warning("⚠️ Telugu text processor not available")
        
        # Initialize EasyOCR
        if EASYOCR_AVAILABLE:
            try:
                # Parse language codes
                langs = EASYOCR_LANG.replace('+', ' ').split()
                lang_map = {'te': 'te', 'en': 'en', 'tel': 'te', 'eng': 'en'}
                self.easyocr_langs = [lang_map.get(lang, lang) for lang in langs]
                
                self.easyocr_reader = easyocr.Reader(
                    self.easyocr_langs,
                    gpu=EASYOCR_USE_GPU,
                    verbose=False
                )
                logger.info(f"✅ EasyOCR initialized with languages: {self.easyocr_langs}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize EasyOCR: {e}")
                self.easyocr_reader = None
        else:
            self.easyocr_reader = None
            logger.warning("⚠️ EasyOCR not available")
        
        # Configure Tesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        logger.info(f"✅ Tesseract configured: {TESSERACT_PATH}")
        
        # Settings
        self.adaptive_ocr = ENABLE_ADAPTIVE_OCR
        self.simple_threshold = ADAPTIVE_SIMPLE_THRESHOLD
        self.complex_threshold = ADAPTIVE_COMPLEX_THRESHOLD
        
        logger.info(f"Enhanced Telugu OCR initialized (Adaptive: {self.adaptive_ocr})")
    
    def calculate_page_complexity(self, image: Image.Image) -> float:
        """
        Calculate page complexity score (0-100)
        Higher score = more complex (tables, multiple columns, etc.)
        
        Args:
            image: PIL Image
            
        Returns:
            Complexity score (0-100)
        """
        try:
            import cv2
            import numpy as np
            
            # Convert to grayscale
            img_array = np.array(image.convert('L'))
            
            # Edge detection
            edges = cv2.Canny(img_array, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size * 100
            
            # Detect lines (horizontal and vertical)
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            
            _, binary = cv2.threshold(img_array, 150, 255, cv2.THRESH_BINARY_INV)
            horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            
            h_line_density = np.sum(horizontal_lines > 0) / horizontal_lines.size * 100
            v_line_density = np.sum(vertical_lines > 0) / vertical_lines.size * 100
            
            # Calculate complexity score
            complexity = (
                edge_density * 0.4 +
                h_line_density * 0.3 +
                v_line_density * 0.3
            )
            
            # Normalize to 0-100
            complexity = min(100, max(0, complexity * 2))
            
            logger.debug(f"Page complexity: {complexity:.2f} (edges: {edge_density:.2f}, h_lines: {h_line_density:.2f}, v_lines: {v_line_density:.2f})")
            
            return complexity
            
        except Exception as e:
            logger.warning(f"Failed to calculate complexity: {e}, using default")
            return 50.0  # Default medium complexity
    
    def select_ocr_engine(self, complexity: float) -> str:
        """
        Select best OCR engine based on page complexity
        
        Args:
            complexity: Page complexity score (0-100)
            
        Returns:
            'tesseract' or 'easyocr'
        """
        if not self.adaptive_ocr:
            # If adaptive is disabled, prefer EasyOCR if available
            return 'easyocr' if self.easyocr_reader else 'tesseract'
        
        if complexity < self.simple_threshold:
            # Simple page - use fast Tesseract
            logger.info(f"📄 Simple page (complexity: {complexity:.1f}) → Using Tesseract")
            return 'tesseract'
        elif complexity > self.complex_threshold:
            # Complex page - use accurate EasyOCR
            if self.easyocr_reader:
                logger.info(f"📊 Complex page (complexity: {complexity:.1f}) → Using EasyOCR")
                return 'easyocr'
            else:
                logger.warning(f"EasyOCR not available, falling back to Tesseract")
                return 'tesseract'
        else:
            # Medium complexity - prefer EasyOCR but Tesseract is acceptable
            if self.easyocr_reader:
                logger.info(f"📑 Medium page (complexity: {complexity:.1f}) → Using EasyOCR")
                return 'easyocr'
            else:
                return 'tesseract'
    
    def extract_with_tesseract(self, image: Image.Image) -> Tuple[str, float]:
        """
        Extract text using Tesseract OCR
        
        Args:
            image: PIL Image
            
        Returns:
            Tuple of (text, confidence)
        """
        try:
            # Get text with confidence
            data = pytesseract.image_to_data(
                image,
                lang=DEFAULT_OCR_LANGUAGE,
                config=TESSERACT_CONFIG,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text
            text = pytesseract.image_to_string(
                image,
                lang=DEFAULT_OCR_LANGUAGE,
                config=TESSERACT_CONFIG
            )
            
            # Calculate average confidence
            confidences = [float(conf) for conf in data['conf'] if conf != '-1']
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            avg_confidence = avg_confidence / 100.0  # Normalize to 0-1
            
            logger.debug(f"Tesseract extracted {len(text)} chars with {avg_confidence:.2%} confidence")
            
            return text, avg_confidence
            
        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}")
            return "", 0.0
    
    def extract_with_easyocr(self, image: Image.Image) -> Tuple[str, float]:
        """
        Extract text using EasyOCR
        
        Args:
            image: PIL Image
            
        Returns:
            Tuple of (text, confidence)
        """
        if not self.easyocr_reader:
            logger.error("EasyOCR reader not initialized")
            return "", 0.0
        
        try:
            import numpy as np
            
            # Preprocess image (remove lines for better table OCR)
            processed_image = self._preprocess_for_easyocr(image)
            img_array = np.array(processed_image)
            
            # Perform OCR with optimized settings
            results = self.easyocr_reader.readtext(
                img_array,
                detail=1,
                paragraph=False,
                min_size=EASYOCR_MIN_SIZE,
                text_threshold=EASYOCR_TEXT_THRESHOLD,
                low_text=EASYOCR_LOW_TEXT,
                link_threshold=EASYOCR_LINK_THRESHOLD,
                canvas_size=2560,
                mag_ratio=EASYOCR_MAG_RATIO,
                slope_ths=0.1,
                ycenter_ths=0.5,
                height_ths=0.5,
                width_ths=0.25,
                add_margin=0.2,
                contrast_ths=0.1,
                adjust_contrast=0.5
            )
            
            if not results:
                return "", 0.0
            
            # Extract text and confidence
            texts = []
            confidences = []
            
            for bbox, text, conf in results:
                texts.append(text)
                confidences.append(conf)
            
            combined_text = '\n'.join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            logger.debug(f"EasyOCR extracted {len(combined_text)} chars with {avg_confidence:.2%} confidence")
            
            return combined_text, avg_confidence
            
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            return "", 0.0
    
    def _preprocess_for_easyocr(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for EasyOCR (remove table lines)
        
        Args:
            image: PIL Image
            
        Returns:
            Preprocessed image
        """
        try:
            import cv2
            import numpy as np
            from PIL import ImageEnhance, ImageFilter
            
            # Convert to grayscale
            image = image.convert('L')
            img_array = np.array(image)
            
            # Binary threshold (inverse)
            _, binary_inv = cv2.threshold(img_array, 150, 255, cv2.THRESH_BINARY_INV)
            
            # Detect horizontal lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            detected_h = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            
            # Detect vertical lines
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            detected_v = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            
            # Combine and thicken lines
            lines_mask = cv2.add(detected_h, detected_v)
            kernel_dil = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            lines_mask = cv2.dilate(lines_mask, kernel_dil, iterations=1)
            
            # Remove lines from original image
            cleaned_img = img_array.copy()
            cleaned_img[lines_mask > 0] = 255  # Paint lines white
            
            # Final adaptive threshold for crisp text
            final_bin = cv2.adaptiveThreshold(
                cleaned_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2
            )
            
            processed_image = Image.fromarray(final_bin)
            return processed_image.convert('RGB')
            
        except Exception as e:
            logger.warning(f"Preprocessing failed: {e}, using original image")
            return image.convert('RGB')
    
    def enhance_with_telugu_analysis(self, text: str, engine: str, confidence: float) -> Dict:
        """
        Enhance OCR output with Telugu text analysis (Vatulu & Guninthalu)
        
        Args:
            text: Extracted text
            engine: OCR engine used ('tesseract' or 'easyocr')
            confidence: OCR confidence score
            
        Returns:
            Enhanced result dictionary
        """
        result = {
            'text': text,
            'engine': engine,
            'confidence': confidence,
            'char_count': len(text),
            'telugu_analysis': None
        }
        
        # Add Telugu analysis if available
        if self.telugu_processor and ENABLE_TELUGU_PROCESSING and text:
            try:
                # Get comprehensive Telugu analysis
                enhanced = self.telugu_processor.enhance_ocr_output(text, confidence)
                stats = enhanced['statistics']
                
                result['telugu_analysis'] = {
                    'telugu_chars': stats['telugu_characters'],
                    'vatulu_count': stats['vatulu_count'],
                    'guninthalu_count': stats['guninthalu_count'],
                    'complex_chars': stats['complex_characters_count'],
                    'has_vatulu': stats['has_vatulu'],
                    'has_guninthalu': stats['has_guninthalu'],
                    'vatulu_percentage': f"{stats['vatulu_percentage']:.1f}%",
                    'guninthalu_percentage': f"{stats['guninthalu_percentage']:.1f}%",
                }
                
                # Use normalized text
                result['text'] = enhanced['normalized_text']
                result['original_text'] = text
                
                # Add detailed analysis if requested
                if ANALYZE_VATULU:
                    result['vatulu_details'] = enhanced['vatulu']
                
                if ANALYZE_GUNINTHALU:
                    result['guninthalu_details'] = enhanced['guninthalu']
                
                logger.info(f"📝 Telugu Analysis: {stats['telugu_characters']} chars, "
                           f"{stats['vatulu_count']} vatulu, {stats['guninthalu_count']} guninthalu")
                
            except Exception as e:
                logger.warning(f"Telugu analysis failed: {e}")
        
        return result
    
    def extract_text(self, image: Image.Image, force_engine: Optional[str] = None) -> Dict:
        """
        Extract text from image with intelligent OCR selection and Telugu enhancement
        
        Args:
            image: PIL Image
            force_engine: Optional - force specific engine ('tesseract' or 'easyocr')
            
        Returns:
            Enhanced result dictionary with text, confidence, and Telugu analysis
        """
        # Calculate page complexity
        complexity = self.calculate_page_complexity(image)
        
        # Select OCR engine
        if force_engine:
            engine = force_engine
            logger.info(f"🔧 Forced engine: {engine}")
        else:
            engine = self.select_ocr_engine(complexity)
        
        # Extract text with selected engine
        if engine == 'easyocr' and self.easyocr_reader:
            text, confidence = self.extract_with_easyocr(image)
        else:
            text, confidence = self.extract_with_tesseract(image)
        
        # Enhance with Telugu analysis
        result = self.enhance_with_telugu_analysis(text, engine, confidence)
        result['complexity'] = complexity
        
        return result
    
    def get_engine_info(self) -> Dict:
        """Get information about available OCR engines"""
        return {
            'tesseract_available': True,
            'easyocr_available': self.easyocr_reader is not None,
            'telugu_processor_available': self.telugu_processor is not None,
            'adaptive_ocr_enabled': self.adaptive_ocr,
            'simple_threshold': self.simple_threshold,
            'complex_threshold': self.complex_threshold,
            'easyocr_languages': self.easyocr_langs if self.easyocr_reader else [],
            'tesseract_languages': DEFAULT_OCR_LANGUAGE,
        }


def test_enhanced_telugu_ocr():
    """Test Enhanced Telugu OCR"""
    print("=" * 70)
    print("Testing Enhanced Telugu OCR")
    print("=" * 70)
    
    try:
        ocr = EnhancedTeluguOCR()
        
        # Print engine info
        info = ocr.get_engine_info()
        print("\n📊 OCR Engine Information:")
        print(f"  Tesseract: {'✅' if info['tesseract_available'] else '❌'}")
        print(f"  EasyOCR: {'✅' if info['easyocr_available'] else '❌'}")
        print(f"  Telugu Processor: {'✅' if info['telugu_processor_available'] else '❌'}")
        print(f"  Adaptive OCR: {'✅' if info['adaptive_ocr_enabled'] else '❌'}")
        
        if info['adaptive_ocr_enabled']:
            print(f"  Simple threshold: < {info['simple_threshold']}")
            print(f"  Complex threshold: > {info['complex_threshold']}")
        
        print("\n✅ Enhanced Telugu OCR initialized successfully!")
        
    except Exception as e:
        print(f"\n❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)


if __name__ == "__main__":
    test_enhanced_telugu_ocr()
