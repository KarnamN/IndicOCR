"""
EPUB Extractor Utility
Handles unzipping and text extraction from existing EPUB files for the Auditor.
"""
import zipfile
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class EPUBExtractor:
    """Extracts text and structure from an existing EPUB file."""
    
    def __init__(self, epub_path: Path):
        self.epub_path = epub_path
        self.temp_dir = epub_path.parent / f"extracted_{epub_path.stem}"
        self.chapters = [] # List of {'file_name': str, 'title': str, 'text': str}

    def extract_all(self) -> bool:
        """Unzip and parse all XHTML chapters."""
        if not self.epub_path.exists():
            logger.error(f"EPUB file not found: {self.epub_path}")
            return False
            
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            
            # Find all XHTML files in the OEBPS/EPUB directory
            # Standard path is usually OEBPS/text/ or EPUB/text/
            xhtml_files = []
            for root, _, files in os.walk(self.temp_dir):
                for file in files:
                    if file.endswith(('.xhtml', '.html')):
                        xhtml_files.append(Path(root) / file)
            
            # Sort chapters (important for alignment)
            xhtml_files.sort()
            
            for xhtml_path in xhtml_files:
                with open(xhtml_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f.read(), 'html.parser')
                    
                    # Extract title
                    title = soup.title.string if soup.title else xhtml_path.stem
                    
                    # Extract text (preserving some structure)
                    # We replace <p> with \n\n and <br/> with \n to mimic original OCR
                    for br in soup.find_all("br"):
                        br.replace_with("\n")
                    
                    text_blocks = []
                    for p in soup.find_all("p"):
                        text_blocks.append(p.get_text())
                    
                    full_text = "\n\n".join(text_blocks)
                    
                    self.chapters.append({
                        'file_path': xhtml_path,
                        'relative_path': xhtml_path.relative_to(self.temp_dir),
                        'title': title,
                        'text': full_text
                    })
            
            logger.info(f"Successfully extracted {len(self.chapters)} chapters from EPUB")
            return True
            
        except Exception as e:
            logger.error(f"Failed to extract EPUB: {e}")
            return False

    def get_text_for_chapter(self, index: int) -> str:
        """Return text for a specific chapter index (0-based)."""
        if 0 <= index < len(self.chapters):
            return self.chapters[index]['text']
        return ""

    def cleanup(self):
        """Remove temporary extraction directory."""
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"Cleaned up temp extraction dir: {self.temp_dir}")
