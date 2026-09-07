"""
Configuration for Tesseract-Only Mode
High-quality Telugu OCR using Tesseract with tessdata_best
No EasyOCR dependency - faster startup, lower memory, simpler deployment
"""
import os
import platform
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent / '.env')

# Detect Operating System
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'
IS_MAC = platform.system() == 'Darwin'
OS_NAME = platform.system()

print(f"Detected OS: {OS_NAME}")
print(f"Mode: Adaptive (Tesseract + Gemini, No EasyOCR)")

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
UPLOAD_FOLDER = DATA_DIR / 'uploads'

# OS-specific output folder
if IS_WINDOWS:
    OUTPUT_FOLDER = Path(r'C:\Workspace\OutputOCR\EPUB_MOBI_TESSERACT')
else:
    wsl_path = Path('/mnt/c/Workspace/OutputOCR/EPUB_MOBI_TESSERACT')
    if wsl_path.exists() or wsl_path.parent.exists():
        OUTPUT_FOLDER = wsl_path
    else:
        OUTPUT_FOLDER = BASE_DIR / 'outputs'

TEMP_FOLDER = DATA_DIR / 'temp'

# Create directories
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
TEMP_FOLDER.mkdir(exist_ok=True)

print(f"Output folder: {OUTPUT_FOLDER}")

# ═══════════════════════════════════════════════════════
#  TESSERACT CONFIGURATION (Optimized)
# ═══════════════════════════════════════════════════════

WSL_MODE = IS_LINUX and Path('/mnt/c').exists()
USE_WSL_TESSERACT = True

if IS_WINDOWS:
    if USE_WSL_TESSERACT:
        TESSERACT_PATH = r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\tesseract_wsl.bat'
        print("[OK] Using WSL Tesseract (via shim)")
    else:
        TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        print("[OK] Using Windows Tesseract")
elif WSL_MODE:
    TESSERACT_PATH = 'tesseract'
    print("[OK] Using WSL Tesseract (native)")
else:
    TESSERACT_PATH = 'tesseract'
    print(f"[OK] Using native Tesseract on {OS_NAME}")

# ═══════════════════════════════════════════════════════
#  OCR SETTINGS — Tesseract Only
# ═══════════════════════════════════════════════════════

# Telugu-only mode — prevents English character interference
# Where Telugu glyphs like శ్లో get misread as Sn/Fu/En
DEFAULT_OCR_LANGUAGE = 'tel_best+eng'
FALLBACK_LANGUAGE = 'tel_best'
# PSM 4 = Single column of text of variable sizes (best for book pages)
# PSM 6 = Assume a single uniform block of text (misses indented/edge lines)
# NOTE: PSM is now selected DYNAMICALLY per-page by page_complexity_analyzer.py
#       This global config is the FALLBACK only (used if analysis fails).
# textord_heavy_nr=1 → forces detection of faint/thin strokes (old print)
# lstm_choice_mode=2 → better confidence scoring for complex Telugu glyphs
TESSERACT_PSM = 4   # Default fallback PSM (overridden per-page by analyzer)
OCR_CONFIG = '--oem 1 --psm 4 --dpi 400 -c preserve_interword_spaces=1 -c textord_heavy_nr=1 -c lstm_choice_mode=2'
TESSERACT_CONFIG = '--oem 1 --psm 4 --dpi 400 -c preserve_interword_spaces=1 -c textord_heavy_nr=1 -c lstm_choice_mode=2'
OCR_LANGUAGES = ['tel_best', 'eng']

# Allow intelligent logic routing (skips easyocr natively via our other edits)
OCR_ENGINE = 'hybrid'
OCR_LANGUAGE = 'tel_best+eng'

# Upfront routing optimization: run Tesseract first on high-clarity pages
TESSERACT_FIRST_ON_CLEAR = True


# EasyOCR removed — Tesseract + Gemini are the only active engines.

# ═══════════════════════════════════════════════════════
#  TELUGU TEXT PROCESSING
# ═══════════════════════════════════════════════════════

ENABLE_TELUGU_PROCESSING = True
TELUGU_ENCODING_DIR = None
ANALYZE_VATULU = True
ANALYZE_GUNINTHALU = True

