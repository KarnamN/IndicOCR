@echo off
REM Quick Start Script for PDF to EPUB Converter with Enhanced Telugu OCR

echo ========================================
echo PDF to EPUB Converter - Quick Start
echo Enhanced Telugu OCR with Vatulu ^& Guninthalu Detection
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "wenv\" (
    echo Creating virtual environment...
    python -m venv wenv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        echo Please ensure Python is installed and in PATH
        pause
        exit /b 1
    )
    echo Virtual environment created successfully
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call wenv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Check and install dependencies (fast: uses pip, no heavy imports)
echo Checking dependencies...
pip show paddleocr >nul 2>&1
if errorlevel 1 (
    echo Installing/updating dependencies...
    pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
    echo Dependencies installed successfully
    echo.
)

echo.
echo ========================================
echo Starting Enhanced Telugu OCR Server...
echo ========================================
echo.
echo Features:
echo   - Tesseract OCR (primary, fast)
echo   - Gemini Vision OCR (complex pages fallback)
echo   - Telugu Vatulu detection (subscript consonants)
echo   - Telugu Guninthalu detection (vowel modifiers)
echo   - Adaptive complexity-based processing
echo.
echo Server will be available at:
echo   http://localhost:5001
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM ── Disable PaddlePaddle OneDNN (MKL-DNN) to prevent PIR executor crash ──
REM    Error: ConvertPirAttribute2RuntimeAttribute not support pir::ArrayAttribute<pir::DoubleAttribute>
REM    Must be set BEFORE python starts (C++ gflags reads at .so load time)
SET FLAGS_use_mkldnn=0
SET FLAGS_mkldnn_cache_capacity=0
SET PYTHONUTF8=1

python src/app.py

pause

