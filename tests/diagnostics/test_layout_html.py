"""
test_layout_html.py
===================
Demonstrates the full layout-first OCR pipeline on a single image.

OCR Engine:
  - PRIMARY:  PaddleOCR PP-OCRv5 (real production engine)
  - FALLBACK: Tesseract (if PaddleOCR unavailable)

Output: data/layout_test_output.html (standalone HTML with base64 image)
"""
import sys
sys.path.insert(0, '/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/src')
import os, re, base64
from PIL import Image
from io import BytesIO

img_path = '/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/text_w_image.png'
page_image = Image.open(img_path).convert('RGB')
page_w, page_h = page_image.size
print(f"Image size: {page_w}x{page_h}")

# ── Step 1: Layout analysis (detect & crop figures) ──────────────────────────
from layout_analyzer import LayoutAnalyzer
analyzer = LayoutAnalyzer()
figure_crops, figure_coords = analyzer.extract_figures(page_image)
print(f"\n[LAYOUT] Detected {len(figure_crops)} figure(s):")
for i, c in enumerate(figure_coords):
    print(f"  Figure {i+1}: x1={c[0]},y1={c[1]},x2={c[2]},y2={c[3]}  [{c[2]-c[0]}x{c[3]-c[1]}px]")

# ── Step 2: Get text-masked image (figures blanked white) ─────────────────────
masked = analyzer.get_text_mask(page_image, figure_coords)

# ── Step 3: OCR — try PaddleOCR first, fall back to Tesseract ────────────────
ocr_engine_used = None
ocr_text = ''

try:
    from paddle_v5_processor import PaddleV5Processor
    proc = PaddleV5Processor()
    result = proc.extract_with_fallback(masked, page_label="test-page")
    ocr_text       = result['text']
    ocr_engine_used = result['engine']   # 'paddleocr' or 'tesseract'
    print(f"\n[OCR]  Engine used : {ocr_engine_used.upper()}")
    print(f"[OCR]  Confidence  : {result.get('confidence', 'n/a')}")
    print(f"[OCR]  Reason      : {result.get('reason', 'ok')}")
except Exception as e:
    print(f"\n[OCR]  PaddleOCR unavailable ({e}) — falling back to Tesseract")
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        masked.save(tmp.name)
        res = subprocess.run(
            ['tesseract', tmp.name, 'stdout', '-l', 'tel+eng', '--psm', '6'],
            capture_output=True, text=True
        )
        ocr_text = res.stdout
    os.unlink(tmp.name)
    ocr_engine_used = 'tesseract-fallback'

print(f"\n[OCR]  Text ({len(ocr_text)} chars):\n{ocr_text[:500]}")

# ── Step 4: Build content_blocks sorted by Y position ────────────────────────
content_blocks = []

# Figure crops as IMAGE blocks
for (x1, y1, x2, y2), crop in zip(figure_coords, figure_crops):
    content_blocks.append({'type': 'image', 'y': y1, 'image': crop})

# Split OCR text proportionally around figure Y boundaries
text_lines      = [l for l in ocr_text.splitlines() if l.strip()]
figure_y_pcts   = sorted([y1 / max(page_h, 1) for (_, y1, _, _) in figure_coords])

if figure_y_pcts and text_lines:
    splits = [0.0] + figure_y_pcts + [1.0]
    for seg_idx in range(len(splits) - 1):
        seg_start  = splits[seg_idx]
        seg_end    = splits[seg_idx + 1]
        seg_y      = int(seg_start * page_h)
        start_line = int(seg_start * len(text_lines))
        end_line   = int(seg_end   * len(text_lines))
        seg_text   = '\n'.join(text_lines[start_line:end_line]).strip()
        if seg_text:
            content_blocks.append({'type': 'text', 'y': seg_y, 'content': seg_text})
else:
    if ocr_text.strip():
        content_blocks.append({'type': 'text', 'y': 0, 'content': ocr_text})

content_blocks.sort(key=lambda b: b['y'])

print(f"\n[BLOCKS] {len(content_blocks)} content blocks (sorted by Y):")
for b in content_blocks:
    if b['type'] == 'image':
        print(f"  [IMAGE  y={b['y']}]")
    else:
        print(f"  [{b['type'].upper():6} y={b['y']}] {b['content'][:80].replace(chr(10),' ')}...")

# ── Step 5: Generate HTML via EPUBBuilder ─────────────────────────────────────
from epub_builder import EPUBBuilder
builder = EPUBBuilder(title="Test", author="Test")
chapter = builder.create_chapter_from_blocks(title="Page 10", content_blocks=content_blocks)
html = chapter.content

# Embed figure crops as base64 data URIs (self-contained HTML)
for i, crop in enumerate(figure_crops):
    buf = BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    b64      = base64.b64encode(buf.getvalue()).decode()
    img_name = f"img_0_{i}.jpg"
    html = html.replace(f'src="images/{img_name}"',
                        f'src="data:image/jpeg;base64,{b64}"')

# Inject clean CSS + engine badge
engine_badge_color = '#16a34a' if 'paddle' in ocr_engine_used else '#d97706'
engine_label       = f'🏏 PaddleOCR PP-OCRv5' if 'paddle' in ocr_engine_used else f'🔧 Tesseract ({ocr_engine_used})'

styled_html = html.replace(
    '<html><head></head>',
    f'''<html><head><meta charset="utf-8"><style>
body  {{ font-family:"Noto Sans Telugu",sans-serif; max-width:700px; margin:2em auto; line-height:1.9; color:#111; }}
h1   {{ font-size:1.4em; color:#333; border-bottom:2px solid #eee; padding-bottom:0.4em; }}
h2   {{ font-size:1.3em; font-weight:bold; text-align:center; margin:1.2em 0 0.6em; }}
p    {{ margin:0.7em 0; text-indent:1.5em; }}
p:first-of-type {{ text-indent:0; }}
img  {{ max-width:100%; display:block; margin:1.4em auto; border:1px solid #ddd; border-radius:4px; box-shadow:0 2px 8px rgba(0,0,0,.1); }}
.badge {{ display:inline-block; font-size:12px; font-family:monospace;
          background:{engine_badge_color}; color:#fff; padding:3px 10px;
          border-radius:4px; margin-bottom:1em; }}
.info  {{ font-size:12px; color:#888; margin-bottom:1.5em; border:1px dashed #ddd;
          padding:8px 14px; border-radius:6px; }}
</style></head>'''
)

# Insert engine badge just after <body><h1>
styled_html = styled_html.replace(
    '<body><h1>Page 10</h1>',
    f'<body><h1>Page 10</h1>'
    f'<div class="badge">{engine_label}</div>'
    f'<div class="info">'
    f'Layout: PP-DocLayout_plus-L &nbsp;|&nbsp; '
    f'Figures detected: {len(figure_crops)} &nbsp;|&nbsp; '
    f'Content blocks: {len(content_blocks)} &nbsp;|&nbsp; '
    f'Full-page snapshots: 0'
    f'</div>'
)

# ── Step 6: Save ──────────────────────────────────────────────────────────────
out_path = '/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/data/layout_test_output.html'
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(styled_html)

print(f"\n✅ HTML saved → {out_path}")
print(f"   OCR engine : {engine_label}")
print(f"   Blocks     : {len(content_blocks)} ({len(figure_crops)} image, {len(content_blocks)-len(figure_crops)} text)")
print("\n--- RAW HTML (structure, base64 stripped) ---")
clean = re.sub(r'src="data:image[^"]*"', 'src="[BASE64_IMAGE]"', styled_html)
print(clean)