# Telugu OCR Post-Processing (fixes known misreads)
ENABLE_TELUGU_POST_PROCESSING = True
ENABLE_SHLOKA_FIXES = True     # Fix శ్లో॥ misreads (Sn/Fu → శ్లో॥)
ENABLE_CHAR_FIXES = False       # Experimental character fixes
ENABLE_PUNCTUATION_FIXES = True # Normalize danda marks (II → ॥)
ENABLE_TELUGU_DICTIONARY_CORRECTION = True  # Dictionary-based spell-correction (default off until validated)
DICTIONARY_CORRECTION_GEMINI_THRESHOLD = 10  # Pages with >= this many corrections need Gemini auto-validation (not yet implemented); fewer need manual review

ENABLE_TELUGU_OOV_JUNK_SIGNAL = False  # Dictionary OOV-word-ratio contributes to junk-text detection (PageComplexityAnalyzer.is_junk_text).
                                        # Default OFF — uncalibrated (no real-page distribution data yet, unlike grapheme_ratio's
                                        # validated 2.5%). The ratio is ALWAYS computed and logged regardless of this flag, via
                                        # scripts/calibrate_oov_ratio.py and per-page structured logging, so real data can justify
                                        # a threshold before this is trusted to discard text.
OOV_JUNK_RATIO_THRESHOLD = 0.5   # Placeholder — set from real calibration data before enabling the flag above.
OOV_JUNK_MIN_WORDS = 8           # Minimum dictionary-eligible words on a page before the OOV ratio is trusted (avoids noisy short/caption pages).

ENABLE_TELUGU_STROKE_CORRECTION = True  # Repair a single MISSING matra or vattu-conjunct stroke on an
                                          # otherwise-clean, dictionary-unknown word (e.g. వాడు OCR'd as వడు).
                                          # Narrower than ENABLE_TELUGU_DICTIONARY_CORRECTION's existing
                                          # structurally-broken-token path. Only takes effect when that flag is
                                          # also on. Enabled 2026-07-20 after real-data validation (see
                                          # docs/TELUGU_SPELL_CORRECTION_TODO.md item 7 and
                                          # scripts/calibrate_stroke_correction.py) found this (missing-stroke)
                                          # direction reliably safe — confirmed again against a real book
                                          # (Nuvve_naa_pranam): 61 clean corrections the existing structural
                                          # path missed entirely.
ENABLE_TELUGU_STROKE_REMOVAL_CORRECTION = False  # Additionally allow the REVERSE direction: removing an
                                          # apparently-extra matra/vattu stroke. Only takes effect when
                                          # ENABLE_TELUGU_STROKE_CORRECTION is also on. Kept as a separate,
                                          # more cautious flag — real-data validation found this direction
                                          # riskier (legitimate long-vowel/emphatic Telugu forms, e.g. అహింసా
                                          # vs అహింస, can look like a false "extra" stroke). See
                                          # docs/TELUGU_SPELL_CORRECTION_TODO.md item 7.

ENABLE_CONJUNCT_RA_WORD_INITIAL_FIX = True  # Dictionary-gated fix for "్ర" misread as a literal "("
                                          # at the START of a word (e.g. "(దుపదుడు" -> "ద్రుపదుడు").
                                          # Enabled 2026-09-07 after calibration against all 36 cached
                                          # books (21,000 raw matches -> 15,692 remaining, 65
                                          # hand-checked samples, zero false positives) — see
                                          # TeluguPostProcessor.fix_word_initial_conjunct_ra().

ENABLE_GEMINI_REFERENCE_GROUNDING = False  # Give Gemini both Paddle's and Tesseract's independent readings
                                          # of the page (+ where they disagree) alongside the image, instead
                                          # of transcribing from a blank slate. Targets a confirmed
                                          # hallucination failure mode: with no reference, Gemini substituted
                                          # a fluent-but-wrong phrase for an unusual person's name that
                                          # Tesseract's unreferenced pass read almost perfectly (rudranethra
                                          # book, page 3 — see docs/TELUGU_SPELL_CORRECTION_TODO.md item 8).
                                          # Applies to BOTH the escalation-ladder rescue tier
                                          # (_run_escalation_ladder) and the direct high-complexity routing
                                          # tier (_ocr_single_image) — the latter means Gemini-tier pages now
                                          # also get local Tesseract+PaddleOCR passes purely as reference
                                          # material (extra local compute, not extra $ — Gemini call count is
                                          # unchanged). Default OFF pending validation — see
                                          # scripts/validate_gemini_reference_grounding.py.

# Image Enhancement for OCR
ENABLE_DESKEW = True   # Auto-straighten tilted scans
ENABLE_SHARPEN = True  # Sharpen text edges for better OCR

