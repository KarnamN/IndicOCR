"""A/B compare PP-OCRv5 detector thresholds (unclip_ratio / box_thresh) on
poratam.png against ground truth. Each variant reloads the detector
singleton (paddle_v5_processor._det_engine), which pays the ~20s OpenVINO
compile cost again -- kept to a small variant set for that reason.

Run from the repository root with the WSL project environment:
    python tests/diagnostics/tune_paddle_detector.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import config_v5 as active_config  # noqa: E402

sys.modules["config"] = active_config
import paddle_v5_processor as pv5  # noqa: E402
from ocr_fusion import letters  # noqa: E402

TELUGU_RANGE = range(0x0C00, 0x0C80)

VARIANTS = [
    ("current (unclip=2.0, thresh=0.3, box_thresh=0.6)", 2.0, 0.3, 0.6),
    ("paddle_default (unclip=1.5, thresh=0.3, box_thresh=0.6)", 1.5, 0.3, 0.6),
    ("looser_box_thresh (unclip=2.0, thresh=0.3, box_thresh=0.5)", 2.0, 0.3, 0.5),
    ("stricter_box_thresh (unclip=2.0, thresh=0.3, box_thresh=0.7)", 2.0, 0.3, 0.7),
]


def _levenshtein(ref, hyp) -> int:
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        row = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (r != h))
        prev = row
    return prev[-1]


def cer(ref_text: str, hyp_text: str) -> float | None:
    ref_units = letters(ref_text)
    if not ref_units:
        return None
    return _levenshtein(ref_units, letters(hyp_text)) / len(ref_units)


def main() -> int:
    gt = json.loads((ROOT / "ocr_comparison" / "poratam" / "draft_ground_truth.json").read_text(encoding="utf-8"))
    gt_text = "\n".join(gt["poratam.png"])
    image = Image.open(ROOT / "images" / "poratam.png")

    for label, unclip, thresh, box_thresh in VARIANTS:
        active_config.PADDLE_DET_UNCLIP_RATIO = unclip
        active_config.PADDLE_DET_THRESH = thresh
        active_config.PADDLE_DET_BOX_THRESH = box_thresh

        pv5._det_engine = None  # force reload with new thresholds
        processor = pv5.PaddleV5Processor(language="tel+eng", config=active_config)

        started = time.perf_counter()
        text, boxes = processor._paddle_extract(image)
        elapsed = time.perf_counter() - started

        c = cer(gt_text, text)
        print(f"{label:60s} boxes={len(boxes):3d} {elapsed:5.2f}s CER={c:.3f}" if c is not None
              else f"{label:60s} boxes={len(boxes):3d} {elapsed:5.2f}s CER=n/a")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
