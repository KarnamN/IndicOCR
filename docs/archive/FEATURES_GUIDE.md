# Telugu OCR Features Guide

## ✅ Available Features

Your recovered system includes these advanced features:

### 1. Text Cleaning (Noise Removal)
**File**: `src/text_cleaner.py`

**Features**:
- ✅ Remove page numbers (Telugu and English)
- ✅ Normalize whitespace
- ✅ Fix common OCR errors
- ✅ Remove headers/footers
- ✅ Clean multiple pages at once

**Usage**:
```python
from src.text_cleaner import TextCleaner

cleaner = TextCleaner()

# Clean single page
cleaned_text = cleaner.clean_text(ocr_text)

# Clean multiple pages
cleaned_pages = cleaner.clean_pages([page1_text, page2_text, page3_text])

# Merge pages
merged = cleaner.merge_pages(cleaned_pages)
```

**Configuration** (in `config.py`):
```python
REMOVE_PAGE_NUMBERS = True
PAGE_NUMBER_PATTERNS = [
    r'Page\s+\d+',      # English: "Page 1"
    r'పేజీ\s+\d+',      # Telugu: "పేజీ 1"
    r'^\d+$',           # Standalone numbers
    r'- \d+ -',         # Centered: "- 1 -"
]
```

### 2. Two-Column / Double-Page Detection
**File**: `src/page_splitter.py`

**Features**:
- ✅ Auto-detect double-page scans (landscape format)
- ✅ Find optimal split point (gutter detection)
- ✅ Split into two single pages
- ✅ Configurable aspect ratio threshold

**Usage**:
```python
from src.page_splitter import PageSplitter
from PIL import Image

splitter = PageSplitter(aspect_ratio_threshold=1.3)

# Load image
image = Image.open('double_page.jpg')

# Process (auto-detect and split if needed)
pages = splitter.process_image(image)

# pages will be:
# - [single_page] if portrait/single page
# - [left_page, right_page] if landscape/double page
```

**How it works**:
1. Checks aspect ratio (width/height)
2. If ratio > 1.3 (configurable), treats as double-page
3. Analyzes vertical brightness to find gutter (center gap)
4. Splits at the gutter or center
5. Returns two separate page images

### 3. Combined Usage in Converter

The main converter (`pdf_to_epub_converter_optimized_v2.py`) already uses both:

```python
# Text cleaning is automatic
text = ocr_processor.extract_text(image)
cleaned_text = self._clean_ocr_text(text)  # Uses TextCleaner

# Page splitting (if enabled)
if self.split_double_pages:
    page_images = self.page_splitter.process_image(page_image)
    # Each image is processed separately
```

## Configuration

### Enable/Disable Features

In `config.py`:

```python
# Text Cleaning
REMOVE_PAGE_NUMBERS = True  # Remove page numbers
PAGE_NUMBER_PATTERNS = [...]  # Patterns to remove

# Page Splitting
# (Enabled via command-line or programmatically)
split_double_pages = True  # In converter initialization
```

### Tesseract with Cleaning

The system automatically:
1. Extracts text with Tesseract (Telugu + English)
2. Cleans noise and page numbers
3. Normalizes whitespace
4. Removes headers/footers (if configured)

## Example: Full Pipeline

```python
from src.pdf_to_epub_converter_optimized_v2 import PDFToEPUBConverter

# Initialize with all features
converter = PDFToEPUBConverter(
    language='tel+eng',           # Telugu + English
    detect_tables=True,           # Detect tables
    preserve_images=True,         # Keep images
    split_double_pages=True,      # Split 2-column pages
)

# Convert with automatic cleaning
converter.convert_streaming(
    pdf_path='input.pdf',
    output_path='output.epub',
    title='My Book'
)

# The converter automatically:
# 1. Detects double-page scans
# 2. Splits them into single pages
# 3. Runs OCR (Tesseract or PaddleOCR)
# 4. Cleans the text (removes noise, page numbers)
# 5. Creates clean EPUB
```

## Testing

### Test Text Cleaner
```bash
cd /mnt/c/Workspace/Antigravity_workspace/Myocr
source .venv/bin/activate
python -c "from src.text_cleaner import TextCleaner; c = TextCleaner(); print(c.clean_text('Page 1\nSome text\n\n\nMore text'))"
```

### Test Page Splitter
```bash
python src/page_splitter.py
```

## Summary

✅ **Text Cleaning**: Fully functional
- Removes page numbers (Telugu + English)
- Cleans noise
- Normalizes whitespace

✅ **2-Column Detection**: Fully functional
- Auto-detects double-page scans
- Splits at optimal point
- Works with both Tesseract and PaddleOCR

✅ **Integration**: Both features are already integrated into the main converter

**Your system is ready to handle:**
- Multi-column content
- Double-page scans
- Noisy OCR output
- Telugu and English text
- Page numbers and headers/footers

All features are working! 🎉
