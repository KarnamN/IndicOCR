#!/usr/bin/env python3
"""
calibrate_stroke_correction.py — Validation data for the missing-stroke repair feature
=========================================================================================
TeluguPostProcessor.correct_spelling() (src/telugu_post_processor.py) can now repair a
single missing/extra matra or vattu-conjunct stroke on an otherwise-clean, dictionary-
unknown word (e.g. వాడు OCR'd as వడు) — see classify_single_stroke_edit() in
src/telugu_text_processor.py. This is gated OFF by default
(ENABLE_TELUGU_STROKE_CORRECTION=False, src/config.py) pending review, because unlike a
detection signal (which only needs a threshold), this actually MUTATES text — every
accepted correction needs to be individually right, not just statistically plausible.

This script runs correct_spelling() with the flag on over the real page texts already in
data/temp/ (from prior conversion runs) and prints every accepted stroke-correction for
manual review, following the "max observed: 3 corrections per page" precedent from the
existing structural-correction feature (docs/TELUGU_SPELL_CORRECTION_TODO.md) — expect a
similarly small, fully human-reviewable volume, so this prints everything rather than
sampling or computing a distribution.

Usage:
  python scripts/calibrate_stroke_correction.py [--data-dir data/temp] [--limit N]
"""

import sys
import json
import argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import config  # noqa: F401 -- satisfies `import config` in telugu_post_processor.py
from telugu_post_processor import TeluguPostProcessor


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', default='data/temp', help='Root directory to walk for *_text*.json samples')
    parser.add_argument('--limit', type=int, default=0, help='Stop after scanning this many files (0 = no limit)')
    args = parser.parse_args()

    root = Path(args.data_dir)
    files = sorted(root.glob('**/*_text*.json'))
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"No *_text*.json samples found under {root}")
        return

    processor = TeluguPostProcessor(
        enable_shloka_fixes=False,
        enable_char_fixes=False,
        enable_punctuation_fixes=False,
        enable_stray_english_cleanup=False,
        enable_conjunct_ra_fixes=False,
        enable_dictionary_correction=True,   # outer gate -- correct_spelling() only runs when this is on
        enable_stroke_correction=True,       # the feature under review
    )

    print(f"Scanning {len(files)} real OCR text samples under {root} for stroke-repair corrections ...")

    total_corrections = 0
    category_counts = Counter()
    read_errors = 0

    for i, path in enumerate(files, 1):
        if i % 500 == 0:
            print(f"  ... {i}/{len(files)}")
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            read_errors += 1
            continue

        text = data.get('text', '') or ''
        if len(text.strip()) < 10:
            continue

        _corrected_text, corrections = processor.correct_spelling(text)
        stroke_corrections = [c for c in corrections if 'category' in c]
        for c in stroke_corrections:
            total_corrections += 1
            category_counts[c['category']] += 1
            print(f"\n  [{c['category']}] {c['from']!r} -> {c['to']!r}  (distance={c['distance']})")
            print(f"    source: {path}")

    print()
    print(f"Samples scanned: {len(files)} ({read_errors} unreadable)")
    print(f"Total stroke-repair corrections: {total_corrections}")
    for category, count in category_counts.most_common():
        print(f"  {category}: {count}")

    print()
    print("Review every correction printed above. If they all look like genuine stroke")
    print("restorations (not accidental real-word-to-real-word substitutions), it's safe")
    print("to consider flipping ENABLE_TELUGU_STROKE_CORRECTION on. Any that look wrong")
    print("indicate the classifier or dictionary needs tightening before enabling.")


if __name__ == '__main__':
    main()
