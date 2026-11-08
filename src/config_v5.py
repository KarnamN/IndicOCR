"""
config_v5.py — PP-OCRv5 Configuration Override
================================================
Inherits ALL settings from config.py (Flask, paths, Gemini, Tesseract, epub, etc.)
and overrides ONLY the OCR engine layer to use PP-OCRv5 as primary engine
with automatic seamless fallback to Tesseract.

HOW TO USE:
-----------
In app.py or any entry point, change the config import:
  - Tesseract-primary mode (current):  import config as config
  - PP-OCRv5-primary mode (new):       import config_v5 as config

EMERGENCY ROLLBACK:
-------------------
If PP-OCRv5 causes any issue, set:
  ENABLE_PADDLE_OCR = False
The entire pipeline instantly reverts to Tesseract + Gemini rescue.
No code change needed — just flip this one flag.
"""

# ── Inherit everything from base config ───────────────────────────────────────
from config import *   # noqa: F401, F403
# All of these are inherited unchanged:
#   TESSERACT_PATH, TESSERACT_CONFIG, OCR_CONFIG, DEFAULT_OCR_LANGUAGE
#   GEMINI_*, GOOGLE_VISION_*, EPUB_*, OUTPUT_FOLDER, MAX_WORKERS, etc.

# ═══════════════════════════════════════════════════════════════════════════════
#  PP-OCRv5 ENGINE — PRIMARY OCR
# ═══════════════════════════════════════════════════════════════════════════════

# Master switch — set False to instantly revert to Tesseract-only mode
ENABLE_PADDLE_OCR = True

# PP-OCRv5 model names (resolved from ~/.paddlex/official_models/ automatically)
PADDLE_REC_MODEL  = 'te_PP-OCRv5_mobile_rec'   # 7.5 MB — Telugu recognition
PADDLE_DET_MODEL  = 'PP-OCRv5_server_det'       # 84 MB — text detection (server; now compiled via OpenVINO to bypass native PIR crash)
# NOTE: Native 'PP-OCRv5_server_det' causes a crash in PaddlePaddle's executor:
#   "(Unimplemented) ConvertPirAttribute2RuntimeAttribute not support pir::ArrayAttribute<pir::DoubleAttribute>"
# We use OpenVINO backend to compile and run this model, bypassing this native Paddle runtime issue.

# Hardware & Engine Acceleration
PADDLE_USE_GPU      = False   # CPU-only (no CUDA required)
PADDLE_USE_OPENVINO = True    # Enable Intel OpenVINO CPU acceleration (bypassed for det in processor to prevent PIR crashes)

# Memory guard — resize longest side before passing to Paddle
PADDLE_MAX_IMAGE_DIM = 1500   # pixels; PP-OCRv5 det resizes internally to 960 anyway

# Batched recognition — how many crops to send to rec.predict() in one call.
# Higher = faster on pages with many text boxes; lower = less peak RAM.
# 4 is a safe default for CPU. It fits better in the L2/L3 cache bounds.
PADDLE_REC_BATCH_SIZE = 4

# ═══════════════════════════════════════════════════════════════════════════════
#  FUSION OCR — PP-OCRv5 + IndicPhotoOCR + Tesseract, EXPERIMENTAL, OFF BY DEFAULT
# ═══════════════════════════════════════════════════════════════════════════════
# Built and validated as standalone diagnostics (tests/diagnostics/fuse_ocr_engines.py,
# build_review_queue.py) across ~18 real pages, not yet run through a full book
# conversion or scored against verified ground truth — see docs/CURRENT_STATE.md,
# "Configuration-Driven OCR Engine Selection", before enabling this for real work.
#
# To activate: set ENABLE_FUSION_OCR = True AND OCR_ENGINE = 'fusion' (this file
# already sets OCR_ENGINE below, in the QUALITY GATE section). OCR_ENGINE = 'fusion'
# forces EVERY page to this path, the same way OCR_ENGINE = 'paddle' or 'tesseract'
# would bypass AdaptiveOCRFactory's complexity-tier routing entirely — there is no
# per-page tier that routes to fusion selectively yet. Leaving ENABLE_FUSION_OCR
# True with OCR_ENGINE left at 'hybrid' does nothing; pages still route to 'paddle'
# via the normal complexity tiers.
ENABLE_FUSION_OCR = True

# Skip the slow IndicPhotoOCR pass on pages PP-OCRv5+Tesseract already look easy on
# (src/engine_router.py). Thresholds were read off one book's data by eye — see that
# module's docstring for the measured trade-off before trusting it on a different book.
FUSION_ADAPTIVE_ROUTER = True

