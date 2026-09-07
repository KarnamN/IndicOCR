import sys
from pathlib import Path
import os

# Add src to path
sys.path.append(str(Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\src')))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
import config

def test_page_111():
    pdf_path = Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\data\uploads\20260329_144957_1aebceb7_siddhayogi_pungavulu_split.pdf')
    page_to_test = 111  # 1-indexed
    
    # Initialize converter
    converter = OptimizedPDFToEPUBConverter(
        only_pages=[page_to_test],
        session_id="test_450dpi"
    )
    
    print(f"--- Testing Tesseract Optimization on Page {page_to_test} ---")
    print(f"Settings: DPI={config.OCR_DPI}, CONFIG={config.TESSERACT_CONFIG}")
    
    # Run conversion for just this page
    output_path = Path(r'c:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026\data\temp\test_page_111.epub')
    success = converter.convert_streaming(pdf_path, output_path)
    
    if success:
        print("\n✅ Test complete. Check the logs above for 'Lines:' count.")
    else:
        print("\n❌ Test failed.")

if __name__ == "__main__":
    test_page_111()
