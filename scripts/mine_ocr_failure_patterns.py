#!/usr/bin/env python3
"""
mine_ocr_failure_patterns.py — Systematic OCR failure analysis across every cached book
==========================================================================================
Step 0 of the Tesseract fine-tuning plan (see the plan file / docs/TELUGU_SPELL_CORRECTION_TODO.md
for background). Everything known so far about where Tesseract/PaddleOCR fail came from manually
inspecting two pages the user happened to flag. This script quantifies failure patterns across
every book already sitting in data/temp/, reusing detection logic already built and validated
this session — no new heuristics:

  1. Line-level garbled-word rate — the signal that caught Nuvve_naa_pranam page 34: lines that
     are >=80% out-of-dictionary with 5+ dictionary-eligible words checked are reliably corrupted
     (unlike the page-level OOV ratio, which is too confounded by morphology/devotional content
     to gate on — see docs/TELUGU_SPELL_CORRECTION_TODO.md item 6).
  2. Conjunct/matra drop rate — for pages where both a Tesseract-only and PaddleOCR-only capture
     exist (_log_ocr_comparison's output, only present for Gemini-final pages), classify every
     Paddle-vs-Tesseract word disagreement via TeluguTextProcessor.classify_single_stroke_edit().
  3. Cross-script confusion rate — words mixing Telugu and Latin characters (the failure class
     telugu_post_processor.py's CHAR_FIXES table patches after the fact), per engine.
  4. Line/word-count escalation reasons — tallied from each book's converter_events.jsonl.

Output: a ranked report of which failure category is most frequent, across how many books/pages,
with concrete examples — meant to decide what a fine-tuning corpus should prioritize, not to
gate/auto-fix anything itself.

Usage:
  python scripts/mine_ocr_failure_patterns.py [--data-dir data/temp] [--examples 5]
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import config  # noqa: F401 -- satisfies `import config` in telugu_text_processor.py etc.
from telugu_text_processor import get_telugu_text_processor, dictionary_lookup_candidate
from telugu_spell_checker import get_telugu_spell_checker
from ocr_text_diff import compute_word_diff_spans

LINE_OOV_THRESHOLD = 0.80
LINE_OOV_MIN_CHECKED = 5

_CONTAMINATED_RE_TELUGU = re.compile(r'[ఀ-౿]')
_CONTAMINATED_RE_LATIN = re.compile(r'[a-zA-Z]')


def is_word_contaminated(word: str) -> bool:
    """Same predicate as PaddleV5Processor._is_word_contaminated, reimplemented inline
    to avoid instantiating the whole (model-loading) PaddleV5Processor just for this check."""
    return bool(_CONTAMINATED_RE_TELUGU.search(word) and _CONTAMINATED_RE_LATIN.search(word))


def line_oov_ratio(line: str, text_processor, spell_checker) -> (float, int):
    checked = 0
    unknown = 0
    for word in line.split():
        candidate = dictionary_lookup_candidate(word, text_processor)
        if candidate is None:
            continue
        checked += 1
        if not spell_checker.is_known_word(candidate):
            unknown += 1
    ratio = (unknown / checked) if checked > 0 else 0.0
    return ratio, checked


def analyze_book(book_dir: Path, text_processor, spell_checker, examples_cap: int):
    """Returns a dict of aggregate stats for one book."""
    stats = {
        'book': book_dir.name,
        'pages_scanned': 0,
        'garbled_lines': 0,
        'eligible_lines': 0,
        'garbled_examples': [],
        'stroke_categories': Counter(),
        'stroke_examples': defaultdict(list),
        'contaminated_words': {'tesseract': 0, 'paddle': 0},
        'total_words': {'tesseract': 0, 'paddle': 0},
        'escalation_reasons': Counter(),
    }

    for text_path in sorted(book_dir.glob('page_*_0_text.json')):
        try:
            with open(text_path, encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            continue
        text = d.get('text', '') or ''
        if len(text.strip()) < 20:
            continue
        stats['pages_scanned'] += 1

        for line in text.split('\n'):
            if not line.strip():
                continue
            ratio, checked = line_oov_ratio(line, text_processor, spell_checker)
            if checked < LINE_OOV_MIN_CHECKED:
                continue
            stats['eligible_lines'] += 1
            if ratio >= LINE_OOV_THRESHOLD:
                stats['garbled_lines'] += 1
                if len(stats['garbled_examples']) < examples_cap:
                    stats['garbled_examples'].append((text_path.name, line.strip()))

        # Conjunct/matra drop + cross-script confusion: only where the comparison
        # captures exist (Gemini-final pages) -- see _log_ocr_comparison().
        page_stem = text_path.stem  # page_{N}_0_text
        tess_path = book_dir / f"{page_stem}_tesseract.json"
        paddle_path = book_dir / f"{page_stem}_paddleocr.json"
        if not (tess_path.exists() and paddle_path.exists()):
            continue
        try:
            with open(tess_path, encoding='utf-8') as f:
                tess_text = json.load(f).get('text', '') or ''
            with open(paddle_path, encoding='utf-8') as f:
                paddle_text = json.load(f).get('text', '') or ''
        except Exception:
            continue

        for word in tess_text.split():
            stats['total_words']['tesseract'] += 1
            if is_word_contaminated(word):
                stats['contaminated_words']['tesseract'] += 1
        for word in paddle_text.split():
            stats['total_words']['paddle'] += 1
            if is_word_contaminated(word):
                stats['contaminated_words']['paddle'] += 1

        spans = compute_word_diff_spans(paddle_text, tess_text)
        for span in spans:
            if span['tag'] != 'replace' or len(span['a']) != len(span['b']):
                continue
            for pw, tw in zip(span['a'], span['b']):
                edit_type = text_processor.classify_single_stroke_edit(pw, tw)
                if edit_type is None:
                    continue
                stats['stroke_categories'][edit_type] += 1
                if len(stats['stroke_examples'][edit_type]) < examples_cap:
                    stats['stroke_examples'][edit_type].append((text_path.name, pw, tw))

    events_path = book_dir / 'converter_events.jsonl'
    if events_path.exists():
        try:
            with open(events_path, encoding='utf-8') as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get('event_type') == 'escalation':
                        stats['escalation_reasons'][d.get('reason', '?')] += 1
        except Exception:
            pass

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', default='data/temp', help='Root directory containing per-book subfolders')
    parser.add_argument('--examples', type=int, default=5, help='Example rows to keep per category per book')
    parser.add_argument('--book', default='', help='Only analyze one book (subfolder name substring match)')
    args = parser.parse_args()

    root = Path(args.data_dir)
    book_dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if args.book:
        book_dirs = [b for b in book_dirs if args.book in b.name]
    if not book_dirs:
        print(f"No book directories found under {root}")
        return

    text_processor = get_telugu_text_processor()
    spell_checker = get_telugu_spell_checker()

    print(f"Scanning {len(book_dirs)} book(s) under {root} ...")
    all_stats = []
    for book_dir in book_dirs:
        stats = analyze_book(book_dir, text_processor, spell_checker, args.examples)
        if stats['pages_scanned'] == 0:
            continue
        all_stats.append(stats)
        garbled_pct = (stats['garbled_lines'] / stats['eligible_lines'] * 100) if stats['eligible_lines'] else 0.0
        print(f"  {stats['book']:<40} pages={stats['pages_scanned']:>4} "
              f"garbled_lines={stats['garbled_lines']:>4}/{stats['eligible_lines']:<4} ({garbled_pct:4.1f}%)")

    print()
    print("=" * 78)
    print("RANKED SUMMARY")
    print("=" * 78)

    print("\n-- 1. Line-level garbled-word rate (per book, highest first) --")
    ranked = sorted(all_stats, key=lambda s: (s['garbled_lines'] / s['eligible_lines']) if s['eligible_lines'] else 0, reverse=True)
    for s in ranked[:15]:
        if s['eligible_lines'] == 0:
            continue
        pct = s['garbled_lines'] / s['eligible_lines'] * 100
        print(f"  {pct:5.1f}%  ({s['garbled_lines']}/{s['eligible_lines']} lines)  {s['book']}")
    print("\n  Examples from the worst book:")
    if ranked and ranked[0]['garbled_examples']:
        for fname, line in ranked[0]['garbled_examples']:
            print(f"    [{fname}] {line}")

    print("\n-- 2. Conjunct/matra drop categories (aggregate across all books) --")
    total_categories = Counter()
    category_examples = defaultdict(list)
    for s in all_stats:
        for cat, n in s['stroke_categories'].items():
            total_categories[cat] += n
        for cat, examples in s['stroke_examples'].items():
            category_examples[cat].extend((s['book'],) + e for e in examples[:args.examples])
    for cat, n in total_categories.most_common():
        print(f"  {cat}: {n}")
        for book, fname, pw, tw in category_examples[cat][:args.examples]:
            print(f"    [{book}/{fname}] paddle={pw!r} vs tesseract={tw!r}")

    print("\n-- 3. Cross-script (Telugu+Latin mixed) word contamination rate, per engine --")
    total_contaminated = Counter()
    total_words = Counter()
    for s in all_stats:
        for engine in ('tesseract', 'paddle'):
            total_contaminated[engine] += s['contaminated_words'][engine]
            total_words[engine] += s['total_words'][engine]
    for engine in ('tesseract', 'paddle'):
        tw = total_words[engine]
        pct = (total_contaminated[engine] / tw * 100) if tw else 0.0
        print(f"  {engine}: {total_contaminated[engine]}/{tw} words ({pct:.2f}%)")

    print("\n-- 4. Escalation reasons (aggregate across all books) --")
    total_reasons = Counter()
    for s in all_stats:
        total_reasons.update(s['escalation_reasons'])
    for reason, n in total_reasons.most_common():
        print(f"  {reason}: {n}")

    print()
    print("=" * 78)
    print("This report is descriptive only -- it doesn't gate or fix anything. Use it to decide")
    print("what a fine-tuning corpus should prioritize before committing to Step 1.")


if __name__ == '__main__':
    main()
