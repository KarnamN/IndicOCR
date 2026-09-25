"""Second, independent review signal: is the fused line itself plausible Telugu?

``ocr_fusion.fuse_page`` only catches an error when the engines disagree. When
PP-OCRv5, IndicPhotoOCR and Tesseract all misread the same crop the same way
(a real, observed failure mode -- see docs/CURRENT_STATE.md), agreement is
perfect and nothing gets flagged. This module adds a second signal that does not
depend on agreement at all: whether the *chosen* text is plausible Telugu,
using the project's existing dictionary and grapheme-validity tools
(``telugu_spell_checker.py``, ``telugu_text_processor.py`` -- already built and
tuned on real books, not reimplemented here).

A line is flagged when either signal fires:
  - engine disagreement  (``ocr_fusion``'s ``needs_review`` / ``missing_from_paddle``)
  - implausible text      (structurally invalid graphemes, or too many
                           out-of-dictionary words, above a threshold calibrated
                           against this book's own high-confidence lines)

``build_review_queue`` turns a ``fuse_ocr_engines.py`` report into a single flat,
page-ordered list of only the flagged lines -- what a reviewer should actually
look at, instead of a full per-page grid.
"""

from __future__ import annotations

import re
from typing import Sequence

# A short ASCII run in the chosen text that appears in NONE of the other
# candidates is almost always noise (a Telugu conjunct misread as Latin
# letters -- e.g. "CET" for "ఇచ్చారు"), not real English content. Longer runs
# are left alone: a real English phrase (a printer's name, a loanword run) is
# more likely to be several letters long, and one engine correctly reading
# English while the others garble it entirely is a real, if rarer, case this
# would otherwise punish. Found and calibrated on one real example, 2026-09-22
# (docs/CURRENT_STATE.md) -- a single data point, not a tuned threshold.
UNCORROBORATED_ASCII_MAX_LEN = 6

STRUCTURAL_THRESHOLD = 0.05   # invalid_ratio above this: orphaned matra / dangling virama present

# ocr_fusion's own needs_review flag requires >=2 candidates to disagree -- a line
# with only one candidate (engine_router skipped IndicPhotoOCR, or Tesseract found
# nothing there) gets reason "only_engine" and is NEVER flagged by agreement, no
# matter how unconfident PP-OCRv5 itself was. Found live 2026-09-22, book pilot,
# page_130 line 29: PP-OCRv5 read "జాూరగత్ల!" (confidence 0.744, structurally valid,
# so the grammar check missed it too) for what should likely be "జాగ్రత్తగ" --
# would have gone through with zero review signal at all if IndicPhotoOCR had been
# skipped for that page. Set below CONFIDENT (0.85, ocr_fusion.py) on purpose: an
# uncorroborated reading should need to look *more* certain than a corroborated one.
LOW_CONFIDENCE_SOLO_THRESHOLD = 0.80

# OOV_THRESHOLD default is 1.01 -- effectively OFF. Measured 2026-09-22: at 0.40 it
# flagged 77% of all lines (useless -- floods the queue). Calibrating it against this
# book's own "confident_and_confirmed" (agreement-passed) lines pushed the threshold
# to 1.00 (still never fires) -- those lines are only *agreed*, not verified, and
# apparently carry plenty of real rare-word/proper-noun OOV mass themselves, so
# calibrating against them is circular. Leave off (or pass an explicit threshold from
# a book you have real ground truth for) until tests/diagnostics/score_ocr_accuracy.py
# has scored it against human-corrected lines.
OOV_THRESHOLD = 1.01
MIN_ELIGIBLE_TOKENS = 2       # below this, the OOV signal is too noisy to trust (short lines, captions)


def _spell_checker():
    from telugu_spell_checker import get_telugu_spell_checker
    return get_telugu_spell_checker()


def _text_processor():
    from telugu_text_processor import get_telugu_text_processor
    return get_telugu_text_processor()


