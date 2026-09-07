import sys
import os
from pathlib import Path

# Inject config_v5 as global config before importing anything else
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), './src')))
import config_v5 as config_module
sys.modules['config'] = config_module

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter

def main():
    input_pdf = Path("data/uploads/20260606_143544_2f0f09c0_pdf")
    output_epub = Path("test_cli.epub")
    
    if not input_pdf.exists():
        print(f"Error: Input PDF {input_pdf} not found.")
        sys.exit(1)
        
    print(f"Starting test conversion of {input_pdf} -> {output_epub} using config_v5...")
    converter = OptimizedPDFToEPUBConverter(
        language="tel_best+eng",
        dpi=250,
        detect_tables=False,
        preserve_images=True,
        max_workers=4,
        enable_parallel=True,
        batch_size=5
    )
    
    success = converter.convert_streaming(
        input_pdf,
        output_epub,
        title="Test Book Rahasyam",
        author="Author",
        max_pages=5,
        skip_first_pages=2
    )
    
    if success:
        print("SUCCESS! Output saved to test_cli.epub")
    else:
        print("FAILED!")

if __name__ == "__main__":
    main()
