"""One-off: import already-computed fusion.json results into the performance log.

Reuses candidates/timings/router-decisions already on disk from earlier runs
this session, and only computes page-quality metrics fresh from the source
image (cheap — no OCR re-run needed). Going forward, fuse_ocr_engines.py and
FusionOCRProcessor log every page automatically; this script exists only to
backfill runs made before that logging existed.

Usage:
    python tests/diagnostics/backfill_performance_log.py \
        ocr_comparison/fusion/fusion.json:images \
        ocr_comparison/book_sample_fusion/fusion.json:ocr_comparison/book_sample \
        ocr_comparison/poratam/fusion.json:images
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from engine_performance_log import page_quality_metrics, record_page  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("specs", nargs="+",
                        help="fusion.json:image_dir pairs, e.g. ocr_comparison/fusion/fusion.json:images")
    args = parser.parse_args()

    imported = 0
    for spec in args.specs:
        fusion_path, image_dir = spec.split(":", 1)
        report = json.loads(Path(fusion_path).read_text(encoding="utf-8"))
        image_dir = ROOT / image_dir
        for page_name, page in report["images"].items():
            image_path = image_dir / page_name
            if not image_path.exists():
                print(f"[skip] {image_path} not found")
                continue
            image = Image.open(image_path).convert("RGB")
            timings = {k: v for k, v in page.get("timings", {}).items()
                      if k in ("paddle", "indicphoto", "tesseract")}
            record_page(page_label=page_name, quality=page_quality_metrics(image), timings=timings,
                       fused_lines=page["lines"], router_meta=page.get("router"), source="diagnostic")
            imported += 1
            print(f"imported {fusion_path} :: {page_name}")

    print(f"\n{imported} page records imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
