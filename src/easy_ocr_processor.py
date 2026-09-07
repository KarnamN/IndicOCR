"""
EasyOCR Processor
Wrapper for EasyOCR with Telugu support
"""
from PIL import Image
import numpy as np
from typing import Optional
import logging
import gc

logger = logging.getLogger(__name__)

# Check if EasyOCR is available
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR not available. Install with: pip install easyocr")


class EasyOCRProcessor:
    """EasyOCR processor with Telugu support"""
    
    def __init__(self, language: str = 'te', use_gpu: bool = False):
        """
        Initialize EasyOCR processor
        
        Args:
            language: Language code ('te' for Telugu, 'en' for English)
            use_gpu: Whether to use GPU (default: False for WSL stability)
        """
        if not EASYOCR_AVAILABLE:
            raise ImportError("EasyOCR is not installed. Install with: pip install easyocr")
        
        # Map language codes
        lang_map = {
            'tel': 'te',
            'eng': 'en',
            'te': 'te',
            'en': 'en'
        }
        
        # Handle multi-language
        if '+' in language:
            langs = [lang_map.get(lang.strip(), lang.strip()) for lang in language.split('+')]
        else:
            langs = [lang_map.get(language, language)]
        
        self.language = langs
        self.use_gpu = use_gpu
        
        logger.info(f"Initializing EasyOCR with languages: {self.language}, GPU: {self.use_gpu}")
        
        # Initialize reader (this downloads models on first run)
        self.reader = easyocr.Reader(
            self.language,
            gpu=self.use_gpu,
            verbose=False
        )
        
        logger.info("EasyOCR initialized successfully")
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Advanced line removal for tables. 
        Detects and wipes out grid lines so OCR can focus on pure text.
        """
        try:
            import cv2
            from PIL import ImageEnhance, ImageFilter
            
            # 1. Convert to grayscale
            image = image.convert('L')
            img_array = np.array(image)
            
            # 2. Binary Threshold (Inverse: text is white, background is black)
            # This helps in identifying the structural lines
            _, binary_inv = cv2.threshold(img_array, 150, 255, cv2.THRESH_BINARY_INV)
            
            # 3. Detect Horizontal Lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            detected_h = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            
            # 4. Detect Vertical Lines
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            detected_v = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            
            # 5. Combine lines and thicken them slightly to ensure full removal
            lines_mask = cv2.add(detected_h, detected_v)
            kernel_dil = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            lines_mask = cv2.dilate(lines_mask, kernel_dil, iterations=1)
            
            # 6. Wipe out lines in the original grayscale image (make them white)
            cleaned_img = img_array.copy()
            cleaned_img[lines_mask > 0] = 255  # Paint lines white
            
            # 7. Final adaptive threshold for super crisp text
            final_bin = cv2.adaptiveThreshold(
                cleaned_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            processed_image = Image.fromarray(final_bin)
            return processed_image.convert('RGB')
            
        except Exception as e:
            logger.warning(f"Line removal failed: {e}, using fallback contrast")
            return image.convert('RGB')
    
    def _downscale_for_ocr(self, image: Image.Image, max_dimension: int = 2000) -> Image.Image:
        """
        Downscale image if it's too large to prevent OOM crashes in WSL.
        EasyOCR internally uses mag_ratio which further increases memory usage,
        so we cap the input image size.
        
        Args:
            image: PIL Image
            max_dimension: Maximum width or height (default: 2000px)
            
        Returns:
            Downscaled image (or original if already small enough)
        """
        w, h = image.size
        if w <= max_dimension and h <= max_dimension:
            return image
        
        scale = min(max_dimension / w, max_dimension / h)
        new_w, new_h = int(w * scale), int(h * scale)
        logger.info(f"  🔽 Downscaling for EasyOCR: {w}x{h} → {new_w}x{new_h} (prevents OOM)")
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    def _check_memory(self):
        """
        Check available memory before OCR. If low, force garbage collection.
        Returns available memory in MB.
        """
        try:
            import psutil
            available_mb = psutil.virtual_memory().available / (1024 * 1024)
            if available_mb < 500:
                logger.warning(f"⚠️ Low memory: {available_mb:.0f}MB available. Forcing cleanup...")
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except (ImportError, Exception):
                    pass
                gc.collect()
                available_mb = psutil.virtual_memory().available / (1024 * 1024)
                logger.info(f"  💾 After cleanup: {available_mb:.0f}MB available")
            return available_mb
        except ImportError:
            return 9999  # Assume enough if psutil not available
    
    def _reinitialize_reader(self):
        """
        Reinitialize EasyOCR reader after a crash.
        This is needed because crashes can leave the reader in a bad state.
        """
        try:
            logger.info("🔄 Reinitializing EasyOCR reader after crash...")
            if hasattr(self, 'reader'):
                del self.reader
            gc.collect()
            
            self.reader = easyocr.Reader(
                self.language,
                gpu=self.use_gpu,
                verbose=False
            )
            logger.info("✅ EasyOCR reader reinitialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to reinitialize EasyOCR: {e}")
            return False
    
    def extract_text(self, image: Image.Image, timeout: int = 60) -> str:
        """
        Extract text with line removal and maximized magnification.
        Includes crash protection: image downscaling, memory checks, and auto-reinit.
        
        Args:
            image: PIL Image
            timeout: Maximum seconds to wait for OCR (default: 60)
        
        Returns:
            Extracted text
        """
        try:
            # Check memory before starting
            available_mb = self._check_memory()
            
            # Preprocess image (Remove lines!)
            image = self.preprocess_image(image)
            
            # CRASH PREVENTION: Downscale large images to prevent OOM
            image = self._downscale_for_ocr(image, max_dimension=2000)
            
            img_array = np.array(image)
            
            # Adjust OCR parameters based on image size and available memory
            w, h = image.size
            if w * h > 3000000 or available_mb < 1000:  # >3MP or <1GB RAM
                # Use conservative settings for large images / low memory
                canvas_size = 1280
                mag_ratio = 1.5
                logger.info(f"  ⚡ Using conservative EasyOCR settings (image: {w}x{h}, RAM: {available_mb:.0f}MB)")
            else:
                canvas_size = 2560
                mag_ratio = 2.0
            
            # Use threading with timeout to prevent hanging
            import threading
            result_container = {'text': '', 'error': None}
            
            def ocr_worker():
                try:
                    # Perform OCR with maximized settings for tables
                    results = self.reader.readtext(
                        img_array,
                        detail=0,
                        paragraph=False,
                        min_size=8,                   # Smaller min size for compressed cells
                        text_threshold=0.4,           # MUCH more aggressive (was 0.5)
                        low_text=0.2,                 # Better for thin/faint fonts
                        link_threshold=0.15,          # Very tight linking to keep cells separate
                        canvas_size=canvas_size,
                        mag_ratio=mag_ratio,
                        slope_ths=0.1,
                        ycenter_ths=0.5,
                        height_ths=0.5,
                        width_ths=0.25,               # EVEN TIGHTER: Stop column merging
                        add_margin=0.2,
                        contrast_ths=0.1,
                        adjust_contrast=0.5
                    )
                    result_container['text'] = '\n'.join(results)
                except Exception as e:
                    result_container['error'] = e
            
            # Run OCR in thread with timeout
            ocr_thread = threading.Thread(target=ocr_worker, daemon=True)
            ocr_thread.start()
            ocr_thread.join(timeout=timeout)
            
            if ocr_thread.is_alive():
                # Timeout occurred - force cleanup
                logger.error(f"EasyOCR timeout after {timeout}s - page too complex")
                gc.collect()
                raise TimeoutError(f"EasyOCR extraction exceeded {timeout}s timeout")
            
            if result_container['error']:
                raise result_container['error']
            
            # Free the numpy array immediately
            del img_array
            
            return result_container['text']
            
        except TimeoutError:
            # Re-raise timeout for fallback handling
            raise
        except (MemoryError, OSError) as e:
            # OOM or system error - try to recover
            logger.error(f"EasyOCR memory/system error: {e}")
            gc.collect()
            self._reinitialize_reader()
            raise  # Re-raise so fallback to Tesseract kicks in
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            # Try to reinitialize for next page
            if 'CUDA' in str(e).upper() or 'memory' in str(e).lower() or 'killed' in str(e).lower():
                self._reinitialize_reader()
            return ""
    
    def extract_text_with_semaphore(self, image: Image.Image, semaphore: 'threading.Semaphore', timeout: int = 60) -> str:
        """
        Extract text with semaphore lock to prevent parallel EasyOCR execution.
        
        CRITICAL: EasyOCR uses ~500MB+ memory. Running multiple instances in parallel
        causes OOM crashes. This method ensures only ONE EasyOCR runs at a time.
        
        Args:
            image: PIL Image
            semaphore: Threading semaphore to limit concurrency
            timeout: Maximum seconds to wait for OCR
        
        Returns:
            Extracted text
        """
        import threading
        thread_id = threading.current_thread().name
        
        logger.debug(f"[{thread_id}] Waiting for EasyOCR lock...")
        with semaphore:
            logger.debug(f"[{thread_id}] EasyOCR lock acquired, starting extraction...")
            try:
                result = self.extract_text(image, timeout)
            except Exception as e:
                logger.error(f"[{thread_id}] EasyOCR crashed: {e}")
                # Clean up memory before releasing semaphore
                gc.collect()
                raise
            finally:
                # Always clean up after EasyOCR regardless of success/failure
                gc.collect()
            logger.debug(f"[{thread_id}] EasyOCR extraction complete, releasing lock")
            return result
    
    def extract_text_with_confidence(self, image: Image.Image) -> tuple:
        """
        Extract text with confidence scores
        
        Args:
            image: PIL Image
            
        Returns:
            Tuple of (text, average_confidence)
        """
        try:
            # Convert PIL Image to numpy array
            img_array = np.array(image)
            
            # Perform OCR with details
            results = self.reader.readtext(img_array, detail=1, paragraph=False)
            
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
            
            return combined_text, avg_confidence
            
        except Exception as e:
            logger.error(f"EasyOCR extraction with confidence failed: {e}")
            return "", 0.0
    
    def auto_rotate(self, image: Image.Image) -> Image.Image:
        """
        Auto-rotate image (EasyOCR handles rotation internally)
        
        Args:
            image: PIL Image
            
        Returns:
            Original image (EasyOCR handles rotation)
        """
        # EasyOCR has built-in rotation detection
        return image
    
    def verify_telugu_support(self) -> bool:
        """Verify Telugu language support"""
        return 'te' in self.language or 'tel' in self.language
    
    def get_available_languages(self) -> list:
        """Get list of available languages"""
        return self.language
    
    def cleanup(self):
        """Release EasyOCR resources to free memory"""
        try:
            if hasattr(self, 'reader'):
                del self.reader
                import gc
                gc.collect()
                logger.info("EasyOCR resources released")
        except Exception as e:
            logger.warning(f"EasyOCR cleanup failed: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        try:
            self.cleanup()
        except:
            pass


# Test function
if __name__ == "__main__":
    print("Testing EasyOCR Processor...")
    
    try:
        processor = EasyOCRProcessor(language='te+en', use_gpu=False)
        print(f"✅ EasyOCR initialized successfully")
        print(f"Languages: {processor.get_available_languages()}")
        print(f"Telugu support: {processor.verify_telugu_support()}")
    except Exception as e:
        print(f"❌ Failed to initialize EasyOCR: {e}")