# 'hinted' (default): IndicPhotoOCR's slow script-identifier only runs on crops PP-OCRv5
# already flagged as containing Latin letters. Known gap (docs/CURRENT_STATE.md): misses
# English PP-OCRv5 already misread as Telugu-shaped garbage. 'vit' checks every crop
# (slower, its own false-positive problem on Telugu-only pages). 'none' never checks.
FUSION_IDENTIFIER_MODE = 'hinted'

# Drops IndicPhotoOCR word candidates below this recognition confidence before they
# reach fusion. Found 2026-09-25: on a real book page, its recognizer collapses on
# ambiguous/junk crops instead of abstaining -- one page had the same 4-5-char string
# ('అడుగ') recognized 68 separate times (14% of all 482 word-crops on that page),
# every occurrence clustered at confidence 0.22-0.36, alongside several other strings
# with the identical pattern (repeated dozens of times, all in that same low band).
# Plausible real recurring words on the same page sat higher (0.42-0.59). Default 0.0
# (IndicPhotoOCRProcessor's own default) never filtered anything. 0.35 is a first-pass
# threshold read off that one page's separation, not calibrated against ground truth --
# revisit once score_ocr_accuracy.py has real corrections to check it against.
FUSION_INDIC_MIN_CONFIDENCE = 0.35

# ═══════════════════════════════════════════════════════════════════════════════
#  PADDLE DETECTOR OVERRIDES
# ═══════════════════════════════════════════════════════════════════════════════
# Increase unclip_ratio to expand detected bounding boxes slightly.
# This prevents Telugu guninthalu (vowels at top) and vathulu (consonants at bottom)
# from being cut off during crop segmentation, significantly improving recognition.
PADDLE_DET_UNCLIP_RATIO = 2.0  # default in PaddleOCR is 1.5
PADDLE_DET_THRESH       = 0.3  # default in PaddleOCR is 0.3
PADDLE_DET_BOX_THRESH   = 0.6  # default in PaddleOCR is 0.6

if IS_LINUX:
    if WSL_MODE:
        # REVISED (2026-07-04): earlier this session MAX_WORKERS was lowered to 2
        # because almost every page routes to PaddleOCR as primary and every
        # Paddle det/rec call is serialized process-wide by _engine_lock — only
        # one page's inference can actually run at a time regardless of worker
        # count (live evidence: 6 pages queued behind the lock within a 30s
        # window, one logged 56.8s "duration" of which ~44s was queue wait, not
        # compute). That's still true, but the fix now lives at the OCR-call
        # granularity (STAGE2_WORKERS below), not at this outer pool's size —
        # this pool's size also bounds Stage-1 (analysis+enhancement) concurrency,
        # which is NOT lock-bound and has ample measured RAM headroom (see
        # STAGE1_MEMORY_FLOOR_GB / process_page_optimized's memory pre-flight
        # check). Raised back up so Stage 1 can actually use that headroom;
        # STAGE2_WORKERS is the new, separate sub-throttle for the OCR portion.
        MAX_WORKERS = 6
        # Sub-throttle applied only around the OCR portion of each page (inside
        # process_page_optimized) — keeps concurrent Paddle-lock contention low
        # even though MAX_WORKERS (Stage-1 concurrency) is higher.
        # Raised from 2 to 4, 2026-09-25: with fusion mode live, IndicPhotoOCR also
        # got its own internal lock (indicphoto_ocr_processor._INDIC_LOCK, added this
        # session) -- both heavy engines already serialize their own model calls
        # independently of this semaphore. Confirmed live: pages where the page-level
        # router SKIPPED IndicPhotoOCR entirely (pure PaddleOCR+Tesseract, a few
        # seconds of real work) still reported 44-65s "Completed in", because they
        # were blocked waiting for one of only 2 STAGE2_WORKERS slots while a
        # different page's IndicPhotoOCR call (30-60s) held one. Raising this doesn't
        # reintroduce the original Paddle-lock thrash the comment above describes --
        # threads still queue on _engine_lock/_INDIC_LOCK either way -- it just stops
        # an unrelated fast page from being held hostage behind a slow one.
        STAGE2_WORKERS = 4

# ═══════════════════════════════════════════════════════════════════════════════
#  QUALITY GATE — Controls When to Fall Back to Tesseract
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum average confidence across all detected text regions
# If below this → soft-fail → try Tesseract
PADDLE_CONFIDENCE_THRESH = 0.45

