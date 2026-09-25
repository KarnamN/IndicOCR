"""A/B compare PP-OCRv5 recognition-quality levers that are built but off by
default: ENABLE_PADDLE_CONFIDENCE_REVOTE and PADDLE_USE_CLAHE.

Both flags already exist in config_v5.py and are wired into
PaddleV5Processor; this script exercises them against real page images
without editing config_v5.py, by flipping the attributes on the loaded
config module between runs (one model load, several extraction calls).

Where ocr_comparison/poratam/draft_ground_truth.json exists, scores each
variant's whole-page text against it (CER / Telugu-char precision, same
grapheme-cluster tokenizer as score_ocr_accuracy.py, compared page-level
so line-boundary shifts from CLAHE changing detection don't skew the
diff). For images with no ground truth, prints a word-level diff against
the baseline so the flips/changes can be read and judged by eye.

Run from the repository root with the WSL project environment:
    python tests/diagnostics/tune_paddle_quality.py
    python tests/diagnostics/tune_paddle_quality.py --images images/poratam.png ocr_comparison/No616_page15/page15_source.png
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import config_v5 as active_config  # noqa: E402

sys.modules["config"] = active_config
from paddle_v5_processor import PaddleV5Processor  # noqa: E402
from ocr_fusion import letters  # noqa: E402  (grapheme-cluster tokenizer)

TELUGU_RANGE = range(0x0C00, 0x0C80)

VARIANTS = [
    # (label, preprocess, revote, clahe)
    ("baseline_noprep",     False, False, False),
    ("baseline_prep",       True,  False, False),
    ("revote_prep",         True,  True,  False),
    ("clahe_prep",          True,  False, True),
    ("revote_clahe_prep",   True,  True,  True),
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


def telugu_precision(ref_text: str, hyp_text: str) -> float | None:
    ref_t = [c for c in letters(ref_text) if ord(c[0]) in TELUGU_RANGE]
    if not ref_t:
        return None
    hyp_t = [c for c in letters(hyp_text) if ord(c[0]) in TELUGU_RANGE]
    return 1 - (_levenshtein(ref_t, hyp_t) / len(ref_t))


def load_ground_truth(image_name: str) -> str | None:
    gt_path = ROOT / "ocr_comparison" / "poratam" / "draft_ground_truth.json"
    if not gt_path.exists():
        return None
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    lines = data.get(image_name)
    if not lines:
        return None
    return "\n".join(lines)


def word_diff(baseline: str, variant: str, max_show: int = 12) -> list[str]:
    sm = difflib.SequenceMatcher(None, baseline.split(), variant.split(), autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        b = " ".join(baseline.split()[i1:i2]) or "∅"
        v = " ".join(variant.split()[j1:j2]) or "∅"
        out.append(f"    {b!r} -> {v!r}")
        if len(out) >= max_show:
            out.append(f"    ... ({sum(1 for t,*_ in sm.get_opcodes() if t != 'equal') - max_show} more)")
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs="+", default=[
        str(ROOT / "images" / "poratam.png"),
        str(ROOT / "ocr_comparison" / "No616_page15" / "page15_source.png"),
    ])
    args = parser.parse_args()

    processor = PaddleV5Processor(language="tel+eng", config=active_config)

    for image_path in args.images:
        path = Path(image_path)
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        image = Image.open(path)
        gt = load_ground_truth(path.name)

        print(f"\n{'=' * 70}\n{path.name}  (ground truth: {'yes' if gt else 'no'})\n{'=' * 70}")

        results = {}
        for label, preprocess, revote, clahe in VARIANTS:
            active_config.ENABLE_PADDLE_CONFIDENCE_REVOTE = revote
            active_config.PADDLE_USE_CLAHE = clahe
            started = time.perf_counter()
            text = processor.extract_paddle_only(image, preprocess=preprocess, page_label=label)
            elapsed = time.perf_counter() - started
            results[label] = text
            row = f"{label:22s} {elapsed:6.2f}s  chars={len(text):5d}"
            if gt:
                c = cer(gt, text)
                tp = telugu_precision(gt, text)
                row += f"  CER={c:.3f}" if c is not None else "  CER=n/a"
                row += f"  telugu_precision={tp:.3f}" if tp is not None else ""
            print(row)

        baseline = results["baseline_prep"]
        for label in ("revote_prep", "clahe_prep", "revote_clahe_prep"):
            diffs = word_diff(baseline, results[label])
            print(f"\n  {label} vs baseline_prep — {len(diffs)} differing span(s) shown:")
            if not diffs:
                print("    (identical)")
            for line in diffs:
                print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
