# Intelligent Image Preservation for Complex Pages

## Feature Overview

The system now **automatically preserves page images for complex pages** alongside OCR text, ensuring readability even when OCR isn't perfect.

## How It Works

### Automatic Detection

```python
# During page processing:
if complexity_score > 70:
    preserve_image = True  # Always preserve for complex pages
    logger.info("📸 Complex page detected - preserving image alongside OCR text")
```

### Page Classification

| Page Type | Complexity | Image Preserved | OCR Engine | Reason |
|-----------|-----------|-----------------|------------|--------|
| **Simple text** | < 45 | ❌ No | Tesseract | OCR sufficient |
| **Standard** | 45-70 | ⚙️ Optional | Tesseract | Good OCR quality |
| **Complex** | > 70 | ✅ **Always** | EasyOCR | Ensures readability |

### Your Astrology Pages

Your Telugu astrology pages with tables and charts will:
1. ✅ Be detected as **complex** (score > 70)
2. ✅ Use **EasyOCR** for best OCR
3. ✅ **Preserve original image** alongside OCR text
4. ✅ Appear in both EPUB and MOBI

## Benefits

### For Complex Pages:

✅ **Dual View**: Readers see both OCR text AND original image  
✅ **Fallback**: If OCR misses something, image shows it  
✅ **Tables/Charts**: Complex layouts preserved visually  
✅ **Searchable**: OCR text enables search, image ensures accuracy  

### Example EPUB Output:

```html
<!-- Complex page (e.g., your astrology chart) -->
<div class="page-content">
    <!-- OCR Text (searchable) -->
    <div class="ocr-text">
        క్వ్యాణజాతక విశ్లేషణ ౩
        అష్టమ, ద్వాదశ రాశులలో...
    </div>
    
    <!-- Original Image (visual reference) -->
    <img src="images/page_179.jpg" alt="Page 179" />
</div>
```

## Configuration

### In `config.py`:

```python
# Image Preservation Settings
PRESERVE_IMAGES = True                      # Enable image preservation
SELECTIVE_IMAGE_PRESERVATION = True         # Smart mode
COMPLEX_PAGE_IMAGE_THRESHOLD = 70           # Complexity threshold
```

### Adjust Threshold:

```python
# More aggressive (preserve more images)
COMPLEX_PAGE_IMAGE_THRESHOLD = 60

# Less aggressive (preserve fewer images)
COMPLEX_PAGE_IMAGE_THRESHOLD = 80
```

## Storage Optimization

Images are automatically optimized for storage:

```python
# Two-Stage DPI Processing
OCR_DPI = 300          # High DPI for accurate OCR
STORAGE_DPI = 150      # Lower DPI for storage (50% size reduction)
```

### Size Comparison:

| Setting | Image Size | Quality | Use Case |
|---------|-----------|---------|----------|
| **300 DPI** | ~2 MB/page | Excellent | OCR processing |
| **150 DPI** | ~500 KB/page | Good | EPUB/MOBI storage |
| **100 DPI** | ~200 KB/page | Fair | Very small files |

## Monitoring

### Check Logs:

```bash
tail -f converter.log | grep -E "(complexity|📸|Complex page)"
```

### Example Output:

```
[Thread-1] 📄 Page 179: Using EASYOCR (complexity: 85.3)
  📸 Complex page detected - preserving image alongside OCR text
  • Reduced storage DPI: 2480x3508 -> 1240x1754 (150 DPI)
```

## Disable for Specific Pages

If you want to disable image preservation for all pages:

```python
# In config.py
PRESERVE_IMAGES = False
SELECTIVE_IMAGE_PRESERVATION = False
```

Or via web UI:
- Uncheck "Preserve Images" option

## Advanced: Custom Logic

### Preserve images based on OCR confidence:

```python
# In pdf_to_epub_converter_optimized_v2.py
if hasattr(ocr_processor, 'extract_text_with_confidence'):
    text, confidence = ocr_processor.extract_text_with_confidence(ocr_image)
    if confidence < 0.8:  # Low confidence
        preserve_image_for_this_page = True
        logger.info(f"  📸 Low OCR confidence ({confidence:.2f}) - preserving image")
```

### Preserve images for specific page ranges:

```python
# Always preserve images for pages 1-10 and 100-110
if page_num < 10 or (100 <= page_num < 110):
    preserve_image_for_this_page = True
```

## File Size Impact

### Example: 200-page book

| Mode | EPUB Size | MOBI Size | Notes |
|------|-----------|-----------|-------|
| **No images** | 2 MB | 3 MB | Text only |
| **All images** | 120 MB | 150 MB | Every page |
| **Smart (complex only)** | 40 MB | 50 MB | ~30% of pages |

### Optimization Tips:

1. **Adjust threshold**: Higher = smaller files
2. **Lower storage DPI**: 100 DPI instead of 150
3. **JPEG quality**: Reduce from 70 to 60

```python
IMAGE_QUALITY = 60      # Lower quality, smaller size
STORAGE_DPI = 100       # Even smaller images
```

## Testing

### Test with your PDF:

1. Upload your Telugu astrology PDF
2. Check logs for complexity scores
3. Open generated EPUB
4. Verify complex pages have both text AND images

### Verify in EPUB:

```bash
# Extract EPUB
unzip output.epub -d epub_contents

# Check images
ls -lh epub_contents/images/

# Check which pages have images
grep -r "img src" epub_contents/OEBPS/
```

## Summary

✅ **Automatic**: No manual configuration needed  
✅ **Smart**: Only complex pages get images  
✅ **Optimized**: Images compressed for storage  
✅ **Dual benefit**: Searchable text + visual accuracy  
✅ **Works in**: Both EPUB and MOBI formats  

Your complex Telugu astrology pages will now have **both OCR text and original images** for the best reading experience! 📚✨