# Minimum fraction of expected lines that must be found
# Expected lines = image_height // 40  (rough: ~40px per Telugu line at 400 DPI)
# If actual_lines < expected * this ratio → soft-fail → try Tesseract
PADDLE_MIN_LINE_RATIO = 0.50

# If output has zero Telugu Unicode characters (U+0C00–U+0C7F) and text length > 20
# it's probably garbage ASCII → soft-fail → try Tesseract
PADDLE_REQUIRE_TELUGU_CHARS = True

# Reject PP-OCRv5 output if too many words are contaminated with mixed Telugu/English letters.
# This indicates the engine is misrecognizing characters (e.g. 'న' -> 'a', 'కే' -> 'te').
PADDLE_MAX_MIXED_WORDS = 3       # max allowed corrupted/mixed words
PADDLE_MAX_MIXED_RATIO = 0.02    # max allowed ratio of corrupted words (2%)

# Upfront clarity-routing thresholds for Tesseract selection
TESSERACT_MIN_SHARPNESS = 800    # Laplacian variance threshold
TESSERACT_MIN_CONTRAST = 45       # Standard deviation of intensity threshold
TESSERACT_FIRST_ON_CLEAR = False # Disable Tesseract-first flow; always execute PaddleOCR first
PADDLE_HIGH_CONF_BYPASS = 0.80   # Bypass line-count/density gates if Paddle confidence is >= 80%
ENABLE_COMPARATIVE_MERGE = True  # Enable deep sequence-alignment word merging on fallback

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIDENCE-BAND RE-VOTE — targets wrong-but-plausible single-letter misreads
# ═══════════════════════════════════════════════════════════════════════════════
# A box scoring below PADDLE_CONFIDENCE_THRESH already gets dropped above; a
# box scoring near 1.0 is usually right. The band between them (confident
# enough to pass, not confident enough to trust) is where a single wrong
# letter that still forms a plausible-looking word is most likely to hide --
# no other quality gate or post-processing layer targets this failure shape
# (see 2026-08-31 investigation: grapheme-validity/dictionary-correction only
# catch structurally-broken or out-of-dictionary text). When enabled, boxes
# in this band get re-read from an upscaled crop and the higher-confidence
# result wins. Default OFF, same rollout pattern as the other Telugu
# correction features in this codebase -- calibrate against real books via
# scripts/mine_ocr_failure_patterns.py-style comparison before flipping on.
ENABLE_PADDLE_CONFIDENCE_REVOTE = False
PADDLE_REVOTE_CONF_LOW  = 0.45   # matches PADDLE_CONFIDENCE_THRESH floor
PADDLE_REVOTE_CONF_HIGH = 0.70   # above this, treat the read as solid, skip re-vote
PADDLE_REVOTE_UPSCALE   = 1.6    # crop upscale factor for the alternate read

# Dictionary-gated fix for "్ర" (subjoined-ra conjunct) misread as a literal "("
# at the START of a word (e.g. "(దుపదుడు" -> "ద్రుపదుడు", Drupada) — see
# TeluguPostProcessor.fix_word_initial_conjunct_ra(). Enabled 2026-09-07 after
# calibration against all 36 cached books in data/temp/: 21,000 raw matches ->
# 15,692 remaining (~5,300 corrections applied), 65 hand-checked samples
# (25 applied + 40 left alone) found zero false positives — genuine
# parentheses like "నవల (novel)" are correctly left untouched since "నవల" is
# already a valid dictionary word on its own.
ENABLE_CONJUNCT_RA_WORD_INITIAL_FIX = True


# Log the reason for every fallback (useful for tuning thresholds)
PADDLE_LOG_FALLBACK_REASON = True

# Force garbage collection after each Paddle inference to prevent memory growth
PADDLE_ENABLE_GC = True

# ═══════════════════════════════════════════════════════════════════════════════
#  DYNAMIC PREPROCESSING (CONTRAST & SHARPNESS)
# ═══════════════════════════════════════════════════════════════════════════════
# Adjust preprocessing factors dynamically based on page image metrics
PADDLE_SHARPNESS_LOW_LIMIT  = 1500.0   # below this = blurry, gets max boost
PADDLE_SHARPNESS_HIGH_LIMIT = 3000.0   # above this = sharp, keep as is (1.0)
PADDLE_MAX_SHARPNESS_BOOST  = 2.2      # multiplier for blurry images
PADDLE_MIN_SHARPNESS_BOOST  = 1.0      # multiplier for already sharp images

