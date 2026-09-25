#!/bin/bash

echo "========================================"
echo "PDF to EPUB Converter - Quick Start"
echo "Enhanced Telugu OCR with Vatulu & Guninthalu Detection"
echo "========================================"
echo ""

# ── Clean stale Python bytecode caches (the mvn-clean equivalent) ────────────
# A shared/reused venv + edited .py files can leave stale __pycache__/*.pyc
# around; Python usually invalidates these by mtime/hash on its own, but this
# guarantees a clean slate on every launch, same intent as `mvn clean`.
echo "Cleaning stale __pycache__ / .pyc files..."
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for d in src tests scripts IndicPhotoOCR; do
    [ -d "$PROJECT_ROOT/$d" ] || continue
    find "$PROJECT_ROOT/$d" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    find "$PROJECT_ROOT/$d" -type f -name "*.pyc" -delete 2>/dev/null
done
echo ""

# ── Prefer the shared venv (paddleocr + torch + IndicPhotoOCR + tesseract, ────
# already fully set up by scripts/setup_shared_ocr_venv.sh) over creating a
# separate ./venv from plain requirements.txt. requirements.txt alone does not
# include torch/transformers/IndicPhotoOCR — a ./venv built from it can run
# PP-OCRv5+Tesseract fine, but config.ENABLE_FUSION_OCR's IndicPhotoOCR pass
# would silently be unavailable (FusionOCRProcessor catches the ImportError and
# keeps going without it, so nothing crashes — it just quietly loses the
# feature). Falls back to the old ./venv behavior if the shared venv isn't set
# up yet, so this stays backward compatible.
SHARED_VENV="$HOME/venvs/ocr-common"
if [ -f "$SHARED_VENV/bin/activate" ]; then
    echo "Using shared venv: $SHARED_VENV (has IndicPhotoOCR — see scripts/setup_shared_ocr_venv.sh)"
    source "$SHARED_VENV/bin/activate"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to activate shared virtual environment"
        read -p "Press Enter to exit..."
        exit 1
    fi
    VENV_DIR="$SHARED_VENV"
else
    echo "Shared venv not found at $SHARED_VENV — falling back to a local ./venv"
    echo "(run scripts/setup_shared_ocr_venv.sh once to get IndicPhotoOCR support here too)"
    echo ""

    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
        if [ $? -ne 0 ]; then
            echo "Error: Failed to create virtual environment"
            echo "Please ensure Python 3 is installed and in PATH"
            read -p "Press Enter to exit..."
            exit 1
        fi
        echo "Virtual environment created successfully"
        echo ""
    fi

    # Activate virtual environment
    echo "Activating virtual environment..."
    source venv/bin/activate
    if [ $? -ne 0 ]; then
        echo "Error: Failed to activate virtual environment"
        read -p "Press Enter to exit..."
        exit 1
    fi
    VENV_DIR="venv"
fi

# ── Dependency check with stamp-file cache ───────────────────────────────────
# We only re-run pip install when requirements.txt has actually changed.
# The stamp file stores the last-modified time of requirements.txt.
# Skipped entirely for the shared venv -- that one is managed by
# setup_shared_ocr_venv.sh, not by pip install -r requirements.txt here.
STAMP_FILE="$VENV_DIR/.deps_stamp"
REQ_FILE="requirements.txt"

if [ "$VENV_DIR" = "$SHARED_VENV" ]; then
    # The shared venv is managed by setup_shared_ocr_venv.sh, which installs
    # PaddleOCR, then IndicPhotoOCR, then deliberately strips any CUDA torch
    # pulled in transitively and installs CPU-only torch LAST (see its own
    # comments and docs/CURRENT_STATE.md). `pip install -r requirements.txt`
    # here has no such ordering and could silently clobber that pin. If a
    # package is genuinely missing from the shared venv, re-run
    # scripts/setup_shared_ocr_venv.sh instead of installing into it here.
    echo "Dependencies: managed by scripts/setup_shared_ocr_venv.sh, not checked here ✓"
else
    needs_install=false
    if [ ! -f "$STAMP_FILE" ]; then
        needs_install=true
    elif [ "$REQ_FILE" -nt "$STAMP_FILE" ]; then
        echo "requirements.txt changed — re-checking dependencies..."
        needs_install=true
    fi

    if [ "$needs_install" = true ]; then
        echo "Checking dependencies..."
        if ! pip show flask > /dev/null 2>&1 || ! pip show pytesseract > /dev/null 2>&1; then
            echo "Dependencies missing or incomplete. Installing..."
            pip install --upgrade pip -q
            pip install -r requirements.txt -q
            if [ $? -ne 0 ]; then
                echo "Error: Failed to install dependencies"
                read -p "Press Enter to exit..."
                exit 1
            fi
            echo "Dependencies installed successfully"
            echo ""
        fi
        # Write stamp (touch it to match requirements.txt mtime)
        touch -r "$REQ_FILE" "$STAMP_FILE" 2>/dev/null || touch "$STAMP_FILE"
    else
        echo "Dependencies OK (cached) ✓"
    fi
fi