def distortion_score(text: str) -> dict:
    """Structural validity and dictionary coverage for one line of text.

    Returns:
        {structural_invalid_ratio, oov_ratio, eligible_tokens, oov_words}
    """
    from telugu_text_processor import dictionary_lookup_candidate

    processor = _text_processor()
    checker = _spell_checker()

    validity = processor.grapheme_validity_score(text)
    eligible, oov = [], []
    for token in text.split(" "):
        candidate = dictionary_lookup_candidate(token, processor)
        if candidate is None:
            continue
        eligible.append(candidate)
        if not checker.is_known_word(candidate):
            oov.append(candidate)

    return {
        "structural_invalid_ratio": validity["invalid_ratio"],
        "oov_ratio": (len(oov) / len(eligible)) if eligible else 0.0,
        "eligible_tokens": len(eligible),
        "oov_words": oov,
    }


def uncorroborated_ascii(chosen: str, candidates: dict[str, str]) -> list[str]:
    """Short ASCII runs in ``chosen`` that no other candidate also contains."""
    others = " ".join(text.lower() for name, text in candidates.items() if text != chosen)
    found = []
    for run in re.findall(r"[A-Za-z]+", chosen):
        if len(run) <= UNCORROBORATED_ASCII_MAX_LEN and run.lower() not in others:
            found.append(run)
    return found


def best_candidate(candidates: dict[str, str], current: str) -> tuple[str, dict]:
    """The candidate with the lowest structural-invalid ratio (ties keep ``current``).

    Fusion's agreement voting has no idea whether a candidate is grammatically
    valid Telugu -- it only compares candidates to each other. A candidate that
    is structurally cleaner than the one fusion picked is a concrete, checkable
    suggestion for the reviewer, not just a flag with nothing to act on.
    """
    # CAUTION (measured 2026-09-22, 5-page sample): of 7 structurally-flagged lines
    # where a candidate scored lower than `current`, 5 were clearly better and 1 was
    # a modest improvement, but 1 was WORSE -- a candidate with fluent-looking wrong
    # words scored a lower invalid_ratio than the correct-but-garbled original, since
    # this only checks grapheme grammar, not whether the words are the right ones.
    # Treat this as a suggestion to confirm or edit, never auto-apply it -- the
    # review queue always shows every candidate alongside it for exactly this reason.
    #
    # Also found live the same day (poratam.png line 7): this used to rank purely on
    # structural_invalid_ratio, so it could suggest a candidate that IS grammatically
    # clean Telugu but also carries its own stray Latin fragment ("od" from a Tesseract
    # misread) that the structural check has no opinion on. Candidates with an
    # uncorroborated_ascii hit of their own are now excluded from the running whenever
    # a clean alternative exists, so the suggestion isn't swapping one uncaught defect
    # for another.
    def clean_of_stray_ascii(text: str) -> bool:
        return not uncorroborated_ascii(text, candidates)

    best_text, best_score = current, distortion_score(current)
    best_clean = clean_of_stray_ascii(current)
    for text in candidates.values():
        if text == current:
            continue
        score = distortion_score(text)
        text_clean = clean_of_stray_ascii(text)
        better = (text_clean and not best_clean) or (
            text_clean == best_clean and score["structural_invalid_ratio"] < best_score["structural_invalid_ratio"]
        )
        if better:
            best_text, best_score, best_clean = text, score, text_clean
    return best_text, best_score


