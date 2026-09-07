import sys
import os
import joblib
from pathlib import Path
import glob

# Add src to python path so we can import epub builder stuff
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter

def reverse_text_in_jbl(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        print(f"Error: Folder {folder_path} does not exist.")
        return

    jbl_files = list(folder.glob("page_*.jbl"))
    if not jbl_files:
        print(f"No .jbl files found in {folder_path}.")
        return

    print(f"Found {len(jbl_files)} .jbl files. Reversing text lines...")

    for jbl_file in jbl_files:
        try:
            data = joblib.load(jbl_file)
            
            # Only reverse the text if the OCR engine was 'paddle'
            # Tesseract (used for TOC pages) and Gemini do not have the sorting bug
            ocr_engine = data.get('ocr_engine', 'paddle')
            
            if ocr_engine == 'paddle':
                # Reverse the raw text lines
                if 'text' in data and data['text']:
                    lines = data['text'].split('\n')
                    data['text'] = '\n'.join(reversed(lines))
                
                # If content_blocks exists, delete it so EPUB builder falls back to reversed text
                if 'content_blocks' in data:
                    del data['content_blocks']
                
                # Save it back
                joblib.dump(data, jbl_file)
                print(f"✅ Reversed text in {jbl_file.name} (Engine: Paddle)")
            else:
                print(f"⏭️ Skipped reversing {jbl_file.name} (Engine: {ocr_engine})")
        except Exception as e:
            print(f"❌ Failed to process {jbl_file.name}: {e}")

    # Now recreate the EPUB and MOBI
    print("\nText reversed! Rebuilding EPUB and MOBI...")
    
    # We create a dummy converter just to use its rebuild function
    # The output filename will be based on the folder name
    book_name = folder.name.split("__")[0]
    output_epub = folder.parent.parent / "results" / f"{book_name}_fixed.epub"
    output_epub.parent.mkdir(exist_ok=True)
    
    converter = OptimizedPDFToEPUBConverter(max_workers=1)
    # Override the specific temp folder to point directly to this book's cache
    converter.temp_results_dir = folder
    converter.book_title = book_name
    
    try:
        converter.rebuild_book_from_results(output_epub)
        print(f"\n🎉 Successfully rebuilt: {output_epub}")
    except Exception as e:
        print(f"Error rebuilding book: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reverse_rebuild.py <path_to_book_temp_folder>")
        print("Example: python reverse_rebuild.py data/temp/గ_ప_త_ఙ_ఞ_న__b817a00c")
        sys.exit(1)
        
    target_folder = sys.argv[1]
    reverse_text_in_jbl(target_folder)
