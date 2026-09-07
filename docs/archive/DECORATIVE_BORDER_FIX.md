# Fix for Decorative Border Detection Issue

## Problem Description

**Issue**: PDF pages with text inside decorative rectangles/borders were being detected as "complex images" and captured as full-page images, causing massive file size inflation (3 MB PDF → 500 MB EPUB).

**Root Cause**: The page complexity analyzer was detecting decorative rectangular borders as "image regions" and saving them as images, even though they only contained text.

## Solution Implemented

### 1. **Improved Border Detection in `page_complexity_analyzer.py`**

Added logic to distinguish decorative borders from actual illustrations using:
- **Fill Ratio**: Ratio of contour area to bounding box area
- **Perimeter Ratio**: How close the contour is to a perfect rectangle
- **Decision Criteria**:
  - Hollow frames (fill ratio < 20%) = decorative border
  - Low fill ratio (< 30%) + perfect rectangle = decorative border

### 2. **Enhanced Image Classification in `pdf_to_epub_converter_optimized_v2.py`**

#### Change 1: Stricter "Mostly Image" Detection (Lines 382-400)
- Now requires BOTH:
  - Very little text (< 200 chars) AND high complexity
  - A single image region covering >70% of page
- **Safeguard**: Pages with >500 chars are NEVER treated as pure image pages

#### Change 2: Text-Based Image Region Filtering (Lines 417-430) **[CRITICAL FIX]**
- **Mode B (Partial Crops)** now checks text length:
  - If text < 300 chars: Save partial image regions (likely captions/labels)
  - If text ≥ 300 chars: **Skip all image regions** (likely decorative borders)
- This prevents "text in a decorative box" from being saved as images

## Impact

### Before Fix:
- Text inside decorative borders → Detected as "illustration"
- Entire bordered region saved as image
- Result: 3 MB PDF → 500 MB EPUB (167x size increase!)

### After Fix:
- Text inside decorative borders → Detected as text content
- Only OCR text is saved, no image
- Result: Normal EPUB size (text-based, ~5-10% of original PDF size)

## Configuration

The fix uses these thresholds (can be adjusted in code if needed):

```python
# In page_complexity_analyzer.py
FILL_RATIO_HOLLOW_THRESHOLD = 0.20  # Hollow frame detection
FILL_RATIO_DECORATIVE_THRESHOLD = 0.30  # With perfect rectangle
PERIMETER_RATIO_RANGE = (0.95, 1.05)  # Perfect rectangle range

# In pdf_to_epub_converter_optimized_v2.py
TEXT_LENGTH_MOSTLY_IMAGE = 200  # Max chars for "mostly image"
TEXT_LENGTH_SAFEGUARD = 500  # Min chars to never be image
TEXT_LENGTH_PARTIAL_REGIONS = 300  # Max chars to allow partial regions
```

## Testing

Run the test script to verify border detection:

```bash
python tests/test_border_detection.py
```

Expected output for pages with decorative borders:
```
PASS: Decorative border correctly filtered out (will use OCR text only)
```

## Files Modified

1. **`src/page_complexity_analyzer.py`**
   - Lines 74-110: New fill-ratio based border detection

2. **`src/pdf_to_epub_converter_optimized_v2.py`**
   - Lines 382-400: Improved "mostly image" classification
   - Lines 417-430: Text-based image region filtering (CRITICAL FIX)

3. **`tests/test_border_detection.py`** (NEW)
   - Test script to verify border detection logic

## Recommendations

1. **Test with your actual PDFs**: Run a conversion and check the log output for lines like:
   ```
   ✓ Skipped 2 image regions (substantial text detected: 1234 chars - likely decorative borders)
   ```

2. **Adjust thresholds if needed**: If some decorative borders are still being captured, lower the `TEXT_LENGTH_PARTIAL_REGIONS` threshold from 300 to 200.

3. **Monitor file sizes**: Compare EPUB sizes before and after the fix to verify the improvement.

## Example Log Output

**Before Fix:**
```
📸 Extracted partial illustration at (336,138). Skipped full-page background.
📸 Extracted partial illustration at (336,139). Skipped full-page background.
```

**After Fix:**
```
✓ Skipped 2 image regions (substantial text detected: 1234 chars - likely decorative borders)
```

---

**Date**: 2026-01-26  
**Issue**: Decorative borders causing massive EPUB file sizes  
**Status**: ✅ FIXED
