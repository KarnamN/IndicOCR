# Decorative Border Detection

## Problem

PDF pages with text inside decorative rectangles/borders were being detected as "complex
images" and captured as full-page images, causing massive file size inflation
(e.g. 3 MB PDF → 500 MB EPUB, a 167x increase).

**Root cause**: the page complexity analyzer detected decorative rectangular borders as
"image regions" and saved them as images, even though they only contained text.

## How it's fixed

Three-level protection against false image detection, implemented in
`src/page_complexity_analyzer.py` and `src/pdf_to_epub_converter_optimized_v2.py`:

1. **Border shape analysis** (`page_complexity_analyzer.py:422-434`) — `fill_ratio` (contour
   area / bounding box area) and `is_perfect_rectangle` distinguish decorative borders from
   real illustrations:
   - `fill_ratio < 0.20` → hollow frame → decorative border.
   - `fill_ratio < 0.30` and a perfect rectangle → also decorative border.
2. **Text-length gating** (`pdf_to_epub_converter_optimized_v2.py:1434, 1443, 1483`):
   - `text_len < 200` and `complexity > 60` → candidate "mostly image" page.
   - `text_len > 500` → safeguard, **never** treated as a pure image page regardless of
     complexity score.
   - `text_len >= 300` → skip saving partial image regions entirely (region is almost
     certainly a decorative border around real text, not an illustration).

## Expected behavior

| Scenario | Text length | Image regions | Result |
|---|---|---|---|
| Text in decorative box | > 300 chars | Detected | Skipped — OCR text used instead |
| Pure illustration | < 200 chars | Large region | Saved as image |
| Mixed content | 200–300 chars | Small regions | Saved as partial images |
| Table page | Any | Table detected | Saved as full page image |

Log line to look for when the fix engages:
```
✓ Skipped N image regions (substantial text detected: XXX chars - likely decorative borders)
```

## Tuning

Thresholds live in the two files above (not in `config.py`/`config_v5.py` — this is
page-analysis logic, not a declarative config value):

```python
# src/page_complexity_analyzer.py
fill_ratio < 0.20   # hollow frame
fill_ratio < 0.30   # + perfect rectangle

# src/pdf_to_epub_converter_optimized_v2.py
text_len < 200   # "mostly image" candidate threshold
text_len > 500   # never-treat-as-image safeguard
text_len >= 300  # skip partial image regions
```

If decorative borders are still being captured as images, lower the `text_len >= 300`
threshold toward 200. If real illustrations mixed with text start getting skipped, raise it.

## Testing

```bash
python tests/test_border_detection.py
```

Expected output for pages with decorative borders: `PASS: Decorative border correctly
filtered out (will use OCR text only)`.
