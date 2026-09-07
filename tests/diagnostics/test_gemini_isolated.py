"""
Isolated test for all recent Gemini OCR changes:
  1. Image dominance ratio (image_22.png should be detected as graphic page → skip OCR)
  2. Gemini image sizing (verify payload KB and pixel count)
  3. Live Gemini API call with gemini-1.5-flash on a TEXT page (page19.png)
  4. Error handler: 404 fast-fail (no retries)

Run from repo root:
    python3 test_gemini_isolated.py
"""

import sys, os, io, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# ── silence config stdout ────────────────────────────────────────────────────
import contextlib, io as _io
with contextlib.redirect_stdout(_io.StringIO()):
    import config

from PIL import Image
import numpy as np

SEP  = "=" * 65
SEP2 = "-" * 65

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Image dominance ratio detection
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 1 — Graphic-page detection (image_22.png)")
print(SEP)

from page_complexity_analyzer import PageComplexityAnalyzer

for fname, expect_graphic in [("image_22.png", True), ("page19.png", False)]:
    path = os.path.join(os.path.dirname(__file__), fname)
    if not os.path.exists(path):
        print(f"  ⚠  {fname} not found — skipping")
        continue

    img = Image.open(path)
    print(f"\n  📄 {fname}  ({img.size[0]}×{img.size[1]}px)")

    ana  = PageComplexityAnalyzer()
    result = ana.analyze(img)

    ratio      = result.get('image_dominant_ratio', 0.0)
    lines      = result.get('estimated_lines', 0)
    regions    = result.get('image_regions', [])
    complexity = result.get('complexity_score', 0)
    engine     = result.get('recommended_engine', '?')

    print(f"  has_illustrations    : {result.get('has_illustrations', False)}")
    print(f"  image_regions count  : {len(regions)}")
    print(f"  image_dominant_ratio : {ratio:.3f}  ({ratio*100:.1f}%)")
    print(f"  estimated_lines      : {lines}")
    print(f"  complexity_score     : {complexity:.1f}")
    print(f"  recommended_engine   : {engine}")

    thresh = getattr(config, 'IMAGE_PAGE_DOMINANT_RATIO', 0.55)
    would_skip = (
        ratio >= thresh
        or (ratio >= 0.70 and lines <= 15)
        or any((rw*rh) > (img.width*img.height*0.60) for (_,_,rw,rh) in regions)
        or (result.get('has_illustrations') and lines < 8)
    )

    status = "✅ PASS" if (would_skip == expect_graphic) else "❌ FAIL"
    print(f"\n  Expected skip_ocr={expect_graphic}  |  Got skip_ocr={would_skip}  →  {status}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Image payload size
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("TEST 2 — Gemini payload size (image_22.png)")
print(SEP)

from gemini_ocr_processor import GeminiOCRProcessor

path = os.path.join(os.path.dirname(__file__), "image_22.png")
if os.path.exists(path):
    img = Image.open(path)
    print(f"\n  Original size   : {img.size[0]}×{img.size[1]} px")

    proc = GeminiOCRProcessor.__new__(GeminiOCRProcessor)   # skip __init__ (no API key needed)
    proc.model_name = config.GEMINI_MODEL

    payload = proc._image_to_bytes(img)
    max_dim = getattr(config, 'GEMINI_MAX_IMAGE_PIXELS', 1536)
    quality = getattr(config, 'GEMINI_JPEG_QUALITY', 72)
    resized = Image.open(io.BytesIO(payload))

    # Tile calculation (Gemini Vision: 768×768 tiles)
    tw = int(np.ceil(resized.size[0] / 768))
    th = int(np.ceil(resized.size[1] / 768))
    tokens = 258 + tw * th * 258

    print(f"  Resized to      : {resized.size[0]}×{resized.size[1]} px  (max_dim={max_dim})")
    print(f"  JPEG quality    : {quality}")
    print(f"  Payload size    : {len(payload)/1024:.1f} KB  (was ~4,500 KB at 400 DPI)")
    print(f"  Tiles           : {tw}×{th} = {tw*th}  →  ~{tokens} tokens")
    print(f"  Old token cost  : ~9,288 tokens  (3307×4677 @ q=85)")
    print(f"  Savings         : ~{9288/tokens:.1f}× fewer tokens  ✅")
else:
    print("  ⚠  image_22.png not found")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Live Gemini API call
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("TEST 3 — Live Gemini API call with gemini-1.5-flash")
print(SEP)

api_key = getattr(config, 'GEMINI_API_KEY', '')
if not api_key or api_key == 'your-api-key-here':
    print("\n  ⚠  GEMINI_API_KEY not set — skipping live API test")
else:
    # Use page19.png (text page) so we get real OCR output
    test_img_path = os.path.join(os.path.dirname(__file__), "page19.png")
    fallback_path = os.path.join(os.path.dirname(__file__), "image_22.png")
    img_path = test_img_path if os.path.exists(test_img_path) else fallback_path

    img = Image.open(img_path)
    print(f"\n  Using image     : {os.path.basename(img_path)}")
    print(f"  Model           : {config.GEMINI_MODEL}")

    processor = GeminiOCRProcessor()

    if not processor.is_available:
        print("  ❌ Gemini processor not available — check API key")
    else:
        print("  🚀 Sending request...")
        t0 = time.time()
        text = processor.extract_text(img, page_label="[TEST]")
        elapsed = time.time() - t0

        if text:
            lines = [l for l in text.split('\n') if l.strip()]
            print(f"  ✅ Success in {elapsed:.1f}s")
            print(f"  Chars returned  : {len(text)}")
            print(f"  Lines returned  : {len(lines)}")
            print(f"\n  --- First 300 chars of output ---")
            print(f"  {text[:300].replace(chr(10), chr(10)+'  ')}")
            print(f"  ---")
        else:
            print(f"  ❌ Empty response after {elapsed:.1f}s — check logs above")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Error handler: 404 fast-fail (model spoofed to bad name)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("TEST 4 — Error handler: 404 must fail fast (no retries)")
print(SEP)

if not api_key or api_key == 'your-api-key-here':
    print("\n  ⚠  GEMINI_API_KEY not set — skipping error handler test")
else:
    bad_proc = GeminiOCRProcessor()
    bad_proc.model_name = "gemini-nonexistent-model-xyz"  # guaranteed 404

    img = Image.open(os.path.join(os.path.dirname(__file__), "image_22.png"))
    print(f"\n  Model set to    : {bad_proc.model_name}  (should 404 instantly)")

    t0 = time.time()
    result = bad_proc.extract_text(img, page_label="[404-TEST]")
    elapsed = time.time() - t0

    # Should return empty string in < 3s (no retries)
    if elapsed < 3.0 and result == "":
        print(f"  ✅ 404 fast-fail in {elapsed:.1f}s — no retries wasted")
    elif elapsed >= 3.0:
        print(f"  ❌ Took {elapsed:.1f}s — still retrying on 404 (fix not working)")
    else:
        print(f"  ⚠  Returned in {elapsed:.1f}s but got text: '{result[:50]}'")

print(f"\n{SEP}")
print("All tests complete.")
print(SEP)
