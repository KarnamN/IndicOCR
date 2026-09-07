import sys
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import subprocess
from pathlib import Path

def process_epub(epub_path_str, output_dir_str):
    epub_path = Path(epub_path_str)
    output_dir = Path(output_dir_str)
    
    if not epub_path.exists():
        print(f"Error: Could not find file {epub_path}")
        return

    print(f"📖 Processing: {epub_path.name}")
    try:
        book = epub.read_epub(str(epub_path))
    except Exception as e:
        print(f"❌ Failed to read EPUB: {e}")
        return

    pages_modified = 0

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            html = item.get_content().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            
            from bs4 import NavigableString
            
            # Find all paragraph or div tags which might contain text
            text_containers = soup.find_all(['p', 'div'])
            if not text_containers:
                continue
                
            # Filter and extract lines
            all_lines = []
            valid_containers = []
            
            for container in text_containers:
                # Skip if it contains an image
                if container.find('img'):
                    continue
                    
                has_text = False
                for child in container.contents:
                    if isinstance(child, NavigableString):
                        text = str(child).strip()
                        if text:
                            all_lines.append(text)
                            has_text = True
                            
                if has_text:
                    valid_containers.append(container)
            
            if not all_lines:
                continue
                
            # Reverse the master list of lines for this page!
            all_lines.reverse()
            
            # Put the reversed lines back into the containers
            line_idx = 0
            for container in valid_containers:
                # Count how many text lines were originally in this container
                count = sum(1 for c in container.contents if isinstance(c, NavigableString) and str(c).strip())
                
                new_contents = []
                for _ in range(count):
                    if line_idx < len(all_lines):
                        new_contents.append(all_lines[line_idx])
                        line_idx += 1
                
                # Clear and rebuild the container with <br/> tags
                container.clear()
                for i, text in enumerate(new_contents):
                    container.append(NavigableString(text))
                    if i < len(new_contents) - 1:
                        container.append(soup.new_tag('br'))
                        
            item.set_content(str(soup).encode('utf-8'))
            pages_modified += 1
            
    if pages_modified == 0:
        print("⚠️ No text found to reverse in this EPUB.")
        return

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the modified EPUB to the output directory
    out_path = output_dir / f"{epub_path.stem}_reversed.epub"
    
    try:
        epub.write_epub(str(out_path), book)
        print(f"✅ Reversed {pages_modified} pages. Saved to: {out_path}")
    except Exception as e:
        print(f"❌ Failed to save EPUB: {e}")
        return

    # Try to convert to MOBI
    print("🔄 Attempting to generate MOBI file...")
    try:
        # Check if ebook-convert (Calibre) is available
        mobi_path = out_path.with_suffix('.mobi')
        if subprocess.run(['command', '-v', 'ebook-convert'], capture_output=True).returncode == 0:
            subprocess.run(
                ['ebook-convert', str(out_path), str(mobi_path)], 
                check=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            if mobi_path.exists():
                print(f"✅ Successfully created MOBI: {mobi_path}")
        else:
            # Fallback to kindlegen if ebook-convert isn't there
            subprocess.run(
                ['kindlegen', str(out_path)], 
                check=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            if mobi_path.exists():
                print(f"✅ Successfully created MOBI: {mobi_path}")
    except FileNotFoundError:
        print("⚠️ Neither 'ebook-convert' nor 'kindlegen' found on system. MOBI conversion skipped.")
    except subprocess.CalledProcessError:
        print("⚠️ MOBI conversion command failed, but EPUB is ready.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reverse_epub.py <input_epub_or_folder> <output_folder>")
        print("Example: python reverse_epub.py data/results/mybook.epub /output/fixed_books/")
        sys.exit(1)
        
    target = Path(sys.argv[1])
    out_folder = Path(sys.argv[2])
    
    if target.is_file() and target.suffix == '.epub':
        process_epub(target, out_folder)
    elif target.is_dir():
        epub_files = list(target.glob("*.epub"))
        # Exclude already reversed files to avoid infinite loops
        epub_files = [f for f in epub_files if not f.name.endswith('_reversed.epub')]
        
        print(f"Found {len(epub_files)} EPUB files in directory.")
        for epub_file in epub_files:
            process_epub(epub_file, out_folder)
            print("-" * 40)
    else:
        print(f"Error: {target} is neither an EPUB file nor a directory.")
