"""
Standalone CLI Tool to split wide-format PDFs into individual portrait pages.
Supports 2-page, 3-page, and 4-page (quad) scans recursively.
"""
import argparse
import os
import fitz
from PIL import Image
from pathlib import Path
import io
import sys

# Add src to path to import PageSplitter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from page_splitter import PageSplitter

def split_pdf_pages(input_path: str, output_path: str, dpi: int = 150, split_threshold: float = 1.15,
                     require_spine_confirmation: bool = True):
    """
    Split a wide PDF into a single-page PDF using non-destructive cropbox slicing.
    Preserves original vector text and image resolution while preventing massive size expansion.
    """
    input_pdf = Path(input_path)
    output_pdf_path = Path(output_path)
    
    if not input_pdf.exists():
        print(f"Error: Input file {input_path} not found.")
        return False
        
    print(f"Processing PDF (non-destructive crop): {input_pdf.name}")
    
    splitter = PageSplitter(aspect_ratio_threshold=split_threshold,
                             require_spine_confirmation=require_spine_confirmation)
    doc = fitz.open(input_path)
    output_doc = fitz.open()
    
    total_pages = len(doc)
    
    for i in range(total_pages):
        print(f"  Analyzing and splitting page {i+1}/{total_pages}...", end="\r")
        page = doc.load_page(i)
        
        # 1. Render at a lower DPI just for visual spine/gutter analysis (saves time and memory)
        # Note: We do NOT insert this rendered image into the output PDF.
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # 2. Get relative split coordinates
        slices = splitter.get_page_slices(img)
        
        # 3. Apply crops to the vector pages
        cropbox = page.cropbox
        rotation = page.rotation
        
        for start_rel, end_rel in slices:
            # Duplicate the original page structure into the output document
            output_doc.insert_pdf(doc, from_page=i, to_page=i)
            new_page = output_doc[-1]
            
            # Map visual vertical slices (from start_rel to end_rel) to cropbox coordinates,
            # taking page rotation into account.
            if rotation in (90, 270):
                # Visual width corresponds to vertical dimension of cropbox
                if rotation == 90:
                    y0 = cropbox.y1 - end_rel * cropbox.height
                    y1 = cropbox.y1 - start_rel * cropbox.height
                else: # 270
                    y0 = cropbox.y0 + start_rel * cropbox.height
                    y1 = cropbox.y0 + end_rel * cropbox.height
                crop_rect = fitz.Rect(cropbox.x0, y0, cropbox.x1, y1)
            else:
                # Visual width corresponds to horizontal dimension of cropbox
                if rotation == 180:
                    x0 = cropbox.x1 - end_rel * cropbox.width
                    x1 = cropbox.x1 - start_rel * cropbox.width
                else: # 0
                    x0 = cropbox.x0 + start_rel * cropbox.width
                    x1 = cropbox.x0 + end_rel * cropbox.width
                crop_rect = fitz.Rect(x0, cropbox.y0, x1, cropbox.y1)
                
            new_page.set_cropbox(crop_rect)
            
    # Save the final PDF with garbage collection and compression options
    print(f"\nSaving final PDF: {output_pdf_path.name}")
    output_doc.save(
        str(output_pdf_path),
        garbage=3,            # eliminate unused objects
        deflate=True,         # compress streams
        clean=True            # sanitize content streams
    )
    output_doc.close()
    doc.close()
    
    print("✓ Success! PDF split into individual pages natively.")
    return True

def main():
    parser = argparse.ArgumentParser(description="Split wide-page PDFs into portrait pages (Supports 2,3,4-page spreads)")
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output PDF file (default: input_split.pdf)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for image processing (default: 300)")
    parser.add_argument("--split-threshold", type=float, default=1.15, help="Aspect ratio threshold (default: 1.15)")
    parser.add_argument("--assume-double-page-spreads", action="store_true",
                         help="Split every wide page without requiring a detected spine gutter. "
                              "Use for corpora that are always genuine double-page scans but have "
                              "faint/worn gutters (e.g. old book photocopies).")

    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output) if args.output else input_file.parent / f"{input_file.stem}_split.pdf"

    split_pdf_pages(str(input_file), str(output_file), args.dpi, args.split_threshold,
                     require_spine_confirmation=not args.assume_double_page_spreads)

if __name__ == "__main__":
    main()
