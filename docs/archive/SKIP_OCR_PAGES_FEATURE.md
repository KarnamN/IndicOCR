# Skip OCR on Specific Pages Feature

## Problem
Some pages in PDFs cause EasyOCR to crash or hang, even with timeout protection and semaphore limits. Users need a way to bypass OCR on these problematic pages.

## Solution
Added a **"Skip OCR on Pages"** input field in the UI that allows users to specify page numbers to skip OCR and preserve as images only.

---

## How to Use

### 1. **Identify Problematic Pages**

When the conversion crashes, check the log to see which page caused the issue:

```
Page 7: Using EASYOCR (complexity: 75.0)
Killed  ← Crashed on page 7
```

### 2. **Enter Page Numbers in UI**

In the web interface, find the **"Skip OCR on Pages (Image Only)"** field and enter:

```
7
```

Or for multiple pages:

```
5,7,12
```

Or for ranges:

```
5-10,15,20-25
```

### 3. **Convert**

Click "Convert to EPUB & MOBI" - the specified pages will:
- ✅ Skip all OCR processing
- ✅ Be preserved as full-page images
- ✅ Not cause crashes
- ✅ Still appear in the EPUB

---

## Examples

### Single Page
```
Input: 7
Result: Page 7 → Image only (no OCR)
```

### Multiple Pages
```
Input: 5,7,12
Result: Pages 5, 7, 12 → Images only (no OCR)
```

### Page Ranges
```
Input: 5-10,15,20-25
Result: Pages 5,6,7,8,9,10,15,20,21,22,23,24,25 → Images only (no OCR)
```

### Mixed
```
Input: 3,7-9,15,20-22
Result: Pages 3,7,8,9,15,20,21,22 → Images only (no OCR)
```

---

## Expected Log Output

### When Page is Skipped

```
[ThreadPoolExecutor-1_2] 📄 Processing page 7...
[ThreadPoolExecutor-1_2] ⚠️ Page 7: SKIPPING OCR (user-specified)
  📸 Preserving page 7 as image only (no OCR)
[ThreadPoolExecutor-1_2] ✅ Page 7 completed (image only, no OCR)
```

### At Startup

```
Optimized Converter initialized: language=tel, dpi=300, workers=4
preserve_images=True, detect_tables=True
parallel_processing=True, batch_size=4
Skip OCR on pages: [5, 7, 12]  ← Shows which pages will be skipped
```

---

## What Happens

### Normal Page (OCR Enabled)
```
Page 6:
1. Auto-rotate ✓
2. Detect tables ✓
3. Run OCR (EasyOCR or Tesseract) ✓
4. Extract text ✓
5. Preserve image (if complex) ✓
```

### Skipped Page (No OCR)
```
Page 7:
1. Check skip list → Found! ✓
2. Preserve full page as image ✓
3. Skip all OCR ✓
4. Return immediately ✓
```

**Result**: Page 7 processes in ~1 second instead of 60+ seconds and doesn't crash!

---

## Benefits

### 1. **Bypass Problematic Pages**
- Pages that crash EasyOCR → Skip OCR
- Pages that timeout → Skip OCR
- Pages with complex layouts → Skip OCR

### 2. **Fast Processing**
- Skipped pages process in ~1 second
- No OCR overhead
- No timeout delays

### 3. **Still Readable**
- Pages preserved as high-quality images
- Still appear in EPUB
- Still readable by users

### 4. **No Crashes**
- Problematic pages can't crash the process
- Conversion completes successfully
- All pages included in output

---

## Implementation Details

### UI Field (`index.html`)

```html
<div class="form-group full-width">
    <label for="skipOcrPages">Skip OCR on Pages (Image Only)</label>
    <input type="text" id="skipOcrPages" name="skip_ocr_pages" 
           placeholder="e.g., 5,7,12-15 (leave empty to OCR all pages)">
    <small>
        Enter page numbers to skip OCR and preserve as images only. 
        Useful for problematic pages.
    </small>
</div>
```

### Backend Parsing (`app.py`)

