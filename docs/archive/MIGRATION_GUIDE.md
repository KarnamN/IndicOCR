# Project Reorganization - Migration Guide

## Overview
The project has been reorganized into a cleaner structure with separate directories for source code, tests, documentation, scripts, and data.

## New Structure

```
Chatbot/
├── src/              # All source code
├── tests/            # All tests and demos
├── docs/             # All documentation
│   ├── guides/       # Detailed guides
│   └── examples/     # Example outputs
├── scripts/          # Utility scripts
├── utils/            # Configuration files
└── data/             # Data directories
    ├── uploads/
    ├── outputs/
    └── temp/
```

## Changes Made

### 1. Source Code → `src/`
Moved all Python modules:
- `app.py`
- `config.py`
- `epub_builder.py`
- `filename_utils.py`
- `folder_scanner.py`
- `mobi_converter.py`
- `ocr_processor.py`
- `pdf_to_epub_converter.py`
- `pdf_to_epub_converter_optimized.py`
- `table_detector.py`
- `static/` (web UI files)
- `templates/` (HTML templates)

### 2. Tests → `tests/`
Moved all test files:
- `test_filename_utils.py`
- `test_installation.py`
- `demo_folder_scanner.py`
- Test data folders

### 3. Documentation → `docs/`
Moved all markdown files to `docs/guides/`:
- All `.md` files (except root README.md)
- Setup guides
- Usage examples
- Architecture docs
- Troubleshooting guides

### 4. Scripts → `scripts/`
Moved utility scripts:
- `convert_large_pdf.py`
- `setup_wsl.sh`
- `start.sh`
- `start.bat`

### 5. Configuration → `utils/`
Moved configuration files:
- `requirements.txt`
- `.gitignore`

### 6. Data → `data/`
Created new data directory:
- `data/uploads/` - For uploaded PDFs
- `data/outputs/` - For generated files (if not using custom path)
- `data/temp/` - For temporary files

## Updated Paths in Code

### config.py
```python
# Old:
BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / 'uploads'

# New:
BASE_DIR = Path(__file__).parent.parent  # Project root
DATA_DIR = BASE_DIR / 'data'
UPLOAD_FOLDER = DATA_DIR / 'uploads'
```

## How to Use After Reorganization

### Running the Web Application
```bash
# Old:
python3 app.py

# New:
python3 src/app.py
```

### Running Folder Scanner
```bash
# Old:
python3 folder_scanner.py /path/to/folder

# New:
python3 src/folder_scanner.py /path/to/folder
```

### Running Tests
```bash
# Old:
python3 test_filename_utils.py

# New:
python3 tests/test_filename_utils.py
```

### Running Scripts
```bash
# Old:
python3 convert_large_pdf.py input.pdf output.epub

# New:
python3 scripts/convert_large_pdf.py input.pdf output.epub
```

### Installing Dependencies
```bash
# Old:
pip install -r requirements.txt

# New:
pip install -r utils/requirements.txt
```

## Cleanup Old Directories

The old `uploads/`, `outputs/`, and `temp/` directories still exist at the root level. You can:

1. **Keep them** - They won't interfere with the new structure
2. **Delete them** - Once you've verified everything works with the new structure

To delete old directories:
```bash
cd /mnt/c/Workspace/Antigravity_workspace/Chatbot
rm -rf uploads outputs temp
```

## Benefits of New Structure

### ✅ Better Organization
- Clear separation of concerns
- Easy to find files
- Professional project structure

### ✅ Easier Development
- Source code isolated in `src/`
- Tests separated in `tests/`
- Documentation centralized in `docs/`

### ✅ Cleaner Root Directory
- Only essential files at root
- Less clutter
- Better overview

### ✅ Scalability
- Easy to add new modules
- Clear where new files should go
- Better for version control

## Verification

### Check Structure
```bash
cd /mnt/c/Workspace/Antigravity_workspace/Chatbot
ls -la
```

You should see:
- `src/` - Source code
- `tests/` - Tests
- `docs/` - Documentation
- `scripts/` - Scripts
- `utils/` - Config files
- `data/` - Data directories
- `README.md` - Main readme
- `converter.log` - Log file

### Test the Application
```bash
# Test imports
python3 -c "import sys; sys.path.insert(0, 'src'); import config; print('✓ Config imports successfully')"

# Run tests
python3 tests/test_filename_utils.py

# Run web app (Ctrl+C to stop)
python3 src/app.py
```

## Updating Your Workflow

### If You Have Scripts/Aliases
Update any scripts or aliases that reference the old paths:

```bash
# Old alias:
alias convert-pdf='python3 /path/to/Chatbot/app.py'

# New alias:
alias convert-pdf='python3 /path/to/Chatbot/src/app.py'
```

### If You Import Modules
If you have external scripts that import from this project:

```python
# Old:
import sys
sys.path.append('/path/to/Chatbot')
import filename_utils

# New:
import sys
sys.path.append('/path/to/Chatbot/src')
import filename_utils
```

## Rollback (If Needed)

If you need to rollback to the old structure:

1. Copy files back from subdirectories to root
2. Revert `config.py` changes
3. Delete new directories

However, the new structure is recommended for better organization.

## Next Steps

1. ✅ Verify all imports work
2. ✅ Test the web application
3. ✅ Run test suite
4. ✅ Update any external scripts/aliases
5. ✅ Clean up old directories (optional)
6. ✅ Update documentation links (if any)

## Support

If you encounter any issues:
1. Check `converter.log` for errors
2. Verify paths in `src/config.py`
3. Ensure all files were moved correctly
4. Run `python3 tests/test_installation.py`

---

**Migration Date**: 2025-11-23  
**Project Version**: 2.0 (Reorganized Structure)  
**Status**: ✅ Complete
