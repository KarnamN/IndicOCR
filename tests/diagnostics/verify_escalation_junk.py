import os
import sys
from pathlib import Path
import logging
import json

# Add src to python path
sys.path.append(str(Path(__file__).parent / 'src'))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
import config

# Setup logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TestRun")

def main():
    pdf_path = Path("/mnt/c/Myfolder/Ebooks-foldersample/OnePlus/01-2026/28-03-2026/siddhayogi_pungavulu_split.pdf")
    output_dir = Path("/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/outputs/test_batch")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"🚀 Starting test run on: {pdf_path}")
    logger.info(f"   Target pages: 1-10")
    
    # Set workers to 1 for perfectly clear serial logs
    config.MAX_WORKERS = 1
    config.BATCH_SIZE = 1
    config.ENABLE_AUTOMATIC_GEMINI_RESCUE = False  # Disabled to focus on Tesseract debugging
    
    # Target specific pages to show normal, complex, and junk handling
    target_pages = list(range(1, 11))
    
    # DISABLE TABLES AND IMAGES as requested
    converter = OptimizedPDFToEPUBConverter(
        only_pages=target_pages,
        detect_tables=False,
        preserve_images=False
    )
    
    output_epub = output_dir / "test_rescue.epub"
    
    try:
        success = converter.convert_streaming(
            pdf_path=pdf_path,
            output_path=output_epub
        )
        
        if success:
            logger.info("✅ Test run completed successfully!")
            logger.info(f"   Output saved to: {output_dir}")
            
            # Print a summary of the rescue report
            if converter.rescue_report:
                logger.info("\n📊 RESCUE REPORT SUMMARY:")
                for rescue in converter.rescue_report:
                    reason = rescue.get('reason', '')
                    actual = rescue.get('actual_lines', '?')
                    est = rescue.get('estimated_lines', '?')
                    logger.info(f"   - Page {rescue['page_num']}: Engine {rescue['engine']} ({rescue['status']}) - {reason} - lines: {actual}/{est}")
            else:
                logger.info("\nℹ️ No escalations needed - Tesseract handled all pages.")
        else:
            logger.error("❌ Conversion failed.")
            
    except Exception as e:
        logger.error(f"❌ Test run aborted: {e}")

if __name__ == "__main__":
    main()