# Column-Aware OCR
ENABLE_COLUMN_OCR = True   # Split multicolumn pages and OCR each column separately
                           # Also masks illustration regions to prevent junk chars

# ═══════════════════════════════════════════════════════
#  PERFORMANCE — Optimized for Tesseract
# ═══════════════════════════════════════════════════════

# Tesseract is thread-safe and lightweight — we can use MORE workers
os.environ['OMP_THREAD_LIMIT'] = '1'

# Ceiling applied to each Tesseract subprocess's own environment (scoped
# independently of the in-process OMP ceiling by ocr_processor.py, so raising
# Paddle's in-process thread count on the config_v5/WSL path never affects
# concurrently-running Tesseract child processes).
TESSERACT_SUBPROCESS_OMP_LIMIT = '1'

# No hybrid mode needed
HYBRID_PRIMARY = 'tesseract'
HYBRID_FALLBACK = 'tesseract'
HYBRID_CONFIDENCE_THRESHOLD = 0.7

# Adaptive OCR routing enabled
ENABLE_ADAPTIVE_OCR = True
ADAPTIVE_SIMPLE_THRESHOLD = 45
ADAPTIVE_COMPLEX_THRESHOLD = 60

# Flask Server Configuration
HOST = '0.0.0.0'
PORT = 5001
DEBUG = True

# Timeout Settings — Tesseract is much faster, shorter timeouts OK
OCR_TIMEOUT = 60       # Tesseract rarely needs >30s per page
OCR_CELL_TIMEOUT = 15
SUBPROCESS_TIMEOUT = 180

# Checkpoint Settings
CHECKPOINT_ENABLED = True
CHECKPOINT_SAVE_INTERVAL = 1

# ═══════════════════════════════════════════════════════
#  PDF & IMAGE PROCESSING
# ═══════════════════════════════════════════════════════

# Two-Stage DPI Strategy
# NOTE: DEFAULT_DPI is the ACTUAL rendering DPI used for PDF→image conversion.
# The --dpi flag in OCR_CONFIG is metadata only (tells Tesseract what to expect).
# Old Telugu print needs ≥400 DPI to resolve vatulu/guninthalu distinctly.
DEFAULT_DPI = 400
OCR_DPI = 400
USE_TWO_STAGE_DPI = True
STORAGE_DPI = 150
TEXT_BACKUP_DPI = 50

IMAGE_FORMAT = 'JPEG'
PDF_MAX_SIZE_MB = 1000
AUTO_ROTATE = True
ROTATION_CONFIDENCE_THRESHOLD = 1.5

# Text Cleaning
REMOVE_PAGE_NUMBERS = True
PAGE_NUMBER_PATTERNS = [
    r'Page\s+\d+',
    r'పేజీ\s+\d+',
    r'^\d+$',
    r'- \d+ -',
]

# Image Processing
IMAGE_QUALITY = 70
IMAGE_MAX_WIDTH = 600
IMAGE_MAX_HEIGHT = 900

# Aggressive Compression for Pages with OCR Text
COMPRESS_IMAGES_WITH_TEXT = True
TEXT_BACKUP_IMAGE_QUALITY = 40
TEXT_BACKUP_IMAGE_MAX_WIDTH = 400
TEXT_BACKUP_IMAGE_MAX_HEIGHT = 600
MIN_TEXT_FOR_COMPRESSION = 300

# Image Preservation
PRESERVE_IMAGES = True
SELECTIVE_IMAGE_PRESERVATION = True
COMPLEX_PAGE_IMAGE_THRESHOLD = 60
MIN_TEXT_LENGTH_FOR_TEXT_ONLY = 100

# Image-Dominant Page Detection
# When the combined bounding-box area of detected illustrations exceeds this
# fraction of the total page area, the page is treated as a "image plate" and
# OCR is skipped entirely — it is captured as a high-quality image instead.
# 0.55 = if illustrations cover ≥55% of the page, skip OCR (safe default).
# Lower to 0.40 if you want to catch even partial illustration pages.
# Raise to 0.70 if you find too many text pages being skipped.
IMAGE_PAGE_DOMINANT_RATIO = 0.55

# Table & TOC Detection
ENABLE_TABLE_DETECTION = False
ENABLE_TOC_DETECTION = True
TABLE_DETECTION_THRESHOLD = 0.7

MIN_TABLE_ROWS = 2
MIN_TABLE_COLS = 2

# ═══════════════════════════════════════════════════════
#  EPUB / MOBI
# ═══════════════════════════════════════════════════════

