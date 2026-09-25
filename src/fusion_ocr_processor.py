"""OCRFactory-compatible wrapper around the PP-OCRv5 + IndicPhotoOCR + Tesseract
fusion pipeline (src/ocr_fusion.py, engine_router.py, indicphoto_ocr_processor.py).

This is the only file that adapts that pipeline (built and validated as
standalone diagnostics under tests/diagnostics/) to the interface the real
conversion pipeline expects, so the two stay decoupled: the fusion logic
itself doesn't know about Flask, config objects, or the converter's return
contract, and the converter doesn't know fusion exists beyond one more engine
name. See docs/CURRENT_STATE.md, "Configuration-Driven OCR Engine Selection".

Selected the same way every other engine is (ocr_factory.py, adaptive_ocr_factory.py):
    config.ENABLE_FUSION_OCR = True
    config.OCR_ENGINE = 'fusion'   # force it, same mechanism as 'paddle'/'gemini'/etc.

Off by default. Nothing about the existing paddle/tesseract/gemini path changes
unless both flags above are set.
"""

from __future__ import annotations

import statistics
import time
import unicodedata
from typing import Dict, List, Optional

from PIL import Image

from engine_performance_log import page_quality_metrics, record_page
from logging_config import get_logger

logger = get_logger(__name__)

# IndicPhotoOCR's identifier expects a full language name, not a code -- the rest of
# the app deals in codes like 'te'/'tel'/'tel+eng'. Only Telugu has been exercised
# (see docs/CURRENT_STATE.md); other codes fall back to 'auto' rather than guessing.
_LANGUAGE_TO_INDICPHOTO = {
    'te': 'telugu', 'tel': 'telugu', 'tel_best': 'telugu',
    'tel+eng': 'telugu', 'tel_best+eng': 'telugu',
}