def flag_line(line: dict, structural_threshold: float = STRUCTURAL_THRESHOLD,
             oov_threshold: float = OOV_THRESHOLD,
             min_eligible: int = MIN_ELIGIBLE_TOKENS) -> tuple[bool, list[str], dict, str]:
    """Combine ocr_fusion's agreement flag with the distortion signal for one line.

    Returns (needs_review, reasons, score_of_chosen_text, suggested_text) --
    ``suggested_text`` is ``best_candidate``'s pick when the chosen text is
    structurally flagged, else the chosen text unchanged.
    """
    reasons = []
    if line["reason"] == "missing_from_paddle":
        reasons.append("missing_from_paddle")
    elif line.get("needs_review"):
        reasons.append("engine_disagreement")
    elif line["reason"] == "only_engine" and line["paddle_confidence"] < LOW_CONFIDENCE_SOLO_THRESHOLD:
        reasons.append("low_confidence_uncorroborated")

    score = distortion_score(line["text"])
    suggested = line["text"]
    if score["structural_invalid_ratio"] > structural_threshold:
        reasons.append("structurally_invalid_telugu")
        suggested, _ = best_candidate(line["candidates"], line["text"])
    if score["eligible_tokens"] >= min_eligible and score["oov_ratio"] > oov_threshold:
        reasons.append("out_of_dictionary")

    stray = uncorroborated_ascii(line["text"], line["candidates"])
    if stray:
        reasons.append("uncorroborated_ascii")
        score = {**score, "uncorroborated_ascii": stray}
        if suggested == line["text"]:  # not already replaced by the structural check above
            candidate_wo_stray = {n: t for n, t in line["candidates"].items()
                                  if not uncorroborated_ascii(t, line["candidates"])}
            if candidate_wo_stray:
                suggested = next(iter(candidate_wo_stray.values()))

    return bool(reasons), reasons, score, suggested


def calibrate_oov_threshold(fusion_report: dict, percentile: float = 0.95) -> float:
    """Suggest an OOV threshold from this book's own high-confidence, agreed lines.

    CAUTION (measured 2026-09-22): this is circular. "Confident and confirmed"
    means the engines agreed, not that the line is correct -- two engines making
    the same misread still counts as agreement, and that is exactly the failure
    mode this module exists to catch. On this book it calibrated to a threshold
    of 1.00, i.e. never fires. Kept for when real human-corrected ground truth is
    available to calibrate against instead (see score_ocr_accuracy.py); until
    then prefer the structural check alone, or pass a threshold chosen by hand
    after reading a sample of the flagged lines it produces.
    """
    rates = []
    for page in fusion_report["images"].values():
        for line in page["lines"]:
            if line.get("reason") != "confident_and_confirmed":
                continue
            score = distortion_score(line["text"])
            if score["eligible_tokens"] >= MIN_ELIGIBLE_TOKENS:
                rates.append(score["oov_ratio"])
    if not rates:
        return OOV_THRESHOLD
    rates.sort()
    return rates[min(len(rates) - 1, int(len(rates) * percentile))]


def build_review_queue(fusion_report: dict, **flag_kwargs) -> dict:
    """Flag every line in a fuse_ocr_engines.py report and build the review queue."""
    queue = []
    per_page = {}
    for page_name, page in fusion_report["images"].items():
        flagged = 0
        for i, line in enumerate(page["lines"]):
            needs_review, reasons, score, suggested = flag_line(line, **flag_kwargs)
            if needs_review:
                flagged += 1
                queue.append({
                    "page": page_name,
                    "line": i,
                    "text": line["text"],
                    "suggested_text": suggested,
                    "reasons": reasons,
                    "chosen": line["chosen"],
                    "agreement": line["agreement"],
                    "distortion": score,
                    "candidates": line["candidates"],
                })
        per_page[page_name] = {"lines": len(page["lines"]), "flagged": flagged,
                               "flagged_rate": flagged / len(page["lines"]) if page["lines"] else 0.0}

    total_lines = sum(p["lines"] for p in per_page.values())
    total_flagged = sum(p["flagged"] for p in per_page.values())
    pages_touched = sum(1 for p in per_page.values() if p["flagged"] > 0)
    return {
        "per_page": per_page,
        "queue": queue,
        "summary": {
            "pages": len(per_page),
            "pages_with_any_flag": pages_touched,
            "pages_with_any_flag_rate": pages_touched / len(per_page) if per_page else 0.0,
            "total_lines": total_lines,
            "total_flagged": total_flagged,
            "line_flag_rate": total_flagged / total_lines if total_lines else 0.0,
        },
    }
