"""One-off diagnostic: where does IndicPhotoOCR's time go, with vs without the
preprocess=True boost the real production call site applies (fusion_ocr_processor.py
always passes preprocess=True; every prior diagnostic used preprocess=False).

Instruments detect / crop / identify / recognize separately, and counts raw
detections vs. crops actually sent to the ViT identifier vs. crops recognized,
so a timing gap can be attributed to "more crops" vs "something else slower".

Run inside WSL shared env from repo root:
    python tests/diagnostics/profile_indicphoto.py --only page_130.png page_210.png
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2] if "diagnostics" in str(Path(__file__)) else Path(
    r"/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/IndicOCR_21-09-2026"
)
sys.path.insert(0, str(ROOT / "src"))


def profile_one(paddle, indic, image: Image.Image, label: str, preprocess: bool,
                filter_by_paddle: bool = False) -> dict:
    import cv2
    import numpy as np

    from ocr_fusion import latin_regions, paddle_line

    img = paddle._preprocess(image, page_label=label) if preprocess else paddle._ensure_rgb(image)
    img = paddle._resize_if_needed(img)

    t0 = time.perf_counter()
    _, boxes = paddle._paddle_extract(img)
    t_paddle = time.perf_counter() - t0
    lines = [paddle_line(b) for b in boxes]
    english_boxes = latin_regions(lines)
    paddle_boxes = [l["bbox"] for l in lines] if filter_by_paddle else None

    # ---- replicate IndicPhotoOCRProcessor.extract_words with sub-timings ----
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image_path = Path(tmp.name)
    img.save(image_path, format="PNG")
    bgr = cv2.imread(str(image_path))

    engine = indic.engine
    t0 = time.perf_counter()
    detections = engine.detect(str(image_path))
    t_detect = time.perf_counter() - t0

    t0 = time.perf_counter()
    crop_paths = [engine.crop_bbox(bgr, bbox) for bbox in detections]
    valid = [i for i, p in enumerate(crop_paths) if p]
    t_crop = time.perf_counter() - t0

    if paddle_boxes:
        from indicphoto_ocr_processor import _center_in_any
        valid = [i for i in valid if _center_in_any(detections[i], paddle_boxes)]

    t0 = time.perf_counter()
    labels = indic._identify(crop_paths, detections, valid, english_boxes)
    t_identify = time.perf_counter() - t0
    need = sum(1 for pos, i in enumerate(valid) if labels[pos] != "native") if labels else 0

    routed = [indic._route(l) if l != "native" else indic.native_lang for l in labels]
    by_script: dict[str, list[int]] = {}
    for index, script in zip(valid, routed):
        by_script.setdefault(script, []).append(index)

    t0 = time.perf_counter()
    total_recognized = 0
    for script, indexes in by_script.items():
        results = engine.recogniser.recognise_batch(
            script, [crop_paths[i] for i in indexes], script, False,
            engine._torch_device, return_confidence=True, batch_size=indic.batch_size,
        )
        total_recognized += len(results)
    t_recognize = time.perf_counter() - t0

    for p in crop_paths:
        if p:
            import os
            os.remove(p)
    image_path.unlink(missing_ok=True)

    return {
        "label": label, "preprocess": preprocess, "filter_by_paddle": filter_by_paddle, "size": img.size,
        "detections": len(detections), "valid_crops": len(valid),
        "identified_by_vit": need, "by_script_counts": {k: len(v) for k, v in by_script.items()},
        "recognized": total_recognized,
        "t_paddle": round(t_paddle, 2), "t_detect": round(t_detect, 2), "t_crop": round(t_crop, 2),
        "t_identify": round(t_identify, 2), "t_recognize": round(t_recognize, 2),
        "t_indic_total": round(t_detect + t_crop + t_identify + t_recognize, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-dir", type=Path, default=ROOT / "ocr_comparison" / "book_sample")
    ap.add_argument("--only", nargs="+", required=True)
    args = ap.parse_args()

    import config_v5 as active_config
    sys.modules["config"] = active_config
    from indicphoto_ocr_processor import IndicPhotoOCRProcessor
    from paddle_v5_processor import PaddleV5Processor

    paddle = PaddleV5Processor(language="tel+eng", config=active_config)
    indic = IndicPhotoOCRProcessor(device="cpu", identifier_lang="telugu", identifier_mode="hinted")

    for name in args.only:
        image = Image.open(args.image_dir / name).convert("RGB")
        for filter_by_paddle in (False, True):
            r = profile_one(paddle, indic, image, name, preprocess=False, filter_by_paddle=filter_by_paddle)
            print(r)


if __name__ == "__main__":
    raise SystemExit(main())
