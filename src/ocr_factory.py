"""
OCR Factory Module
Factory pattern to create appropriate OCR processor based on configuration
WITH TELUGU MULTI-LANGUAGE SUPPORT FIX
"""
import logging
from typing import Optional
import config
from logging_config import get_logger

logger = get_logger(__name__)


class OCRFactory:
    """Factory class to create OCR processors"""
    
    @staticmethod
    def create_processor(engine: str = None, language: str = None, **kwargs):
        """
        Create OCR processor based on engine type
        
        Args:
            engine: OCR engine to use ('tesseract', 'paddle', 'hybrid')
            language: Language code (e.g., 'tel', 'eng', 'te', 'tel+eng')
            **kwargs: Additional arguments passed to processor
            
        Returns:
            OCR processor instance
        """
        if engine is None:
            engine = getattr(config, 'OCR_ENGINE', 'tesseract').lower()
        
        if language is None:
            language = getattr(config, 'OCR_LANGUAGE', 'tel')
        
        logger.info(f"Creating OCR processor: engine={engine}, language={language}")
        
        if engine == 'tesseract':
            return OCRFactory._create_tesseract(language, **kwargs)
        elif engine == 'easyocr':
            return OCRFactory._create_easyocr(language, **kwargs)
        elif engine == 'paddle':
            return OCRFactory._create_paddle(language, **kwargs)
        elif engine == 'hybrid':
            return OCRFactory._create_hybrid(language, **kwargs)
        elif engine == 'gemini':
            return OCRFactory._create_gemini(language, **kwargs)
        elif engine == 'google_vision' or engine == 'google':
            return OCRFactory._create_google_vision(language, **kwargs)
        else:
            raise ValueError(
                f"Unsupported OCR engine: {engine}. "
                f"Supported engines: tesseract, easyocr, paddle, hybrid, gemini"
            )
    
    @staticmethod
    def _create_tesseract(language: str, **kwargs):
        """
        Create Tesseract OCR processor
        WITH TELUGU MULTI-LANGUAGE SUPPORT FIX
        """
        try:
            from ocr_processor import OCRProcessor
            
            # TELUGU FIX: Map language codes (handle both single and multi-language)
            lang_map = {
                'te': 'tel',
                'en': 'eng',
                'tel': 'tel',
                'eng': 'eng',
                'tel+eng': 'tel+eng',  # Multi-language support
                'te+en': 'tel+eng',    # Alternative format
            }
            
            # TELUGU FIX: If language contains '+', it's multi-language - map each part
            if '+' in language and language not in lang_map:
                parts = language.split('+')
                mapped_parts = [lang_map.get(part.strip(), part.strip()) for part in parts]
                tesseract_lang = '+'.join(mapped_parts)
            else:
                tesseract_lang = lang_map.get(language, language)
            
            config_str = kwargs.get('config_str', getattr(config, 'TESSERACT_CONFIG', None))
            
            processor = OCRProcessor(language=tesseract_lang, config_str=config_str)
            logger.info(f"Created Tesseract OCR processor with language={tesseract_lang}")
            return processor
            
        except ImportError as e:
            logger.error(f"Failed to import Tesseract OCR processor: {e}")
            raise ImportError(
                "Tesseract OCR processor not available. "
                "Make sure ocr_processor.py exists and pytesseract is installed."
            )
    
    @staticmethod
    def _create_easyocr(language: str, **kwargs):
        """Create EasyOCR processor (replaces PaddleOCR for stability)"""
        try:
            from easy_ocr_processor import EasyOCRProcessor
            
            # Map language codes
            lang_map = {
                'tel': 'te',
                'eng': 'en',
                'te': 'te',
                'en': 'en',
            }
            
            # Handle multi-language
            if '+' in language:
                langs = [lang_map.get(lang.strip(), lang.strip()) for lang in language.split('+')]
                easyocr_lang = '+'.join(langs)
            else:
                easyocr_lang = lang_map.get(language, language)
            
            use_gpu = kwargs.get('use_gpu', getattr(config, 'EASYOCR_USE_GPU', False))
            
            processor = EasyOCRProcessor(language=easyocr_lang, use_gpu=use_gpu)
            logger.info(f"Created EasyOCR processor with language={easyocr_lang}, GPU={use_gpu}")
            return processor
            
        except ImportError as e:
            logger.error(f"Failed to import EasyOCR processor: {e}")
            raise ImportError(
                "EasyOCR is not installed. "
                "Install with: pip install easyocr"
            )
    
    @staticmethod
    def _create_paddle(language: str, **kwargs):
        """
        Create PP-OCRv5 processor (PaddleX API) with built-in Tesseract fallback.
        If paddleocr is not installed or ENABLE_PADDLE_OCR=False, falls back to Tesseract.
        """
        try:
            from paddle_v5_processor import PaddleV5Processor, PADDLEOCR_AVAILABLE
            if not PADDLEOCR_AVAILABLE:
                raise ImportError("paddleocr package not installed")
            if not getattr(config, 'ENABLE_PADDLE_OCR', True):
                raise RuntimeError("ENABLE_PADDLE_OCR=False in config")
            processor = PaddleV5Processor(language=language, config=config)
            logger.info(f"✅ Created PP-OCRv5 processor (lang={language})")
            return processor
        except Exception as e:
            logger.warning(f"PP-OCRv5 unavailable ({e}) — using Tesseract")
            return OCRFactory._create_tesseract(language, **kwargs)

    @staticmethod
    def _create_hybrid(language: str, **kwargs):
        """
        Hybrid mode: route to PP-OCRv5 if enabled (has built-in Tesseract fallback),
        otherwise pure Tesseract.
        """
        if getattr(config, 'ENABLE_PADDLE_OCR', False):
            return OCRFactory._create_paddle(language, **kwargs)
        logger.info("Hybrid → Tesseract (PP-OCRv5 disabled)")
        return OCRFactory._create_tesseract(language, **kwargs)
    
    @staticmethod
    def _create_gemini(language: str, **kwargs):
        """Create Gemini Vision OCR processor (premium tier for complex pages)"""
        try:
            from gemini_ocr_processor import GeminiOCRProcessor
            
            processor = GeminiOCRProcessor()
            if not processor.is_available:
                raise RuntimeError(
                    "Gemini OCR not available — set GEMINI_API_KEY in .env file"
                )
            
            logger.info(f"Created Gemini Vision OCR processor")
            return processor
            
        except ImportError as e:
            logger.error(f"Failed to import Gemini OCR processor: {e}")
            raise ImportError(
                "Gemini OCR processor not available. "
                "Install with: pip install google-genai"
            )

    @staticmethod
    def _create_google_vision(language: str, **kwargs):
        """Create Google Cloud Vision OCR processor"""
        try:
            from google_vision_processor import GoogleVisionProcessor
            
            processor = GoogleVisionProcessor()
            if not processor.is_available:
                raise RuntimeError(
                    "Google Vision OCR not available — check GOOGLE_VISION_SERVICE_ACCOUNT or quota"
                )
            
            logger.info(f"Created Google Cloud Vision OCR processor")
            return processor
            
        except ImportError as e:
            logger.error(f"Failed to import Google Vision processor: {e}")
            raise ImportError(
                "Google Vision processor not available. "
                "Install with: pip install google-cloud-vision"
            )
    
    
    @staticmethod
    def get_available_engines() -> list:
        """Get list of available OCR engines"""
        available = []

        # Check Tesseract
        try:
            from ocr_processor import OCRProcessor
            available.append('tesseract')
        except ImportError:
            pass

        # Check PP-OCRv5 (PaddleX) — config-gated + import check
        if getattr(config, 'ENABLE_PADDLE_OCR', False):
            try:
                from paddle_v5_processor import PADDLEOCR_AVAILABLE
                if PADDLEOCR_AVAILABLE:
                    available.append('paddle')
                else:
                    logger.debug("paddle: ENABLE_PADDLE_OCR=True but paddleocr not installed")
            except ImportError:
                logger.debug("paddle_v5_processor.py not found")

        # Check Gemini (config-gated, no heavy import)
        if getattr(config, 'GEMINI_AVAILABLE', False):
            available.append('gemini')

        # Check Google Vision (config-gated, no heavy import)
        if getattr(config, 'GOOGLE_VISION_AVAILABLE', False):
            available.append('google_vision')

        return available
    
    @staticmethod
    def get_engine_info(engine: str) -> dict:
        """Get information about an OCR engine"""
        info = {
            'tesseract': {
                'name': 'Tesseract OCR',
                'description': 'Traditional OCR engine with Telugu support',
                'pros': ['Lightweight', 'CPU-friendly', 'Well-tested'],
                'cons': ['Lower accuracy', 'Slower on complex layouts'],
                'requires': ['pytesseract', 'tesseract-ocr (system)']
            },
            'paddle': {
                'name': 'PaddleOCR',
                'description': 'AI-powered OCR with deep learning',
                'pros': ['High accuracy', 'GPU support', 'Auto-rotation', 'No system deps'],
                'cons': ['Larger memory footprint', 'Slower on CPU'],
                'requires': ['paddleocr', 'paddlepaddle']
            },
            'hybrid': {
                'name': 'Hybrid OCR',
                'description': 'Combines PaddleOCR and Tesseract for best results',
                'pros': ['Best accuracy', 'Automatic fallback', 'Confidence-based'],
                'cons': ['Requires both engines', 'Higher resource usage'],
                'requires': ['All of the above']
            },
            'gemini': {
                'name': 'Gemini Vision OCR',
                'description': 'Google Gemini Vision API for complex pages (tables, mixed layouts)',
                'pros': ['Excellent accuracy', 'Handles complex layouts', 'Telugu native support'],
                'cons': ['Requires API key', 'Rate limited', 'Needs internet'],
                'requires': ['google-genai', 'GEMINI_API_KEY in .env']
            },
            'google_vision': {
                'name': 'Google Cloud Vision OCR',
                'description': 'Legacy Google Vision API with high reliability',
                'pros': ['Extremely reliable', 'Great for dense text', 'Document layout analysis'],
                'cons': ['1000 call monthly limit', 'Needs Service Account JSON'],
                'requires': ['google-cloud-vision', 'GOOGLE_VISION_SERVICE_ACCOUNT']
            },
        }
        
        return info.get(engine, {'name': 'Unknown', 'description': 'Unknown engine'})


def test_factory():
    """Test OCR factory"""
    print("Testing OCR Factory...")
    print(f"\nAvailable engines: {OCRFactory.get_available_engines()}")
    
    for engine in OCRFactory.get_available_engines():
        print(f"\n{engine.upper()} Engine Info:")
        info = OCRFactory.get_engine_info(engine)
        print(f"  Name: {info['name']}")
        print(f"  Description: {info['description']}")
        print(f"  Pros: {', '.join(info['pros'])}")
        print(f"  Cons: {', '.join(info['cons'])}")
        
        try:
            processor = OCRFactory.create_processor(engine=engine, language='tel')
            print(f"  ✅ Successfully created {engine} processor")
        except Exception as e:
            print(f"  ❌ Failed to create {engine} processor: {e}")


if __name__ == "__main__":
    test_factory()
