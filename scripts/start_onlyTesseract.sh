#!/bin/bash

echo "════════════════════════════════════════════════════════"
echo "  PDF to EPUB Converter — Tesseract-Only Mode"
echo "  Fast, lightweight Telugu OCR (no EasyOCR/PyTorch)"
echo "════════════════════════════════════════════════════════"
echo ""

# ─── Step 1: Check Tesseract is installed ───
echo "🔍 Checking Tesseract installation..."
if ! command -v tesseract &> /dev/null; then
    echo "❌ Tesseract is not installed!"
    echo "   Install with: sudo apt install tesseract-ocr tesseract-ocr-tel"
    read -p "Press Enter to exit..."
    exit 1
fi

TESS_VERSION=$(tesseract --version 2>&1 | head -1)
echo "   ✅ Found: $TESS_VERSION"

# ─── Step 2: Check Telugu language data ───
echo ""
echo "🔍 Checking Telugu language data..."
TEL_FILE=$(find /usr/share/tesseract-ocr -name "tel.traineddata" 2>/dev/null | head -1)

if [ -z "$TEL_FILE" ]; then
    echo "❌ Telugu language data not found!"
    echo "   Installing tesseract-ocr-tel..."
    sudo apt-get install -y tesseract-ocr-tel
    TEL_FILE=$(find /usr/share/tesseract-ocr -name "tel.traineddata" 2>/dev/null | head -1)
    if [ -z "$TEL_FILE" ]; then
        echo "❌ Failed to install Telugu data"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Check if tessdata_best is installed (file size > 4MB = best quality)
TEL_SIZE=$(stat -f%z "$TEL_FILE" 2>/dev/null || stat -c%s "$TEL_FILE" 2>/dev/null)
TEL_SIZE_MB=$((TEL_SIZE / 1024 / 1024))

if [ "$TEL_SIZE_MB" -lt 4 ]; then
    echo "   ⚠️  Found tessdata_fast ($TEL_SIZE_MB MB) — upgrading to tessdata_best..."
    echo "   📥 Downloading tessdata_best Telugu model (≈9 MB)..."
    sudo wget -q -O "$TEL_FILE" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata
    if [ $? -eq 0 ]; then
        NEW_SIZE=$(stat -f%z "$TEL_FILE" 2>/dev/null || stat -c%s "$TEL_FILE" 2>/dev/null)
        NEW_SIZE_MB=$((NEW_SIZE / 1024 / 1024))
        echo "   ✅ Upgraded to tessdata_best ($NEW_SIZE_MB MB)"
    else
        echo "   ⚠️  Download failed — continuing with tessdata_fast"
    fi
else
    echo "   ✅ tessdata_best already installed ($TEL_SIZE_MB MB)"
fi
echo "   📁 Path: $TEL_FILE"

# Also check English data
ENG_FILE=$(find /usr/share/tesseract-ocr -name "eng.traineddata" 2>/dev/null | head -1)
if [ -z "$ENG_FILE" ]; then
    echo "   📥 Installing English language data..."
    sudo apt-get install -y tesseract-ocr-eng
fi

# ─── Step 3: Virtual environment ───
echo ""
echo "🐍 Setting up Python environment..."

if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        echo "   Ensure Python 3 is installed: sudo apt install python3 python3-venv"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "   ✅ Virtual environment created"
fi

source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "❌ Failed to activate virtual environment"
    read -p "Press Enter to exit..."
    exit 1
fi

# ─── Step 4: Install dependencies (lightweight, no PyTorch) ───
echo ""
echo "📦 Checking dependencies..."
if ! pip show flask > /dev/null 2>&1 || ! pip show pytesseract > /dev/null 2>&1; then
    echo "   Installing lightweight dependencies (no PyTorch!)..."
    pip install --upgrade pip -q
    pip install -r requirements-tesseract.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "   ✅ Dependencies installed"
fi

# ─── Step 5: Set PYTHONPATH ───
export PYTHONPATH=$(pwd):$PYTHONPATH

# ─── Step 8: Start the server ───
echo ""
echo "════════════════════════════════════════════════════════"
echo "  🚀 Starting Tesseract-Only OCR Server"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  Mode:       Tesseract Only (no EasyOCR)"
echo "  Language:   Telugu (tel) with tessdata_best"
echo "  Features:"
echo "    ✅ High-quality LSTM Telugu OCR"
echo "    ✅ Image deskew (auto-straighten)"
echo "    ✅ Image sharpening"
echo "    ✅ Telugu post-processing (శ్లో॥ fix, danda normalize)"
echo "    ✅ Vatulu & Guninthalu detection"
echo "    ❌ EasyOCR (disabled for speed & stability)"
echo ""
echo "  URL: http://localhost:5001"
echo "  Press Ctrl+C to stop"
echo ""
echo "════════════════════════════════════════════════════════"
echo ""

python3 src/app.py

read -p "Press Enter to exit..."
