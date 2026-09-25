"""
paddle_v5_processor.py — PP-OCRv5 Telugu OCR Processor
=======================================================
Uses the PaddleX TextRecognition / TextDetection API (new PP-OCRv5 ecosystem).
Models used (from ~/.paddlex/official_models/):
  - Detection:    PP-OCRv5_server_det    (84 MB)
  - Recognition:  te_PP-OCRv5_mobile_rec (7.5 MB)

KEY FEATURE: Seamless Tesseract Fallback
-----------------------------------------
Every extract_text() call goes through a 3-step process:
  Step 1 → Try PP-OCRv5
  Step 2 → Quality gate check (confidence, line count, Telugu chars)
  Step 3 → If gate fails: try Tesseract automatically
  
The caller never needs to handle fallback logic — it just calls extract_text()
and gets the best available result with full logging of which engine was used.
"""

from __future__ import annotations

import sys
import os

# Automatically inject the current virtual environment's bin folder to PATH
# This prevents FileNotFoundError when PaddleX executes subprocesses like `paddlex --install`
venv_bin = os.path.dirname(sys.executable)
if venv_bin and venv_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")

import gc
import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance

import config as _base_config
from logging_config import get_logger

logger = get_logger(__name__)

try:
    from openvino_runner import accelerate_with_openvino as _accelerate_with_openvino
except ImportError:  # openvino not installed: stay on Paddle's CPU runner
    def _accelerate_with_openvino(engine, model_name):
        return False

# ── Module-level availability flag ────────────────────────────────────────────
# Updated at import time — imported by config_v5.py to set PADDLE_OCR_AVAILABLE
PADDLEOCR_AVAILABLE = False

_TextRecognition = None
_TextDetection   = None

# Track distinct paddle errors so we only log each unique error once
_paddle_logged_errors: set = set()

# ── Crash tracking (hard crashes only, not soft quality fails) ────────────────
_hard_crash_count: int = 0          # OOM + C++ exception crashes
_soft_fail_count: int  = 0          # too_few_lines, low_confidence, etc.
_crash_lock = threading.Lock()

def get_crash_stats() -> dict:
    """Return current crash statistics for health monitoring."""
    return {
        'hard_crashes': _hard_crash_count,
        'soft_fails':   _soft_fail_count,
        'available':    PADDLEOCR_AVAILABLE,
    }

def reset_crash_stats():
    """Reset crash counters (call after user acknowledges alert)."""
    global _hard_crash_count, _soft_fail_count
    with _crash_lock:
        _hard_crash_count = 0
        _soft_fail_count  = 0


import os as _os
# Pre-set env flags BEFORE paddleocr import (forced to prevent PIR oneDNN crashes)
_os.environ["FLAGS_use_mkldnn"] = "0"
_os.environ["FLAGS_mkldnn_cache_capacity"] = "0"
_os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
_os.environ["FLAGS_enable_pir_api"] = "0"
_os.environ["FLAGS_enable_pir_in_executor"] = "0"

try:
    from paddleocr import TextRecognition as _TextRecognition
    from paddleocr import TextDetection   as _TextDetection
    PADDLEOCR_AVAILABLE = True
    # ── Runtime flag override via paddle API (works even after .so is loaded) ──
    try:
        import paddle as _paddle
        _paddle.set_flags({"FLAGS_use_mkldnn": False})
        logger.info("✅ paddleocr (PP-OCRv5 / PaddleX API) is available (OneDNN disabled via paddle.set_flags)")
    except Exception as _fe:
        logger.info(f"✅ paddleocr (PP-OCRv5 / PaddleX API) is available (set_flags note: {_fe})")
except ImportError:
    logger.warning("⚠️  paddleocr not installed — PP-OCRv5 engine disabled. "
                   "Run: pip install paddleocr paddlepaddle")
except Exception as _e:
    logger.warning(f"⚠️  paddleocr import error: {_e} — PP-OCRv5 disabled")

# Update config availability flag if config_v5 is the active config
try:
    import sys
    _cfg = sys.modules.get('config')
    if _cfg and hasattr(_cfg, 'PADDLE_OCR_AVAILABLE'):
        _cfg.PADDLE_OCR_AVAILABLE = PADDLEOCR_AVAILABLE
except Exception:
    pass

# ── Singleton engine instances (lazy, thread-safe) ────────────────────────────
_rec_engine: Optional[object] = None
_det_engine: Optional[object] = None
_engine_lock = threading.Lock()


def _get_rec_engine(config=None):
    """Lazy-load TextRecognition singleton (thread-safe, loaded once)."""
    global _rec_engine
    if _rec_engine is not None:
        return _rec_engine
    if not PADDLEOCR_AVAILABLE:
        return None
    cfg = config or _base_config
    with _engine_lock:
        if _rec_engine is None:
            model_name = getattr(cfg, 'PADDLE_REC_MODEL', 'te_PP-OCRv5_mobile_rec')
            use_openvino = getattr(cfg, 'PADDLE_USE_OPENVINO', False)
            logger.info(f"🚀 Loading recognition model: {model_name} (OpenVINO/HPI={use_openvino})")
            
            try:
                _rec_engine = _TextRecognition(
                    model_name=model_name, 
                    enable_mkldnn=False,
                    enable_hpi=use_openvino
                )
            except Exception as e:
                if use_openvino:
                    logger.warning(f"Failed to load recognition model with OpenVINO (HPI): {e}. "
                                   "Falling back to standard CPU mode.")
                    _rec_engine = _TextRecognition(
                        model_name=model_name, 
                        enable_mkldnn=False,
                        enable_hpi=False
                    )
                else:
                    raise e
            logger.info(f"✅ {model_name} loaded successfully")
            if use_openvino:
                _accelerate_with_openvino(_rec_engine, model_name)
    return _rec_engine


