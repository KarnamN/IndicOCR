# Skip OCR Pages - User Guide

## What is "Skip OCR Pages"?

This feature allows you to specify which pages should **skip OCR processing entirely** and be preserved as images only. This is useful for:

- 📸 **Problematic pages** that cause OCR to crash or hang
- 🖼️ **Image-heavy pages** where OCR adds no value (charts, diagrams, photos)
- 🎨 **Decorative pages** with complex layouts that OCR struggles with
- ⚡ **Speed optimization** by skipping pages that don't need text extraction

## How to Use

In the web interface, find the **"Skip OCR Pages"** input field and enter page numbers using the patterns below.

### Supported Patterns

#### 1. **Single Pages** (comma-separated)
```
5,7,12
```
Skips pages: 5, 7, and 12

#### 2. **Ranges** (hyphen-separated)
```
5-9
```
Skips pages: 5, 6, 7, 8, 9

#### 3. **Individual Pages**
```
10,11
```
Skips pages: 10 and 11

#### 4. **Mixed Patterns** (combine ranges and individual pages)
```
5-9,10,11
```
Skips pages: 5, 6, 7, 8, 9, 10, 11

#### 5. **Multiple Ranges**
```
1-3,5-7,10-12
```
Skips pages: 1, 2, 3, 5, 6, 7, 10, 11, 12

#### 6. **Complex Combinations**
```
2,5-9,15,20-25,30
```
Skips pages: 2, 5, 6, 7, 8, 9, 15, 20, 21, 22, 23, 24, 25, 30

## Important Notes

✅ **Page numbers are 1-indexed** (first page is page 1, not page 0)
✅ **Ranges are inclusive** (5-9 includes both 5 and 9)
✅ **Whitespace is ignored** (`5-9, 10, 11` works the same as `5-9,10,11`)
✅ **Invalid pages are filtered out** (if you specify page 100 but PDF only has 50 pages, it's ignored)
✅ **No OCR, no splitting** - Skipped pages are preserved as-is (no double-page splitting)

## Examples

### Example 1: Skip problematic pages that crash OCR
```
Input: 23,45,67
Result: Pages 23, 45, and 67 are preserved as images only
```

### Example 2: Skip a range of image-heavy pages
```
Input: 10-20
Result: Pages 10 through 20 are preserved as images only
```

### Example 3: Skip cover pages and problematic pages
```
Input: 1-2,15,28-30
Result: Pages 1, 2, 15, 28, 29, 30 are preserved as images only
```

### Example 4: Complex pattern for multiple sections
```
Input: 1-5,12,18-22,45-50,99
Result: All specified pages are preserved as images only
```

## What Happens to Skipped Pages?

When you skip OCR on a page:

1. ✅ **Page is converted to image** (at the DPI you specified)
2. ❌ **No OCR processing** (no text extraction)
3. ❌ **No table detection** (even if enabled)
4. ❌ **No page splitting** (even if double-page splitting is enabled)
5. ✅ **Image is preserved in EPUB** (you can still view the page)
6. ⚡ **Faster processing** (skips the most time-consuming step)

## Logs

When a page is skipped, you'll see this in the logs:

```
⚠️ Page 5: SKIPPING OCR (user-specified)
  📸 Preserving page 5 as image only (no OCR)
✅ Page 5 completed (image only, no OCR)
```

## Tips

💡 **Test first**: Try converting a small range of pages first to identify problematic pages
💡 **Check logs**: Monitor the conversion logs to see which pages are causing issues
💡 **Be specific**: Only skip pages that actually need it - OCR is valuable for most pages
💡 **Combine with cover pages**: Remember that the first 2 pages are already preserved as covers by default

## Troubleshooting

**Q: I entered `5-9` but it's still processing those pages**
- ✅ **Fixed!** This was a bug that has been resolved. The skip check now happens before page splitting.

**Q: Can I skip all pages?**
- Yes, but that defeats the purpose of OCR conversion. You'd just get an image-based EPUB.

**Q: What if I enter invalid page numbers?**
- Invalid pages are automatically filtered out. Only valid pages within the PDF range are skipped.

**Q: Does this work with double-page splitting?**
- Yes! The skip check happens **before** page splitting, so it works correctly regardless of splitting settings.
