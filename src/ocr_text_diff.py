"""
ocr_text_diff.py — Word-level comparison between two OCR readings
====================================================================
Generalizes the difflib-based word alignment already used by
PaddleV5Processor._merge_ocr_texts() (paddle_v5_processor.py) into a reusable
comparison tool, without that function's merge-selection logic. Used to build
a compact "these words disagree" summary for Gemini reference-grounding
prompts, and to log an agreement ratio between two OCR outputs.
"""

import difflib
from typing import Dict, List


def compute_word_diff_spans(text_a: str, text_b: str) -> List[Dict]:
    """
    Word-level alignment between two OCR texts, in reading order.

    Returns a list of spans:
      {'tag': 'equal'|'replace'|'delete'|'insert', 'a': [...words...], 'b': [...words...]}
    'a'/'b' hold the words from text_a/text_b in that span — empty for the
    side that had nothing there ('delete' means only text_a had words,
    'insert' means only text_b did).
    """
    words_a = text_a.split()
    words_b = text_b.split()
    matcher = difflib.SequenceMatcher(None, words_a, words_b)
    return [
        {'tag': tag, 'a': words_a[i1:i2], 'b': words_b[j1:j2]}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def agreement_ratio(text_a: str, text_b: str) -> float:
    """
    Fraction of words two OCR texts agree on (0.0-1.0), via
    difflib.SequenceMatcher.ratio() over their word sequences — a cheap proxy
    for how much two independent OCR engines agree on a page. 1.0 for two
    empty texts (nothing to disagree on).
    """
    words_a = text_a.split()
    words_b = text_b.split()
    if not words_a and not words_b:
        return 1.0
    return difflib.SequenceMatcher(None, words_a, words_b).ratio()


def summarize_diff_spans(spans: List[Dict], max_spans: int = 20,
                          label_a: str = 'A', label_b: str = 'B') -> str:
    """
    Human/LLM-readable summary of the disagreement spans only (skips 'equal'
    spans — nothing to report there). Caps at max_spans entries so a page
    with pervasive disagreement doesn't blow up a prompt's size.
    """
    lines = []
    disagreements = [s for s in spans if s['tag'] != 'equal']
    for span in disagreements:
        if len(lines) >= max_spans:
            lines.append(f"... ({len(disagreements) - len(lines)} more disagreements not shown)")
            break
        a_text = ' '.join(span['a']) or '(nothing)'
        b_text = ' '.join(span['b']) or '(nothing)'
        lines.append(f"  {label_a}: {a_text!r}  vs  {label_b}: {b_text!r}")
    return '\n'.join(lines) if lines else '(no disagreements — both readings match)'
