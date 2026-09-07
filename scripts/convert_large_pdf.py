
"""
Test script for optimized PDF to EPUB converter
Use this to convert large PDFs without hanging WSL
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
import logging
import argparse # Added import for argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define the convert_large_pdf function
def convert_large_pdf(input_path, output_path, chunk_size, workers, dpi, title, author):
    """
    Converts a large PDF to EPUB using the optimized v2 converter.
    """
    logger.info(f"Starting conversion of '{input_path}' to '{output_path}'")
    logger.info(f"Settings: batch_size={chunk_size}, workers={workers}, dpi={dpi}, title='{title}', author='{author}'")

    converter = OptimizedPDFToEPUBConverter(
        language="tel+eng",
        dpi=dpi,
        detect_tables=False,
        preserve_images=True,
        max_workers=workers,
        enable_parallel=True,
        batch_size=chunk_size
    )
    
    success = converter.convert_streaming(
        pdf_path=Path(input_path),
        epub_path=Path(output_path),
        title=title,
        author=author
    )
    if success:
        logger.info(f"Conversion complete. EPUB saved to '{output_path}'")
    else:
        logger.error("Conversion failed.")



def main(): # Added main function
    parser = argparse.ArgumentParser(
        description='Convert large PDFs to EPUB without hanging WSL'
    )
    parser.add_argument('input', help='Input PDF file')
    parser.add_argument('output', help='Output EPUB file')
    parser.add_argument('--chunk-size', type=int, default=10,
                       help='Pages per chunk (default: 10, use 5 for 400+ pages)')
    parser.add_argument('--workers', type=int, default=2,
                       help='Max workers (default: 2, use 1 for 400+ pages)')
    parser.add_argument('--dpi', type=int, default=150,
                       help='DPI (default: 150, max recommended: 200)')
    parser.add_argument('--title', default='Converted Document',
                       help='Book title')
    parser.add_argument('--author', default='Unknown',
                       help='Book author')
    
    args = parser.parse_args()
    
    # Recommend settings based on file
    try:
        import fitz
        doc = fitz.open(args.input)
        page_count = len(doc)
        doc.close()
        
        print(f"\n📄 PDF has {page_count} pages")
        
        # Auto-adjust settings for very large files
        if page_count > 400:
            print(f"⚠️  Large PDF detected! Recommending conservative settings:")
            print(f"   - Chunk size: 5 pages")
            print(f"   - Workers: 1")
            print(f"   - DPI: 150")
            if args.chunk_size > 5:
                args.chunk_size = 5
            if args.workers > 1:
                args.workers = 1
            if args.dpi > 150:
                args.dpi = 150
    except Exception as e:
        print(f"⚠️  Could not read PDF: {e}")
    
    convert_large_pdf(
        args.input,
        args.output,
        chunk_size=args.chunk_size,
        workers=args.workers,
        dpi=args.dpi,
        title=args.title,
        author=args.author
    )

if __name__ == '__main__': # Added main execution block
    main()