EPUB_METADATA = {
    'title': 'Converted Document',
    'author': 'Unknown',
    'language': 'te',
    'publisher': 'PDF to EPUB Converter',
}
EPUB_LANGUAGE = 'te'
EPUB_PUBLISHER = 'PDF to EPUB Converter'
EPUB_IDENTIFIER_PREFIX = 'epub-converter-'
PAGES_PER_CHAPTER = 10
EMBED_FONTS = True

ENABLE_MOBI_CONVERSION = True
CALIBRE_EBOOK_CONVERT_PATH = 'ebook-convert'
GENERATE_MOBI = True

# ═══════════════════════════════════════════════════════
#  FILE UPLOAD & WEB
# ═══════════════════════════════════════════════════════

MAX_FILE_SIZE = 1000 * 1024 * 1024
MAX_CONTENT_LENGTH = MAX_FILE_SIZE
ALLOWED_EXTENSIONS = {'pdf'}

# OS-Specific Performance Settings
# Tesseract is much lighter than EasyOCR — can use more workers safely
if IS_WINDOWS:
    MAX_WORKERS = 10    # More workers since no EasyOCR memory pressure
    NUM_WORKERS = 10
    BATCH_SIZE = 16
    DEBUG = False
    print("Using Windows settings: MAX_WORKERS=10, BATCH_SIZE=16")
elif IS_LINUX:
    if WSL_MODE:
        MAX_WORKERS = 6      # Reduced from 10: optimal for WSL without over-committing CPU
        NUM_WORKERS = 6
        BATCH_SIZE = 10
        DEBUG = False
        print("Using WSL settings: MAX_WORKERS=10, BATCH_SIZE=10")
    else:
        MAX_WORKERS = 16
        NUM_WORKERS = 16
        BATCH_SIZE = 20
        DEBUG = False
        print("Using Linux settings: MAX_WORKERS=16, BATCH_SIZE=20")
else:
    MAX_WORKERS = 8
    NUM_WORKERS = 8
    BATCH_SIZE = 10
    DEBUG = False
    print(f"Using default settings for {OS_NAME}")

# Stage-2 (OCR) worker ceiling — the outer thread pool (MAX_WORKERS) already caps
# total concurrent pages, which naturally bounds Stage-1 (analysis+enhancement)
# concurrency too. STAGE2_WORKERS is a separate, SMALLER sub-throttle applied only
# around the OCR portion of each page, since OCR calls are serialized by a single
# engine lock in config_v5.py's WSL path — more Stage-2 concurrency just queues,
# it doesn't add throughput. Defaults to MAX_WORKERS (no extra restriction) here;
# config_v5.py narrows this for the WSL/Paddle-primary path.
STAGE2_WORKERS = MAX_WORKERS
# Minimum free system RAM (GB) required before a page may start Stage 1. A live
# psutil check, not a static per-worker guess — see pdf_to_epub_converter_optimized_v2.py.
STAGE1_MEMORY_FLOOR_GB = 1.5

PARALLEL_PROCESSING = True
CLEANUP_TEMP_FILES = True

# Web Interface
SECRET_KEY = 'your-secret-key-change-in-production'
HOST = '0.0.0.0'
PORT = 5001

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = BASE_DIR / 'converter.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ═══════════════════════════════════════════════════════
#  GEMINI VISION OCR (Premium tier for complex pages)
# ═══════════════════════════════════════════════════════

ENABLE_GEMINI_OCR = True
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
# Confirmed working via API model list (ListModels) — gemini-1.5-flash returns 404.
# gemini-2.5-flash is available on this account and tested working (6.1s, clean Telugu OCR).
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_COMPLEXITY_THRESHOLD = 85             # Raised from 75: only truly complex pages go direct to Gemini
GEMINI_USE_AS_FALLBACK = True                # Use Gemini when Tesseract fails
GEMINI_RATE_LIMIT_RPM = 10                   # Free tier: 10 RPM
GEMINI_TIMEOUT = 45                          # 2.5-flash may take slightly longer
GEMINI_MAX_RETRIES = 5                       # Resilience against transient 429s
GEMINI_MONTHLY_QUOTA = 5000                  # Safe under free tier daily limits
GEMINI_RESCUE_THRESHOLD = 0.60              # Rescue if lines found < 60% of estimated
TESSERACT_MIN_SAFE_LINES = 19               # If Tesseract gets >= 22 clean lines, skip Gemini rescue to save budget!

