"""
OCR Processing Module
Handles text extraction from images using Tesseract OCR with Telugu support
"""
import os
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import cv2
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import config

# Logging is configured centrally by logging_config.setup_logging() (invoked at
# app.py's import time) — this module just gets its own named logger from
# whatever root configuration is already in place.
logger = logging.getLogger(__name__)

# Set Tesseract path
if hasattr(config, 'TESSERACT_PATH') and config.TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH

# ── CPU thread ceilings ───────────────────────────────────────────────────────
# config.py sets OMP_THREAD_LIMIT=1 globally — tuned for a pure-Tesseract
# pipeline (many lightweight concurrent subprocesses). That same ceiling also
# throttles PaddleOCR/PP-DocLayout in-process CPU inference (config_v5.py /
# WSL path) to 1 thread each, which is a major bottleneck since those calls
# are additionally serialized process-wide by _engine_lock/_layout_lock —
# meaning the single active Paddle/layout call runs on exactly 1 core.
#
# Only raise the in-process ceiling when Paddle is actually the active engine
# (ENABLE_PADDLE_OCR, set by config_v5.py) — Windows Tesseract-only mode never
# touches Paddle, so it keeps config.py's OMP_THREAD_LIMIT=1 untouched.
if getattr(config, 'ENABLE_PADDLE_OCR', False):
    _cpu_count = os.cpu_count() or 4
    _default_paddle_threads = max(2, _cpu_count // 2)  # heuristic: half the cores, min 2
    _paddle_omp_limit = os.environ.get('OCR_PADDLE_OMP_LIMIT', str(_default_paddle_threads))
    os.environ['OMP_THREAD_LIMIT'] = _paddle_omp_limit
    os.environ.setdefault('PADDLE_PDX_CPU_NUM_THREADS', _paddle_omp_limit)
    logger.info(f"🚀 Paddle/layout in-process OMP thread ceiling set to {_paddle_omp_limit} "
                f"(cpu_count={_cpu_count}; override with OCR_PADDLE_OMP_LIMIT env var)")

# Tesseract always gets its own private, per-call env — independent of
# whatever the in-process ceiling above is set to. This builds a NEW dict on
# every call (never mutating the shared os.environ object), so it's safe to
# call concurrently from multiple worker threads.
try:
    import pytesseract.pytesseract as _pt_internal

    # Guard against double-wrapping: if ocr_processor.py is ever re-executed
    # (module reload, duplicate import path, a dev-server auto-reloader),
    # re-running this unconditionally would wrap the already-patched function
    # around itself, and since _orig_subprocess_args is looked up as a module
    # global at CALL time (not frozen at definition time), that produces
    # infinite self-recursion the first time OCR actually runs.
    if not getattr(_pt_internal.subprocess_args, '_ocr_thread_scoped', False):
        _orig_subprocess_args = _pt_internal.subprocess_args

        def _scoped_subprocess_args(include_stdout=True):
            kwargs = _orig_subprocess_args(include_stdout)
            limit = getattr(config, 'TESSERACT_SUBPROCESS_OMP_LIMIT', '1')
            kwargs['env'] = dict(os.environ, OMP_THREAD_LIMIT=limit, OMP_NUM_THREADS=limit)
            return kwargs

        _scoped_subprocess_args._ocr_thread_scoped = True
        _pt_internal.subprocess_args = _scoped_subprocess_args
except AttributeError:
    logger.warning("pytesseract.subprocess_args not found — skipping Tesseract "
                    "thread-scoping (pytesseract API may have changed)")


class OCRProcessor:
    """Process images and extract text using OCR"""
    
    def __init__(self, language: str = None, config_str: str = None):
        """
        Initialize OCR processor
        
        Args:
            language: OCR language code (e.g., 'tel', 'tel+eng')
            config_str: Tesseract configuration string
        """
        self.language = language or config.DEFAULT_OCR_LANGUAGE
        self.config_str = config_str or config.OCR_CONFIG
        logger.info(f"OCR Processor initialized with language: {self.language}")
    
    def preprocess_image(self, image: Image.Image, aggressive: bool = False) -> Image.Image:
        """
        Preprocess image for better OCR accuracy.
        Since Tesseract is designed to work best on grayscale/color images and has
        its own internal local binarization algorithms, we return the image directly
        to avoid destroying font anti-aliasing and stroke details.
        """
        return image
    
    def extract_text(self, image: Image.Image, preprocess: bool = True, psm: int = 3, page_label: str = "") -> str:
        """
        Extract text from image using Tesseract with a specific PSM.
        """
        import re
        import unicodedata
        prefix = f"[{page_label}] " if page_label else ""
        try:
            if preprocess:
                processed = self.preprocess_image(image)
            else:
                processed = image
            
            # Base config cleanup — strip existing --psm so we can inject the right one
            base_config = self.config_str
            base_config = re.sub(r'--psm\s+\d+', '', base_config).strip()
            
            # --- BLANK CELL SKIP ---
            # If image is mostly white/empty, skip Tesseract to save time (common in tables)
            if image.size[0] * image.size[1] > 0:
                from PIL import ImageStat
                stat = ImageStat.Stat(image.convert('L'))
                # If mean brightness is very high (>250), it's likely blank
                if stat.mean[0] > 252:
                    return ""
            
            cfg = f"{base_config} --psm {psm}"
            text = pytesseract.image_to_string(processed, lang=self.language, config=cfg).strip()
            
            # NFC normalization: Tesseract can emit decomposed Unicode for Telugu glyphs.
            # e.g., కా as 2 codepoints vs 1. NFC ensures consistent composed form,
            # which is required for EPUB search and correct rendering on Telugu displays.
            text = unicodedata.normalize('NFC', text)
            
            lines = [l for l in text.split('\n') if l.strip()]
            if len(lines) > 0:
                logger.info(f"    {prefix}✓ Tesseract (PSM {psm}): {len(lines)} lines found")
            else:
                logger.debug(f"    {prefix}✓ Tesseract (PSM {psm}): 0 lines found")
            
            return text
            
        except Exception as e:
            logger.error(f"{prefix}OCR extraction failed (PSM {psm}): {e}")
            return ""
    
    def extract_text_with_boxes(self, image: Image.Image, preprocess: bool = True) -> List[Dict]:
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
            
            # Get detailed OCR data
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                config=self.config_str,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text blocks with positions
            text_blocks = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                if int(data['conf'][i]) > 0:  # Only include confident detections
                    text_blocks.append({
                        'text': data['text'][i],
                        'left': data['left'][i],
                        'top': data['top'][i],
                        'width': data['width'][i],
                        'height': data['height'][i],
                        'confidence': data['conf'][i],
                        'block_num': data['block_num'][i],
                        'line_num': data['line_num'][i],
                        'word_num': data['word_num'][i]
                    })
            
            return text_blocks
            
        except Exception as e:
            logger.error(f"OCR extraction with boxes failed: {e}")
            return []
    
    def detect_orientation(self, image: Image.Image) -> Dict:
        """
        Detect image orientation and script
        
        Args:
            image: PIL Image object
            
        Returns:
            Dictionary with orientation info
        """
        try:
            # Check image size - OSD requires minimum dimensions
            if image.width < 300 or image.height < 300:
                logger.debug(f"Image too small for OSD ({image.width}x{image.height}), skipping orientation detection")
                return {'Rotate': '0', 'Confidence': '0'}
            
            osd = pytesseract.image_to_osd(image)
            
            # Parse OSD output
            orientation_info = {}
            for line in osd.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    orientation_info[key.strip()] = value.strip()
            
            return orientation_info
            
        except pytesseract.TesseractError as e:
            # Common OSD failures: too few characters, invalid resolution
            error_msg = str(e)
            if 'Too few characters' in error_msg:
                logger.debug("OSD skipped: too few characters in image")
            elif 'Invalid resolution' in error_msg:
                logger.debug("OSD skipped: invalid image resolution")
            else:
                logger.debug(f"OSD failed: {error_msg}")
            return {'Rotate': '0', 'Confidence': '0'}
        except Exception as e:
            logger.debug(f"Orientation detection skipped: {type(e).__name__}")
            return {'Rotate': '0', 'Confidence': '0'}

    
    def auto_rotate(self, image: Image.Image) -> Image.Image:
        """
        Automatically rotate image to correct orientation
        
        Args:
            image: PIL Image object
            
        Returns:
            Rotated PIL Image
        """
        try:
            orientation_info = self.detect_orientation(image)
            
            if 'Rotate' in orientation_info:
                angle = int(orientation_info['Rotate'])
                if angle != 0:
                    logger.info(f"Rotating image by {angle} degrees")
                    image = image.rotate(-angle, expand=True)
            
            return image
            
        except Exception as e:
            logger.warning(f"Auto-rotation failed: {e}")
            return image
    
    def process_image_file(self, image_path: Path, preprocess: bool = True) -> str:
        """
        Process an image file and extract text
        
        Args:
            image_path: Path to image file
            preprocess: Whether to preprocess the image
            
        Returns:
            Extracted text as string
        """
        try:
            image = Image.open(image_path)
            
            # Auto-rotate if needed
            image = self.auto_rotate(image)
            
            # Extract text
            text = self.extract_text(image, preprocess=preprocess)
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to process image file {image_path}: {e}")
            return ""
    
    def get_available_languages(self) -> List[str]:
        """
        Get list of available Tesseract languages
        
        Returns:
            List of language codes
        """
        try:
            languages = pytesseract.get_languages()
            return languages
        except Exception as e:
            logger.error(f"Failed to get available languages: {e}")
            return []
    
    def verify_telugu_support(self) -> bool:
        """
        Verify that Telugu language support is available
        
        Returns:
            True if Telugu is supported, False otherwise
        """
        try:
            languages = self.get_available_languages()
            has_telugu = 'tel' in languages
            
            if has_telugu:
                logger.info("Telugu language support verified")
            else:
                logger.warning("Telugu language support not found!")
                logger.info(f"Available languages: {', '.join(languages)}")
            
            return has_telugu
            
        except Exception as e:
            logger.error(f"Failed to verify Telugu support: {e}")
            return False


def test_ocr():
    """Test OCR functionality"""
    processor = OCRProcessor()
    
    # Verify Telugu support
    if processor.verify_telugu_support():
        print("✓ Telugu OCR is ready")
    else:
        print("✗ Telugu OCR is not available")
        print("Please install Telugu language data for Tesseract")
    
    # List available languages
    languages = processor.get_available_languages()
    print(f"\nAvailable languages: {', '.join(languages)}")


if __name__ == "__main__":
    test_ocr()