```python
# Parse skip_ocr_pages (e.g., "5,7,12-15")
skip_ocr_pages_str = request.form.get('skip_ocr_pages', '').strip()
skip_ocr_pages = []
if skip_ocr_pages_str:
    try:
        skip_ocr_pages = parse_page_list(skip_ocr_pages_str, 9999)
        logger.info(f"Skip OCR on pages: {skip_ocr_pages}")
    except Exception as e:
        logger.warning(f"Failed to parse skip_ocr_pages: {e}")
```

### Converter Check (`pdf_to_epub_converter_optimized_v2.py`)

```python
# Check if this page should skip OCR (user-specified problematic pages)
if (page_num + 1) in self.skip_ocr_pages:  # +1 because page_num is 0-indexed
    logger.warning(f"[{thread_id}] ⚠️ Page {page_num + 1}: SKIPPING OCR (user-specified)")
    logger.info(f"  📸 Preserving page {page_num + 1} as image only (no OCR)")
    
    # Preserve full page as image
    result['images'].append({
        'image': page_image,
        'bbox': (0, 0, page_image.width, page_image.height),
        'page_num': page_num,
        'is_full_page': True
    })
    
    logger.info(f"[{thread_id}] ✅ Page {page_num + 1} completed (image only, no OCR)")
    return result  # Skip all OCR processing
```

---

## Workflow

### 1. **First Attempt (Crashes)**

```
User uploads PDF → Crashes on page 7
```

### 2. **Check Logs**

```
Page 7: Using EASYOCR (complexity: 75.0)
Killed  ← Found the problematic page!
```

### 3. **Second Attempt (Skip Page 7)**

```
User enters "7" in "Skip OCR on Pages" field
User uploads PDF again
Page 7 → Skipped (image only)
Conversion completes successfully! ✅
```

---

## Use Cases

### 1. **Crash Recovery**
```
Problem: Page 15 crashes EasyOCR
Solution: Enter "15" → Skip OCR on page 15
Result: Conversion completes
```

### 2. **Timeout Prevention**
```
Problem: Pages 20-25 timeout after 60s each
Solution: Enter "20-25" → Skip OCR on those pages
Result: Saves 6 × 60s = 6 minutes
```

### 3. **Complex Diagrams**
```
Problem: Pages with complex diagrams have poor OCR
Solution: Enter "10,15,20" → Skip OCR, use images
Result: Better quality (image instead of garbled text)
```

### 4. **Mixed Content**
```
Problem: Some pages are pure images (photos, charts)
Solution: Enter those page numbers → Skip OCR
Result: Faster processing, same quality
```

---

## Testing

### Test 1: Single Page

1. **Upload a PDF**
2. **Enter "5" in Skip OCR field**
3. **Convert**
4. **Check logs:**
   ```
   Page 5: SKIPPING OCR (user-specified)
   Page 5 completed (image only, no OCR)
   ```

### Test 2: Multiple Pages

1. **Upload a PDF**
2. **Enter "3,7,12" in Skip OCR field**
3. **Convert**
4. **Check logs:**
   ```
   Skip OCR on pages: [3, 7, 12]
   ...
   Page 3: SKIPPING OCR (user-specified)
   Page 7: SKIPPING OCR (user-specified)
   Page 12: SKIPPING OCR (user-specified)
   ```

### Test 3: Page Range

1. **Upload a PDF**
2. **Enter "10-15" in Skip OCR field**
3. **Convert**
4. **Check logs:**
   ```
   Skip OCR on pages: [10, 11, 12, 13, 14, 15]
   ...
   Pages 10-15: All skipped
   ```

---

## Summary

| Feature | Description |
|---------|-------------|
| **Input Field** | "Skip OCR on Pages (Image Only)" |
| **Format** | Single: `7`, Multiple: `5,7,12`, Range: `5-10` |
| **Effect** | Skips OCR, preserves as image |
| **Speed** | ~1 second per skipped page |
| **Quality** | High-quality image (300 DPI) |
| **Use Case** | Bypass problematic/crashing pages |

**Result**: Reliable conversion even with problematic pages! 🎉

---

**Date**: 2026-02-08  
**Status**: ✅ Implemented  
**Files Modified**:
- `src/templates/index.html` (UI field)
- `src/static/css/style.css` (full-width styling)
- `src/app.py` (parameter parsing)
- `src/pdf_to_epub_converter_optimized_v2.py` (skip OCR logic)

**Testing**: Ready for testing with problematic PDFs
