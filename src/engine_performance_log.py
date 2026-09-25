"""Persistent, growing log of per-page OCR engine performance, for periodic review.

Every time the fusion pipeline runs a page (FusionOCRProcessor in production, or
fuse_ocr_engines.py as a diagnostic), one JSON line is appended: page-quality
metrics (brightness, sharpness, contrast — the same numbers the page-quality
router and the existing Tesseract-first clarity gate already use, so this stays
consistent with the rest of the project rather than inventing a fourth metric),
per-engine timing, per-engine win/presence counts for that page, and the
router's decision.

`tests/diagnostics/report_engine_performance.py` reads this file and buckets by
page quality to answer "which engine actually fits which kind of page" and
"does the router's threshold still look right" — meant to be re-run
periodically as real usage accumulates, not a one-off analysis. This module
only records; it never decides anything on its own.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np
from PIL import Image

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "ocr_comparison" / "engine_performance_log.jsonl"
ENGINES = ("paddle", "indicphoto", "tesseract")


def page_quality_metrics(image: Image.Image) -> dict:
    """Sharpness (Laplacian variance) and contrast (std dev) are exactly
    PaddleV5Processor._assess_clarity's numbers, computed the same way, so this
    report and the router/clarity-gate thresholds stay comparable. Brightness
    (mean gray value) is new — _assess_clarity doesn't compute it, but it was
    asked for explicitly as a bucketing dimension.
    """
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return {
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "contrast": float(gray.std()),
        "brightness": float(gray.mean()),
    }


def record_page(*, page_label: str, quality: dict, timings: dict, fused_lines: Sequence[dict],
                router_meta: Optional[dict], source: str, log_path: Path = DEFAULT_LOG_PATH) -> None:
    """Append one page's facts. Best-effort: a logging failure must never break
    a real conversion or a diagnostic run over it.

    source: 'production' (FusionOCRProcessor, real conversions) or
    'diagnostic' (fuse_ocr_engines.py) — kept separate so a report reader can
    choose to trust one more than the other, or look at both.
    """
    try:
        engine_stats = {}
        for engine in ENGINES:
            engine_stats[engine] = {
                "won": sum(1 for line in fused_lines if line["chosen"] == engine),
                "present": sum(1 for line in fused_lines if engine in line.get("candidates", {})),
            }
        record = {
            "ts": time.time(),
            "source": source,
            "page_label": page_label,
            "quality": quality,
            "timings": timings,
            "lines": len(fused_lines),
            "flagged": sum(1 for line in fused_lines if line.get("needs_review")),
            "engine_stats": engine_stats,
            "router": router_meta,
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_records(log_path: Path = DEFAULT_LOG_PATH) -> list[dict]:
    if not log_path.exists():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
