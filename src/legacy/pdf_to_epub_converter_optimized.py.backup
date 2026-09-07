"""
PDF to EPUB Converter - Optimized for Large PDFs
Memory‑efficient version that processes PDFs in chunks, skips OCR on the first two cover pages, and moves any page that looks like a table‑of‑contents to the end of the book.
"""

import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import config
from ocr_processor import OCRProcessor
from table_detector import TableDetector
from epub_builder import EPUBBuilder

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class PDFToEPUBConverterOptimized:
    """Convert a scanned PDF to an EPUB file.

    Features:
    * Chunked processing to keep memory usage low.
    * Optional table detection.
    * First two pages are treated as *cover* pages – they are kept as images only, no OCR.
    * Pages that contain the word "contents" are identified as TOC pages and are moved to the end of the EPUB.
    """

    def __init__(
        self,
        language: str = None,
        dpi: int = None,
        detect_tables: bool = True,
        preserve_images: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        chunk_size: int = 10,
        max_workers: int = 2,
    ):
        self.language = language or config.DEFAULT_OCR_LANGUAGE
        # Cap DPI for large files – 200 is a good compromise between quality and speed.
        self.dpi = min(dpi or config.DEFAULT_DPI, 200)
        self.detect_tables = detect_tables
        self.preserve_images = preserve_images
        self.progress_callback = progress_callback
        self.chunk_size = chunk_size
        self.max_workers = max_workers

        # Initialise OCR and (optional) table detection helpers.
        self.ocr_processor = OCRProcessor(language=self.language)
        self.table_detector = TableDetector() if self.detect_tables else None

        logger.info(
            f"Optimized converter initialised – language={self.language}, dpi={self.dpi}, "
            f"chunk_size={self.chunk_size}, max_workers={self.max_workers}"
        )

    # ---------------------------------------------------------------------
    # Helper utilities
    # ---------------------------------------------------------------------
    def _update_progress(self, stage: str, current: int, total: int):
        if self.progress_callback:
            try:
                self.progress_callback(stage, current, total)
            except Exception as exc:
                logger.warning(f"Progress callback error: {exc}")

    def get_page_count(self, pdf_path: Path) -> int:
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception as exc:
            logger.error(f"Failed to get page count: {exc}")
            return 0

    def extract_pages_chunk(self, pdf_path: Path, start_page: int, end_page: int) -> List[Image.Image]:
        """Convert a slice of the PDF (0‑based indices) to a list of PIL images."""
        try:
            logger.info(
                f"Converting pages {start_page + 1}-{end_page} to images (DPI={self.dpi})..."
            )
            images = convert_from_path(
                pdf_path,
                dpi=self.dpi,
                fmt=config.IMAGE_FORMAT,
                first_page=start_page + 1,
                last_page=end_page,
            )
            logger.info(f"Converted {len(images)} pages to images")
            return images
        except Exception as exc:
            logger.error(
                f"Failed to convert pages {start_page + 1}-{end_page}: {exc}"
            )
            return []

    # ---------------------------------------------------------------------
    # Page‑level processing
    # ---------------------------------------------------------------------
    def process_page(self, page_image: Image.Image, page_num: int, total_pages: int = 0) -> Dict:
        """Process a single page.

        * For the first two pages (cover pages) we keep the image only – no OCR or table detection.
        * For all other pages we optionally run table detection and always run OCR.
        """
        if total_pages > 0:
            progress = int(20 + (page_num / total_pages) * 60)  # 20‑80% range
            self._update_progress(
                f"Processing page {page_num + 1}/{total_pages}", progress, 100
            )

        logger.info(f"Processing page {page_num + 1}…")

        result: Dict = {
            "page_num": page_num,
                if self.preserve_images:
                    if (
                        page_image.width > config.IMAGE_MAX_WIDTH
                        or page_image.height > config.IMAGE_MAX_HEIGHT
                    ):
                        ratio = min(
                            config.IMAGE_MAX_WIDTH / page_image.width,
                            config.IMAGE_MAX_HEIGHT / page_image.height,
                        )
                        new_sz = (
                            int(page_image.width * ratio),
                            int(page_image.height * ratio),
                        )
                        page_image = page_image.resize(new_sz, Image.Resampling.LANCZOS)
                    result["images"].append(page_image)
                logger.info(f"Cover page {page_num + 1} preserved without OCR")
                return result

            # -----------------------------------------------------------------
            # Table detection (optional, skipped for cover pages already).
            # -----------------------------------------------------------------
            if self.detect_tables and self.table_detector:
                try:
                    tables = self.table_detector.detect_tables(page_image)
                    for table in tables:
                        cells = self.table_detector.extract_cells(
                            table["image"],
                            table["row_positions"],
                            table["col_positions"],
                        )
                        table_data = []
                        for row in cells:
                            row_data = []
                            for cell_img in row:
                                cell_text = self.ocr_processor.extract_text(cell_img)
                                row_data.append(cell_text.strip())
                            table_data.append(row_data)
                        result["tables"].append(
                            {
                                "data": table_data,
                                "rows": table["rows"],
                                "cols": table["cols"],
                            }
                        )
                except Exception as exc:
                    logger.warning(
                        f"Table detection failed on page {page_num + 1}: {exc}"
                    )

            # -----------------------------------------------------------------
            # OCR the full page text.
            # -----------------------------------------------------------------
            result["text"] = self.ocr_processor.extract_text(page_image)

            # -----------------------------------------------------------------
            # Preserve image for the EPUB (resize to EPUB limits if needed).
            # -----------------------------------------------------------------
            if self.preserve_images:
                if (
                    page_image.width > config.IMAGE_MAX_WIDTH
                    or page_image.height > config.IMAGE_MAX_HEIGHT
                ):
                    ratio = min(
                        config.IMAGE_MAX_WIDTH / page_image.width,
                        config.IMAGE_MAX_HEIGHT / page_image.height,
                    )
                    new_sz = (
                        int(page_image.width * ratio),
                        int(page_image.height * ratio),
                    )
                    page_image = page_image.resize(new_sz, Image.Resampling.LANCZOS)
                result["images"].append(page_image)
        except Exception as exc:
            logger.error(f"Failed to process page {page_num + 1}: {exc}")

        return result

    # ---------------------------------------------------------------------
    # Chunk‑level processing (parallelised)
    # ---------------------------------------------------------------------
    def process_chunk(
        self, page_images: List[Image.Image], start_page_num: int, total_pages: int
    ) -> List[Dict]:
        results = [None] * len(page_images)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(
                    self.process_page, img, start_page_num + idx, total_pages
                ): idx
                for idx, img in enumerate(page_images)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        f"Page {start_page_num + idx + 1} processing failed: {exc}"
                    )
                    results[idx] = {
                        "page_num": start_page_num + idx,
                        "text": "",
                        "tables": [],
                        "images": [],
                    }
        return results

    # ---------------------------------------------------------------------
    # Full conversion workflow
    # ---------------------------------------------------------------------
    def convert_chunked(
        self, pdf_path: Path, output_path: Path, title: str = None, author: str = None
    ) -> bool:
        """Convert *pdf_path* to an EPUB at *output_path*.

        The conversion proceeds in chunks, collects all page results, then:
        1. Adds normal pages (including cover pages) first.
        2. Adds any page whose text contains the word "contents" at the end.
        """
        try:
            logger.info(f"Starting conversion: {pdf_path}")

            # Verify OCR language data is present.
            if not self.ocr_processor.verify_telugu_support():
                logger.warning("Telugu OCR support not verified – proceeding anyway")

            total_pages = self.get_page_count(pdf_path)
            if total_pages == 0:
                logger.error("PDF contains no pages")
                return False

            logger.info(
                f"Processing {total_pages} pages in chunks of {self.chunk_size}"
            )

            # Initialise the EPUB builder.
            builder = EPUBBuilder(
                title=title or config.EPUB_METADATA["title"],
                author=author or config.EPUB_METADATA["author"],
                language=self.language,
            )
            builder.set_metadata(publisher=config.EPUB_METADATA["publisher"], date=None)

            # -----------------------------------------------------------------
            # Process the whole document, collecting results.
            # -----------------------------------------------------------------
            all_results: List[Dict] = []
            for chunk_start in range(0, total_pages, self.chunk_size):
                chunk_end = min(chunk_start + self.chunk_size, total_pages)
                self._update_progress(
                    f"Processing pages {chunk_start + 1}-{chunk_end}/{total_pages}",
                    chunk_start,
                    total_pages,
                )
                page_imgs = self.extract_pages_chunk(pdf_path, chunk_start, chunk_end)
                if not page_imgs:
                    logger.warning(
                        f"No images extracted for chunk {chunk_start + 1}-{chunk_end}"
                    )
                    continue
                chunk_results = self.process_chunk(page_imgs, chunk_start, total_pages)
                all_results.extend(chunk_results)
                del page_imgs, chunk_results
                gc.collect()
                logger.info(f"Finished chunk {chunk_start + 1}-{chunk_end}")

            # -----------------------------------------------------------------
            # Separate normal pages from potential TOC pages.
            # -----------------------------------------------------------------
            normal_pages: List[Dict] = []
            toc_pages: List[Dict] = []
            for res in all_results:
                if res is None:
                    continue
                txt = res.get("text", "").lower()
                if "contents" in txt:
                    toc_pages.append(res)
                else:
                    normal_pages.append(res)

            # -----------------------------------------------------------------
            # Helper to add chapters for a list of page results.
            # -----------------------------------------------------------------
            def add_chapters(page_list: List[Dict]):
                for page_res in page_list:
                    pn = page_res["page_num"]
                    if page_res["text"].strip():
                        chap = builder.create_chapter(
                            title=str(pn + 1),
                            content=page_res["text"],
                            images=page_res["images"] if self.preserve_images else None,
                        )
                        builder.add_chapter(chap)
                    for idx, tbl in enumerate(page_res["tables"]):
                        tbl_chap = builder.create_table_chapter(
                            title=f"Table {pn + 1}.{idx + 1}",
                            table_data=tbl["data"],
                        )
                        builder.add_chapter(tbl_chap)

            # Add normal pages first, then TOC pages.
            add_chapters(normal_pages)
            add_chapters(toc_pages)

            # -----------------------------------------------------------------
            # Build EPUB.
            # -----------------------------------------------------------------
            self._update_progress("Building EPUB", 90, 100)
            logger.info("Building EPUB…")
            success = builder.build(output_path)
            if success:
                self._update_progress("EPUB created", 100, 100)
                logger.info(f"✓ EPUB created successfully: {output_path}")
            else:
                logger.error("✗ Failed to create EPUB")
            return success
        except Exception as exc:
            logger.error(f"Conversion failed: {exc}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert large PDFs to EPUB (optimized)"
    )
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("output", help="Output EPUB file")
    parser.add_argument("--language", default="tel", help="OCR language code (default: tel)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for conversion (default: 150)")
    parser.add_argument("--chunk-size", type=int, default=10, help="Pages per chunk (default: 10)")
    parser.add_argument("--workers", type=int, default=2, help="Max parallel workers (default: 2)")
    parser.add_argument("--no-tables", action="store_true", help="Disable table detection")
    parser.add_argument("--no-images", action="store_true", help="Do not preserve images")
    parser.add_argument("--title", help="Book title")
    parser.add_argument("--author", help="Book author")
    args = parser.parse_args()

    converter = PDFToEPUBConverterOptimized(
        language=args.language,
        dpi=args.dpi,
        detect_tables=not args.no_tables,
        preserve_images=not args.no_images,
        chunk_size=args.chunk_size,
        max_workers=args.workers,
    )

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    success = converter.convert_chunked(
        input_path, output_path, title=args.title, author=args.author
    )
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
