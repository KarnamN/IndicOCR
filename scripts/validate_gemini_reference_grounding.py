#!/usr/bin/env python3
"""
validate_gemini_reference_grounding.py — Before/after check for reference-grounded Gemini OCR
=================================================================================================
GeminiOCRProcessor.extract_text_with_references() (src/gemini_ocr_processor.py) gives Gemini
the page image PLUS PaddleOCR's and Tesseract's independent readings, instead of transcribing
from a blank slate — targeting a confirmed hallucination failure: on page 3 of
rudranethra_split.pdf, unreferenced Gemini substituted a fluent-but-wrong phrase for a
person's name that Tesseract's raw pass read almost perfectly. Gated OFF by default
(ENABLE_GEMINI_REFERENCE_GROUNDING=False, src/config.py) pending review of real before/after
output — this script produces that comparison.

IMPORTANT: this makes REAL, BILLED Gemini API calls (one per page checked). Keep --limit small.

Usage:
  python scripts/validate_gemini_reference_grounding.py --pdf <path.pdf> --data-dir <data/temp/book_folder> [--pages 2,5,9] [--limit 5]

If --pages is omitted, auto-discovers pages in --data-dir that have both
page_{N}_0_text_tesseract.json and page_{N}_0_text_paddleocr.json (the existing
_log_ocr_comparison() capture) alongside a Gemini-chosen page_{N}_0_text.json, and checks up
to --limit of them.
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import config  # noqa: F401 -- satisfies `import config` in gemini_ocr_processor.py
from PIL import Image
import fitz  # PyMuPDF, same library _convert_single_page() uses
from gemini_ocr_processor import GeminiOCRProcessor


def render_page(pdf_path: Path, page_num: int, dpi: int = 400) -> Image.Image:
    """Same approach as OptimizedPDFToEPUBConverter._convert_single_page()."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def discover_pages(data_dir: Path, limit: int) -> list:
    pages = []
    for tess_path in sorted(data_dir.glob('page_*_0_text_tesseract.json')):
        page_num = int(tess_path.stem.split('_')[1])
        paddle_path = data_dir / f"page_{page_num}_0_text_paddleocr.json"
        main_path = data_dir / f"page_{page_num}_0_text.json"
        if paddle_path.exists() and main_path.exists():
            pages.append(page_num)
        if len(pages) >= limit:
            break
    return pages


def load_text(path: Path) -> str:
    if not path.exists():
        return ''
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('text', '') or ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pdf', required=True, help='Path to the source PDF')
    parser.add_argument('--data-dir', required=True, help='Path to the book\'s data/temp/<folder> with cached OCR results')
    parser.add_argument('--pages', default='', help='Comma-separated internal (0-indexed) page numbers to check; auto-discovers if omitted')
    parser.add_argument('--limit', type=int, default=5, help='Max pages to check (real Gemini API calls — keep small)')
    parser.add_argument('--dpi', type=int, default=400, help='Render DPI, matching the pipeline default')
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    data_dir = Path(args.data_dir)

    if args.pages:
        page_nums = [int(p) for p in args.pages.split(',')][:args.limit]
    else:
        page_nums = discover_pages(data_dir, args.limit)

    if not page_nums:
        print(f"No pages found (with both tesseract+paddleocr comparison captures) under {data_dir}")
        return

    print(f"Checking {len(page_nums)} page(s): {page_nums}")
    print("WARNING: each page below makes a real, billed Gemini API call.\n")

    gemini = GeminiOCRProcessor()
    if not gemini.is_available:
        print("Gemini is not available (check GEMINI_API_KEY / quota) — aborting.")
        return

    for page_num in page_nums:
        tess_text = load_text(data_dir / f"page_{page_num}_0_text_tesseract.json")
        paddle_text = load_text(data_dir / f"page_{page_num}_0_text_paddleocr.json")
        old_gemini_text = load_text(data_dir / f"page_{page_num}_0_text.json")

        image = render_page(pdf_path, page_num, dpi=args.dpi)
        new_text = gemini.extract_text_with_references(
            image, paddle_text, tess_text, page_label=f"[validate p{page_num}]")

        print(f"\n{'=' * 70}\nPage internal={page_num} (printed page may differ)")
        print(f"\n--- OLD (unreferenced Gemini, already shipped) ---\n{old_gemini_text[:400]}")
        print(f"\n--- NEW (reference-grounded Gemini) ---\n{new_text[:400]}")
        print(f"\n--- Tesseract reference (for comparison) ---\n{tess_text[:400]}")

    print(f"\n{'=' * 70}")
    print("Review each NEW output above against OLD and the Tesseract/Paddle references.")
    print("Only flip ENABLE_GEMINI_REFERENCE_GROUNDING once this looks reliably better,")
    print("not just different, across a range of pages.")


if __name__ == '__main__':
    main()
