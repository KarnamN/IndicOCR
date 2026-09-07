import sys
import subprocess
from pathlib import Path

def rename_book(epub_path_str, new_title):
    epub_path = Path(epub_path_str)
    if not epub_path.exists():
        print(f"Error: Could not find EPUB file {epub_path}")
        return

    print(f"🔄 Updating EPUB title to: '{new_title}'...")
    try:
        subprocess.run(['ebook-meta', str(epub_path), '-t', new_title], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"✅ Successfully updated EPUB: {epub_path.name}")
    except Exception as e:
        print(f"❌ Failed to update EPUB: {e}")

    mobi_path = epub_path.with_suffix('.mobi')
    if mobi_path.exists():
        print(f"🔄 Updating MOBI title to: '{new_title}'...")
        try:
            subprocess.run(['ebook-meta', str(mobi_path), '-t', new_title], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ Successfully updated MOBI: {mobi_path.name}")
        except Exception as e:
            print(f"❌ Failed to update MOBI: {e}")
    else:
        print(f"⚠️ No matching MOBI file found at {mobi_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python rename_book.py <path_to_epub_file> <\"New Book Title\">")
        print("Example: python rename_book.py data/results/mybook.epub \"The Actual Book Title\"")
        sys.exit(1)
        
    epub_file = sys.argv[1]
    title = sys.argv[2]
    
    rename_book(epub_file, title)
