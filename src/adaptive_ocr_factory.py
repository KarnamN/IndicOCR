"""
Adaptive OCR Factory
Determines and provides the optimal OCR engine for each page.
"""
import logging
import threading
from typing import Dict, Optional, Any, Tuple
from ocr_factory import OCRFactory
from page_complexity_analyzer import PageComplexityAnalyzer
import config
from usage_tracker import UsageTracker

logger = logging.getLogger(__name__)

class AdaptiveOCRFactory:
    """Manages OCR processors with adaptive logic based on page content."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AdaptiveOCRFactory, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.factory = OCRFactory()
        self.analyzer = PageComplexityAnalyzer()
        self.usage_tracker = UsageTracker()
        self.processor_cache = {}
        self._lock = threading.Lock()
        self._initialized = True
        paddle_status = "PP-OCRv5 primary" if getattr(config, 'ENABLE_PADDLE_OCR', False) else "Tesseract primary"
        logger.info(f"Adaptive OCR Factory initialized ({paddle_status} + Gemini)")

    def get_processor_for_page(self, image, language: str,
                               figure_regions=None) -> Tuple[Any, Dict[str, Any]]:
        """
        Analyzes the page and returns (processor, metadata).

        figure_regions: optional list of (x, y, w, h) illustration boxes in
            original-page coords (e.g. the layout analyzer's figure_coords).
            Forwarded to analyze() so column/text-region detection stays correct
            even when the passed image has illustrations masked to white.
        """
        analysis = self.analyzer.analyze(image, figure_regions=figure_regions)
        
        # --- ROUTING LOGIC ---
        engine_to_use = analysis['recommended_engine']
        complexity = analysis['complexity_score']
        page_type = analysis.get('page_type', '')  # e.g. 'toc', 'mixed_image_text'

        gemini_thresh  = getattr(config, 'GEMINI_COMPLEXITY_THRESHOLD', 80)
        vision_thresh  = getattr(config, 'GOOGLE_VISION_COMPLEXITY_THRESHOLD', 90)
        paddle_enabled = getattr(config, 'ENABLE_PADDLE_OCR', False)
        paddle_min     = getattr(config, 'PADDLE_COMPLEXITY_MIN', 0)

        # --- Tier 1: Premium (>= 90) — Google Vision, then Gemini ---
        if complexity >= vision_thresh:
            if self.usage_tracker.has_quota('google_vision'):
                engine_to_use = 'google_vision'
                logger.info("💎 High complexity -> Google Cloud Vision")
            elif self.usage_tracker.has_quota('gemini'):
                engine_to_use = 'gemini'
                logger.info("💎 High complexity -> GCV quota out, using Gemini")
            # else fall through to paddle/tesseract

        # --- Tier 2: Premium (80-90) — Gemini, then Google Vision ---
        elif complexity >= gemini_thresh:
            if self.usage_tracker.has_quota('gemini'):
                engine_to_use = 'gemini'
                logger.info("🚀 Mid-High complexity -> Gemini Vision")
            elif self.usage_tracker.has_quota('google_vision'):
                engine_to_use = 'google_vision'
                logger.info("🚀 Mid-High complexity -> Gemini quota out, using Google Vision")

        # --- Tier 3: PP-OCRv5 primary (complexity < gemini_thresh) ---
        # PP-OCRv5 handles all pages below Gemini threshold.
        # Built-in Tesseract fallback fires automatically inside the processor
        # if quality gate fails — no extra routing needed here.
        elif paddle_enabled and complexity >= paddle_min:
            engine_to_use = 'paddle'
            logger.info(f"🏏 PP-OCRv5 primary (complexity={complexity:.1f})")

        # --- Tier 4: Tesseract (paddle disabled or complexity below paddle_min) ---
        # engine_to_use already = recommended_engine (tesseract) from analyzer

        # Config-level override always wins (only when not 'hybrid')
        force_engine = getattr(config, 'OCR_ENGINE', 'hybrid').lower()
        if force_engine != 'hybrid':
            engine_to_use = force_engine
            logger.info(f"📍 Config override: forcing engine {engine_to_use}")

        processor = self._get_cached_processor(engine_to_use, language)

        # CRITICAL: Store the actual engine used
        analysis['actual_engine'] = engine_to_use

        # Enhanced logging
        icons = {
            "tesseract":    "🔧",
            "paddle":       "🏏",
            "gemini":       "🚀",
            "google_vision":"💎",
            "easyocr":      "🧠",
            "fusion":       "🧩",
        }
        icon = icons.get(engine_to_use, "🤖")
        logger.info(f"{icon} OCR Engine: {engine_to_use.upper()} | Complexity: {complexity:.1f} | Type: {page_type or 'standard'}")
        
        return processor, analysis

    def _get_cached_processor(self, engine: str, language: str):
        cache_key = f"{engine}_{language}"
        
        # Double-checked locking to prevent parallel initialization
        if cache_key not in self.processor_cache:
            with self._lock:
                if cache_key not in self.processor_cache:
                    # Check if engine is enabled in config
                    is_enabled = True
                    effective_engine = engine
                    if engine == 'gemini':
                        is_enabled = (getattr(config, 'ENABLE_GEMINI_OCR', False) and
                                     getattr(config, 'GEMINI_AVAILABLE', False))
                    elif engine == 'paddle':
                        # PP-OCRv5: check config flag + package availability
                        is_enabled = getattr(config, 'ENABLE_PADDLE_OCR', False)
                        if is_enabled:
                            try:
                                from paddle_v5_processor import PADDLEOCR_AVAILABLE
                                is_enabled = PADDLEOCR_AVAILABLE
                            except ImportError:
                                is_enabled = False
                    # NOTE: 'fusion' deliberately has no is_enabled gate here (unlike
                    # 'paddle'/'gemini'/'google_vision' above) -- the generic
                    # fallback a few lines down would send it to Tesseract when
                    # disabled, throwing away PP-OCRv5 entirely. Instead
                    # OCRFactory._create_fusion (ocr_factory.py) does its own
                    # config.ENABLE_FUSION_OCR check and falls back to plain
                    # PaddleV5Processor internally when off -- the better default
                    # for "the experimental extra stage is disabled" than dropping
                    # to Tesseract. See docs/CURRENT_STATE.md, "Configuration-Driven
                    # OCR Engine Selection".
                    elif engine == 'google_vision':
                        # Check both config AND package availability
                        try:
                            import importlib.util
                            has_package = importlib.util.find_spec('google.cloud.vision') is not None
                        except:
                            has_package = False
                            
                        is_enabled = (getattr(config, 'ENABLE_GOOGLE_VISION_OCR', False) and 
                                     getattr(config, 'GOOGLE_VISION_AVAILABLE', False) and
                                     has_package)
                    
                    if not is_enabled:
                        logger.warning(f"Engine {engine} is disabled in config or not available. Falling back to Tesseract.")
                        effective_engine = 'tesseract'
                        cache_key = f"tesseract_{language}"
                        if cache_key in self.processor_cache:
                            return self.processor_cache[cache_key]

                    logger.info(f"Initializing {effective_engine} processor for {language}...")
                    try:
                        self.processor_cache[cache_key] = self.factory.create_processor(effective_engine, language)
                    except Exception as e:
                        logger.warning(f"Failed to initialize {effective_engine} processor: {e}")
                        # Fallback to Tesseract if the requested engine fails
                        if effective_engine != 'tesseract':
                            logger.info(f"Falling back to Tesseract OCR")
                            fallback_key = f"tesseract_{language}"
                            if fallback_key not in self.processor_cache:
                                self.processor_cache[fallback_key] = self.factory.create_processor('tesseract', language)
                            self.processor_cache[cache_key] = self.processor_cache[fallback_key]
                        else:
                            raise  # Re-raise if Tesseract itself fails
                    
        return self.processor_cache[cache_key]
