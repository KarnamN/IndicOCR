"""Run PaddleX ONNX models on OpenVINO, bypassing PaddleX's HPI (ultra-infer).

PaddleX predictors call ``self.runner(x)`` between their own pre- and
post-processing, so swapping the runner speeds inference up without changing
preprocessing, DB post-processing, or the model weights.

On the 12-thread dev CPU the PP-OCRv5 server detector takes ~10 s per page on
Paddle's CPU runner and ~1.4 s on OpenVINO.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence

import numpy as np

logger = logging.getLogger(__name__)

PADDLEX_MODEL_DIR = Path.home() / ".paddlex" / "official_models"


class OpenVINORunner:
    """Callable with the same contract as PaddleX's InferenceRunner."""

    def __init__(self, onnx_path: Path, performance_hint: str = "LATENCY"):
        import openvino as ov

        core = ov.Core()
        model = core.read_model(str(onnx_path))
        self._compiled = core.compile_model(model, "CPU", {"PERFORMANCE_HINT": performance_hint})
        self._outputs = list(self._compiled.outputs)

    def __call__(self, x: Sequence[np.ndarray]) -> List[np.ndarray]:
        feed = {index: np.ascontiguousarray(array) for index, array in enumerate(x)}
        results = self._compiled(feed)
        return [results[output] for output in self._outputs]

    def close(self) -> None:
        self._compiled = None


def accelerate_with_openvino(engine, model_name: str) -> bool:
    """Swap a PaddleOCR TextDetection/TextRecognition engine's runner for OpenVINO.

    Returns True on success. On any problem (no ONNX export, OpenVINO missing) the
    engine is left untouched and keeps running on Paddle.
    """
    onnx_path = PADDLEX_MODEL_DIR / model_name / "inference.onnx"
    if not onnx_path.exists():
        logger.warning("OpenVINO runner skipped for %s: %s not found "
                       "(export it with paddle2onnx)", model_name, onnx_path)
        return False
    try:
        predictor = engine.paddlex_predictor
        predictor.runner = OpenVINORunner(onnx_path)
        logger.info("OpenVINO runner active for %s", model_name)
        return True
    except Exception as exc:
        logger.warning("OpenVINO runner unavailable for %s: %s", model_name, exc)
        return False
