"""Line-level fusion of PP-OCRv5, IndicPhotoOCR, and Tesseract output.

PP-OCRv5 supplies the skeleton (line boxes, reading order, punctuation, a
confidence per line). For every PP-OCRv5 line the words the other engines read
inside that box are gathered into one candidate each. The candidates vote by
agreement, measured on Telugu character clusters (a consonant plus its vowel
signs counts as one unit) with spaces, punctuation and digits ignored, so a
single wrong vowel sign costs one unit instead of several code points.

Rules, in order:

1. PP-OCRv5 is confident and confirmed by another engine  -> keep PP-OCRv5.
2. Three candidates                                        -> keep the medoid
   (best mean agreement with the others); ties go to PP-OCRv5.
3. Two candidates that disagree                            -> keep PP-OCRv5 if it
   is confident, otherwise the other engine.
4. Nothing agrees with anything                            -> keep PP-OCRv5 and
   flag the line for review.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Sequence

try:
    import regex

    def _clusters(text: str) -> list[str]:
        return regex.findall(r"\X", text)
except ImportError:  # grapheme clusters need the optional `regex` package
    def _clusters(text: str) -> list[str]:
        return list(text)

CONFIDENT = 0.85          # PP-OCRv5 line confidence treated as reliable
CONFIRMED = 0.80          # agreement with another engine that confirms a line
REVIEW_BELOW = 0.60       # best pairwise agreement under this flags the line
_TRAILING_PUNCT = re.compile(r"[.,;:?!।\"'”’)\]]+$")


def letters(text: str) -> list[str]:
    """Comparable units: character clusters without spaces, punctuation or digits."""
    text = unicodedata.normalize("NFC", text).replace("౦", "ం")
    return _clusters(re.sub(r"[\W_\d]+", "", text, flags=re.UNICODE))


def similarity(a: str, b: str) -> float:
    ua, ub = letters(a), letters(b)
    if not ua and not ub:
        return 1.0
    return difflib.SequenceMatcher(None, ua, ub, autojunk=False).ratio()


def _center(bbox: Sequence[float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def assign_words(words: Sequence[dict], boxes: Sequence[Sequence[float]]) -> list[str]:
    """Give every word to exactly one box and return the joined text per box.

    PP-OCRv5 boxes are padded (``unclip_ratio``) and overlap neighbouring lines, so
    "the word's centre is inside the box" matches several lines. Each word instead
    goes to the box that horizontally contains its centre and whose vertical centre
    is nearest, measured in box heights; words further than one box height from
    every box are dropped.
    """
    per_box: list[list[dict]] = [[] for _ in boxes]
    for word in words:
        cx, cy = _center(word["bbox"])
        best, best_distance = None, 1.0
        for index, (x1, y1, x2, y2) in enumerate(boxes):
            if not x1 <= cx <= x2:
                continue
            height = max(1.0, y2 - y1)
            distance = abs(cy - (y1 + y2) / 2) / height
            if distance < best_distance:
                best, best_distance = index, distance
        if best is not None:
            per_box[best].append(word)
    return [
        " ".join(word["text"] for word in sorted(group, key=lambda w: w["bbox"][0]) if word["text"].strip())
        for group in per_box
    ]


def orphan_words(words: Sequence[dict], boxes: Sequence[Sequence[float]]) -> list[dict]:
    """Words from ``assign_words``'s input that landed in no PP-OCRv5 box.

    A word PP-OCRv5's detector missed entirely is invisible to the rest of fusion,
    since every fused line starts from a PP-OCRv5 box. These are what is left over
    -- the raw material for ``missing_lines``.
    """
    assigned_ids = set()
    for word in words:
        cx, cy = _center(word["bbox"])
        best, best_distance = None, 1.0
        for index, (x1, y1, x2, y2) in enumerate(boxes):
            if not x1 <= cx <= x2:
                continue
            height = max(1.0, y2 - y1)
            distance = abs(cy - (y1 + y2) / 2) / height
            if distance < best_distance:
                best, best_distance = index, distance
        if best is not None:
            assigned_ids.add(id(word))
    return [word for word in words if id(word) not in assigned_ids]


def missing_lines(indic_words: Sequence[dict], tesseract_words: Sequence[dict],
                  paddle_boxes: Sequence[Sequence[float]], line_height: float) -> list[dict]:
    """Cluster words PP-OCRv5 missed entirely into candidate lines for review.

    Only built from words at least two other engines would have to both miss for
    PP-OCRv5 to be right in dropping them -- concretely, words orphaned from the
    PP-OCRv5 skeleton by *both* IndicPhotoOCR and Tesseract, so a single engine's
    stray detection (noise, a decoration) does not manufacture a phantom line.
    Clustered by vertical position only (within one PP-OCRv5 line height), then
    ordered left to right -- these have no PP-OCRv5 box to anchor column order.
    """
    orphan_indic = {(round(w["bbox"][0]), round(w["bbox"][1])): w for w in orphan_words(indic_words, paddle_boxes)}
    orphan_tess = {(round(w["bbox"][0]), round(w["bbox"][1])): w for w in orphan_words(tesseract_words, paddle_boxes)}

    def close(a: dict, b: dict) -> bool:
        return abs(_center(a["bbox"])[1] - _center(b["bbox"])[1]) < line_height * 0.6

    corroborated = []
    for word in orphan_indic.values():
        if any(close(word, other) for other in orphan_tess.values()):
            corroborated.append(word)

    corroborated.sort(key=lambda w: _center(w["bbox"])[1])
    lines: list[list[dict]] = []
    for word in corroborated:
        if lines and close(word, lines[-1][-1]):
            lines[-1].append(word)
        else:
            lines.append([word])

    results = []
    for group in lines:
        group.sort(key=lambda w: w["bbox"][0])
        xs = [x for w in group for x in (w["bbox"][0], w["bbox"][2])]
        ys = [y for w in group for y in (w["bbox"][1], w["bbox"][3])]
        results.append({
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "text": " ".join(w["text"] for w in group),
            "chosen": "indicphoto+tesseract",
            "reason": "missing_from_paddle",
            "paddle_confidence": 0.0,
            "agreement": None,
            "needs_review": True,
            "candidates": {"indicphoto": " ".join(w["text"] for w in group)},
        })
    return results


def paddle_line(box: dict) -> dict:
    """Convert a PaddleV5Processor box dict into a fusion line."""
    return {
        "bbox": [box["left"], box["top"], box["left"] + box["width"], box["top"] + box["height"]],
        "text": box["text"],
        "confidence": box["confidence"],
    }


def unresolved_lines(paddle_lines: Sequence[dict], tesseract_words: Sequence[dict]) -> list[dict]:
    """PP-OCRv5 lines ``fuse_page`` can't already resolve from PP-OCRv5+Tesseract alone.

    ``fuse_page``'s first rule picks PP-OCRv5 whenever it is confident (>=CONFIDENT)
    and *any* other candidate agrees with it (>=CONFIRMED), regardless of what a
    third candidate says. Found 2026-09-25: on real book pages that rule alone
    already resolves ~84% of lines from PP-OCRv5+Tesseract (see docs/CURRENT_STATE.md,
    "Engine Failure/Strength Tabulation") -- IndicPhotoOCR is run on the whole page
    anyway today, so ~84% of its recognition work is thrown away unread. This lets
    the caller skip IndicPhotoOCR entirely on those lines (pass the result as
    ``paddle_boxes`` to ``IndicPhotoOCRProcessor.extract_words``) before paying for
    detection/identification/recognition there, since the fused output is identical
    either way for a line this function excludes.
    """
    boxes = [line["bbox"] for line in paddle_lines]
    tess_by_line = assign_words(tesseract_words, boxes)
    return [
        line for line, tess_text in zip(paddle_lines, tess_by_line)
        if not (line["confidence"] >= CONFIDENT and tess_text and similarity(line["text"], tess_text) >= CONFIRMED)
    ]


def latin_regions(lines: Sequence[dict], min_letters: int = 2) -> list[list[float]]:
    """Boxes of PP-OCRv5 lines that contain Latin words (hints for IndicPhotoOCR's identifier)."""
    return [line["bbox"] for line in lines
            if len(re.findall(r"[A-Za-z]", line["text"])) >= min_letters]


def fuse_page(paddle_lines: Sequence[dict], indic_words: Sequence[dict],
              tesseract_words: Sequence[dict], include_missing: bool = True) -> list[dict]:
    """Return one fused line per PP-OCRv5 line, with candidates and the decision.

    When ``include_missing`` is set, lines two other engines saw but PP-OCRv5's
    detector missed entirely (see ``missing_lines``) are inserted in y order,
    always flagged for review since nothing here corroborates them against PP-OCRv5.
    """
    fused = []
    boxes = [line["bbox"] for line in paddle_lines]
    indic_by_line = assign_words(indic_words, boxes)
    tess_by_line = assign_words(tesseract_words, boxes)
    for line, indic, tess in zip(paddle_lines, indic_by_line, tess_by_line):
        candidates = {"paddle": line["text"]}
        if indic:
            candidates["indicphoto"] = indic
        if tess:
            candidates["tesseract"] = tess

        names = list(candidates)
        pair = {(a, b): similarity(candidates[a], candidates[b])
                for i, a in enumerate(names) for b in names[i + 1:]}

        def agree(a: str, b: str) -> float:
            return pair.get((a, b), pair.get((b, a), 0.0))

        best_pair = max(pair.values()) if pair else None
        paddle_confirmed = any(agree("paddle", other) >= CONFIRMED for other in names if other != "paddle")

        if len(names) == 1:
            chosen, reason = "paddle", "only_engine"
        elif line["confidence"] >= CONFIDENT and paddle_confirmed:
            chosen, reason = "paddle", "confident_and_confirmed"
        elif len(names) == 3:
            score = {n: sum(agree(n, m) for m in names if m != n) / 2 for n in names}
            top = max(score.values())
            chosen = "paddle" if score["paddle"] >= top - 1e-9 else max(score, key=score.get)
            reason = "medoid"
        else:
            other = next(n for n in names if n != "paddle")
            if line["confidence"] >= CONFIDENT or agree("paddle", other) >= CONFIRMED:
                chosen, reason = "paddle", "two_way_paddle"
            else:
                chosen, reason = other, "two_way_paddle_unconfident"

        text = candidates[chosen]
        if chosen != "paddle":
            tail = _TRAILING_PUNCT.search(line["text"].strip())
            if tail and not _TRAILING_PUNCT.search(text):
                text += tail.group(0)      # word models drop punctuation; PP-OCRv5 keeps it

        fused.append({
            "bbox": line["bbox"],
            "text": text,
            "chosen": chosen,
            "reason": reason,
            "paddle_confidence": round(line["confidence"], 3),
            "agreement": None if best_pair is None else round(best_pair, 3),
            "needs_review": best_pair is not None and best_pair < REVIEW_BELOW,
            "candidates": candidates,
        })

    if include_missing and paddle_lines:
        avg_height = sum(b[3] - b[1] for b in boxes) / len(boxes)
        extra = missing_lines(indic_words, tesseract_words, boxes, avg_height)
        fused.extend(extra)
        fused.sort(key=lambda line: _center(line["bbox"])[1])
    return fused
