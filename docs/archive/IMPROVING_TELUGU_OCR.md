# Improving Telugu OCR Quality

## Current Status

✅ **Tesseract-only mode** enabled (stable, no crashes)  
⚙️ **Optimized PSM settings** for structured Telugu documents  
📊 **Best for**: Complex pages with tables, charts, and mixed layouts

## Quick Improvements Made

### 1. **Disabled Adaptive OCR**
- Using Tesseract only (most stable)
- No EasyOCR (poor quality for complex Telugu)
- No PaddleOCR (segfaults in WSL)

### 2. **Optimized Tesseract Settings**
```python
OCR_CONFIG = '--oem 3 --psm 6'  # PSM 6: Uniform text block
TESSERACT_CONFIG = '--oem 3 --psm 6'  # Better for structured pages
```

**PSM (Page Segmentation Mode) Options:**
- `PSM 3`: Fully automatic (default) - good for general pages
- `PSM 6`: Uniform block of text - **BEST for your astrology pages**
- `PSM 4`: Single column of text
- `PSM 11`: Sparse text - good for finding text in images

## Advanced: Install Best Telugu Models

For **significantly better accuracy**, install `tessdata_best`:

### Step 1: Download Best Telugu Model
```bash
cd /tmp
wget https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata
```

### Step 2: Install (requires sudo)
```bash
sudo cp tel.traineddata /usr/share/tesseract-ocr/5/tessdata/tel_best.traineddata
```

### Step 3: Update Config
In `config.py`, change:
```python
DEFAULT_OCR_LANGUAGE = 'tel_best+eng'  # Use best model
TESSERACT_CONFIG = '--oem 1 --psm 6'   # OEM 1: Neural nets LSTM only
```

### Verification
```bash
tesseract --list-langs | grep tel
# Should show: tel_best
```

## Image Preprocessing for Better OCR

Add these preprocessing steps in `ocr_processor.py`:

### 1. **Increase Contrast**
```python
from PIL import ImageEnhance

def enhance_image(image):
    # Increase contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # Increase sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)
    
    return image
```

### 2. **Denoise**
```python
import cv2
import numpy as np

def denoise_image(image):
    img_array = np.array(image)
    denoised = cv2.fastNlMeansDenoisingColored(img_array, None, 10, 10, 7, 21)
    return Image.fromarray(denoised)
```

### 3. **Binarization (Black & White)**
```python
def binarize_image(image):
    gray = image.convert('L')
    # Otsu's thresholding
    img_array = np.array(gray)
    _, binary = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(binary)
```

## DPI Optimization

Your config already has good DPI settings, but for complex pages:

```python
# In config.py
DEFAULT_DPI = 400  # Increase from 300 for better quality
OCR_DPI = 400      # Higher DPI = better OCR for small text
STORAGE_DPI = 200  # Keep storage DPI reasonable
```

## Testing Different PSM Modes

Create a test script to find the best PSM for your pages:

```python
# test_psm_modes.py
import pytesseract
from PIL import Image

image_path = "your_test_page.png"
image = Image.open(image_path)

psm_modes = {
    3: "Fully automatic",
    4: "Single column",
    6: "Uniform text block",
    11: "Sparse text",
    12: "Sparse text with OSD"
}

for psm, description in psm_modes.items():
    config = f'--oem 3 --psm {psm} -l tel+eng'
    text = pytesseract.image_to_string(image, config=config)
    
    print(f"\n{'='*60}")
    print(f"PSM {psm}: {description}")
    print(f"{'='*60}")
    print(text[:500])  # First 500 chars
```

## Comparison: Model Quality

| Model | Accuracy | Speed | File Size | Best For |
|-------|----------|-------|-----------|----------|
| **tessdata** (current) | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ~9 MB | General use |
| **tessdata_best** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ~20 MB | Complex Telugu |
| **tessdata_fast** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ~2 MB | Quick scans |

## Current Configuration Summary

```python
# Active Settings
OCR_ENGINE = 'tesseract'           # Stable, no crashes
ENABLE_ADAPTIVE_OCR = False        # Disabled for consistency
DEFAULT_OCR_LANGUAGE = 'tel+eng'   # Telugu + English
OCR_CONFIG = '--oem 3 --psm 6'     # Optimized for structured pages
DEFAULT_DPI = 300                  # Good balance
```

## Recommended Next Steps

1. ✅ **Already Done**: Optimized PSM to 6
2. 📥 **Recommended**: Install `tessdata_best` for better accuracy
3. 🔧 **Optional**: Add image preprocessing (contrast, denoise)
4. 📊 **Test**: Try different PSM modes for your specific pages
5. ⚡ **Tune**: Adjust DPI if needed (400 for small text)

## Troubleshooting

### If OCR quality is still poor:

1. **Check image quality**
   ```bash
   identify -verbose your_page.png | grep -E "(Resolution|Geometry)"
   ```

2. **Test with different PSM**
   - PSM 4 for single column
   - PSM 11 for sparse text
   - PSM 12 for rotated text

3. **Increase DPI**
   ```python
   DEFAULT_DPI = 400  # or even 600 for very small text
   ```

4. **Preprocess images**
   - Add contrast enhancement
   - Apply denoising
   - Convert to black & white

## Performance Impact

| Setting | Quality | Speed | Memory |
|---------|---------|-------|--------|
| PSM 6 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| DPI 400 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| tessdata_best | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Preprocessing | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |

## Quick Test

Restart server and test:
```bash
pkill -f "python3.*app.py"
cd /mnt/c/Workspace/Antigravity_workspace/Myocr
./scripts/start.sh
```

Then upload your PDF and check the logs for OCR quality improvements!
