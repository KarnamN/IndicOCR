# PDF to EPUB/MOBI Converter with Telugu Support

A comprehensive PDF to EPUB/MOBI converter with OCR support, Telugu language handling, and folder scanning utilities.

## 🌟 Key Features

- **PDF to EPUB Conversion** - Convert scanned PDFs to EPUB format
- **OCR Support** - Extract text from images using Tesseract OCR
- **Telugu Language** - Full support for Telugu text recognition and filename translation
- **Table Detection** - Automatically detect and extract tables from PDFs
- **MOBI Conversion** - Optional EPUB to MOBI conversion using Calibre
- **Web Interface** - User-friendly web UI for easy conversions
- **Folder Scanner** - Recursively scan folders with Telugu filename translation
- **Large PDF Support** - Optimized processing for large PDF files

## 📁 Project Structure

```
Chatbot/
├── src/           # Source code
├── tests/         # Tests and demos
├── docs/          # Documentation
├── scripts/       # Utility scripts
├── utils/         # Configuration files
└── data/          # Data directories (uploads, outputs, temp)
```

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for detailed structure.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Tesseract OCR
- Poppler utilities
- Calibre (optional, for MOBI conversion)

### Installation

1. **Clone the repository**
   ```bash
   cd /mnt/c/Workspace/Antigravity_workspace/Chatbot
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r utils/requirements.txt
   ```

3. **Install system dependencies**
   
   **Ubuntu/Debian:**
   ```bash
   sudo apt-get update
   sudo apt-get install tesseract-ocr tesseract-ocr-tel poppler-utils
   ```
   
   **For MOBI support (optional):**
   ```bash
   sudo apt-get install calibre
   ```

### Running the Application

#### Web Interface
```bash
python3 src/app.py
```
Then open your browser to: `http://localhost:5001`

#### Folder Scanner (CLI)
```bash
python3 src/folder_scanner.py /path/to/folder -o report.txt
```

#### Large PDF Converter (CLI)
```bash
python3 scripts/convert_large_pdf.py input.pdf output.epub
```

## 📖 Documentation

- **[Setup Guide](docs/guides/SETUP_GUIDE.md)** - Detailed installation instructions
- **[Usage Examples](docs/guides/USAGE_EXAMPLES.md)** - How to use the converter
- **[Folder Scanner Guide](docs/guides/FOLDER_SCANNER_GUIDE.md)** - Folder scanning tool
- **[Architecture](docs/guides/ARCHITECTURE.md)** - System architecture overview
- **[Project Structure](docs/PROJECT_STRUCTURE.md)** - Directory organization
- **[WSL Setup](docs/guides/WSL_UBUNTU_SETUP.md)** - Windows Subsystem for Linux setup

## 🎯 Main Features

### 1. PDF to EPUB Conversion
Convert scanned PDFs to EPUB format with OCR:
- Automatic text extraction
- Image preservation
- Table detection
- Telugu language support

### 2. Telugu Support
- **OCR**: Recognize Telugu text in PDFs
- **Filename Translation**: Automatically translate Telugu filenames to English
- **Unicode**: Full Unicode support

### 3. Folder Scanner
Recursively scan folders and generate reports:
- Detect Telugu filenames
- Translate to English
- Generate text and JSON reports
- File statistics and summaries

### 4. Web Interface
User-friendly web UI:
- Drag-and-drop file upload
- Real-time progress tracking
- Download converted files
- Configurable settings

## 🔧 Configuration

Edit `src/config.py` to customize:
- Output directories
- OCR settings (language, DPI)
- Processing options
- Web server settings

## 📊 Examples

### Telugu Filename Translation
```
Input:  తెలుగు_పుస్తకం.pdf
Output: telugu_pustakam.epub
        telugu_pustakam.mobi
```

### Folder Scanning
```bash
python3 src/folder_scanner.py ~/Documents -o inventory.txt -p
```

Output includes:
- File counts and sizes
- Telugu filename translations
- Directory structure
- File type statistics

## 🧪 Testing

Run tests to verify installation:
```bash
python3 tests/test_installation.py
python3 tests/test_filename_utils.py
```

Run demo:
```bash
python3 tests/demo_folder_scanner.py
```

## 📝 Requirements

### Python Packages
See `utils/requirements.txt`:
- Flask
- PyMuPDF
- pdf2image
- pytesseract
- Pillow
- opencv-python
- numpy
- pandas
- ebooklib
- flask-socketio

### System Requirements
- **Tesseract OCR** - Text recognition
- **Poppler** - PDF processing
- **Calibre** - MOBI conversion (optional)

## 🌐 Supported Languages

- Telugu (tel)
- English (eng)
- Mixed Telugu + English (tel+eng)

## 📄 License

[Add your license here]

## 👥 Contributors

[Add contributors here]

## 🐛 Troubleshooting

See documentation in `docs/guides/`:
- [Installation Issues](docs/guides/INSTALLATION_FIX.md)
- [WSL Hanging Solution](docs/guides/WSL_HANGING_SOLUTION.md)
- [OCR Quality Fixes](docs/guides/OCR_QUALITY_FIXES.md)
- [Large PDF Guide](docs/guides/LARGE_PDF_GUIDE.md)

## 📞 Support

For issues and questions:
1. Check the documentation in `docs/guides/`
2. Run `python3 tests/test_installation.py` to verify setup
3. Check logs in `converter.log`

## 🎉 Recent Updates

- ✅ Reorganized project structure
- ✅ Added folder scanner with Telugu translation
- ✅ Improved Telugu transliteration
- ✅ Simplified output filenames
- ✅ Custom output directory support
- ✅ Comprehensive documentation

---

**Version**: 2.0 (Reorganized)  
**Last Updated**: 2025-11-23  
**Status**: Active Development
