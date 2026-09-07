"""
Configuration for Tesseract-Only Mode
High-quality Telugu OCR using Tesseract with tessdata_best
No EasyOCR dependency - faster startup, lower memory, simpler deployment
"""
import os
import platform
from pathlib import Path

# Detect Operating System
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'
IS_MAC = platform.system() == 'Darwin'
OS_NAME = platform.system()

print(f"Detected OS: {OS_NAME}")
print(f"Mode: Tesseract-Only (No EasyOCR)")

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
        TESSERACT_PATH = 'wsl tesseract'
        print("[OK] Using WSL Tesseract")
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
DEFAULT_OCR_LANGUAGE = 'tel'
FALLBACK_LANGUAGE = 'tel'
OCR_CONFIG = '--oem 3 --psm 6 --dpi 300 -c preserve_interword_spaces=1'
TESSERACT_CONFIG = '--oem 3 --psm 6 --dpi 300 -c preserve_interword_spaces=1'
OCR_LANGUAGES = ['tel', 'eng']

# Force Tesseract only — no EasyOCR, no hybrid
OCR_ENGINE = 'tesseract'
OCR_LANGUAGE = 'tel'

# EasyOCR Settings — Disabled (kept for compatibility)
EASYOCR_USE_GPU = False
EASYOCR_LANG = 'te+en'
EASYOCR_MIN_SIZE = 8
EASYOCR_TEXT_THRESHOLD = 0.4
EASYOCR_LOW_TEXT = 0.2
EASYOCR_LINK_THRESHOLD = 0.15
EASYOCR_MAG_RATIO = 2.0

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
ENABLE_TELUGU_DICTIONARY_CORRECTION = False  # Dictionary-based spell-correction (default off until validated)

ENABLE_TELUGU_OOV_JUNK_SIGNAL = False  # Dictionary OOV-word-ratio contributes to junk-text detection — see config.py for full rationale.
OOV_JUNK_RATIO_THRESHOLD = 0.5   # Placeholder — set from real calibration data before enabling the flag above.
OOV_JUNK_MIN_WORDS = 8           # Minimum dictionary-eligible words on a page before the OOV ratio is trusted.

ENABLE_TELUGU_STROKE_CORRECTION = True   # Repair a single MISSING matra or vattu-conjunct stroke on an
                                          # otherwise-clean, dictionary-unknown word — see config.py for full rationale.
                                          # NOTE: currently inert in this profile since
                                          # ENABLE_TELUGU_DICTIONARY_CORRECTION is False here (pre-existing
                                          # discrepancy vs config.py) — stroke correction only runs when that
                                          # flag is also on. Set True here for consistency / ready if enabled.
ENABLE_TELUGU_STROKE_REMOVAL_CORRECTION = False  # Reverse direction (removing a stroke) — riskier, see config.py.

ENABLE_CONJUNCT_RA_WORD_INITIAL_FIX = True  # Dictionary-gated fix for "్ర" misread as a literal "(" at
                                          # the START of a word — see config.py for full rationale.

ENABLE_GEMINI_REFERENCE_GROUNDING = False  # Give Gemini both Paddle's and Tesseract's independent readings
                                          # alongside the image, to curb hallucination — see config.py for full rationale.

# Image Enhancement for OCR
ENABLE_DESKEW = True   # Auto-straighten tilted scans
ENABLE_SHARPEN = True  # Sharpen text edges for better OCR

# ═══════════════════════════════════════════════════════
#  PERFORMANCE — Optimized for Tesseract
# ═══════════════════════════════════════════════════════

# Tesseract is thread-safe and lightweight — we can use MORE workers
os.environ['OMP_THREAD_LIMIT'] = '1'

# No hybrid mode needed
HYBRID_PRIMARY = 'tesseract'
HYBRID_FALLBACK = 'tesseract'
HYBRID_CONFIDENCE_THRESHOLD = 0.7

# Adaptive OCR disabled — always Tesseract
ENABLE_ADAPTIVE_OCR = False
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
DEFAULT_DPI = 300
OCR_DPI = 300
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

# Table Detection
ENABLE_TABLE_DETECTION = False
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
        MAX_WORKERS = 6     # More workers since no EasyOCR memory pressure
        NUM_WORKERS = 6
        BATCH_SIZE = 10
        DEBUG = False
        print("Using WSL settings: MAX_WORKERS=6, BATCH_SIZE=10")
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


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Print configuration summary
print("="*60)
print("Configuration Summary (Tesseract-Only):")
print(f"  OS: {OS_NAME}")
print(f"  OCR Engine: TESSERACT ONLY (no EasyOCR)")
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
