import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
import fitz # PyMuPDF
from PIL import Image
import logging

# Setup logging to console
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_pages(pdf_path, pages_to_test):
    """Test OCR quality for specific pages or ranges."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}")
        return

    output_dir = Path("test_results")
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir) # Clear old results
    output_dir.mkdir(exist_ok=True)

    print(f"====================================================")
    print(f"🧪 TESTING QUALITY: {pdf_path.name}")
    print(f"Pages to test: {pages_to_test}")
    print(f"====================================================\n")

    # Initialize converter
    converter = OptimizedPDFToEPUBConverter(language='tel+eng', dpi=300)
    
    doc = fitz.open(pdf_path)
    total_doc_pages = len(doc)
    
    for p in pages_to_test:
        page_idx = p - 1 # 0-indexed
        if page_idx < 0 or page_idx >= total_doc_pages:
            print(f"⚠️ Skipping invalid page: {p}")
            continue

        print(f"📄 Processing Page {p}...")
        
        # Render page to image
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Run analysis
        processor, analysis = converter.adaptive_factory.get_processor_for_page(img, 'tel+eng')
        
        print(f"   • Recommended Engine: {analysis['recommended_engine'].upper()}")
        print(f"   • Complexity Score: {analysis['complexity_score']:.1f}")
        print(f"   • Reason: {analysis['reasoning']}")
        
        # OCR
        text = processor.extract_text(img)
        
        # Save results
        result_file = output_dir / f"page_{p}_result.txt"
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(f"--- METADATA ---\n")
            f.write(f"Page: {p}\n")
            f.write(f"Engine: {analysis['recommended_engine']}\n")
            f.write(f"Complexity: {analysis['complexity_score']:.1f}\n")
            f.write(f"Reason: {analysis['reasoning']}\n")
            f.write(f"Has Illustration: {analysis.get('has_illustrations', False)}\n\n")
            f.write(f"--- OCR TEXT ---\n")
            f.write(text)
        
        # Decide what images to save (Mimicking the main converter's STRICT PRIORITY logic)
        text_len = len(text.strip())
        page_area = img.width * img.height
        is_table = analysis.get('has_table', False)
        
        # Check for Mostly Image Page
        is_mostly_img = (text_len < 200 and analysis['complexity_score'] > 60)
        for region in analysis.get('image_regions', []):
            if (region[2] * region[3]) > (page_area * 0.7):
                is_mostly_img = True
                break

        # Decision making
        if is_table or is_mostly_img:
            # Mode A: Full Page Only
            img.save(output_dir / f"page_{p}_image.jpg", quality=80)
            reason = "Table" if is_table else "Full Image"
            print(f"   🖼️  Saved Full Page ({reason}). Redundancy cleanup: skipped partial crops.")
            
        elif analysis.get('image_regions'):
            # Mode B: Partial Crops Only
            for i, region in enumerate(analysis['image_regions']):
                x, y, bw, bh = region
                sub_img = img.crop((x, y, x+bw, y+bh))
                sub_img.save(output_dir / f"page_{p}_illustration_{i+1}.jpg")
                print(f"   📸 Saved partial illustration {i+1} ({bw}x{bh}). Skipped full-page background.")
        
        else:
            # Mode C: Basic Page (Save full page only if no partials exist)
            img.save(output_dir / f"page_{p}_image.jpg", quality=80)
            print(f"   📄 Saved Full Page (no specific regions detected)")

    print(f"\n🏁 Test Complete! Inside 'test_results' folder.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/test_quality.py <path_to_pdf> [page1] [page2] [page3]...")
        sys.exit(1)
        
    pdf = sys.argv[1]
    
    # Identify if user provided a range or a list
    # If 3 args and 2nd < 3rd, treat as range for backward compatibility
    # Otherwise, treat all numbers as a specific list
    remaining_args = sys.argv[2:]
    pages = []
    
    # Check if we have a single string with commas like "18,60,61"
    raw_pages = []
    for arg in remaining_args:
        # Replace commas with spaces and split
        parts = arg.replace(',', ' ').split()
        raw_pages.extend(parts)

    try:
        if len(raw_pages) == 2 and int(raw_pages[0]) < int(raw_pages[1]):
            # Range mode: Start End (if exactly two numbers and first < second)
            pages = list(range(int(raw_pages[0]), int(raw_pages[1]) + 1))
        else:
            # List mode: 18,60,61 or 18 60 61
            pages = [int(x) for x in raw_pages]
    except ValueError as e:
        print(f"Error: Page numbers must be integers. Found: {raw_pages}")
        sys.exit(1)
    
    if not pages:
        pages = [1] # Default to page 1
        
    test_pages(pdf, pages)
