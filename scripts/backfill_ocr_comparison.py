#!/usr/bin/env python3
"""
backfill_ocr_comparison.py — Full dual-engine (Tesseract + PaddleOCR) coverage for one book
================================================================================================
mine_ocr_failure_patterns.py's conjunct/matra-drop signal only sees pages that already have both
a page_{N}_0_text_tesseract.json and page_{N}_0_text_paddleocr.json capture -- which
_log_ocr_comparison() (pdf_to_epub_converter_optimized_v2.py) only saves for pages where Gemini
ended up as the final engine. For a book where most pages never escalated to Gemini, this misses
most of the book's real Paddle-vs-Tesseract disagreement.

This backfills those two capture files for every page of ONE book by re-rendering from the source
PDF and running Tesseract + PaddleOCR directly -- both local, no Gemini/API cost -- skipping pages
that already have both files. After running this, re-run mine_ocr_failure_patterns.py --book
<folder> for full coverage.

Usage:
  python scripts/backfill_ocr_comparison.py --pdf <path.pdf> --data-dir data/temp/<book_folder> [--dpi 400]
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import config  # noqa: F401 -- satisfies `import config` in ocr_processor.py / paddle_v5_processor.py
from PIL import Image
import fitz  # PyMuPDF, same approach as OptimizedPDFToEPUBConverter._convert_single_page()
from ocr_processor import OCRProcessor
from paddle_v5_processor import PaddleV5Processor


def render_page(pdf_path: Path, page_num: int, dpi: int = 400) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pdf', required=True, help='Path to the source PDF')
    parser.add_argument('--data-dir', required=True, help='Path to the book\'s data/temp/<folder>')
    parser.add_argument('--dpi', type=int, default=400, help='Render DPI, matching the pipeline default')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    pdf_path = Path(args.pdf)

    main_files = sorted(data_dir.glob('page_*_0_text.json'), key=lambda p: int(p.stem.split('_')[1]))
    todo = []
    for mf in main_files:
        page_num = int(mf.stem.split('_')[1])
        tess_path = data_dir / f"page_{page_num}_0_text_tesseract.json"
        paddle_path = data_dir / f"page_{page_num}_0_text_paddleocr.json"
        if tess_path.exists() and paddle_path.exists():
            continue
        todo.append((page_num, mf))

    print(f"{len(main_files)} total pages, {len(todo)} need backfilling (already covered: {len(main_files) - len(todo)})")
    if not todo:
        print("Nothing to do.")
        return

    tess_proc = OCRProcessor()
    paddle_proc = PaddleV5Processor(language='te')

    for i, (page_num, main_path) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] page {page_num} ...", end=' ', flush=True)

        final_engine = 'unknown'
        try:
            with open(main_path, encoding='utf-8') as f:
                final_engine = json.load(f).get('ocr_engine', 'unknown')
        except Exception:
            pass

        try:
            image = render_page(pdf_path, page_num, dpi=args.dpi)
        except Exception as e:
            print(f"render failed: {e}")
            continue

        try:
            tess_text = tess_proc.extract_text(image, page_label=f"[backfill p{page_num}]")
        except Exception as e:
            tess_text = ''
            print(f"tesseract failed: {e}", end=' ')

        try:
            paddle_text = paddle_proc.extract_paddle_only(image, page_label=f"[backfill p{page_num}]")
        except Exception as e:
            paddle_text = ''
            print(f"paddle failed: {e}", end=' ')

        for suffix, text, engine in (('tesseract', tess_text, 'tesseract'), ('paddleocr', paddle_text, 'paddle')):
            out = {
                'page_num': page_num,
                'sub_idx': 0,
                'ocr_engine': engine,
                'text': text,
                'text_length': len(text),
                'final_engine_used_in_epub': final_engine,
            }
            with open(data_dir / f"page_{page_num}_0_text_{suffix}.json", 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)

        print(f"tess={len(tess_text)} chars, paddle={len(paddle_text)} chars")

    print("\nDone. Re-run mine_ocr_failure_patterns.py --book <folder> for full-coverage stats.")


if __name__ == '__main__':
    main()