# ── IMAGE SIZE CONTROL (directly reduces 429 / TPM errors) ──────────────────
# Gemini charges tokens per 768×768 tile: tokens = 258 + (W_tiles × H_tiles × 258)
# At 400 DPI A4 (3307×4677px) → 35 tiles → ~9,288 tokens/image → TPM exhausted fast.
# At 1536px longest side      → 4 tiles  → ~1,290 tokens/image → 7× cheaper.
# Gemini OCR quality is NOT degraded — it upsamples internally and the model
# resolution is sufficient to read Telugu glyphs at 1024-1536px.
GEMINI_MAX_IMAGE_PIXELS = 1536   # Max longest-side pixels sent to Gemini (was 4096)
GEMINI_JPEG_QUALITY = 72         # JPEG quality for Gemini payload (was 85; 72 saves ~30%)

# Check if Gemini is actually usable
GEMINI_AVAILABLE = bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-api-key-here')

# --- BUDGET & VERIFICATION ---
ENABLE_AUTOMATIC_GEMINI_RESCUE = True   # ENABLED: Automatically resolve Tesseract failures
GEMINI_RESCUE_BUDGET = 500              # Increased to handle 520-page books

# ═══════════════════════════════════════════════════════
#  GOOGLE CLOUD VISION OCR (Legacy premium tier)
# ═══════════════════════════════════════════════════════

ENABLE_GOOGLE_VISION_OCR = False  # Disabled: billing not enabled on GCP project
GOOGLE_VISION_API_KEY = os.environ.get('GOOGLE_VISION_API_KEY', '')
GOOGLE_VISION_SERVICE_ACCOUNT = os.environ.get('GOOGLE_VISION_SERVICE_ACCOUNT', '') 
GOOGLE_VISION_COMPLEXITY_THRESHOLD = 90      # Even higher bar than Gemini
GOOGLE_VISION_MONTHLY_QUOTA = 1000           # Free tier limit

# Check if Google Vision is usable (disabled: requires billing to be enabled on GCP)
GOOGLE_VISION_AVAILABLE = False

# ═══════════════════════════════════════════════════════
#  PREMIUM QUOTA MANAGEMENT
# ═══════════════════════════════════════════════════════

# Enable usage tracking to stay within free tiers
ENABLE_QUOTA_MANAGEMENT = True
if ENABLE_GEMINI_OCR and not GEMINI_AVAILABLE:
    print("⚠️  Gemini OCR enabled but GEMINI_API_KEY not set in .env — Gemini will be skipped")


# ═══════════════════════════════════════════════════════
#  LANGCHAIN / LANGGRAPH PIPELINE
# ═══════════════════════════════════════════════════════

ENABLE_LANGCHAIN_PIPELINE = True             # Use LangGraph state graph for OCR routing
                                              # False = legacy direct calls (backward compatible)


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Print configuration summary
print("="*60)
print("Configuration Summary:")
print(f"  OS: {OS_NAME}")
print(f"  OCR Engine: TESSERACT (primary)")
print(f"  Gemini OCR: {'ENABLED' if GEMINI_AVAILABLE else 'Disabled (no API key)'}")
if GEMINI_AVAILABLE:
    print(f"    Model: {GEMINI_MODEL} | Quota: {GEMINI_MONTHLY_QUOTA}")
print(f"  Google Vision OCR: {'ENABLED' if GOOGLE_VISION_AVAILABLE else 'Disabled'}")
if GOOGLE_VISION_AVAILABLE:
    print(f"    Quota: {GOOGLE_VISION_MONTHLY_QUOTA}")
print(f"  Quota Management: {'ENABLED' if ENABLE_QUOTA_MANAGEMENT else 'Disabled'}")
print(f"  LangChain Pipeline: {'ENABLED' if ENABLE_LANGCHAIN_PIPELINE else 'Disabled'}")
print(f"  Language: {DEFAULT_OCR_LANGUAGE}")
print(f"  Output: {OUTPUT_FOLDER}")
print(f"  Tesseract: {TESSERACT_PATH}")
print(f"  Workers: {MAX_WORKERS}")
print(f"  Batch Size: {BATCH_SIZE}")
print(f"  OCR DPI: {OCR_DPI}")
print(f"  Post-Processing: {ENABLE_TELUGU_POST_PROCESSING}")
print(f"  Deskew: {ENABLE_DESKEW} | Sharpen: {ENABLE_SHARPEN}")
print(f"  Debug Mode: {DEBUG}")
print("="*60)
