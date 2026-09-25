"""Adapter for the optional IndicPhotoOCR scene-text pipeline.

Indic books mix the native script with English (explanations, names, terms), so
the adapter runs a bilingual pipeline: detect words, classify each crop with the
3-class ``<language>/english/hindi`` script identifier, then recognise every crop
with the matching model (native PARSeq checkpoint or English PARSeq).

``IndicPhotoOCR.ocr.OCR.ocr`` is not used because it always identifies scripts
with the 12-class ``auto`` model and ignores ``identifier_lang``, which lets
unrelated scripts (Malayalam, Marathi, ...) leak into Telugu pages.

The ViT script identifier is compute-bound (~0.12 s per crop on CPU, ~70% of the
runtime) and OpenVINO does not speed it up, so the useful lever is running it on
fewer crops. ``identifier_mode`` controls that:

``vit``     identify every crop (most accurate, slowest)
``hinted``  identify only crops overlapping ``english_boxes`` (regions where
            another engine, e.g. PP-OCRv5, already saw Latin text); everything
            else is read as the native script
``none``    never identify; everything is read as the native script
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import cv2
from PIL import Image

IDENTIFIER_MODES = ("vit", "hinted", "none")

# Serializes all IndicPhotoOCR model calls (detector, identifier, recogniser) across
# threads, the same way paddle_v5_processor.py's _engine_lock serializes PaddleX.
# Found live 2026-09-22: with FusionOCRProcessor cached as one shared instance and
# the converter's STAGE2_WORKERS letting 2 pages run OCR concurrently, two threads
# calling these Torch models at once each spin up their own OMP/MKL thread pool --
# on a 12-core box that's 2x oversubscription, not 2x throughput. Real production
# pages went from the ~10-20s/page seen in single-process diagnostics to 67-208s.
# Serializing trades "no parallelism from IndicPhotoOCR" for "no CPU thrash" --
# the right trade here since it's already the CPU-bound bottleneck engine, so two
# concurrent passes competing for the same cores couldn't have gone faster anyway.
_INDIC_LOCK = threading.Lock()


class IndicPhotoOCRProcessor:
    """Expose IndicPhotoOCR through IndicOCR's ``extract_text`` interface."""

    def __init__(
        self,
        device: str = "cpu",
        identifier_lang: str = "telugu",
        batch_size: int = 16,
        min_confidence: float = 0.0,
        identifier_mode: str = "vit",
        quantize_identifier: bool = False,
    ):
        if identifier_mode not in IDENTIFIER_MODES:
            raise ValueError(f"identifier_mode must be one of {IDENTIFIER_MODES}")
        try:
            from IndicPhotoOCR.ocr import OCR
            from IndicPhotoOCR.utils.helper import detect_para
        except ImportError as exc:
            raise ImportError(
                "IndicPhotoOCR is not installed. Clone "
                "https://github.com/Bhashini-IITJ/IndicPhotoOCR and run "
                "pip install -e . in its Python environment."
            ) from exc

        self.native_lang = identifier_lang
        self.batch_size = batch_size
        self.min_confidence = min_confidence
        self.identifier_mode = identifier_mode
        self.quantize_identifier = quantize_identifier
        self._quantized = False
        self._detect_para = detect_para
        self.engine = OCR(device=device, identifier_lang=identifier_lang, verbose=False)
        self.last_script_counts: dict[str, int] = {}

    def _route(self, label: str) -> str:
        """Map an identifier label to a recogniser.

        The 3-class model also has a ``hindi`` class; in a book that is declared
        as ``native_lang`` it is almost always the native script, so route it there.
        """
        if self.native_lang == "auto":
            return label
        return "english" if label == "english" else self.native_lang

    def _maybe_quantize_identifier(self) -> None:
        """Dynamic int8 quantisation of the ViT's Linear layers (~30% faster)."""
        if not self.quantize_identifier or self._quantized:
            return
        import torch

        identifier = self.engine.identifier
        identifier.identify_batch([], self.native_lang, self.engine._pipeline_device)  # force load
        pipe = identifier._model_cache[self.native_lang]
        pipe.model = torch.ao.quantization.quantize_dynamic(
            pipe.model, {torch.nn.Linear}, dtype=torch.qint8
        )
        self._quantized = True

    def _identify(self, crop_paths: list[str], detections: list, valid: list[int],
                  english_boxes: Sequence[Sequence[float]] | None) -> list[str]:
        """Return a script label per valid crop, following ``identifier_mode``."""
        native = "native"
        if self.identifier_mode == "none":
            return [native] * len(valid)

        if self.identifier_mode == "hinted":
            hints = english_boxes or []
            need = [pos for pos, i in enumerate(valid)
                    if _center_in_any(detections[i], hints)]
        else:
            need = list(range(len(valid)))

        labels = [native] * len(valid)
        if need:
            self._maybe_quantize_identifier()
            predicted = self.engine.identifier.identify_batch(
                [crop_paths[valid[pos]] for pos in need],
                self.native_lang,
                self.engine._pipeline_device,
                batch_size=self.batch_size,
            )
            for pos, label in zip(need, predicted):
                labels[pos] = label
        return labels

    def extract_words(self, image: Image.Image,
                      english_boxes: Sequence[Sequence[float]] | None = None,
                      paddle_boxes: Sequence[Sequence[float]] | None = None) -> list[dict]:
        """Detect and read words; each is ``{text, bbox=[x1,y1,x2,y2], confidence, script}``.

        ``paddle_boxes``, when given, drops crops whose centre falls outside every
        PP-OCRv5 line box *before* identification/recognition -- the two model
        passes, not detection itself (IndicPhotoOCR's own detector already ran).
        On real book pages the detector finds far more crops (~500) than PP-OCRv5
        has lines for (~30) -- punctuation fragments, broken characters, decorative
        marks -- and recognise_batch's cost scales with crop count (~65ms/crop on
        CPU), so this is the single biggest lever on IndicPhotoOCR's per-page time.
        Trade-off: this also discards any crop from a line PP-OCRv5's detector
        missed entirely, which is the raw material ocr_fusion.missing_lines needs.
        That feature has not fired on any of the ~18 pages tested to date, so the
        trade favours speed; pass paddle_boxes=None to keep missing-line detection.
        """
        engine = self.engine
        image_path = None
        crop_paths: list[str | None] = []
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
                image_path = Path(temp.name)
            image.save(image_path, format="PNG")

            bgr = cv2.imread(str(image_path))
            with _INDIC_LOCK:
                detections = engine.detect(str(image_path))
                crop_paths = [engine.crop_bbox(bgr, bbox) for bbox in detections]
                valid = [i for i, path in enumerate(crop_paths) if path]
                if paddle_boxes:
                    valid = [i for i in valid if _center_in_any(detections[i], paddle_boxes)]
                if not valid:
                    self.last_script_counts = {}
                    return []

                labels = self._identify(crop_paths, detections, valid, english_boxes)
                routed = [self._route(label) if label != "native" else self.native_lang
                          for label in labels]
                self.last_script_counts = dict(Counter(routed))

                by_script: dict[str, list[int]] = {}
                for index, script in zip(valid, routed):
                    by_script.setdefault(script, []).append(index)

                words: list[dict] = []
                for script, indexes in by_script.items():
                    results = engine.recogniser.recognise_batch(
                        script,
                        [crop_paths[i] for i in indexes],
                        script,
                        False,
                        engine._torch_device,
                        return_confidence=True,
                        batch_size=self.batch_size,
                    )
                    for index, (text, confidence) in zip(indexes, results):
                        if not text.strip() or confidence < self.min_confidence:
                            continue
                        xs = [point[0] for point in detections[index]]
                        ys = [point[1] for point in detections[index]]
                        words.append({
                            "text": fix_telugu_anusvara(text) if self.native_lang == "telugu" else text,
                            "bbox": [min(xs), min(ys), max(xs), max(ys)],
                            "confidence": confidence,
                            "script": script,
                            "index": index,
                        })
            words.sort(key=lambda word: word["index"])
            return words
        finally:
            for path in crop_paths:
                if path and os.path.exists(path):
                    os.remove(path)
            if image_path:
                image_path.unlink(missing_ok=True)

    def extract_text(self, image: Image.Image,
                     english_boxes: Sequence[Sequence[float]] | None = None,
                     paddle_boxes: Sequence[Sequence[float]] | None = None, **_: Any) -> str:
        """Run detection, per-crop script identification, and recognition."""
        words = self.extract_words(image, english_boxes=english_boxes, paddle_boxes=paddle_boxes)
        recognized = {
            f"img_{word['index']}": {"txt": word["text"], "bbox": word["bbox"],
                                     "confidence": word["confidence"]}
            for word in words
        }
        return _flatten_result(self._detect_para(recognized)).strip()


def _center_in_any(polygon: Sequence[Sequence[float]], boxes: Sequence[Sequence[float]]) -> bool:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return any(x1 <= cx <= x2 and y1 <= cy <= y2 for x1, y1, x2, y2 in boxes)


# The Telugu PARSeq checkpoint emits the digit zero (U+0C66) for the anusvara
# (U+0C02). A zero that follows a Telugu letter or vowel sign, rather than
# another digit, is the anusvara.
_ZERO_AFTER_LETTER = re.compile("(?<=[అ-హా-ౖ])౦")


def fix_telugu_anusvara(text: str) -> str:
    """Replace the Telugu digit zero misread for anusvara inside words."""
    return _ZERO_AFTER_LETTER.sub("ం", text)


def _flatten_result(value: Any) -> str:
    """Flatten IndicPhotoOCR's nested paragraph/word output into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("txt", "text"):
            if key in value:
                return _flatten_result(value[key])
        return "\n".join(_flatten_result(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        separator = "\n" if value and all(isinstance(item, (list, tuple)) for item in value) else " "
        return separator.join(_flatten_result(item) for item in value)
    return str(value)
