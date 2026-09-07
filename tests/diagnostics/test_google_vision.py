"""
Google Cloud Vision OCR — Availability & Live API Test
Tests:
  1. Package import
  2. Service Account JSON exists and is valid
  3. Client initialization with credentials
  4. Live API call with a synthetic test image (white background + black text)
"""

import sys
import os
import json
from pathlib import Path

# ── Resolve project root so we can load .env ──────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


# ── TEST 1: Package import ─────────────────────────────────────────────────────
banner("TEST 1: Package Import")
try:
    from google.cloud import vision
    print(f"  ✅ google-cloud-vision imported (version available via grpc)")
except ImportError as e:
    print(f"  ❌ Import FAILED: {e}")
    sys.exit(1)


# ── TEST 2: Service Account JSON ───────────────────────────────────────────────
banner("TEST 2: Service Account JSON")
sa_path_raw = os.environ.get("GOOGLE_VISION_SERVICE_ACCOUNT", "")
# Resolve relative paths from the project root
if sa_path_raw.startswith("./"):
    sa_path = PROJECT_ROOT / sa_path_raw[2:]
else:
    sa_path = Path(sa_path_raw)

print(f"  Configured path : {sa_path_raw}")
print(f"  Resolved path   : {sa_path}")

if not sa_path.exists():
    print(f"  ❌ File NOT found!")
    sys.exit(1)

try:
    with open(sa_path) as f:
        sa_data = json.load(f)
    required_fields = ["type", "project_id", "client_email", "private_key"]
    missing = [k for k in required_fields if k not in sa_data]
    if missing:
        print(f"  ❌ JSON missing fields: {missing}")
        sys.exit(1)
    print(f"  ✅ JSON valid")
    print(f"     type         : {sa_data.get('type')}")
    print(f"     project_id   : {sa_data.get('project_id')}")
    print(f"     client_email : {sa_data.get('client_email')}")
except Exception as e:
    print(f"  ❌ JSON parse error: {e}")
    sys.exit(1)


# ── TEST 3: Client initialization ─────────────────────────────────────────────
banner("TEST 3: Client Initialization")
try:
    client = vision.ImageAnnotatorClient.from_service_account_json(str(sa_path))
    print(f"  ✅ ImageAnnotatorClient created from Service Account JSON")
except Exception as e:
    print(f"  ❌ Client init FAILED: {e}")
    sys.exit(1)


# ── TEST 4: Live API call with a synthetic test image ─────────────────────────
banner("TEST 4: Live API Call (Synthetic Image)")
try:
    from PIL import Image, ImageDraw, ImageFont
    import io

    # Create a simple white image with black Telugu+English text
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40),  "Hello World — Test Image", fill=(0, 0, 0))
    draw.text((20, 100), "Telugu: నమస్కారం", fill=(0, 0, 0))

    # Convert to JPEG bytes
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    image_bytes = buf.getvalue()

    print(f"  Test image size : {img.size}, bytes: {len(image_bytes)}")

    # Call Vision API
    vision_image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=vision_image)

    if response.error.message:
        print(f"  ❌ API Error: {response.error.message}")
        sys.exit(1)

    extracted = response.full_text_annotation.text if response.full_text_annotation else ""
    print(f"  ✅ API call SUCCESS!")
    print(f"     Extracted text ({len(extracted)} chars):")
    for line in extracted.strip().split("\n"):
        print(f"       | {line}")

except Exception as e:
    print(f"  ❌ Live API call FAILED: {e}")
    sys.exit(1)


# ── SUMMARY ───────────────────────────────────────────────────────────────────
banner("SUMMARY")
print("  ✅ TEST 1 PASSED — Package import OK")
print("  ✅ TEST 2 PASSED — Service Account JSON valid")
print("  ✅ TEST 3 PASSED — Client initialized successfully")
print("  ✅ TEST 4 PASSED — Live API call returned text")
print("\n  🎉 Google Cloud Vision is FULLY OPERATIONAL and ready to use!")
print(f"     Project: {sa_data.get('project_id')}")
print(f"     Account: {sa_data.get('client_email')}")