def _get_det_engine(config=None):
    """Lazy-load TextDetection singleton (thread-safe, loaded once)."""
    global _det_engine
    if _det_engine is not None:
        return _det_engine
    if not PADDLEOCR_AVAILABLE:
        return None
    cfg = config or _base_config
    with _engine_lock:
        if _det_engine is None:
            model_name = getattr(cfg, 'PADDLE_DET_MODEL', 'PP-OCRv5_server_det')
            use_openvino = getattr(cfg, 'PADDLE_USE_OPENVINO', False)
            logger.info(f"🚀 Loading detection model: {model_name} (OpenVINO/HPI={use_openvino})")
            
            # Extract detection parameters from config with safe defaults
            unclip_ratio = getattr(cfg, 'PADDLE_DET_UNCLIP_RATIO', None)
            thresh = getattr(cfg, 'PADDLE_DET_THRESH', None)
            box_thresh = getattr(cfg, 'PADDLE_DET_BOX_THRESH', None)
            limit_side_len = getattr(cfg, 'PADDLE_DET_LIMIT_SIDE_LEN', None)
            limit_type = getattr(cfg, 'PADDLE_DET_LIMIT_TYPE', None)
            
            det_opts = []
            if unclip_ratio is not None: det_opts.append(f"unclip_ratio={unclip_ratio}")
            if thresh is not None: det_opts.append(f"thresh={thresh}")
            if box_thresh is not None: det_opts.append(f"box_thresh={box_thresh}")
            if limit_side_len is not None: det_opts.append(f"limit_side_len={limit_side_len}")
            if limit_type is not None: det_opts.append(f"limit_type={limit_type}")
            if use_openvino: det_opts.append("enable_hpi=True")
            if det_opts:
                logger.info(f"🔧 Detection parameters: {', '.join(det_opts)}")
                
            # RESOLVED (2026-07-04): PP-OCRv5_server_det previously crashed under
            # enable_hpi=True with a native PIR executor error. Root cause (traced
            # directly in PaddleX's source, not guesswork): PaddleX auto-selects
            # the HPI backend from its own bundled priority list
            # (hpi_model_info_collection.json), which for this model is
            # ['paddle_mkldnn', 'openvino', 'onnxruntime', 'paddle'] — since
            # Paddle-format files are always present, 'paddle_mkldnn' always wins
            # BEFORE OpenVINO is ever considered. Meanwhile config_v5.py globally
            # disables MKL-DNN (FLAGS_use_mkldnn=0, for a separate older crash),
            # so PaddleX selects a backend config assuming mkldnn accel is active
            # while it's actually neutered — that mismatch is what crashed.
            # OpenVINO itself was never actually attempted.
            # Fix: force the backend choice via a bucketed engine_config, bypassing
            # auto-selection entirely. Verified working in isolation in WSL
            # (scratch/test_openvino_det_forced.py): "Inference backend: openvino"
            # in the log, and a real predict() call succeeded (35 boxes, 2.7s;
            # ~23s one-time construction cost for ONNX/OpenVINO compilation, paid
            # once since this is a lazy-loaded singleton, not per-page).
            try:
                if use_openvino:
                    _det_engine = _TextDetection(
                        model_name=model_name,
                        enable_mkldnn=False,
                        enable_hpi=True,
                        unclip_ratio=unclip_ratio,
                        thresh=thresh,
                        box_thresh=box_thresh,
                        limit_side_len=limit_side_len,
                        limit_type=limit_type,
                        engine_config={"hpi": {"auto_config": False, "backend": "openvino"}}
                    )
                else:
                    _det_engine = _TextDetection(
                        model_name=model_name,
                        enable_mkldnn=False,
                        enable_hpi=False,
                        unclip_ratio=unclip_ratio,
                        thresh=thresh,
                        box_thresh=box_thresh,
                        limit_side_len=limit_side_len,
                        limit_type=limit_type
                    )
                logger.info(f"✅ {model_name} loaded successfully"
                            + (" (OpenVINO/HPI active)" if use_openvino else ""))
            except Exception as e:
                if use_openvino:
                    logger.warning(f"Failed to load detection model with forced OpenVINO (HPI): {e}. "
                                   "Falling back to standard CPU mode.")
                    _det_engine = _TextDetection(
                        model_name=model_name,
                        enable_mkldnn=False,
                        enable_hpi=False,
                        unclip_ratio=unclip_ratio,
                        thresh=thresh,
                        box_thresh=box_thresh,
                        limit_side_len=limit_side_len,
                        limit_type=limit_type
                    )
                    logger.info(f"✅ {model_name} loaded successfully (CPU mode, OpenVINO bypassed)")
                else:
                    raise e

            # PaddleX's HPI backend needs the non-PyPI `ultra-infer`, so on most
            # installs the engine above ends up on Paddle's own CPU runner. Run the
            # exported ONNX model on OpenVINO directly instead: same weights and
            # PaddleX pre/post-processing, ~6x faster per page, and higher
            # recognition confidence (see docs/CURRENT_STATE.md).
            if use_openvino:
                _accelerate_with_openvino(_det_engine, model_name)

    return _det_engine