PADDLE_CONTRAST_LOW_LIMIT   = 30.0     # below this = low contrast, gets max boost
PADDLE_CONTRAST_HIGH_LIMIT  = 50.0     # above this = high contrast, keep as is (1.0)
PADDLE_MAX_CONTRAST_BOOST   = 1.6      # multiplier for low contrast images
PADDLE_MIN_CONTRAST_BOOST   = 1.0      # multiplier for already high contrast images

# ── Alternative: CLAHE (adaptive local contrast) ──────────────────────────────
# The boost above applies ONE contrast/sharpness multiplier to the whole page.
# CLAHE instead corrects each region of the page independently (a tile grid,
# each tile histogram-equalized against its own local contrast, clipped to
# avoid amplifying noise in near-blank tiles) — better suited to unevenly
# faded/stained old scans, where one global setting either under-corrects the
# faintest patch or over-amplifies noise everywhere else.
# Off by default: A/B compare against the global boost above before enabling.
PADDLE_USE_CLAHE = False
PADDLE_CLAHE_CLIP_LIMIT = 2.0        # higher = stronger local contrast (typical range 2.0-4.0)
PADDLE_CLAHE_TILE_GRID_SIZE = 8      # NxN tile grid for local histogram equalization


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTING — Adaptive OCR tier thresholds
# ═══════════════════════════════════════════════════════════════════════════════
# With PP-OCRv5 as primary, Tesseract is only the fallback (not routed directly).
# Routing tiers:
#   Score  0–85  → PP-OCRv5 (primary); Tesseract on soft/hard fail
#   Score 85–90  → Gemini Vision
#   Score  90+   → Google Vision (if enabled) → Gemini

# Override base config: Paddle handles everything below Gemini threshold
PADDLE_COMPLEXITY_MIN       = 0     # Paddle takes ALL pages below Gemini threshold
                                    # (was 40 in middle-tier plan; now 0 = primary)

# Gemini threshold unchanged (inherited from config.py as GEMINI_COMPLEXITY_THRESHOLD=85)

# ═══════════════════════════════════════════════════════════════════════════════
#  TESSERACT — Still Available as Fallback
# ═══════════════════════════════════════════════════════════════════════════════
# All Tesseract settings (TESSERACT_PATH, OCR_CONFIG, etc.) are inherited from
# config.py unchanged. Tesseract is used automatically when PP-OCRv5 fails.

# Post-processing: reduce noisy fixups since PP-OCRv5 is cleaner than Tesseract
# Keep them True so the Tesseract fallback path still benefits from them.
ENABLE_TELUGU_POST_PROCESSING = True
ENABLE_SHLOKA_FIXES           = True    # still needed on Tesseract fallback pages
ENABLE_PUNCTUATION_FIXES      = True

# ═══════════════════════════════════════════════════════════════════════════════
#  OVERRIDE — OCR ENGINE MODE
# ═══════════════════════════════════════════════════════════════════════════════
# Reverted to 'hybrid' 2026-09-22: 'fusion' (PP-OCRv5 + IndicPhotoOCR + Tesseract)
# measured at 35-40s/page real throughput on a live 76-page book, dominated by
# IndicPhotoOCR (~70% of its own runtime is its script identifier alone) -- 10-20x
# slower than plain PP-OCRv5's 1.7-3.6s/page, for an accuracy benefit that is still
# unverified beyond one draft, unconfirmed ground-truth page. Not worth that cost in
# the live conversion path yet. IndicPhotoOCR stays available for the offline
# tests/diagnostics/build_review_queue.py workflow, where its cost is naturally
# limited to the small set of already-flagged lines rather than every line of every
# page. Set OCR_ENGINE = 'fusion' again once either (a) real ground truth justifies
# the cost, or (b) IndicPhotoOCR is restructured to run only on flagged crops instead
# of the whole page per invocation (see docs/CURRENT_STATE.md's latency section).
OCR_ENGINE       = 'hybrid'        # 'paddle', 'tesseract', 'fusion', or 'hybrid' (PP-OCRv5 primary, Tesseract fallback)
HYBRID_PRIMARY   = 'paddle'      # was 'tesseract' in base config
HYBRID_FALLBACK  = 'tesseract'   # Tesseract is now the safety net

# ── Runtime availability flag (updated by paddle_v5_processor at import time) ──
# Do not set this manually — it is overwritten automatically.
PADDLE_OCR_AVAILABLE = ENABLE_PADDLE_OCR
