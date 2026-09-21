# IndicOCR

IndicOCR converts scanned Telugu and mixed Telugu/English PDFs into reflowable EPUB files, with optional MOBI output. It combines PP-OCRv5, Tesseract, layout analysis, Telugu post-processing, and a Flask web interface for long-running conversions.

## Features

- Telugu and English OCR with automatic fallback and quality checks
- PDF to EPUB conversion with image preservation
- Optional MOBI conversion through Calibre
- Double-page splitting, column-aware OCR, table and illustration handling
- Real-time conversion progress through Flask-SocketIO
- Folder scanning and Telugu filename transliteration utilities
- Repair and resume workflows for interrupted or low-quality conversions

## Requirements

- Python 3.10 or newer
- Linux or WSL is recommended for PP-OCRv5 and PaddleX
- Tesseract OCR with Telugu and English language data
- Poppler utilities for PDF rendering
- Calibre is optional and only required for MOBI output

Windows is supported for development and Tesseract-primary operation. See
[`requirements-windows.txt`](requirements-windows.txt) and [`docs/WSL_FIX_GUIDE.md`](docs/WSL_FIX_GUIDE.md).

## Installation

### Linux or WSL

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-tel tesseract-ocr-eng poppler-utils
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For MOBI output, also install `calibre`. Paddle models are downloaded by PaddleX on first use.

### Windows

```powershell
py -3.10 -m venv wenv
wenv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows.txt
```

Install Tesseract separately and make sure it is available in `PATH`, or configure its path in [`src/config.py`](src/config.py).

## Configuration

Copy [`.env.example`](.env.example) to `.env` when using optional cloud OCR providers. Never commit `.env` or service-account JSON files.

## Run

From the repository root:

```bash
python src/app.py
```

Open <http://localhost:5001>. On Windows, `start.bat` creates a virtual environment and starts the server. On Linux or WSL, `scripts/start.sh` performs dependency and OCR pre-flight checks before starting it.

Useful command-line entry points:

```bash
python scripts/convert_large_pdf.py input.pdf output.epub
python src/folder_scanner.py /path/to/folder -o report.txt
```

## Project Layout

```text
src/       Flask app, OCR engines, conversion pipeline, templates, and static files
scripts/   Batch conversion, benchmarking, setup, and maintenance utilities
tests/     Focused regression and installation checks
docs/      Architecture, setup, repair, and OCR quality notes
data/      Runtime uploads, temporary files, and generated output (ignored by Git)
```

The processing pipeline and current engine routing are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tests

```bash
python tests/test_filename_utils.py
python tests/test_transliteration.py
python tests/test_border_detection.py
```

Run [`tests/test_installation.py`](tests/test_installation.py) after installing Tesseract, Poppler, and the Python dependencies to validate the complete local environment.

## Privacy and Generated Files

Uploaded PDFs, OCR output, logs, model caches, credentials, and scratch data are excluded by [`.gitignore`](.gitignore).

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PDF_TOOLS.md`](docs/PDF_TOOLS.md)
- [`docs/CORRECTION_AND_REPAIR.md`](docs/CORRECTION_AND_REPAIR.md)
- [`docs/SKIP_PAGES.md`](docs/SKIP_PAGES.md)
- [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md)
