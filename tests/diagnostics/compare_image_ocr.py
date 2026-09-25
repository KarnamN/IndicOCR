"""Compare Tesseract, PP-OCRv5, and optional IndicPhotoOCR on images.

Run from the repository root with the WSL project environment:
    python tests/diagnostics/compare_image_ocr.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def _load_engines(device: str, indicphoto_language: str):
    import config_v5 as active_config

    sys.modules["config"] = active_config
    from ocr_processor import OCRProcessor
    from paddle_v5_processor import PaddleV5Processor

    engines = {
        "tesseract": OCRProcessor(language="tel+eng"),
        "paddle": PaddleV5Processor(language="tel+eng", config=active_config),
    }
    try:
        from indicphoto_ocr_processor import IndicPhotoOCRProcessor

        engines["indicphoto"] = IndicPhotoOCRProcessor(
            device=device,
            identifier_lang=indicphoto_language,
        )
    except ImportError as exc:
        print(f"[skip] indicphoto: {exc}")
    return engines


def _run(engine, image: Image.Image) -> dict:
    started = time.perf_counter()
    try:
        text = engine.extract_text(image, preprocess=False)
        error = None
    except Exception as exc:
        text = ""
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    return {
        "seconds": round(elapsed, 3),
        "characters": len(text),
        "lines": len([line for line in text.splitlines() if line.strip()]),
        "telugu_characters": sum("\u0c00" <= char <= "\u0c7f" for char in text),
        "latin_characters": sum(char.isascii() and char.isalpha() for char in text),
        "other_script_characters": sum(
            ord(char) > 0x7F and not "\u0c00" <= char <= "\u0c7f" and char.isalpha()
            for char in text
        ),
        "script_counts": getattr(engine, "last_script_counts", None),
        "text": text,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", type=Path, default=ROOT / "images")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--only", nargs="+", help="Image file names to run instead of the first --limit images.")
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--indicphoto-language",
        default="telugu",
        choices=["auto", "telugu", "kannada", "tamil", "malayalam", "marathi", "hindi", "bengali", "gujarati", "odia", "punjabi", "assamese"],
        help="Native script paired with English by IndicPhotoOCR (native+English identifier).",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "ocr_comparison" / "image_engine_comparison.json")
    args = parser.parse_args()

    image_paths = sorted(
        path for path in args.image_dir.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if args.only:
        image_paths = [path for path in image_paths if path.name in set(args.only)]
    else:
        image_paths = image_paths[:args.limit]
    if not image_paths:
        print(f"No images found in {args.image_dir}")
        return 1

    engines = _load_engines(args.device, args.indicphoto_language)
    report = {
        "image_dir": str(args.image_dir),
        "engines": list(engines),
        "indicphoto_language": args.indicphoto_language,
        "images": {},
    }
    for image_path in image_paths:
        print(f"\n{image_path.name}")
        image = Image.open(image_path).convert("RGB")
        report["images"][image_path.name] = {}
        for name, engine in engines.items():
            result = _run(engine, image)
            report["images"][image_path.name][name] = result
            status = result["error"] or f"{result['characters']} chars in {result['seconds']}s"
            print(f"  {name:10} {status}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())