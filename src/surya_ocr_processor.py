"""Adapter for Surya OCR (surya-ocr 0.22.1+) as a manual rescue engine.

Surya's current release is a full-page vision-language model (Qwen3.5 backbone,
served via a spawned `llama-server` process), not the older CNN detector+
recognizer architecture the project name used to imply. On this project's
CPU-only WSL box it measured ~180-215s/page (see docs/CURRENT_STATE.md or the
2026-09-26 investigation notes) — far too slow to run automatically on every
page, but genuinely more accurate than PaddleOCR/IndicPhotoOCR on catastrophically
degraded pages (verified word-for-word against source scans on two of the
worst pages in a real book). Wired in here as a manual REWORK-button engine
only (like 'gemini'/'google_vision'), not part of the automatic escalation
ladder — none of the pipeline's existing "needs review" signals are selective
enough to safely automate this without effectively running it on the whole
book (measured: 117/121 pages flagged `needs_manual_review` on one real book).

Config (fa+q8) matches the fastest configuration found that did not change
output text versus the untuned default — see the flash-attn/q8_0 KV-cache
comparison in that investigation. Do not add `--threads N` or raise
`--ubatch-size` here: both were tested and made this specific box significantly
slower (contention in the WSL VM), not faster.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Optional

from PIL import Image

import config
from logging_config import get_logger

logger = get_logger(__name__)

# The llama.cpp release this project's install script (scripts/install_surya.bat)
# downloads to. Overridable via SURYA_LLAMA_CPP_BINARY in .env for a different path.
_DEFAULT_LLAMA_SERVER = os.path.expanduser("~/tools/llama-cpp/llama-b11200/llama-server")

_TAG_RE = re.compile(r"</?(p|h1|h2|h3|h4|h5|h6|li|ul|ol|table|tr|td|th|br)[^>]*>", re.IGNORECASE)


def _html_to_text(html: str) -> str:
    """Strip Surya's per-block HTML markup down to plain text."""
    text = _TAG_RE.sub("", html or "")
    return text.strip()


class SuryaOCRProcessor:
    """Runs Surya's full-page OCR through a locally spawned llama-server."""

    def __init__(self):
        self.binary_path = getattr(config, "SURYA_LLAMA_CPP_BINARY", "") or _DEFAULT_LLAMA_SERVER
        self._rec_predictor = None

    @property
    def is_available(self) -> bool:
        if not os.path.isfile(self.binary_path):
            return False
        try:
            import surya  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_predictor(self):
        if self._rec_predictor is None:
            os.environ.setdefault("LLAMA_CPP_BINARY", self.binary_path)
            # Verified fastest-without-quality-loss config for this project's CPU-only
            # environment — see module docstring. Do not add --threads/--ubatch-size.
            os.environ.setdefault("LLAMA_CPP_EXTRA_ARGS", "-fa on -ctk q8_0 -ctv q8_0")
            from surya.inference import SuryaInferenceManager
            from surya.recognition import RecognitionPredictor
            manager = SuryaInferenceManager()
            self._rec_predictor = RecognitionPredictor(manager)
        return self._rec_predictor

    def extract_text(self, image: Image.Image) -> str:
        """Run full-page OCR. Slow (~3 minutes/page on CPU) — intended for
        one-off manual rescue via the correction dashboard, not batch use."""
        if not self.is_available:
            logger.warning("Surya OCR not available (binary or package missing) — returning empty text")
            return ""

        if image.mode != "RGB":
            image = image.convert("RGB")

        try:
            predictor = self._get_predictor()
            t0 = time.time()
            results = predictor([image], full_page=True)
            elapsed = time.time() - t0

            page = results[0]
            dump = page.model_dump() if hasattr(page, "model_dump") else {}
            blocks = sorted(dump.get("blocks", []), key=lambda b: b.get("reading_order", 0))
            lines = [_html_to_text(b.get("html", "")) for b in blocks if not b.get("skipped") and not b.get("error")]
            text = "\n".join(line for line in lines if line)

            logger.info(f"  🐢 Surya OCR extracted {len(text)} chars in {elapsed:.1f}s")
            return text.strip()
        except Exception as e:
            logger.error(f"  🐢 Surya OCR failed: {e}")
            return ""
