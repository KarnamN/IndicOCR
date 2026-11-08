"""One-off: run Surya full-page OCR on a single image and print timing + text.

Usage: python3 test_surya_page.py <image_path> <output_txt_path>
"""
import sys
import time

from PIL import Image

from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor

image_path, out_path = sys.argv[1], sys.argv[2]

print(f"Loading image: {image_path}", flush=True)
image = Image.open(image_path).convert("RGB")

print("Loading Surya model (first run downloads checkpoint, can take a while)...", flush=True)
t0 = time.time()
manager = SuryaInferenceManager()
rec_predictor = RecognitionPredictor(manager)
print(f"Model loaded in {time.time() - t0:.1f}s", flush=True)

print("Running OCR...", flush=True)
t0 = time.time()
results = rec_predictor([image], full_page=True)
elapsed = time.time() - t0
print(f"OCR done in {elapsed:.1f}s", flush=True)

page = results[0]
text = getattr(page, "text", None) or getattr(page, "markdown", None) or str(page)
if hasattr(page, "model_dump"):
    dump = page.model_dump()
    text = dump.get("text") or dump.get("markdown") or str(dump)

with open(out_path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"Wrote output to {out_path}", flush=True)
print(f"TIMING: {elapsed:.1f}s for this page", flush=True)