# ── PP-OCRv5 PRE-FLIGHT CHECK ─────────────────────────────────────────────────
echo ""
echo "========================================"
echo "PP-OCRv5 Pre-flight Check"
echo "========================================"

PADDLE_OK=true
PADDLE_WARN=false

# Check 1: paddleocr package
if pip show paddleocr > /dev/null 2>&1; then
    PADDLE_VER=$(pip show paddleocr 2>/dev/null | grep "^Version:" | awk '{print $2}')
    echo "  ✅ paddleocr        : $PADDLE_VER"
else
    echo "  ❌ paddleocr        : NOT INSTALLED"
    echo "     → Run: pip install paddleocr paddlepaddle"
    PADDLE_OK=false
fi

# Check 2: paddlepaddle package
if pip show paddlepaddle > /dev/null 2>&1; then
    PP_VER=$(pip show paddlepaddle 2>/dev/null | grep "^Version:" | awk '{print $2}')
    echo "  ✅ paddlepaddle     : $PP_VER"
else
    echo "  ❌ paddlepaddle     : NOT INSTALLED"
    PADDLE_OK=false
fi

# Check 3: paddlex package
if pip show paddlex > /dev/null 2>&1; then
    PX_VER=$(pip show paddlex 2>/dev/null | grep "^Version:" | awk '{print $2}')
    echo "  ✅ paddlex          : $PX_VER"
else
    echo "  ⚠️  paddlex         : not found (optional but recommended)"
    PADDLE_WARN=true
fi

# Check 4: PP-OCRv5 recognition model on disk
REC_MODEL="$HOME/.paddlex/official_models/te_PP-OCRv5_mobile_rec/inference.pdiparams"
if [ -f "$REC_MODEL" ]; then
    REC_SIZE=$(du -sh "$REC_MODEL" 2>/dev/null | awk '{print $1}')
    echo "  ✅ rec model on disk: te_PP-OCRv5_mobile_rec ($REC_SIZE)"
else
    echo "  ⚠️  rec model       : te_PP-OCRv5_mobile_rec NOT found in ~/.paddlex"
    echo "     → Will auto-download on first use (~7.5MB)"
    PADDLE_WARN=true
fi

# Check 5: PP-OCRv5 detection model on disk
DET_MODEL="$HOME/.paddlex/official_models/PP-OCRv5_mobile_det/inference.pdiparams"
if [ -f "$DET_MODEL" ]; then
    DET_SIZE=$(du -sh "$DET_MODEL" 2>/dev/null | awk '{print $1}')
    echo "  ✅ det model on disk: PP-OCRv5_mobile_det ($DET_SIZE)"
else
    echo "  ⚠️  det model       : PP-OCRv5_mobile_det NOT found in ~/.paddlex"
    echo "     → Will auto-download on first use (~4MB)"
    PADDLE_WARN=true
fi

# Check 6: Tesseract fallback available
if command -v tesseract > /dev/null 2>&1; then
    TESS_VER=$(tesseract --version 2>&1 | head -1)
    echo "  ✅ Tesseract fallback: $TESS_VER"
else
    echo "  ❌ Tesseract        : NOT FOUND — fallback engine unavailable!"
    echo "     → Install: sudo apt-get install tesseract-ocr tesseract-ocr-tel"
    PADDLE_OK=false
fi

# Summary & decision
echo ""
if [ "$PADDLE_OK" = false ]; then
    echo "  ⛔ PP-OCRv5 CANNOT start — critical packages missing (see above)"
    echo "  → Starting in TESSERACT-ONLY mode as emergency fallback"
    echo "  → Set USE_PADDLE_V5 = False in src/app.py to suppress this warning"
    echo ""
    export FORCE_TESSERACT_MODE=1
elif [ "$PADDLE_WARN" = true ]; then
    echo "  ⚠️  PP-OCRv5 ready with warnings (models will download on first use)"
else
    echo "  ✅ PP-OCRv5 fully ready — all checks passed"
fi

echo "========================================"
echo ""

# ── LAUNCH ────────────────────────────────────────────────────────────────────
echo "Starting Enhanced Telugu OCR Server..."
echo ""
echo "OCR Engine Mode (set USE_PADDLE_V5 in src/app.py to toggle):"
if [ "$PADDLE_OK" = false ]; then
echo "  🔧 TESSERACT primary (emergency fallback — PP-OCRv5 packages missing)"
else
echo "  🏏 PP-OCRv5 primary  — te_PP-OCRv5_mobile_rec (fast, Telugu-native)"
echo "  🔧 Tesseract fallback — auto if quality gate fails"
echo "  🚀 Gemini Vision OCR  — complex pages (score > 85)"
fi
echo ""
echo "  http://localhost:5001"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# ── Disable PaddlePaddle OneDNN (MKL-DNN) to prevent PIR executor crash ──
# Error: ConvertPirAttribute2RuntimeAttribute not support pir::ArrayAttribute<pir::DoubleAttribute>
# MUST be exported BEFORE python3 starts — C++ gflags reads at .so load time.
export FLAGS_use_mkldnn=0
export FLAGS_mkldnn_cache_capacity=0

# Start the Flask application
python3 src/app.py

read -p "Press Enter to exit..."
