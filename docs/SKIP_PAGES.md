# Skip OCR on Specific Pages

## What it does

Lets you specify page numbers that should skip OCR entirely and be preserved as
full-page images instead. Useful for:

- Problematic pages that cause OCR to crash, hang, or time out.
- Image-heavy pages (charts, diagrams, photos) where OCR adds no value.
- Decorative/complex layouts OCR struggles with — a raw image reads better than
  garbled text.
- Speeding up conversion by skipping pages that don't need text extraction.

## How to use

In the web UI, the **"Skip OCR on Pages (Image Only)"** field accepts:

| Pattern | Example | Result |
|---|---|---|
| Single pages | `7` or `5,7,12` | Skips exactly those pages |
| Ranges | `5-9` | Skips 5, 6, 7, 8, 9 (inclusive both ends) |
| Mixed | `3,7-9,15,20-22` | Skips 3, 7, 8, 9, 15, 20, 21, 22 |

Notes:
- Page numbers are 1-indexed (first page is `1`).
- Whitespace is trimmed automatically (`5-9, 10, 11` works fine).
- Invalid pages (beyond the PDF's page count) are silently filtered out.
- Works correctly regardless of double-page splitting settings (see below).

## What happens to a skipped page

1. Converted to an image at the configured DPI.
2. No OCR, no table detection, no double-page splitting.
3. Included in the EPUB as an image-only page.
4. Processes in roughly 1 second instead of the 5-60+ seconds a full OCR pass takes.

Log output when a page is skipped:
```
⚠️ Page 5: SKIPPING OCR (user-specified)
  📸 Preserving page 5 as image only (no OCR)
✅ Page 5 completed (image only, no OCR)
```

At startup, the active skip list is logged once:
```
Skip OCR on pages: [5, 7, 12]
```

## Implementation

- **UI field**: `src/templates/index.html` — `skip_ocr_pages` form input.
- **Parsing**: `src/app.py` (`parse_page_list()`, imported from `src/pdf_manipulator.py`)
  turns the input string into a validated list of page numbers, then passes it to the
  converter as `skip_ocr_pages`.
- **Storage**: `OptimizedPDFToEPUBConverter.__init__` stores it as a set for O(1) lookup
  (`self.skip_ocr_pages`, `src/pdf_to_epub_converter_optimized_v2.py:78`).
- **Check point**: the skip check runs in `_process_single_page_wrapper()`
  (`src/pdf_to_epub_converter_optimized_v2.py:1624`), matching against the **original**
  PDF page number:
  ```python
  if (page_num + 1) in self.skip_ocr_pages:  # +1 because page_num is 0-indexed
  ```

### Why the check has to run before page splitting

Double-page splitting recomputes an "effective" page number per output page
(`effective_page_num = page_num * 2 + sub_idx`). Checking the skip list against effective
page numbers instead of the original PDF page number caused a real bug: a user asking to
skip "pages 5-9" (meaning the physical PDF pages) would have those numbers checked against
post-split effective numbers, which don't line up — so some intended pages weren't skipped.

Fixed by moving the check into `_process_single_page_wrapper()`, which runs on the
**original** PDF page number before any splitting occurs, so skipped pages never even reach
the splitter or the OCR pipeline.

## Testing

1. Upload a PDF with at least 10 pages.
2. Try each pattern type in the Skip OCR field: `5` (single), `5-9` (range), `5-9,10,11`
   (mixed), with double-page splitting both on and off.
3. Confirm the log shows `SKIPPING OCR (user-specified)` for exactly the pages requested,
   and that those pages appear as images (not garbled/missing text) in the output EPUB.