class FusionOCRProcessor:
    """PP-OCRv5 + IndicPhotoOCR + Tesseract, fused per line, page-adaptive.

    Implements extract_with_fallback() with the same return contract as
    PaddleV5Processor so pdf_to_epub_converter_optimized_v2.py's
    _ocr_single_image() can call either interchangeably (it does, based on the
    ``engine`` string alone -- see that method).
    """

    def __init__(self, language: str = 'te', config=None):
        from engine_router import should_run_indicphoto
        from indicphoto_ocr_processor import IndicPhotoOCRProcessor
        from ocr_fusion import fuse_page, latin_regions, paddle_line, unresolved_lines
        from ocr_processor import OCRProcessor
        from paddle_v5_processor import PaddleV5Processor

        self.config = config
        self.language = language
        self._should_run_indicphoto = should_run_indicphoto
        self._fuse_page = fuse_page
        self._latin_regions = latin_regions
        self._paddle_line = paddle_line
        self._unresolved_lines = unresolved_lines

        self.adaptive = bool(getattr(config, 'FUSION_ADAPTIVE_ROUTER', True))
        identifier_mode = getattr(config, 'FUSION_IDENTIFIER_MODE', 'hinted')
        min_confidence = getattr(config, 'FUSION_INDIC_MIN_CONFIDENCE', 0.35)
        indic_lang = _LANGUAGE_TO_INDICPHOTO.get(language, 'auto')

        # Reuses the same module-level singleton Paddle engines as any other
        # 'paddle'-engine processor (see paddle_v5_processor._get_rec_engine /
        # _get_det_engine) -- constructing this doesn't load a second copy.
        self.paddle = PaddleV5Processor(language=language, config=config)
        self.tesseract = OCRProcessor(language='tel_best+eng' if 'tel' in language else language)
        try:
            self.indic = IndicPhotoOCRProcessor(
                device='cpu', identifier_lang=indic_lang, identifier_mode=identifier_mode,
                min_confidence=min_confidence)
        except ImportError as exc:
            logger.warning(f"IndicPhotoOCR unavailable ({exc}) — fusion falls back to PP-OCRv5+Tesseract only")
            self.indic = None
        logger.info(f"🧩 FusionOCRProcessor ready (adaptive_router={self.adaptive}, "
                   f"identifier_mode={identifier_mode}, indic_available={self.indic is not None})")

    def extract_with_fallback(self, image: Image.Image, preprocess: bool = True,
                              psm: Optional[int] = None, page_label: Optional[str] = None) -> Dict:
        """Same return contract as PaddleV5Processor.extract_with_fallback:
        {'text', 'engine', 'reason', 'confidence', 'boxes'}.
        """
        label_prefix = f"[{page_label}] " if page_label else ""
        timings: Dict[str, float] = {}
        try:
            if preprocess:
                image = self.paddle._preprocess(image, page_label=page_label)
            image = self.paddle._resize_if_needed(self.paddle._ensure_rgb(image))
            quality = page_quality_metrics(image) if getattr(self.config, 'FUSION_LOG_PERFORMANCE', True) else None

            started = time.perf_counter()
            _, paddle_boxes = self.paddle._paddle_extract(image)
            timings['paddle'] = time.perf_counter() - started
            lines = [self._paddle_line(box) for box in paddle_boxes]
            if not lines:
                # No PP-OCRv5 detections at all -- nothing for fusion to anchor on.
                # Same soft-fail shape PaddleV5Processor uses so the caller's
                # existing empty-text handling applies unchanged.
                return {'text': '', 'engine': 'fusion', 'reason': 'no_paddle_lines', 'confidence': 0.0, 'boxes': []}

            started = time.perf_counter()
            tess_words = [
                {'text': unicodedata.normalize('NFC', w['text']),
                 'bbox': [w['left'], w['top'], w['left'] + w['width'], w['top'] + w['height']]}
                for w in self.tesseract.extract_text_with_boxes(image, preprocess=False) if w['text'].strip()
            ]
            timings['tesseract'] = time.perf_counter() - started

            run_indic = self.indic is not None
            router_meta = None
            if run_indic and self.adaptive:
                run_indic, router_meta = self._should_run_indicphoto(lines, tess_words)

            started = time.perf_counter()
            words = []
            if run_indic:
                try:
                    target_lines = self._unresolved_lines(lines, tess_words)
                    words = self.indic.extract_words(
                        image, english_boxes=self._latin_regions(lines),
                        paddle_boxes=[line['bbox'] for line in target_lines])
                except Exception as exc:
                    logger.warning(f"{label_prefix}IndicPhotoOCR pass failed, continuing without it: {exc}")
            timings['indicphoto'] = time.perf_counter() - started

            fused = self._fuse_page(lines, words, tess_words)
            text = '\n'.join(line['text'] for line in fused)
            confidences = [line['paddle_confidence'] for line in fused if line['paddle_confidence'] > 0]
            avg_confidence = statistics.fmean(confidences) if confidences else 0.0

            if quality is not None:
                record_page(page_label=page_label or '', quality=quality, timings=timings,
                           fused_lines=fused, router_meta=router_meta, source='production')

            boxes_out = [
                {
                    'text': line['text'], 'confidence': line['paddle_confidence'],
                    'left': int(line['bbox'][0]), 'top': int(line['bbox'][1]),
                    'width': int(line['bbox'][2] - line['bbox'][0]), 'height': int(line['bbox'][3] - line['bbox'][1]),
                    'chosen_engine': line['chosen'], 'needs_review': line['needs_review'],
                }
                for line in fused
            ]
            reason = 'fusion_ok' if run_indic else 'fusion_indic_skipped_by_router'
            if router_meta:
                logger.info(f"{label_prefix}🧩 Fusion router: {router_meta['triggers'] or 'no triggers (skipped IndicPhotoOCR)'}")
            flagged = sum(line['needs_review'] for line in fused)
            logger.info(f"{label_prefix}🧩 Fusion ✅ | lines={len(fused)} | conf={avg_confidence:.2f} | "
                       f"flagged={flagged} | indic_ran={run_indic}")

            return {'text': text, 'engine': 'fusion', 'reason': reason, 'confidence': avg_confidence, 'boxes': boxes_out}
        except Exception as exc:
            logger.error(f"{label_prefix}Fusion pipeline crashed ({exc}) — falling back to plain PP-OCRv5")
            return self.paddle.extract_with_fallback(image, preprocess=False, psm=psm, page_label=page_label)

    # ── Passthroughs used by other call sites in the converter/app ──────────
    # (auto_rotate, verify_telugu_support, etc. are called on a separate plain
    # OCRProcessor instance the converter keeps for that purpose -- see
    # OptimizedPDFToEPUBConverter.__init__ -- not on whatever the factory
    # returns here, so they're not required on this class. extract_text is
    # kept as a plain-text convenience for any code that checks for it.)
    def extract_text(self, image: Image.Image, preprocess: bool = True, *args, **kwargs) -> str:
        return self.extract_with_fallback(image, preprocess=preprocess).get('text', '')
