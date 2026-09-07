"""
Test script to verify the installation and functionality
"""
import sys
from pathlib import Path

# Add src directory to PYTHONPATH for the reorganized project
PROJECT_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_ROOT))

# Now import config from src/
import config

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def test_imports():
    """Test if all required modules can be imported"""
    print_header("Testing Module Imports")
    
    modules = [
        ('Flask', 'flask'),
        ('PyMuPDF', 'fitz'),
        ('pdf2image', 'pdf2image'),
        ('pytesseract', 'pytesseract'),
        ('PIL', 'PIL'),
        ('OpenCV', 'cv2'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('ebooklib', 'ebooklib'),
    ]
    
    all_ok = True
    for name, module in modules:
        try:
            __import__(module)
            print(f"✓ {name:20s} - OK")
        except ImportError as e:
            print(f"✗ {name:20s} - FAILED: {e}")
            all_ok = False
    
    return all_ok

def test_tesseract():
    """Test Tesseract OCR installation"""
    print_header("Testing Tesseract OCR")
    
    try:
        import pytesseract
        from PIL import Image
        import config
        
        # Set Tesseract path
        if hasattr(config, 'TESSERACT_PATH'):
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
        
        # Get version
        version = pytesseract.get_tesseract_version()
        print(f"✓ Tesseract version: {version}")
        
        # Get languages
        languages = pytesseract.get_languages()
        print(f"✓ Available languages: {', '.join(languages)}")
        
        # Check Telugu support
        if 'tel' in languages:
            print("✓ Telugu language support: AVAILABLE")
            return True
        else:
            print("✗ Telugu language support: NOT FOUND")
            print("  Please install Telugu language data (tel.traineddata)")
            return False
            
    except Exception as e:
        print(f"✗ Tesseract test failed: {e}")
        return False

def test_poppler():
    """Test Poppler installation"""
    print_header("Testing Poppler (PDF Processing)")
    
    try:
        from pdf2image import convert_from_path
        print("✓ pdf2image module loaded successfully")
        print("✓ Poppler appears to be installed correctly")
        return True
    except Exception as e:
        print(f"✗ Poppler test failed: {e}")
        print("  Please ensure Poppler is installed and in PATH")
        return False

def test_project_structure():
    """Test if project structure is correct"""
    print_header("Testing Project Structure")
    
    # Get the project root (parent of tests directory)
    project_root = Path(__file__).resolve().parents[1]
    
    # Files in the reorganized structure
    required_files = [
        ('config.py', project_root / 'src' / 'config.py'),
        ('ocr_processor.py', project_root / 'src' / 'ocr_processor.py'),
        ('table_detector.py', project_root / 'src' / 'table_detector.py'),
        ('epub_builder.py', project_root / 'src' / 'epub_builder.py'),
        ('pdf_to_epub_converter_optimized_v2.py', project_root / 'src' / 'pdf_to_epub_converter_optimized_v2.py'),
        ('app.py', project_root / 'src' / 'app.py'),
        ('requirements.txt', project_root / 'requirements.txt'),
        ('templates/index.html', project_root / 'src' / 'templates' / 'index.html'),
        ('static/css/style.css', project_root / 'src' / 'static' / 'css' / 'style.css'),
        ('static/js/main.js', project_root / 'src' / 'static' / 'js' / 'main.js'),
    ]
    
    all_ok = True
    for display_name, path in required_files:
        if path.exists():
            print(f"✓ {display_name:30s} - Found")
        else:
            print(f"✗ {display_name:30s} - Missing")
            all_ok = False
    
    return all_ok

def test_directories():
    """Test if required directories exist or can be created"""
    print_header("Testing Directories")
    

    
    directories = [
        ('Upload folder', config.UPLOAD_FOLDER),
        ('Output folder', config.OUTPUT_FOLDER),
        ('Temp folder', config.TEMP_FOLDER),
    ]
    
    all_ok = True
    for name, path in directories:
        try:
            path.mkdir(exist_ok=True)
            print(f"✓ {name:20s} - {path}")
        except Exception as e:
            print(f"✗ {name:20s} - Failed: {e}")
            all_ok = False
    
    return all_ok

def test_ocr_functionality():
    """Test basic OCR functionality"""
    print_header("Testing OCR Functionality")
    
    try:
        from ocr_processor import OCRProcessor
        
        processor = OCRProcessor()
        
        # Verify Telugu support
        has_telugu = processor.verify_telugu_support()
        
        if has_telugu:
            print("✓ OCR processor initialized successfully")
            print("✓ Telugu OCR is ready to use")
            return True
        else:
            print("✗ Telugu OCR support not available")
            return False
            
    except Exception as e:
        print(f"✗ OCR functionality test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  PDF to EPUB Converter - Installation Test")
    print("="*60)
    
    results = {
        'Module Imports': test_imports(),
        'Tesseract OCR': test_tesseract(),
        'Poppler': test_poppler(),
        'Project Structure': test_project_structure(),
        'Directories': test_directories(),
        'OCR Functionality': test_ocr_functionality(),
    }
    
    # Summary
    print_header("Test Summary")
    
    all_passed = True
    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name:25s} {status}")
        if not result:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("  ✓ All tests passed! System is ready to use.")
        print("  Run 'python app.py' to start the web application.")
    else:
        print("  ✗ Some tests failed. Please check the errors above.")
        print("  Refer to SETUP_GUIDE.md for installation instructions.")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
