"""One-off: test Surya's block-mode OCR (crop-and-recognize per region) against
full-page mode, using known text-block boxes from an earlier full-page run.

Usage: python3 test_surya_blockmode.py <image_path> <output_txt_path>
"""
import sys
import time

from PIL import Image

from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor
from surya.layout.schema import LayoutBox, LayoutResult

image_path, out_path = sys.argv[1], sys.argv[2]

# Known text blocks for page 30 (from the earlier full-page OCR run), reused
# here as the "layout" so block mode doesn't need its own layout detector pass.
BOXES = [
    (191.25, 427.0, 395.25, 574.0),
    (2528.75, 273.0, 3825.0, 496.99999999999994),
    (208.25, 574.0, 3825.0, 1365.0),
    (412.25, 1351.0, 1037.0, 1533.0),
    (412.25, 1484.0, 2953.75, 1771.0),
    (412.25, 1764.0, 1321.75, 1960.0000000000002),
    (242.25, 1890.0000000000002, 3867.5, 2786.0),
    (263.5, 2744.0, 3867.5, 3598.0),
    (263.5, 3563.0, 3867.5, 4417.0),
    (459.0, 4396.0, 3859.0, 4627.0),
    (263.5, 4613.0, 3897.25, 5047.0),
    (459.0, 5047.0, 3234.25, 5257.0),
    (148.75, 5257.0, 3893.0, 6468.0),
]

print(f"Loading image: {image_path}", flush=True)
image = Image.open(image_path).convert("RGB")

layout_boxes = [
    LayoutBox(polygon=list(b), label="Text", raw_label="Text", position=i, count=300)
    for i, b in enumerate(BOXES)
]
layout = LayoutResult(bboxes=layout_boxes, image_bbox=[0.0, 0.0, float(image.size[0]), float(image.size[1])])

print("Loading Surya model...", flush=True)
t0 = time.time()
manager = SuryaInferenceManager()
rec_predictor = RecognitionPredictor(manager)
print(f"Model loaded in {time.time() - t0:.1f}s", flush=True)

print(f"Running block-mode OCR on {len(BOXES)} blocks...", flush=True)
t0 = time.time()
results = rec_predictor([image], layout_results=[layout], full_page=False)
elapsed = time.time() - t0
print(f"Block-mode OCR done in {elapsed:.1f}s", flush=True)

page = results[0]
with open(out_path, "w", encoding="utf-8") as f:
    f.write(str(page.model_dump()))

print(f"Wrote output to {out_path}", flush=True)
print(f"TIMING: {elapsed:.1f}s for this page (block mode, {len(BOXES)} blocks)", flush=True)
