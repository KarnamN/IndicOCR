#!/usr/bin/env python3
"""
calibrate_oov_ratio.py — Calibration data for the Telugu dictionary OOV junk signal
=====================================================================================
PageComplexityAnalyzer._compute_oov_ratio() (src/page_complexity_analyzer.py) is wired
into is_junk_text() but gated OFF by default (ENABLE_TELUGU_OOV_JUNK_SIGNAL=False,
src/config.py) because — unlike the existing grapheme_ratio signal, which was
calibrated against ~4,700 real pages before its 2.5% threshold was trusted — there is
no real-page distribution data yet for what a normal/acceptable OOV ratio looks like.
Real books have proper nouns, rare/technical words, and dictionary gaps that inflate
OOV ratio even on genuinely clean pages, so an unvalidated threshold risks discarding
good text.

This script walks the real extracted-text samples already on disk in data/temp/ (from
prior conversion runs) and reports the OOV-ratio distribution, split by whether the
page is already flagged junk by the EXISTING signals (structural/grammar) or currently
passes — so a real threshold for OOV_JUNK_RATIO_THRESHOLD can be picked from evidence
instead of a guess, and any suspiciously-high-OOV "currently clean" pages can be
eyeballed for false-positive risk before ENABLE_TELUGU_OOV_JUNK_SIGNAL is ever flipped.

Usage:
  python scripts/calibrate_oov_ratio.py [--data-dir data/temp] [--examples 10]
"""

import sys
import json
import argparse
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import config  # noqa: F401 -- satisfies `import config` in page_complexity_analyzer.py
from page_complexity_analyzer import PageComplexityAnalyzer


def percentiles(values):
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n < 2:
        return {p: sorted_vals[0] for p in (50, 75, 90, 95, 99)}
    quantiles = statistics.quantiles(sorted_vals, n=100, method='inclusive')
    return {p: quantiles[p - 1] for p in (50, 75, 90, 95, 99)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', default='data/temp', help='Root directory to walk for *_text*.json samples')
    parser.add_argument('--examples', type=int, default=10, help='How many high-OOV "currently clean" examples to print')
    args = parser.parse_args()

    root = Path(args.data_dir)
    files = sorted(root.glob('**/*_text*.json'))
    if not files:
        print(f"No *_text*.json samples found under {root}")
        return

    print(f"Scanning {len(files)} real OCR text samples under {root} ...")

    already_junk_ratios = []
    currently_clean_ratios = []
    high_oov_clean_examples = []  # (oov_ratio, checked, unknown, engine, path, text_excerpt)
    skipped_too_short = 0
    read_errors = 0

    for i, path in enumerate(files, 1):
        if i % 500 == 0:
            print(f"  ... {i}/{len(files)}")
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            read_errors += 1
            continue

        text = data.get('text', '') or ''
        if len(text.strip()) < 50:
            skipped_too_short += 1
            continue

        diagnostics = {}
        is_junk = PageComplexityAnalyzer.is_junk_text(text, diagnostics=diagnostics)
        oov_ratio = diagnostics.get('oov_ratio', 0.0)
        oov_checked = diagnostics.get('oov_checked_count', 0)
        oov_unknown = diagnostics.get('oov_unknown_count', 0)

        if oov_checked < 8:  # mirrors OOV_JUNK_MIN_WORDS default — not enough signal on tiny pages
            continue

        if is_junk:
            already_junk_ratios.append(oov_ratio)
        else:
            currently_clean_ratios.append(oov_ratio)
            if oov_ratio > 0.3:
                high_oov_clean_examples.append(
                    (oov_ratio, oov_checked, oov_unknown, data.get('ocr_engine', '?'), path, text[:200])
                )

    print()
    print(f"Samples: {len(files)} total, {skipped_too_short} too short (<50 chars), {read_errors} unreadable")
    print(f"Scored (>= 8 dictionary-eligible words): "
          f"{len(already_junk_ratios)} already junk (existing signals), "
          f"{len(currently_clean_ratios)} currently clean")
    print()

    for label, values in (
        ("Already junk (existing structural/grammar signals)", already_junk_ratios),
        ("Currently clean (passes all existing signals)", currently_clean_ratios),
    ):
        print(f"-- {label} -- n={len(values)}")
        if values:
            p = percentiles(values)
            print(f"   p50={p[50]:.3f}  p75={p[75]:.3f}  p90={p[90]:.3f}  p95={p[95]:.3f}  p99={p[99]:.3f}")
        print()

    high_oov_clean_examples.sort(key=lambda t: t[0], reverse=True)
    print(f"-- Top {min(args.examples, len(high_oov_clean_examples))} highest-OOV 'currently clean' pages "
          f"(review for false-positive risk: proper nouns, rare/technical words, or genuine hallucination) --")
    for oov_ratio, checked, unknown, engine, path, excerpt in high_oov_clean_examples[:args.examples]:
        print(f"\n  oov={unknown}/{checked} ({oov_ratio*100:.1f}%)  engine={engine}  {path}")
        print(f"  {excerpt!r}")

    print()
    print("Explicitly out of scope for this script: picking OOV_JUNK_RATIO_THRESHOLD and flipping "
          "ENABLE_TELUGU_OOV_JUNK_SIGNAL. Use the percentile breakdown and the flagged examples above "
          "to make that call once real evidence is in hand.")


if __name__ == '__main__':
    main()
