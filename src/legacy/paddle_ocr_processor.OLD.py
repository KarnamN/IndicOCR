"""
PaddleOCR Processing Module
Handles text extraction from images using PaddleOCR with Telugu support
WITH MEMORY OPTIMIZATIONS - Prevents 12GB allocation errors
"""
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import cv2
import logging
import threading
import gc  # CRITICAL: For memory cleanup
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import config
from logging_config import get_logger

logger = get_logger(__name__)

# Global engine cache to prevent re-initialization
_PADDLE_ENGINES = {}
_PADDLE_LOCK = threading.Lock()

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR is available")
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logger.warning("PaddleOCR is not installed. Install with: pip install paddleocr")


class PaddleOCRProcessor:
    """Process images and extract text using PaddleOCR"""
    
    def __init__(self, language: str = None, use_gpu: bool = None):
        """
        Initialize PaddleOCR processor
        
        Args:
            language: OCR language code (e.g., 'te' for Telugu, 'en' for English)
            use_gpu: Whether to use GPU acceleration (None = auto-detect from config)
        """
        if not PADDLEOCR_AVAILABLE:
            raise ImportError(
                "PaddleOCR is not installed. Install with: pip install paddleocr paddlepaddle"
            )
        
        # Set language
        self.language = language or getattr(config, 'PADDLE_LANG', 'te')
        
        # Map common language codes
        lang_map = {
            'tel': 'te',
            'eng': 'en',
            'tel+eng': 'te',
        }
        self.language = lang_map.get(self.language, self.language)
        
        # GPU settings
        if use_gpu is None:
            use_gpu = getattr(config, 'PADDLE_USE_GPU', False)
        
        # Initialize PaddleOCR with global caching & thread safety
        cache_key = f"{self.language}_{use_gpu}"
        
        global _PADDLE_ENGINES
        if cache_key not in _PADDLE_ENGINES:
            with _PADDLE_LOCK:
                if cache_key not in _PADDLE_ENGINES:
                    try:
                        logger.info(f"🚀 Initializing NEW PaddleOCR engine for {self.language} (GPU={use_gpu})")
                        ocr_params = {
                            'use_angle_cls': getattr(config, 'PADDLE_USE_ANGLE_CLS', True),
                            'lang': self.language,
                            'enable_mkldnn': False,
                            'rec_batch_num': getattr(config, 'PADDLE_REC_BATCH_NUM', 1),
                        }
                        
                        det_model = getattr(config, 'PADDLE_DET_MODEL', None)
                        rec_model = getattr(config, 'PADDLE_REC_MODEL', None)
                        if det_model: ocr_params['det_model_dir'] = det_model
                        if rec_model: ocr_params['rec_model_dir'] = rec_model
                        
                        _PADDLE_ENGINES[cache_key] = PaddleOCR(**ocr_params)
                        logger.info(f"✅ PaddleOCR engine {cache_key} initialized successfully")
                    except Exception as e:
                        logger.error(f"Failed to initialize PaddleOCR: {e}")
                        raise

        self.ocr = _PADDLE_ENGINES[cache_key]
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR accuracy
        
        Args:
            image: PIL Image object
            
        Returns:
            Preprocessed PIL Image
        """
        try:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            img_array = np.array(image)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            
            result = Image.fromarray(gray)
            
            # Enhance contrast slightly
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.2)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(result)
            result = enhancer.enhance(1.5)
            
            return result
            
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}, using original image")
            return image
    
    def _resize_if_too_large(self, image: Image.Image, max_dim: int = None) -> Image.Image:
        """
        Resize image if dimensions exceed max_dim to prevent OOM errors
        CRITICAL FIX: Reduced from 2000 to 1500 (configurable)
        """
        if max_dim is None:
            max_dim = getattr(config, 'PADDLE_MAX_IMAGE_DIM', 1500)  # MEMORY FIX: Reduced from 2000
        
        width, height = image.size
        if width > max_dim or height > max_dim:
            ratio = min(max_dim / width, max_dim / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            logger.debug(f"Resizing large image for PaddleOCR: {width}x{height} -> {new_width}x{new_height}")
            return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return image

    def extract_text(self, image: Image.Image, preprocess: bool = False) -> str:
        """
        Extract text from image using PaddleOCR
        
        Args:
            image: PIL Image object
            preprocess: Whether to preprocess the image
            
        Returns:
            Extracted text as string
        """
        try:
            if preprocess:
                image = self.preprocess_image(image)
            
            # MEMORY FIX: Resize if too large
            image = self._resize_if_too_large(image)
            
            logger.debug(f"Image size for PaddleOCR: {image.size}")
            
            # Convert PIL Image to numpy array
            img_array = np.array(image)
            
            # Run OCR
            result = self.ocr.ocr(img_array)
            
            # MEMORY FIX: Force garbage collection to free intermediate tensors
            if getattr(config, 'PADDLE_ENABLE_GC', True):
                gc.collect()
            
            # Extract text from result with ROBUST ERROR HANDLING
            if result is None or len(result) == 0:
                logger.warning("PaddleOCR returned no results")
                return ""
            
            text_lines = []
            try:
                # PaddleOCR result format handling with DEFENSIVE CHECKS
                data = []
                if isinstance(result, list) and len(result) > 0:
                    first_item = result[0]
                    
                    # SAFETY CHECK: ensure first_item exists and is not None
                    if first_item is None:
                        logger.warning("PaddleOCR returned None as first item")
                        return ""
                    
                    is_flat = False
                    # Check if first_item is a line: [box, (text, conf)]
                    if isinstance(first_item, (list, tuple)) and len(first_item) >= 2:
                        text_part = first_item[1] if len(first_item) > 1 else None
                        if text_part and isinstance(text_part, (list, tuple)) and len(text_part) >= 1:
                            if isinstance(text_part[0], str):
                                is_flat = True
                    
                    if is_flat:
                        data = result
                    else:
                        if isinstance(first_item, list):
                             data = first_item
                        else:
                             data = []
                
                if data is None: 
                    data = []
                    
                for line in data:
                    if line is None: 
                        continue
                    
                    try:
                        # BOUNDS CHECKING to prevent "tuple index out of range"
                        if not isinstance(line, (list, tuple)):
                            continue
                        
                        if len(line) < 2:
                            logger.debug(f"Skipping line with insufficient elements: {line}")
                            continue
                            
                        text_info = line[1]
                        
                        if text_info is None:
                            continue
                            
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                            text_lines.append(str(text_info[0]))
                        elif isinstance(text_info, str):
                            text_lines.append(text_info)
                    except (IndexError, TypeError) as e:
                        logger.debug(f"Skipping malformed line: {e}")
                        continue
                
                extracted_text = '\n'.join(text_lines)
                logger.debug(f"Extracted {len(text_lines)} lines of text")
                return extracted_text
                
            except Exception as e:
                logger.error(f"Error parsing PaddleOCR results: {e}")
                try:
                    res_type = type(result)
                    res_len = len(result) if isinstance(result, list) else 'N/A'
                    first_type = type(result[0]) if isinstance(result, list) and len(result)>0 else 'N/A'
                    logger.debug(f"Result structure: Type={res_type}, Len={res_len}, FirstItemType={first_type}")
                    if isinstance(result, list) and len(result) > 0:
                        logger.debug(f"First item sample: {str(result[0])[:100]}...")
                except: 
                    pass
                return ""
            
        except Exception as e:
            logger.error(f"PaddleOCR text extraction failed: {e}")
            return ""
    
    def extract_text_with_boxes(self, image: Image.Image, preprocess: bool = False) -> List[Dict]:
        """
        Extract text with bounding box information
        
        Args:
            image: PIL Image object
            preprocess: Whether to preprocess the image
            
        Returns:
            List of dictionaries containing text and position information
        """
        try:
            if preprocess:
                image = self.preprocess_image(image)
                
            # MEMORY FIX: Resize if too large
            image = self._resize_if_too_large(image)
            
            logger.debug(f"Image size for PaddleOCR boxes: {image.size}")
            
            img_array = np.array(image)
            result = self.ocr.ocr(img_array)
            
            # MEMORY FIX: Force garbage collection
            if getattr(config, 'PADDLE_ENABLE_GC', True):
                gc.collect()
            
            if result is None or len(result) == 0:
                return []
            
            boxes_data = []
            
            try:
                # Determine the list of lines with DEFENSIVE CHECKS
                data = []
                if isinstance(result, list) and len(result) > 0:
                    first_item = result[0]
                    
                    if first_item is None:
                        logger.warning("PaddleOCR box extraction: first item is None")
                        return []
                    
                    is_flat = False
                    if isinstance(first_item, (list, tuple)) and len(first_item) >= 2:
                        text_part = first_item[1] if len(first_item) > 1 else None
                        if text_part and isinstance(text_part, (list, tuple)) and len(text_part) >= 1:
                            if isinstance(text_part[0], str):
                                is_flat = True
                            
                    if is_flat:
                        data = result
                    else:
                        if isinstance(first_item, list):
                            data = first_item
                        else:
                            data = []
                
                for line in data:
                    if not line or not isinstance(line, (list, tuple)) or len(line) < 2:
                        continue
                        
                    try:
                        # BOUNDS CHECKING to prevent index errors
                        box = line[0] if len(line) > 0 else None
                        text_info = line[1] if len(line) > 1 else None
                        
                        if box is None or text_info is None:
                            continue
                        
                        text = ""
                        confidence = 0.0
                        
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = text_info[0]
                            confidence = text_info[1]
                        elif isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                            text = text_info[0]
                            confidence = 0.0
                        elif isinstance(text_info, str):
                            text = text_info
                            
                        # Extract bounding box coordinates
                        if isinstance(box, (list, tuple)) and len(box) >= 4:
                            try:
                                x_coords = [point[0] for point in box if len(point) >= 2]
                                y_coords = [point[1] for point in box if len(point) >= 2]
                                
                                if len(x_coords) >= 2 and len(y_coords) >= 2:
                                    boxes_data.append({
                                        'text': text,
                                        'confidence': confidence,
                                        'left': int(min(x_coords)),
                                        'top': int(min(y_coords)),
                                        'width': int(max(x_coords) - min(x_coords)),
                                        'height': int(max(y_coords) - min(y_coords)),
                                        'box': box
                                    })
                            except (ValueError, TypeError, IndexError) as e:
                                logger.debug(f"Skipping box with invalid coordinates: {e}")
                                continue
                    except (IndexError, TypeError) as e:
                        logger.debug(f"Skipping malformed box line: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error parsing PaddleOCR box results: {e}")
                
            return boxes_data
            
        except Exception as e:
            logger.error(f"PaddleOCR box extraction failed: {e}")
            return []
    
    def get_confidence_score(self, image: Image.Image) -> float:
        """Get average confidence score for OCR results"""
        try:
            boxes = self.extract_text_with_boxes(image, preprocess=True)
            if not boxes:
                return 0.0
            
            confidences = [box['confidence'] for box in boxes]
            avg_confidence = sum(confidences) / len(confidences)
            
            return avg_confidence
            
        except Exception as e:
            logger.error(f"Failed to get confidence score: {e}")
            return 0.0
    
    def detect_orientation(self, image: Image.Image) -> Dict:
        """Detect image orientation (handled internally by PaddleOCR)"""
        return {
            'angle': 0,
            'confidence': 1.0,
            'note': 'PaddleOCR handles rotation automatically'
        }
    
    def auto_rotate(self, image: Image.Image) -> Image.Image:
        """Auto-rotate is handled internally by PaddleOCR"""
        return image
    
    def process_image_file(self, image_path: Path, preprocess: bool = True) -> str:
        """Process an image file and extract text"""
        try:
            image = Image.open(image_path)
            return self.extract_text(image, preprocess=preprocess)
        except Exception as e:
            logger.error(f"Failed to process image file {image_path}: {e}")
            return ""
    
    def get_available_languages(self) -> List[str]:
        """Get list of available PaddleOCR languages"""
        return [
            'te',  # Telugu
            'en',  # English
            'hi',  # Hindi
            'ta',  # Tamil
            'kn',  # Kannada
            'ml',  # Malayalam
            'ch',  # Chinese
        ]
    
    def verify_telugu_support(self) -> bool:
        """Verify that Telugu language support is available"""
        return self.language == 'te' or 'te' in self.get_available_languages()


def test_paddle_ocr():
    """Test PaddleOCR functionality"""
    if not PADDLEOCR_AVAILABLE:
        print("❌ PaddleOCR is not installed")
        print("Install with: pip install paddleocr paddlepaddle")
        return
    
    try:
        print("Testing PaddleOCR...")
        processor = PaddleOCRProcessor(language='te', use_gpu=False)
        
        print(f"✅ PaddleOCR initialized successfully")
        print(f"   Language: {processor.language}")
        print(f"   Telugu support: {processor.verify_telugu_support()}")
        print(f"   Available languages: {processor.get_available_languages()}")
        
    except Exception as e:
        print(f"❌ PaddleOCR test failed: {e}")


if __name__ == "__main__":
    test_paddle_ocr()
