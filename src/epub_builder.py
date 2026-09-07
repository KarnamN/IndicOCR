"""
EPUB Builder - Generate reflowable EPUB files from text
"""
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Any
from datetime import datetime
from io import BytesIO
from PIL import Image
from ebooklib import epub

from config import (
    EPUB_LANGUAGE, 
    EPUB_PUBLISHER, 
    EPUB_IDENTIFIER_PREFIX,
    PAGES_PER_CHAPTER
)

logger = logging.getLogger(__name__)


class EPUBBuilder:
    """Build EPUB files with reflowable text"""
    
    def __init__(
        self,
        title: str,
        author: str = "Unknown",
        language: str = EPUB_LANGUAGE,
        publisher: str = EPUB_PUBLISHER
    ):
        """
        Initialize EPUB builder
        
        Args:
            title: Book title
            author: Book author
            language: Language code (default: 'te' for Telugu)
            publisher: Publisher name
        """
        self.book = epub.EpubBook()
        self.title = title
        self.author = author
        self.language = language
        self.publisher = publisher
        self.chapters = []
        
        # Set metadata
        self.book.set_title(title)
        self.book.set_language(language)
        self.book.add_author(author)
        self.book.add_metadata('DC', 'publisher', publisher)
        
        # Generate unique identifier
        identifier = f"{EPUB_IDENTIFIER_PREFIX}{uuid.uuid4()}"
        self.book.set_identifier(identifier)
        
        # Add creation date
        self.book.add_metadata('DC', 'date', datetime.now().strftime('%Y-%m-%d'))
        
        logger.info(f"Initialized EPUB builder for '{title}' by {author}")
    
    def create_chapter(self, title: str, content: str, images: List = None, filename: str = None) -> epub.EpubHtml:
        """
        Create a chapter object with text and embedded images.
        Images are appended AFTER all text content (legacy mode).
        For precise positional placement, use create_chapter_from_blocks().
        """
        if filename is None:
            chapter_num = len(self.chapters) + 1
            filename = f'chapter_{chapter_num:03d}.xhtml'
            
        chapter = epub.EpubHtml(title=title, file_name=filename, lang=self.language)
        
        # Prepare HTML content
        html_start = f'<html><head></head><body><h1>{title}</h1>'
        html_end = '</body></html>'
        
        # Convert plain text to HTML paragraphs if not already HTML
        if content and not content.strip().startswith('<'):
            paragraphs = content.split('\n\n')
            final_content = '\n'.join(f'<p>{p.replace(chr(10), "<br/>")}</p>' for p in paragraphs if p.strip())
        else:
            final_content = content or ""
            
        if images:
            for i, img in enumerate(images):
                img_name = f"img_{len(self.chapters)}_{i}.jpg"
                
                # Convert PIL Image to bytes
                if isinstance(img, Image.Image):
                    img_byte_arr = BytesIO()
                    # Increase JPEG quality to 95 to preserve clarity
                    img.convert('RGB').save(img_byte_arr, format='JPEG', quality=95)
                    img_data = img_byte_arr.getvalue()
                    
                    # Add image to book
                    epub_img = epub.EpubItem(
                        uid=f"img_{len(self.chapters)}_{i}",
                        file_name=f"images/{img_name}",
                        media_type="image/jpeg",
                        content=img_data
                    )
                    self.book.add_item(epub_img)
                    
                    # Calculate natural display width
                    display_w = max(150, img.width // 3)
                    
                    # Add to HTML
                    final_content += f'<div style="text-align:center;margin:1em 0;"><img src="images/{img_name}" alt="Image {i}" style="width:{display_w}px;max-width:100%;max-height:90vh;height:auto;object-fit:contain;"/></div>'

        chapter.content = html_start + final_content + html_end
        return chapter

    def create_chapter_from_blocks(
        self,
        title: str,
        content_blocks: List[dict],
        filename: str = None
    ) -> epub.EpubHtml:
        """
        Create a chapter from an ordered list of content blocks.
        Blocks are rendered in the order provided (caller sorts by Y position).

        Each block is a dict with:
            type  : 'text' | 'title' | 'image'
            y     : int  — top coordinate (used for sorting by caller)
            content: str  — for text/title blocks
            image  : PIL.Image — for image blocks

        This enables precise page reconstruction:
            Image at y=50  → <img>
            Text  at y=200 → <p>...</p>
            Image at y=500 → <img>    ← placed exactly between paragraphs
            Text  at y=650 → <p>...</p>
        """
        if filename is None:
            chapter_num = len(self.chapters) + 1
            filename = f'chapter_{chapter_num:03d}.xhtml'

        chapter = epub.EpubHtml(title=title, file_name=filename, lang=self.language)
        html_parts = [f'<html><head></head><body><h1>{title}</h1>']
        img_counter = [0]  # mutable for closure

        for block in content_blocks:
            btype = block.get('type', 'text')

            if btype == 'image':
                pil_img = block.get('image')
                if not isinstance(pil_img, Image.Image):
                    continue
                idx = img_counter[0]
                img_counter[0] += 1
                img_name = f"img_{len(self.chapters)}_{idx}.jpg"
                img_byte_arr = BytesIO()
                # Increase JPEG quality to 95 to preserve clarity of line art and text
                pil_img.convert('RGB').save(img_byte_arr, format='JPEG', quality=95)
                epub_img = epub.EpubItem(
                    uid=f"img_{len(self.chapters)}_{idx}",
                    file_name=f"images/{img_name}",
                    media_type="image/jpeg",
                    content=img_byte_arr.getvalue()
                )
                self.book.add_item(epub_img)
                
                # If we have the exact percentage width of the image relative to the PDF page,
                # we use that to make the image size perfectly match the physical page proportion.
                width_pct = block.get('width_pct')
                if width_pct:
                    style_str = f'width:{width_pct:.1f}%;max-width:100%;max-height:90vh;height:auto;object-fit:contain;'
                else:
                    # Fallback for legacy blocks
                    display_w = max(150, pil_img.width // 3)
                    style_str = f'width:{display_w}px;max-width:100%;max-height:90vh;height:auto;object-fit:contain;'
                
                html_parts.append(
                    f'<div style="text-align:center;margin:1em 0;">'
                    f'<img src="images/{img_name}" alt="Figure {idx+1}" '
                    f'style="{style_str}"/></div>'
                )

            elif btype == 'title':
                text = block.get('content', '').strip()
                if text:
                    html_parts.append(f'<h2>{text}</h2>')

            else:  # 'text' or anything else
                text = block.get('content', '').strip()
                if text:
                    lines = text.split('\n')
                    paras = []
                    buf = []
                    for line in lines:
                        if line.strip():
                            buf.append(line)
                        else:
                            if buf:
                                paras.append('<br/>'.join(buf))
                                buf = []
                    if buf:
                        paras.append('<br/>'.join(buf))
                    for para in paras:
                        html_parts.append(f'<p>{para}</p>')

        html_parts.append('</body></html>')
        chapter.content = '\n'.join(html_parts)
        return chapter


    def add_chapter(self, chapter_or_title: Any, content: str = None):
        """
        Add a chapter to the book. Supports both a pre-created chapter object 
        or creating one on the fly.
        """
        if isinstance(chapter_or_title, epub.EpubHtml):
            chapter = chapter_or_title
        else:
            chapter = self.create_chapter(chapter_or_title, content)
            
        self.book.add_item(chapter)
        self.chapters.append(chapter)
        return chapter
    
    def add_chapters_from_pages(
        self,
        page_texts: List[str],
        pages_per_chapter: int = PAGES_PER_CHAPTER
    ):
        """
        Add chapters by grouping pages
        
        Args:
            page_texts: List of text strings (one per page)
            pages_per_chapter: Number of pages to group into one chapter
        """
        total_pages = len(page_texts)
        chapter_num = 1
        
        for i in range(0, total_pages, pages_per_chapter):
            # Get pages for this chapter
            end_idx = min(i + pages_per_chapter, total_pages)
            chapter_pages = page_texts[i:end_idx]
            
            # Merge pages with paragraph breaks
            chapter_content = '\n\n'.join(chapter_pages)
            
            # Create chapter title
            start_page = i + 1
            end_page = end_idx
            if start_page == end_page:
                chapter_title = f"Page {start_page}"
            else:
                chapter_title = f"Pages {start_page}-{end_page}"
            
            self.add_chapter(chapter_title, chapter_content)
            chapter_num += 1
        
        logger.info(f"Created {len(self.chapters)} chapters from {total_pages} pages")
    
    def add_cover_image(self, image_path: str):
        """
        Add cover image to EPUB
        
        Args:
            image_path: Path to cover image file
        """
        try:
            with open(image_path, 'rb') as f:
                cover_image = f.read()
            
            # Determine image type
            img_path = Path(image_path)
            ext = img_path.suffix.lower()
            media_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif'
            }.get(ext, 'image/jpeg')
            
            # Add cover image
            self.book.set_cover('cover' + ext, cover_image)
            logger.info(f"Added cover image: {image_path}")
            
        except Exception as e:
            logger.error(f"Failed to add cover image: {e}")
    
    def add_css(self, css_content: Optional[str] = None):
        """
        Add CSS stylesheet to EPUB
        
        Args:
            css_content: CSS content (uses default Telugu-optimized CSS if None)
        """
        if css_content is None:
            # Default CSS for Telugu text
            css_content = """
            @namespace epub "http://www.idpf.org/2007/ops";
            
            body {
                font-family: "Noto Sans Telugu", "Lohit Telugu", "Pothana2000", sans-serif;
                font-size: 1.2em;
                line-height: 1.8;
                text-align: justify;
                margin: 1em;
            }
            
            h1 {
                font-size: 1.8em;
                font-weight: bold;
                margin-top: 1em;
                margin-bottom: 0.5em;
                text-align: center;
            }
            
            h2 {
                font-size: 1.5em;
                font-weight: bold;
                margin-top: 0.8em;
                margin-bottom: 0.4em;
            }
            
            p {
                margin: 0.5em 0;
                text-indent: 1.5em;
            }
            
            p:first-of-type {
                text-indent: 0;
            }
            
            /* Telugu-specific adjustments */
            @font-face {
                font-family: "Noto Sans Telugu";
                font-style: normal;
                font-weight: normal;
            }
            """
        
        # Create CSS file
        css = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=css_content
        )
        
        self.book.add_item(css)
        
        # Apply CSS to all chapters
        for chapter in self.chapters:
            chapter.add_item(css)
        
        logger.info("Added CSS stylesheet")
    
    def build(self, output_path: str) -> str:
        """
        Build and save EPUB file
        
        Args:
            output_path: Path to save EPUB file
        
        Returns:
            Path to saved EPUB file
        """
        try:
            # Add CSS
            self.add_css()
            
            # Define table of contents
            self.book.toc = tuple(self.chapters)
            
            # Add navigation files
            self.book.add_item(epub.EpubNcx())
            self.book.add_item(epub.EpubNav())
            
            # Define spine (reading order)
            self.book.spine = ['nav'] + self.chapters
            
            # Write EPUB file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            epub.write_epub(str(output_file), self.book)
            
            logger.info(f"EPUB file created: {output_path}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"Failed to build EPUB: {e}")
            raise
    
    def set_metadata(self, **kwargs):
        """
        Set additional metadata
        """
        for key, value in kwargs.items():
            if value is None: continue
            
            if key == 'description':
                self.book.add_metadata('DC', 'description', value)
            elif key == 'subject':
                self.book.add_metadata('DC', 'subject', value)
            elif key == 'rights':
                self.book.add_metadata('DC', 'rights', value)
            elif key == 'contributor':
                self.book.add_metadata('DC', 'contributor', value)
            elif key == 'publisher':
                self.book.add_metadata('DC', 'publisher', value)
            elif key == 'date':
                self.book.add_metadata('DC', 'date', value)
            else:
                logger.warning(f"Unknown metadata key: {key}")
