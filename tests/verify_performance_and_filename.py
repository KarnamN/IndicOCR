
import sys
import os
import time
from pathlib import Path
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
from filename_utils import generate_output_filenames
import config

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_filename_logic():
    print("\nTesting Filename Logic:")
    print("-" * 20)
    
    test_file = "తెలుగు_వ్యాకరణం.pdf"
    timestamp = "20231123"
    job_id = "test1234"
    
    epub, mobi = generate_output_filenames(test_file, timestamp, job_id)
    print(f"Input: {test_file}")
    print(f"EPUB: {epub}")
    print(f"MOBI: {mobi}")
    
    # Expected: Transliterated name
    if "telugu_vyakaranam" in epub or "telugu" in epub:
        print("✓ Filename transliteration passed")
    else:
        print("✗ Filename transliteration failed")

def test_conversion_performance():
    print("\nTesting Conversion Performance (PyMuPDF):")
    print("-" * 20)
    
    input_pdf = Path("tests/dummy_test.pdf")
    output_epub = Path("tests/output_test.epub")
    
    if not input_pdf.exists():
        print(f"Skipping performance test: {input_pdf} not found")
        return

    converter = OptimizedPDFToEPUBConverter(
        language='tel+eng',
        dpi=150, # Lower DPI for quick test
        detect_tables=False,
        preserve_images=True,
        max_workers=2
    )
    
    start_time = time.time()
    try:
        success = converter.convert_streaming(
            input_pdf,
            output_epub,
            title="Test Book",
            max_pages=5 # Limit to 5 pages for quick test
        )
        end_time = time.time()
        
        if success:
            print(f"✓ Conversion successful in {end_time - start_time:.2f}s")
            print(f"✓ Output created: {output_epub}")
        else:
            print("✗ Conversion failed")
            
    except Exception as e:
        print(f"✗ Conversion error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_filename_logic()
    test_conversion_performance()
