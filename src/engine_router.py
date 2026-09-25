"""Decide, per page, whether the slow IndicPhotoOCR pass is worth running.

IndicPhotoOCR is 3-10x slower than PP-OCRv5 (see docs/CURRENT_STATE.md, Speed
Work) and its value is concentrated on pages where PP-OCRv5 is struggling -- on
a clean page it rarely changes the outcome (see the correlation below). Always
running it on every page is the safe default; this router is for a batch job
where that cost matters and skipping it on easy pages is worth the small,
measured risk of missing something on a page that looked easy but wasn't
(see ``review_queue.LOW_CONFIDENCE_SOLO_THRESHOLD``, which exists specifically
to catch some of what a skip would otherwise lose).

Trigger, any one of:
  - PP-OCRv5's own average line confidence on the page is low
  - Tesseract found little or no text on the page (a strong independent
    "this page is hard" signal, cheaper than running IndicPhotoOCR to find out)
  - PP-OCRv5's own chosen text is structurally invalid Telugu on more than a
    few lines (see review_queue.py)

Calibrated 2026-09-22 against 17 real pages (5 standalone samples + 12 pages
spread across a real 258-page book) with all three engines already run:
triggered on 12/17 (71%), caught 4 of 5 pages where IndicPhotoOCR's candidate
demonstrably mattered to a flagged line, missed 1 (page_130 -- caught instead
by the low-confidence-solo review flag added the same day). Not a tuned
model -- three thresholds picked by eye from one book's data. Re-check before
trusting it on a different book.
"""

from __future__ import annotations

from typing import Sequence

PADDLE_CONFIDENCE_THRESHOLD = 0.93
TESSERACT_COVERAGE_THRESHOLD = 0.95
STRUCTURAL_BAD_RATE_THRESHOLD = 0.05


def should_run_indicphoto(paddle_lines: Sequence[dict], tesseract_words: Sequence[dict],
                          threshold_conf: float = PADDLE_CONFIDENCE_THRESHOLD,
                          threshold_coverage: float = TESSERACT_COVERAGE_THRESHOLD,
                          threshold_struct: float = STRUCTURAL_BAD_RATE_THRESHOLD) -> tuple[bool, dict]:
    """Page-level decision from PP-OCRv5 + Tesseract output alone (both cheap/fast).

    ``paddle_lines`` is ``ocr_fusion.paddle_line`` output (has ``text``,
    ``confidence``, ``bbox``); ``tesseract_words`` is the same per-word list
    ``fuse_ocr_engines.py`` builds from ``OCRProcessor.extract_text_with_boxes``.
    Returns (run_indicphoto, metrics) so the caller can log why.
    """
    from ocr_fusion import assign_words
    from review_queue import distortion_score

    if not paddle_lines:
        return True, {"reason": "no_paddle_lines"}  # nothing to base a skip on -- be safe

    avg_conf = sum(line["confidence"] for line in paddle_lines) / len(paddle_lines)
    tess_by_line = assign_words(tesseract_words, [line["bbox"] for line in paddle_lines])
    coverage = sum(1 for text in tess_by_line if text) / len(paddle_lines)
    struct_bad = sum(1 for line in paddle_lines
                     if distortion_score(line["text"])["structural_invalid_ratio"] > 0.05)
    struct_rate = struct_bad / len(paddle_lines)

    metrics = {
        "avg_paddle_confidence": round(avg_conf, 3),
        "tesseract_coverage": round(coverage, 3),
        "structural_bad_rate": round(struct_rate, 3),
    }
    triggers = []
    if avg_conf < threshold_conf:
        triggers.append(f"low_paddle_confidence({avg_conf:.2f}<{threshold_conf})")
    if coverage < threshold_coverage:
        triggers.append(f"low_tesseract_coverage({coverage:.0%}<{threshold_coverage:.0%})")
    if struct_rate > threshold_struct:
        triggers.append(f"high_structural_bad_rate({struct_rate:.0%}>{threshold_struct:.0%})")

    metrics["triggers"] = triggers
    return bool(triggers), metrics
