import sys
from pathlib import Path
import os

# Add src to path - handle both Windows and WSL
if os.name == 'nt':
    sys.path.append(str(Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\src')))
else:
    sys.path.append('/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/src')

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
import config

def test_first_5():
    pdf_path = Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\data\uploads\20260329_144957_1aebceb7_siddhayogi_pungavulu_split.pdf')
    if os.name != 'nt':
        pdf_path = Path('/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/data/uploads/20260329_144957_1aebceb7_siddhayogi_pungavulu_split.pdf')
    
    pages_to_test = [1, 2, 3, 4, 5]
    
    print(f"--- Testing Tesseract Optimization (450 DPI + PSM 6) ---")
    print(f"Pages: {pages_to_test}")
    
    # Initialize converter
    converter = OptimizedPDFToEPUBConverter(
        only_pages=pages_to_test,
        session_id="test_opt_v1"
    )
    
    # Run conversion
    output_path = Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\data\temp\test_first_5.epub')
    if os.name != 'nt':
        output_path = Path('/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/data/temp/test_first_5.epub')
        
    success = converter.convert_streaming(pdf_path, output_path)
    
    if success:
        print("\nTest complete! View the results in converter.log.")
    else:
        print("\nTest failed.")

if __name__ == "__main__":
    test_first_5()