# ═════════════════════════════════════════════════════════════════════════════
class PaddleV5Processor:
    """
    PP-OCRv5 Telugu OCR with seamless Tesseract fallback.

    Usage:
        processor = PaddleV5Processor()
        result = processor.extract_with_fallback(image)
        print(result['text'])    # best available text
        print(result['engine'])  # 'paddle' or 'tesseract'
        print(result['reason'])  # 'ok', 'too_few_lines', 'low_confidence', etc.
    """

    def __init__(self, language: str = 'te', config=None):
        self.config = config or _base_config

        # Normalise language code
        _lang_map = {'tel': 'te', 'eng': 'en', 'tel+eng': 'te',
                     'tel_best': 'te', 'tel_best+eng': 'te'}
        self.language = _lang_map.get(language, language)

        # Check if PP-OCRv5 is enabled in config
        self.paddle_enabled = (
            PADDLEOCR_AVAILABLE and
            getattr(self.config, 'ENABLE_PADDLE_OCR', True)
        )

        if self.paddle_enabled:
            # Pre-warm engines at init time (avoids cold-start on first page)
            self.rec = _get_rec_engine(self.config)
            self.det = _get_det_engine(self.config)
            logger.info("🏏 PaddleV5Processor ready (PP-OCRv5 primary, Tesseract fallback)")
        else:
            self.rec = None
            self.det = None
            logger.info("🔧 PaddleV5Processor: Paddle disabled → Tesseract only")

    # ── Image helpers ──────────────────────────────────────────────────────────

    def _ensure_rgb(self, image: Image.Image) -> Image.Image:
        """Convert PIL Image to RGB, compositing transparent backgrounds onto white."""
        if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
            try:
                bg = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                bg.paste(image, mask=image.split()[-1])
                return bg
            except Exception as e:
                logger.debug(f"Alpha channel composite failed, falling back to convert('RGB'): {e}")
                return image.convert('RGB')
        elif image.mode != 'RGB':
            return image.convert('RGB')
        return image

    def _to_bgr(self, image: Image.Image) -> np.ndarray:
        """Convert PIL Image to BGR numpy array (what PaddleOCR expects)."""
        image = self._ensure_rgb(image)
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        """Cap longest side to prevent OOM. PP-OCRv5 det auto-resizes to 960px internally."""
        max_dim = getattr(self.config, 'PADDLE_MAX_IMAGE_DIM', 1500)
        w, h = image.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"Resized image: ({w},{h}) → {new_size}")
        return image

    def _clarity_metrics(self, image: Image.Image) -> Tuple[float, float]:
        """
        Sharpness (Laplacian variance) and contrast (std dev), measured on a
        copy resized to PADDLE_MAX_IMAGE_DIM rather than the raw source image.

        Laplacian variance is not resolution-invariant: the same visually
        crisp page measures lap_var ~8-12 at a real 400 DPI production render
        (~4400x7000, capped by MAX_RENDER_DIM) but ~1500-2000 once resized to
        the ~1500px longest side the OCR model actually receives -- three
        orders of magnitude apart on the same page. Found 2026-09-26: every
        real page in a live conversion was measuring far below
        PADDLE_SHARPNESS_LOW_LIMIT (1500) and TESSERACT_MIN_SHARPNESS (800)
        regardless of true quality, so every page was getting the maximum
        sharpness boost and every page's is_clear was False. Resizing first
        makes the metric comparable to the resolution the thresholds were
        actually tuned against (see docs/CURRENT_STATE.md).

        NOT the same fix as the one already reverted for _assess_clarity (see
        its call site comment): that measured on a copy already ENHANCED and
        downscaled, which is circular -- it tells you whether the enhancement
        worked, not whether the original needed it. This resizes only, with
        no enhancement applied, purely to put the measurement at a consistent
        scale; the decision it feeds is still applied to the original image.
        """
        max_dim = getattr(self.config, 'PADDLE_MAX_IMAGE_DIM', 1500)
        w, h = image.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        gray = np.array(image.convert('L'))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast = float(gray.std())
        return sharpness, contrast

    def _preprocess(self, image: Image.Image, page_label: Optional[str] = None) -> Image.Image:
        """Dynamic preprocessing — contrast + sharpness boost based on image quality metrics."""
        label_prefix = f"[{page_label}] " if page_label else ""
        try:
            image = self._ensure_rgb(image)

            # ── CLAHE path (adaptive local contrast) ──────────────────────────
            # Alternative to the global boost below. ImageEnhance.Contrast applies
            # ONE multiplier to the whole page; CLAHE instead splits the page into
            # a grid of tiles and equalizes each tile's own local histogram
            # (clipped to avoid amplifying noise in near-blank tiles). This suits
            # unevenly faded/stained old scans much better than a single global
            # setting, since each region gets exactly the correction it needs.
            # Opt-in via config — A/B compare against the global path below
            # before making this the default.
            if getattr(self.config, 'PADDLE_USE_CLAHE', False):
                clip_limit = getattr(self.config, 'PADDLE_CLAHE_CLIP_LIMIT', 2.0)
                tile_size = getattr(self.config, 'PADDLE_CLAHE_TILE_GRID_SIZE', 8)
                gray = np.array(image.convert('L'))
                clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
                enhanced_gray = clahe.apply(gray)
                logger.info(
                    f"{label_prefix}🎨 CLAHE applied (clip_limit={clip_limit}, "
                    f"tile_grid={tile_size}x{tile_size})"
                )
                return Image.fromarray(enhanced_gray).convert('RGB')

            # ── Global path (default) ─────────────────────────────────────────
            # Measured at a fixed reference scale (_clarity_metrics), not on
            # the raw source resolution -- see that method's docstring. The
            # enhancement below is still applied to the full-resolution image.
            lap_var, std_dev = self._clarity_metrics(image)

            # Retrieve threshold parameters from config with safe defaults
            sharpness_low    = getattr(self.config, 'PADDLE_SHARPNESS_LOW_LIMIT', 1500.0)
            sharpness_high   = getattr(self.config, 'PADDLE_SHARPNESS_HIGH_LIMIT', 3000.0)
            max_sharpness    = getattr(self.config, 'PADDLE_MAX_SHARPNESS_BOOST', 2.2)
            min_sharpness    = getattr(self.config, 'PADDLE_MIN_SHARPNESS_BOOST', 1.0)
            
            contrast_low     = getattr(self.config, 'PADDLE_CONTRAST_LOW_LIMIT', 30.0)
            contrast_high    = getattr(self.config, 'PADDLE_CONTRAST_HIGH_LIMIT', 50.0)
            max_contrast     = getattr(self.config, 'PADDLE_MAX_CONTRAST_BOOST', 1.6)
            min_contrast     = getattr(self.config, 'PADDLE_MIN_CONTRAST_BOOST', 1.0)
            
            # --- Calculate Sharpness Factor ---
            if lap_var <= sharpness_low:
                sharpness_factor = max_sharpness
            elif lap_var >= sharpness_high:
                sharpness_factor = min_sharpness
            else:
                ratio = (sharpness_high - lap_var) / (sharpness_high - sharpness_low)
                sharpness_factor = min_sharpness + ratio * (max_sharpness - min_sharpness)
                
            # --- Calculate Contrast Factor ---
            if std_dev <= contrast_low:
                contrast_factor = max_contrast
            elif std_dev >= contrast_high:
                contrast_factor = min_contrast
            else:
                ratio = (contrast_high - std_dev) / (contrast_high - contrast_low)
                contrast_factor = min_contrast + ratio * (max_contrast - min_contrast)
            
            # Log computed metrics and selected enhancement factors.
            # DEBUG: fires on every page — routine measurement, not a decision or
            # problem. Switch config.LOG_LEVEL to DEBUG to see this detail again.
            logger.debug(
                f"{label_prefix}📸 Dynamic Preprocessing: "
                f"Blur (Laplacian Var)={lap_var:.1f} -> Sharpness={sharpness_factor:.2f}x | "
                f"Contrast (Std Dev)={std_dev:.1f} -> Contrast={contrast_factor:.2f}x"
            )
            
            # Apply enhancements
            if contrast_factor != 1.0:
                image = ImageEnhance.Contrast(image).enhance(contrast_factor)
            if sharpness_factor != 1.0:
                image = ImageEnhance.Sharpness(image).enhance(sharpness_factor)
                
        except Exception as e:
            logger.warning(f"Dynamic preprocessing failed, falling back to defaults: {e}")
            try:
                image = ImageEnhance.Contrast(image).enhance(1.2)
                image = ImageEnhance.Sharpness(image).enhance(1.5)
            except Exception as e_fallback:
                logger.error(f"Fallback preprocessing also failed: {e_fallback}")
                
        return image

    # ── PP-OCRv5 inference ────────────────────────────────────────────────────

    def _paddle_extract(self, image: Image.Image) -> Tuple[str, List[Dict]]:
        """
        Run PP-OCRv5 detection + batched recognition.

        Optimisation: all valid crops from the detection step are collected
        first, then passed to rec.predict() in a *single* batched call instead
        of one call per box.  This cuts the Python↔C++ round-trips from N→1
        and gives a 20–40% speed boost on pages with many text boxes.

        Returns: (text: str, boxes: list of dicts with text/confidence/coords)
        """
        img_bgr = self._to_bgr(image)
        h, w = img_bgr.shape[:2]
        conf_thresh  = getattr(self.config, 'PADDLE_CONFIDENCE_THRESH', 0.45)
        rec_batch_sz = getattr(self.config, 'PADDLE_REC_BATCH_SIZE', 8)

        # ── Step 1: Text Detection ───────────────────────────────────────────────
        # CRITICAL: PaddleX models are not thread-safe for concurrent inference.
        # We MUST lock the predictor when calling .predict() to prevent internal tensor corruption.
        with _engine_lock:
            det_results = self.det.predict(input=img_bgr, batch_size=1)
        
        # ── Step 2: Collect ALL valid crops + their metadata ─────────────────
        valid_crops = []   # list of numpy arrays (BGR crops)
        valid_meta  = []   # list of (x1, y1, x2, y2, original_box)

        for det_res in det_results:
            boxes = None
            if isinstance(det_res, dict):
                boxes = det_res.get('dt_polys')
            else:
                boxes = getattr(det_res, 'boxes', None) or getattr(det_res, 'dt_polys', None)
                if boxes is None and hasattr(det_res, 'get'):
                    boxes = det_res.get('dt_polys')
            
            if boxes is None:
                boxes = []
                
            for box in boxes:
                try:
                    pts = np.array(box, dtype=np.float32)
                    x1 = max(0, int(pts[:, 0].min()))
                    y1 = max(0, int(pts[:, 1].min()))
                    x2 = min(w, int(pts[:, 0].max()))
                    y2 = min(h, int(pts[:, 1].max()))
                    if x2 <= x1 or y2 <= y1:
                        continue
                    valid_crops.append(img_bgr[y1:y2, x1:x2])
                    valid_meta.append((x1, y1, x2, y2, box))
                except Exception as e:
                    logger.debug(f"Box coordinate error: {e}")
                    continue

        if not valid_crops:
            return '', []

        # ── Step 2.5: Sort boxes in natural reading order (row-by-row, left-to-right) ──
        try:
            paired = list(zip(valid_crops, valid_meta))
            # Sort by top coordinate (y1) first to process boxes top-to-bottom
            sorted_by_y = sorted(paired, key=lambda x: x[1][1])
            
            lines = []
            for item in sorted_by_y:
                crop, (x1, y1, x2, y2, box) = item
                box_h = y2 - y1
                placed = False
                for line in lines:
                    # Representative bounds of the row
                    line_y1 = min(b[1][1] for b in line)
                    line_y2 = max(b[1][3] for b in line)
                    line_h = line_y2 - line_y1
                    
                    # Calculate vertical overlap
                    overlap = max(0, min(y2, line_y2) - max(y1, line_y1))
                    min_h = min(box_h, line_h)
                    
                    # If vertical overlap is > 50% of the smaller height, they are on the same row
                    if min_h > 0 and (overlap / min_h) > 0.5:
                        line.append(item)
                        placed = True
                        break
                if not placed:
                    lines.append([item])
            
            # Sort each row from left to right (by x1)
            sorted_lines = []
            for line in lines:
                sorted_line = sorted(line, key=lambda x: x[1][0])
                sorted_lines.append(sorted_line)
                
            # Sort the lines themselves by their average y1 coordinate
            sorted_lines = sorted(sorted_lines, key=lambda line: sum(b[1][1] for b in line) / len(line))
            
            # Flatten back to a single list of crops and metadata
            flattened = []
            for line in sorted_lines:
                flattened.extend(line)
                
            valid_crops, valid_meta = zip(*flattened)
            valid_crops = list(valid_crops)
            valid_meta = list(valid_meta)
            paired = list(zip(valid_crops, valid_meta))
        except Exception as e:
            logger.warning(f"Error sorting boxes in reading order: {e}")
            paired = list(zip(valid_crops, valid_meta))


        # ── Step 3: Run Batched Recognition ──────────────────────────────────────
        boxes_data = []
        text_lines = []
        # Parallel to boxes_data (1:1, same indices) -- the source crop each
        # entry came from, kept only so an optional re-vote pass (Step 4) can
        # re-read the same region at a different scale without re-running
        # detection. Not populated for entries dropped below conf_thresh.
        revote_crops = []

        try:
            # We MUST lock the predictor when calling .predict()
            with _engine_lock:
                rec_results = list(self.rec.predict(input=valid_crops, batch_size=rec_batch_sz))

            for (crop, (x1, y1, x2, y2, box)), rec_res in zip(paired, rec_results):
                try:
                    text  = (getattr(rec_res, 'rec_text', None)
                             or (rec_res.get('rec_text', '') if isinstance(rec_res, dict) else ''))
                    score = float(getattr(rec_res, 'rec_score', 0.0)
                                  or (rec_res.get('rec_score', 0.0) if isinstance(rec_res, dict) else 0.0))
                    if text and score >= conf_thresh:
                        text_lines.append(text.strip())
                        boxes_data.append({
                            'text':       text.strip(),
                            'confidence': score,
                            'left':   x1, 'top':    y1,
                            'width':  x2 - x1, 'height': y2 - y1,
                            'box':    box,
                        })
                        revote_crops.append(crop)
                except Exception as e:
                    logger.debug(f"Rec result parse error: {e}")
                    continue

        except Exception as e:
            # If batched call fails (e.g. API doesn't support list input),
            # fall back gracefully to per-crop calls.
            logger.debug(f"Batched rec failed ({e}), falling back to per-crop mode")
            for crop, (x1, y1, x2, y2, box) in zip(valid_crops, valid_meta):
                try:
                    with _engine_lock:
                        per_crop_res = list(self.rec.predict(input=crop, batch_size=1))

                    for rec_res in per_crop_res:
                        text  = (getattr(rec_res, 'rec_text', None)
                                 or (rec_res.get('rec_text', '') if isinstance(rec_res, dict) else ''))
                        score = float(getattr(rec_res, 'rec_score', 0.0)
                                      or (rec_res.get('rec_score', 0.0) if isinstance(rec_res, dict) else 0.0))
                        if text and score >= conf_thresh:
                            text_lines.append(text.strip())
                            boxes_data.append({
                                'text':       text.strip(),
                                'confidence': score,
                                'left':   x1, 'top':    y1,
                                'width':  x2 - x1, 'height': y2 - y1,
                                'box':    box,
                            })
                            revote_crops.append(crop)
                except Exception as e2:
                    logger.debug(f"Per-crop rec error: {e2}")
                    continue

        # ── Step 4: Confidence-band re-vote (optional, default off) ──────────
        # A genuinely low-confidence box already fails PADDLE_CONFIDENCE_THRESH
        # above and gets dropped (page falls through to the Tesseract quality
        # gate); a high-confidence box is usually right. The gap between them
        # is where a wrong-but-plausible single-letter misread is most likely
        # to hide -- confident enough to pass, not confident enough to trust.
        # Nothing else in the pipeline targets this band: grapheme-validity and
        # dictionary correction only catch structurally-broken or out-of-
        # dictionary text, not a wrong letter that happens to form a
        # plausible-looking word. Re-reads just those crops upscaled (more
        # stroke detail for the fixed-height rec model) and keeps whichever
        # read scored higher.
        if getattr(self.config, 'ENABLE_PADDLE_CONFIDENCE_REVOTE', False) and boxes_data:
            boxes_data = self._confidence_band_revote(boxes_data, revote_crops)
            text_lines = [b['text'] for b in boxes_data]

        if getattr(self.config, 'PADDLE_ENABLE_GC', True):
            gc.collect()

        return '\n'.join(text_lines), boxes_data

    def _confidence_band_revote(self, boxes_data: List[Dict],
                                 crops: List[np.ndarray]) -> List[Dict]:
        """
        Re-run recognition on crops whose confidence landed in an ambiguous
        middle band (PADDLE_REVOTE_CONF_LOW <= score < PADDLE_REVOTE_CONF_HIGH),
        against an upscaled variant of the same crop, and keep whichever read
        scored higher. See the call site in _paddle_extract for why this band
        specifically. `crops` must be 1:1 with `boxes_data` (same order/length)
        -- the caller guarantees this by only appending to both together.
        """
        conf_low  = getattr(self.config, 'PADDLE_REVOTE_CONF_LOW', 0.45)
        conf_high = getattr(self.config, 'PADDLE_REVOTE_CONF_HIGH', 0.70)
        scale     = getattr(self.config, 'PADDLE_REVOTE_UPSCALE', 1.6)
        batch_sz  = getattr(self.config, 'PADDLE_REC_BATCH_SIZE', 4)

        revote_idx = [i for i, b in enumerate(boxes_data)
                      if conf_low <= b['confidence'] < conf_high]
        if not revote_idx:
            return boxes_data

        alt_crops = []
        for i in revote_idx:
            crop = crops[i]
            h, w = crop.shape[:2]
            if h <= 0 or w <= 0:
                alt_crops.append(crop)
                continue
            alt_crops.append(cv2.resize(crop, (max(1, int(w * scale)), max(1, int(h * scale))),
                                         interpolation=cv2.INTER_CUBIC))

        try:
            with _engine_lock:
                alt_results = list(self.rec.predict(input=alt_crops, batch_size=batch_sz))
        except Exception as e:
            logger.debug(f"Confidence-band re-vote failed ({e}), keeping original reads")
            return boxes_data

        flipped = 0
        for i, alt_res in zip(revote_idx, alt_results):
            try:
                alt_text  = (getattr(alt_res, 'rec_text', None)
                             or (alt_res.get('rec_text', '') if isinstance(alt_res, dict) else ''))
                alt_score = float(getattr(alt_res, 'rec_score', 0.0)
                                  or (alt_res.get('rec_score', 0.0) if isinstance(alt_res, dict) else 0.0))
            except Exception as e:
                logger.debug(f"Re-vote result parse error: {e}")
                continue
            if alt_text and alt_score > boxes_data[i]['confidence']:
                if alt_text.strip() != boxes_data[i]['text']:
                    flipped += 1
                boxes_data[i]['text'] = alt_text.strip()
                boxes_data[i]['confidence'] = alt_score

        logger.debug(f"Confidence-band re-vote: {len(revote_idx)} candidate box(es) in "
                     f"[{conf_low},{conf_high}), {flipped} flipped to a different reading")
        return boxes_data

    # ── Quality gate ──────────────────────────────────────────────────────────

    def _quality_gate(self, text: str, image: Image.Image,
                      boxes: List[Dict]) -> Tuple[bool, str]:
        """
        Check if PP-OCRv5 output meets quality standards.
        Returns: (passed: bool, reason: str)

        Failure reasons:
          'too_few_lines'   — detected < 50% of expected lines
          'low_confidence'  — avg confidence < threshold
          'no_telugu_chars' — no Telugu Unicode found in output
        """
        # Calculate average confidence first to support potential bypasses
        avg_conf = 0.0
        if boxes:
            avg_conf = sum(b['confidence'] for b in boxes) / len(boxes)
        high_conf_bypass = getattr(self.config, 'PADDLE_HIGH_CONF_BYPASS', 0.80)

        # ── Check 1: Line count ──
        img_h = image.size[1]  # height in pixels
        expected_lines = max(1, img_h // 40)   # ~40px per Telugu line at 400 DPI
        actual_lines   = len([l for l in text.splitlines() if l.strip()])
        min_ratio      = getattr(self.config, 'PADDLE_MIN_LINE_RATIO', 0.50)

        if actual_lines < expected_lines * min_ratio:
            # Bypass if confidence is exceptionally high (e.g. >= 0.80)
            if avg_conf < high_conf_bypass:
                return False, f"too_few_lines (got {actual_lines}, expected ≥{int(expected_lines * min_ratio)})"

        # ── Check 2: Average confidence ──
        if boxes:
            conf_thresh = getattr(self.config, 'PADDLE_CONFIDENCE_THRESH', 0.45)
            if avg_conf < conf_thresh:
                return False, f"low_confidence ({avg_conf:.2f} < {conf_thresh})"

        # ── Check 3: Telugu character presence ──
        if getattr(self.config, 'PADDLE_REQUIRE_TELUGU_CHARS', True):
            if len(text) > 20:
                has_telugu = any('\u0C00' <= c <= '\u0C7F' for c in text)
                if not has_telugu:
                    return False, "no_telugu_chars (output looks like ASCII garbage)"

        # ── Check 4: Mixed English/Telugu words (character corruption check) ──
        # Isolated/mixed English letters embedded in Telugu words indicate recognition failure.
        words = re.findall(r'[a-zA-Z\u0C00-\u0C7F]+', text)
        mixed_count = 0
        for word in words:
            has_telugu = any('\u0C00' <= c <= '\u0C7F' for c in word)
            has_english = any('a' <= c.lower() <= 'z' for c in word)
            if has_telugu and has_english:
                mixed_count += 1

        max_mixed_allowed = getattr(self.config, 'PADDLE_MAX_MIXED_WORDS', 3)
        max_mixed_ratio = getattr(self.config, 'PADDLE_MAX_MIXED_RATIO', 0.02)

        total_words = len(words)
        mixed_ratio = mixed_count / total_words if total_words > 0 else 0.0

        if mixed_count > max_mixed_allowed and mixed_ratio > max_mixed_ratio:
            return False, f"mixed_word_contamination (got {mixed_count} mixed words, ratio={mixed_ratio:.2%})"

        return True, "ok"

    # ── Tesseract fallback ────────────────────────────────────────────────────

    def _tesseract_extract(self, image: Image.Image, psm: Optional[int] = None, page_label: Optional[str] = None) -> str:
        """Run Tesseract using the existing OCRProcessor (all config inherited)."""
        try:
            from ocr_processor import OCRProcessor
            lang       = getattr(self.config, 'DEFAULT_OCR_LANGUAGE', 'tel_best+eng')
            config_str = getattr(self.config, 'TESSERACT_CONFIG', '--oem 1 --psm 4')
            if psm is not None:
                config_str = f'--oem 1 --psm {psm}'
            tess       = OCRProcessor(language=lang, config_str=config_str)
            return tess.extract_text(image, page_label=page_label)
        except Exception as e:
            logger.error(f"Tesseract fallback failed: {e}")
            return ""

    # ── Clarity & Sequence Merging Helpers ────────────────────────────────────

    def _assess_clarity(self, image: Image.Image) -> Tuple[float, float, bool]:
        """
        Assess the clarity (sharpness and contrast) of the page image.
        Returns: (sharpness, contrast, is_clear)

        Metrics come from _clarity_metrics (resized to a fixed reference
        scale before measuring) -- see its docstring. Not the same as the
        "already-enhanced-and-downscaled copy" this call site's own comment
        warns against; no enhancement is applied here, only a resize.
        """
        try:
            sharpness, contrast = self._clarity_metrics(image)

            tess_min_sharpness = getattr(self.config, 'TESSERACT_MIN_SHARPNESS', 800)
            tess_min_contrast = getattr(self.config, 'TESSERACT_MIN_CONTRAST', 45)
            
            is_clear = (sharpness >= tess_min_sharpness) and (contrast >= tess_min_contrast)
            return sharpness, contrast, is_clear
        except Exception as e:
            logger.warning(f"Clarity assessment failed: {e}")
            return 0.0, 0.0, False

    def _is_word_contaminated(self, word: str) -> bool:
        """Check if a word contains both Telugu and English characters."""
        has_telugu = any('\u0C00' <= c <= '\u0C7F' for c in word)
        has_english = any('a' <= c.lower() <= 'z' for c in word)
        return has_telugu and has_english

    def _merge_mismatch_blocks(self, tess_block: List[str], paddle_block: List[str]) -> List[str]:
        """Greedily align and merge mismatching word blocks using character-level similarity."""
        import difflib
        
        def word_similarity(w1: str, w2: str) -> float:
            return difflib.SequenceMatcher(None, list(w1), list(w2)).ratio()
            
        tess_matched = [False] * len(tess_block)
        paddle_matched = [False] * len(paddle_block)
        
        pairs = []
        for i, tw in enumerate(tess_block):
            best_j = -1
            best_sim = 0.4  # similarity threshold to consider matching
            for j, pw in enumerate(paddle_block):
                if not paddle_matched[j]:
                    sim = word_similarity(tw, pw)
                    if sim > best_sim:
                        best_sim = sim
                        best_j = j
            if best_j != -1:
                tess_matched[i] = True
                paddle_matched[best_j] = True
                pairs.append((i, best_j))
                
        merged = []
        for j, pw in enumerate(paddle_block):
            matched_i = -1
            for pi, pj in pairs:
                if pj == j:
                    matched_i = pi
                    break
            if matched_i != -1:
                tw = tess_block[matched_i]
                tw_con = self._is_word_contaminated(tw)
                pw_con = self._is_word_contaminated(pw)
                
                if pw_con and not tw_con:
                    merged.append(tw)
                elif tw_con and not pw_con:
                    merged.append(pw)
                else:
                    merged.append(tw)
            else:
                if not self._is_word_contaminated(pw):
                    merged.append(pw)
                    
        for i, tw in enumerate(tess_block):
            if not tess_matched[i]:
                if not self._is_word_contaminated(tw):
                    merged.append(tw)
                    
        return merged

    def _merge_ocr_texts(self, tess_text: str, paddle_text: str) -> str:
        """
        Align Tesseract and PaddleOCR word sequences and select clean tokens.
        Preserves clean Telugu spelling from Tesseract, falling back to PaddleOCR
        for layout representation where Tesseract missed lines or words.
        """
        import difflib
        
        tess_words = tess_text.split()
        paddle_words = paddle_text.split()
        
        matcher = difflib.SequenceMatcher(None, tess_words, paddle_words)
        merged_words = []
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                merged_words.extend(tess_words[i1:i2])
            elif tag == 'replace':
                tess_block = tess_words[i1:i2]
                paddle_block = paddle_words[j1:j2]
                
                if len(tess_block) == len(paddle_block):
                    for tw, pw in zip(tess_block, paddle_block):
                        tw_con = self._is_word_contaminated(tw)
                        pw_con = self._is_word_contaminated(pw)
                        
                        if pw_con and not tw_con:
                            merged_words.append(tw)
                        elif tw_con and not pw_con:
                            merged_words.append(pw)
                        else:
                            merged_words.append(tw)
                else:
                    # Use refined mismatch block merge!
                    merged_words.extend(self._merge_mismatch_blocks(tess_block, paddle_block))
            elif tag == 'delete':
                for tw in tess_words[i1:i2]:
                    if not self._is_word_contaminated(tw):
                        merged_words.append(tw)
            elif tag == 'insert':
                for pw in paddle_words[j1:j2]:
                    if not self._is_word_contaminated(pw):
                        merged_words.append(pw)
                        
        return " ".join(merged_words)

    # ── Main public API ───────────────────────────────────────────────────────

    def extract_with_fallback(self, image: Image.Image,
                              preprocess: bool = False,
                              psm: Optional[int] = None,
                              page_label: Optional[str] = None,
                              *args, **kwargs) -> Dict:
        """
        PRIMARY METHOD — Route based on clarity, fallback, and comparative merge.
        """
        global _soft_fail_count, _hard_crash_count, _paddle_logged_errors

        label_prefix = f"[{page_label}] " if page_label else ""

        # Step 1: Assess image clarity — on the original (unenhanced) scan, but
        # _assess_clarity itself now measures at a fixed reference scale
        # (_clarity_metrics resizes a working copy to PADDLE_MAX_IMAGE_DIM
        # before computing Laplacian variance), not at the source's raw
        # resolution. Still not an already-enhanced-and-downscaled copy (the
        # previous, reverted order) -- that was circular, telling you whether
        # the enhancement worked rather than whether the original needed it.
        # Found 2026-09-26: raw-resolution Laplacian variance is not scale-
        # invariant enough to compare against a fixed threshold across pages
        # of different source resolutions (see docs/CURRENT_STATE.md and
        # _clarity_metrics's docstring) -- every real page in a live 400 DPI
        # conversion was measuring far below TESSERACT_MIN_SHARPNESS on the
        # raw scan regardless of true quality.
        sharpness, contrast, is_clear = self._assess_clarity(image)
        # DEBUG: fires on every page — routine measurement, not a decision or
        # problem. Switch config.LOG_LEVEL to DEBUG to see this detail again.
        logger.debug(
            f"{label_prefix}🔍 Clarity metrics: sharpness={sharpness:.1f}, "
            f"contrast={contrast:.1f} | is_clear={is_clear}"
        )

        if preprocess:
            image = self._preprocess(image, page_label=page_label)
        image = self._resize_if_needed(image)

        enable_merge = getattr(self.config, 'ENABLE_COMPARATIVE_MERGE', True)

        # Expected lines for quality gate
        img_h = image.size[1]
        expected_lines = max(1, img_h // 40)
        min_ratio = getattr(self.config, 'PADDLE_MIN_LINE_RATIO', 0.50)
        min_expected_lines = int(expected_lines * min_ratio)

        # Check if we should run Tesseract first on clear pages
        tess_first_on_clear = getattr(self.config, 'TESSERACT_FIRST_ON_CLEAR', True)

        # ── FLOW A: TESSERACT FIRST (Clear Page) ──────────────────────────────
        if is_clear and tess_first_on_clear:
            logger.info(f"{label_prefix}⚡ Page is clear. Running TESSERACT first.")
            tess_text = ""
            tess_lines = 0
            tess_failed = True
            
            try:
                tess_text = self._tesseract_extract(image, psm=psm, page_label=page_label)
                tess_lines = len([l for l in tess_text.splitlines() if l.strip()])
                
                # Verify Tesseract line count
                has_enough_lines = tess_lines >= min_expected_lines
                # Verify Telugu presence (if length > 20)
                has_telugu = True
                if len(tess_text) > 20:
                    has_telugu = any('\u0C00' <= c <= '\u0C7F' for c in tess_text)
                
                tess_failed = not (has_enough_lines and has_telugu)
            except Exception as e:
                logger.warning(f"{label_prefix}Tesseract primary extraction failed: {e}")
                tess_failed = True

            # If Tesseract is solid, return it directly
            if not tess_failed:
                logger.info(f"{label_prefix}🔧 Tesseract Preferred Choice ✅ | lines={tess_lines}")
                return {
                    'text':       tess_text,
                    'engine':     'tesseract',
                    'reason':     'tess_preferred_passed',
                    'confidence': 0.0,
                    'boxes':      [],
                }

            logger.warning(
                f"{label_prefix}⚠️ Tesseract preferred run underperformed (lines={tess_lines}, "
                f"expected={min_expected_lines}). Falling back/escalating to PP-OCRv5."
            )

            # Escalate to PaddleOCR
            paddle_text = ""
            boxes = []
            paddle_passed = False
            paddle_reason = 'unknown'
            
            if self.paddle_enabled:
                try:
                    paddle_text, boxes = self._paddle_extract(image)
                    paddle_passed, paddle_reason = self._quality_gate(paddle_text, image, boxes)
                except Exception as e:
                    paddle_reason = f"crash: {str(e).splitlines()[0]}"
                    paddle_passed = False

            if paddle_passed:
                # Paddle succeeded, Tesseract underperformed. Let's merge them!
                if enable_merge and tess_text.strip():
                    logger.info(f"{label_prefix}🧬 Running comparative merge (Tesseract spellings + PaddleOCR lines).")
                    merged_text = self._merge_ocr_texts(tess_text, paddle_text)
                    return {
                        'text':       merged_text,
                        'engine':     'merged',
                        'reason':     f'tess_failed_merged_with_paddle_{paddle_reason}',
                        'confidence': (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0),
                        'boxes':      boxes,
                    }
                else:
                    return {
                        'text':       paddle_text,
                        'engine':     'paddle',
                        'reason':     f'tess_failed_paddle_passed_{paddle_reason}',
                        'confidence': (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0),
                        'boxes':      boxes,
                    }
            else:
                # Both failed, return the one with more lines/better text
                paddle_lines = len([l for l in paddle_text.splitlines() if l.strip()])
                if paddle_lines >= tess_lines and paddle_lines > 0:
                    return {
                        'text':       paddle_text,
                        'engine':     'paddle',
                        'reason':     f'both_underperformed_using_paddle_{paddle_reason}',
                        'confidence': (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0),
                        'boxes':      boxes,
                    }
                else:
                    return {
                        'text':       tess_text,
                        'engine':     'tesseract',
                        'reason':     f'both_underperformed_using_tess_{paddle_reason}',
                        'confidence': 0.0,
                        'boxes':      [],
                    }

        # ── FLOW B: PADDLEOCR FIRST (Standard/Blurry/Skewed Page) ──────────────
        else:
            reason_msg = "forcing Paddle first" if is_clear else "page is blurry/complex"
            logger.info(f"{label_prefix}🏏 Running PP-OCRv5 first ({reason_msg}).")
            paddle_text = ""
            boxes = []
            paddle_passed = False
            paddle_reason = 'paddle_disabled'
            
            if self.paddle_enabled:
                try:
                    paddle_text, boxes = self._paddle_extract(image)
                    paddle_passed, paddle_reason = self._quality_gate(paddle_text, image, boxes)
                    
                    if paddle_passed:
                        avg_conf = (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0)
                        logger.info(f"{label_prefix}🏏 PP-OCRv5 ✅ | lines={len(paddle_text.splitlines())} | conf={avg_conf:.2f}")
                        return {
                            'text':       paddle_text,
                            'engine':     'paddle',
                            'reason':     paddle_reason,
                            'confidence': avg_conf,
                            'boxes':      boxes,
                        }
                    
                    with _crash_lock:
                        _soft_fail_count += 1
                    logger.warning(f"{label_prefix}⚠️ PP-OCRv5 soft-fail [{paddle_reason}] → running Tesseract fallback.")
                except Exception as e:
                    first_line = str(e).splitlines()[0].strip()[:120]
                    paddle_reason = f"crash: {first_line}"
                    with _crash_lock:
                        _hard_crash_count += 1
                    logger.warning(f"{label_prefix}⚠️ PP-OCRv5 crash [{first_line}] → running Tesseract fallback.")

            # Run Tesseract fallback
            try:
                tess_text = self._tesseract_extract(image, psm=psm, page_label=page_label)
                tess_lines = len([l for l in tess_text.splitlines() if l.strip()])
                
                # Check if we should merge or use Tesseract directly
                if paddle_text.strip():
                    # We have both outputs! Run comparative merge.
                    if enable_merge and "no_telugu_chars" not in paddle_reason:
                        logger.info(f"{label_prefix}🧬 Running comparative merge (PaddleOCR structure + Tesseract spelling).")
                        merged_text = self._merge_ocr_texts(tess_text, paddle_text)
                        return {
                            'text':       merged_text,
                            'engine':     'merged',
                            'reason':     f'paddle_failed_merged_with_tess_{paddle_reason}',
                            'confidence': (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0),
                            'boxes':      boxes,
                        }
                    
                    # Precedence-based fallback logic (reclaim Paddle if Tesseract is worse)
                    paddle_lines = len([l for l in paddle_text.splitlines() if l.strip()])
                    if paddle_lines >= tess_lines and paddle_lines > 0 and "no_telugu_chars" not in paddle_reason and "mixed_word_contamination" not in paddle_reason:
                        logger.info(f"{label_prefix}🔄 Reclaiming PaddleOCR output (lines: {paddle_lines} >= Tesseract: {tess_lines})")
                        return {
                            'text':       paddle_text,
                            'engine':     'paddle',
                            'reason':     f'reclaimed_{paddle_reason}',
                            'confidence': (sum(b['confidence'] for b in boxes) / len(boxes) if boxes else 0.0),
                            'boxes':      boxes,
                        }

                logger.info(f"{label_prefix}🔧 Tesseract fallback ✅ | lines={tess_lines}")
                return {
                    'text':       tess_text,
                    'engine':     'tesseract',
                    'reason':     paddle_reason,
                    'confidence': 0.0,
                    'boxes':      [],
                }
            except Exception as e:
                logger.error(f"{label_prefix}❌ Both engines failed: {e}")
                return {
                    'text':       paddle_text if paddle_text.strip() else '',
                    'engine':     'none',
                    'reason':     f'both_failed: paddle={paddle_reason}, tess={e}',
                    'confidence': 0.0,
                    'boxes':      [],
                }

    def extract_text(self, image: Image.Image, preprocess: bool = False, *args, **kwargs) -> str:
        """Convenience wrapper — returns just the text string."""
        return self.extract_with_fallback(image, preprocess=preprocess, *args, **kwargs)['text']

    def extract_text_with_boxes(self, image: Image.Image,
                                preprocess: bool = False, *args, **kwargs) -> List[Dict]:
        """Returns bounding box data. Falls back to empty list if Tesseract used."""
        result = self.extract_with_fallback(image, preprocess=preprocess, *args, **kwargs)
        return result.get('boxes', [])

    def get_confidence_score(self, image: Image.Image, *args, **kwargs) -> float:
        """Average confidence score. Returns 0.0 on Tesseract fallback."""
        result = self.extract_with_fallback(image, *args, **kwargs)
        return result.get('confidence', 0.0)

    def extract_paddle_only(self, image: Image.Image, preprocess: bool = True,
                             page_label: Optional[str] = None) -> str:
        """
        Raw PP-OCRv5 text with none of extract_with_fallback's Tesseract-first
        routing or comparative merge — for side-by-side engine comparison
        (e.g. logging what PaddleOCR alone produced on a page Gemini rescued),
        not for production text selection.
        """
        if not self.paddle_enabled:
            return ""
        try:
            if preprocess:
                image = self._preprocess(image, page_label=page_label)
            image = self._resize_if_needed(image)
            text, _boxes = self._paddle_extract(image)
            return text
        except Exception as e:
            logger.debug(f"[{page_label}] extract_paddle_only failed: {e}")
            return ""

    def process_image_file(self, image_path: Path,
                           preprocess: bool = True, *args, **kwargs) -> str:
        """Process an image file path."""
        try:
            return self.extract_text(Image.open(image_path), preprocess=preprocess, *args, **kwargs)
        except Exception as e:
            logger.error(f"process_image_file failed for {image_path}: {e}")
            return ""

    def detect_orientation(self, image: Image.Image, *args, **kwargs) -> Dict:
        return {'angle': 0, 'confidence': 1.0,
                'note': 'PP-OCRv5 handles orientation internally'}

    def auto_rotate(self, image: Image.Image, *args, **kwargs) -> Image.Image:
        return image

    def get_available_languages(self, *args, **kwargs) -> List[str]:
        return ['te', 'en', 'hi', 'ta', 'kn', 'ml']

    def verify_telugu_support(self, *args, **kwargs) -> bool:
        return True


# ── Backwards-compatibility alias ─────────────────────────────────────────────
# ocr_factory.py calls PaddleOCRProcessor — keep the old name working
PaddleOCRProcessor = PaddleV5Processor


# ── Smoke test ────────────────────────────────────────────────────────────────
def test_paddle_v5():
    """Quick smoke test — run directly: python paddle_v5_processor.py"""
    print("=" * 55)
    print("PP-OCRv5 Telugu Processor — Smoke Test")
    print("=" * 55)

    if not PADDLEOCR_AVAILABLE:
        print("❌ paddleocr not installed")
        print("   Run: pip install paddleocr paddlepaddle")
        return

    print("✅ paddleocr import OK")
    print("   Initialising PP-OCRv5 processor...")

    try:
        proc = PaddleV5Processor(language='te')
        print(f"✅ Processor initialised | paddle_enabled={proc.paddle_enabled}")
        print(f"   rec model: {getattr(_base_config, 'PADDLE_REC_MODEL', 'te_PP-OCRv5_mobile_rec')}")
        print(f"   det model: {getattr(_base_config, 'PADDLE_DET_MODEL', 'PP-OCRv5_server_det')}")

        # Test with blank white image (should return empty with fallback to Tesseract)
        blank = Image.new('RGB', (600, 100), color=(255, 255, 255))
        result = proc.extract_with_fallback(blank)
        print(f"\n📋 Test result on blank image:")
        print(f"   engine : {result['engine']}")
        print(f"   reason : {result['reason']}")
        print(f"   text   : '{result['text'] or '(empty — expected for blank image)'}'")
        print("\n✅ Smoke test complete — fallback pipeline working correctly")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_paddle_v5()
