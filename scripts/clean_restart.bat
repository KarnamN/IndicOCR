@echo off
REM Clean Restart Script - Clears Python cache and restarts server

echo ========================================
echo PDF to EPUB Converter - Clean Restart
echo ========================================
echo.

echo Clearing Python cache...
powershell -Command "Get-ChildItem -Path src -Recurse -Filter '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue"
powershell -Command "Get-ChildItem -Path src -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
echo Cache cleared.
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

echo.
echo Starting server on http://localhost:5001
echo.

REM ── Disable PaddlePaddle OneDNN (MKL-DNN) to prevent PIR executor crash ──
SET FLAGS_use_mkldnn=0
SET FLAGS_mkldnn_cache_capacity=0
SET PYTHONUTF8=1

python src/app.py

pause

