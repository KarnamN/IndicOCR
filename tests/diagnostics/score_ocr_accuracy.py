"""Score PP-OCRv5, IndicPhotoOCR, Tesseract, and the fused text against ground truth.

Ground truth is the JSON downloaded from ocr_comparison/fusion/fusion.html's
"Download corrections" button: ``{page_name: [line0, line1, ...]}``, one entry
per line of ``fusion.json``'s ``lines`` array for that page (blank string where
a fusion line is entirely wrong or missing text should be transcribed there).

Run from the repository root, no OCR engines needed (scores an existing
fusion.json):
    python tests/diagnostics/score_ocr_accuracy.py \
        ocr_comparison/fusion/fusion.json ground_truth_corrections.json

Metrics, per engine and per page, then averaged over all lines in all pages:
    CER       character error rate, Levenshtein distance over grapheme
              clusters (matches ocr_fusion.letters, so a Telugu consonant
              plus its vowel signs counts as one unit), punctuation/spaces/
              digits ignored, divided by the ground-truth line's length.
    WER       word error rate, Levenshtein distance over whitespace-split
              tokens. Telugu script does not reliably delimit words with
              spaces, so this under-counts errors within a run-together
              Telugu span; treat it as indicative for the English words and
              as a loose upper bound for Telugu.
    Telugu char precision   1 - CER computed after keeping only Telugu-block
              clusters (U+0C00-U+0C7F) in both ground truth and hypothesis.
    English word accuracy   fraction of the ground truth's ASCII alphabetic
              words that also appear in the hypothesis (multiset match, so a
              repeated word must repeat).
    Missing-line rate       fraction of non-blank ground-truth lines whose
              hypothesis is blank or has CER >= 0.9 (effectively unrelated).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ocr_fusion import letters  # noqa: E402  (grapheme-cluster tokenizer, shared with fusion)

ENGINES = ("paddle", "indicphoto", "tesseract", "fused")
TELUGU_RANGE = range(0x0C00, 0x0C80)


def _levenshtein(ref: Sequence, hyp: Sequence) -> int:
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


def cer(ref: str, hyp: str) -> float | None:
    ref_units = letters(ref)
    if not ref_units:
        return None  # nothing to score against on this line
    return _levenshtein(ref_units, letters(hyp)) / len(ref_units)


def wer(ref: str, hyp: str) -> float | None:
    ref_words = ref.split()
    if not ref_words:
        return None
    return _levenshtein(ref_words, hyp.split()) / len(ref_words)


def telugu_char_precision(ref: str, hyp: str) -> float | None:
    ref_telugu = [c for c in letters(ref) if ord(c[0]) in TELUGU_RANGE]
    if not ref_telugu:
        return None
    hyp_telugu = [c for c in letters(hyp) if ord(c[0]) in TELUGU_RANGE]
    return 1 - _levenshtein(ref_telugu, hyp_telugu) / len(ref_telugu)


def english_word_accuracy(ref: str, hyp: str) -> float | None:
    ref_words = re.findall(r"[A-Za-z]+", ref.lower())
    if not ref_words:
        return None
    from collections import Counter

    ref_counts, hyp_counts = Counter(ref_words), Counter(re.findall(r"[A-Za-z]+", hyp.lower()))
    matched = sum(min(count, hyp_counts[word]) for word, count in ref_counts.items())
    return matched / len(ref_words)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def score_page(fusion_lines: list[dict], ground_truth: list[str]) -> dict:
    per_engine = {engine: {"cer": [], "wer": [], "telugu": [], "english": [], "missing": 0, "scored": 0}
                  for engine in ENGINES}
    for line, ref in zip(fusion_lines, ground_truth):
        ref = (ref or "").strip()
        if not ref:
            continue
        hyps = dict(line["candidates"])
        hyps["fused"] = line["text"]
        for engine in ENGINES:
            hyp = hyps.get(engine, "")
            bucket = per_engine[engine]
            c = cer(ref, hyp)
            if c is None:
                continue
            bucket["scored"] += 1
            bucket["cer"].append(min(c, 1.0))
            w = wer(ref, hyp)
            if w is not None:
                bucket["wer"].append(min(w, 1.0))
            t = telugu_char_precision(ref, hyp)
            if t is not None:
                bucket["telugu"].append(max(t, 0.0))
            e = english_word_accuracy(ref, hyp)
            if e is not None:
                bucket["english"].append(e)
            if not hyp.strip() or c >= 0.9:
                bucket["missing"] += 1
    return {
        engine: {
            "lines_scored": bucket["scored"],
            "cer": _mean(bucket["cer"]),
            "wer": _mean(bucket["wer"]),
            "telugu_char_precision": _mean(bucket["telugu"]),
            "english_word_accuracy": _mean(bucket["english"]),
            "missing_line_rate": bucket["missing"] / bucket["scored"] if bucket["scored"] else None,
        }
        for engine, bucket in per_engine.items()
    }


def _fmt(value: float | None, as_percent: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}" if as_percent else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fusion_json", type=Path)
    parser.add_argument("ground_truth_json", type=Path)
    parser.add_argument("--output", type=Path, help="Optional path to save the scores as JSON.")
    args = parser.parse_args()

    fusion = json.loads(args.fusion_json.read_text(encoding="utf-8"))["images"]
    ground_truth = json.loads(args.ground_truth_json.read_text(encoding="utf-8"))

    missing_pages = [page for page in ground_truth if page not in fusion]
    if missing_pages:
        print(f"[warn] ground truth has pages not in fusion.json, skipping: {missing_pages}")

    all_scores: dict[str, dict] = {}
    for page, ref_lines in ground_truth.items():
        if page not in fusion:
            continue
        page_scores = score_page(fusion[page]["lines"], ref_lines)
        all_scores[page] = page_scores
        scored = next((s["lines_scored"] for s in page_scores.values() if s["lines_scored"]), 0)
        print(f"\n{page}  ({scored} ground-truth lines scored)")
        print(f"  {'engine':12}{'CER':>7}{'WER':>7}{'Telugu prec':>13}{'English acc':>13}{'missing':>9}")
        for engine, s in page_scores.items():
            print(f"  {engine:12}{_fmt(s['cer']):>7}{_fmt(s['wer']):>7}"
                  f"{_fmt(s['telugu_char_precision']):>13}{_fmt(s['english_word_accuracy']):>13}"
                  f"{_fmt(s['missing_line_rate']):>9}")

    if not all_scores:
        print("No pages in the ground truth matched fusion.json — nothing scored.")
        return 1

    print(f"\nOverall ({len(all_scores)} page(s))")
    print(f"  {'engine':12}{'CER':>7}{'WER':>7}{'Telugu prec':>13}{'English acc':>13}{'missing':>9}")
    overall = {}
    for engine in ENGINES:
        overall[engine] = {
            metric: _mean([s[engine][metric] for s in all_scores.values() if s[engine][metric] is not None])
            for metric in ("cer", "wer", "telugu_char_precision", "english_word_accuracy", "missing_line_rate")
        }
        s = overall[engine]
        print(f"  {engine:12}{_fmt(s['cer']):>7}{_fmt(s['wer']):>7}"
              f"{_fmt(s['telugu_char_precision']):>13}{_fmt(s['english_word_accuracy']):>13}"
              f"{_fmt(s['missing_line_rate']):>9}")

    if args.output:
        args.output.write_text(json.dumps({"pages": all_scores, "overall": overall}, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"\nSaved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
