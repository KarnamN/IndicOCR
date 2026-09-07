# Enhanced Telugu OCR with Vatulu & Guninthalu Detection

## 🎯 Overview

This project has been enhanced with advanced Telugu text processing capabilities, including **Vatulu** (వత్తులు - subscript consonants) and **Guninthalu** (గుణింతాలు - vowel modifiers) detection. These features were integrated from the TeluguOCR-develop project to provide superior Telugu language support.

## ✨ New Features

### 1. **Telugu Text Processor** (`telugu_text_processor.py`)
Advanced Telugu text analysis with comprehensive character identification:

- **Vatulu Detection**: Identifies subscript consonants (వత్తులు)
  - Detects virama/halant marks (్)
  - Tracks consonant combinations with vatulu
  - Provides transliteration for each vattu

- **Guninthalu Detection**: Identifies vowel modifiers (గుణింతాలు)
  - Detects all 15 Telugu vowel modifiers (matras)
  - Maps each gunintham to its transliteration
  - Tracks position and context

- **Complex Character Analysis**: 
  - Identifies consonant + vattu + gunintham combinations
  - Provides detailed breakdown of each complex character
  - Calculates statistics (percentage of vatulu/guninthalu in text)

- **Text Normalization**:
  - Unicode NFC normalization
  - Whitespace cleanup
  - Character validation

### 2. **Enhanced Telugu OCR** (`enhanced_telugu_ocr.py`)
Intelligent OCR system with adaptive engine selection:

- **Adaptive OCR Selection**:
  - Calculates page complexity (0-100 score)
  - Simple pages (< 45): Uses fast Tesseract
  - Complex pages (> 60): Uses accurate EasyOCR
  - Medium pages: Prefers EasyOCR if available

- **Page Complexity Analysis**:
  - Edge density detection
  - Horizontal/vertical line detection
  - Table structure identification
  - Automatic engine selection based on content

- **Dual OCR Engine Support**:
  - **Tesseract**: Fast, efficient for simple text
  - **EasyOCR**: Accurate, better for tables and complex layouts
  - Automatic fallback if preferred engine unavailable

- **Enhanced Output**:
  - Both engines' outputs enhanced with Telugu analysis
  - Confidence scores for each extraction
  - Detailed Telugu character statistics
  - Normalized text with original preserved

### 3. **Configuration Updates** (`config.py`)
Streamlined configuration focusing on EasyOCR:

- **Removed PaddleOCR**: Eliminated deprecated PaddleOCR dependencies
- **EasyOCR Primary**: Set as primary OCR engine
- **Telugu Processing**: New configuration options:
  ```python
  ENABLE_TELUGU_PROCESSING = True
  ANALYZE_VATULU = True
  ANALYZE_GUNINTHALU = True
  TELUGU_ENCODING_DIR = None  # Optional: Path to encoding files
  ```

- **Adaptive Thresholds**:
  ```python
  ADAPTIVE_SIMPLE_THRESHOLD = 45   # Tesseract threshold
  ADAPTIVE_COMPLEX_THRESHOLD = 60  # EasyOCR threshold
  ```

## 📊 How It Works

### Page Processing Flow

```
1. Image Input
   ↓
2. Calculate Page Complexity
   ├─ Edge Detection
   ├─ Line Detection (H/V)
   └─ Complexity Score (0-100)
   ↓
3. Select OCR Engine
   ├─ Simple (< 45) → Tesseract
   ├─ Medium (45-60) → EasyOCR (preferred)
   └─ Complex (> 60) → EasyOCR
   ↓
4. Extract Text
   ├─ Tesseract: Fast extraction
   └─ EasyOCR: Line removal + enhanced detection
   ↓
5. Telugu Text Analysis
   ├─ Identify Vatulu
   ├─ Identify Guninthalu
   ├─ Analyze Complex Characters
   └─ Calculate Statistics
   ↓
6. Enhanced Output
   ├─ Normalized Text
   ├─ Confidence Score
   ├─ Telugu Analysis
   └─ Character Details
```

### Example Output

```python
{
    'text': 'తెలుగు భాష',
    'engine': 'easyocr',
    'confidence': 0.92,
    'complexity': 35.4,
    'char_count': 10,
    'telugu_analysis': {
        'telugu_chars': 9,
        'vatulu_count': 0,
        'guninthalu_count': 4,
        'complex_chars': 4,
        'has_vatulu': False,
        'has_guninthalu': True,
        'vatulu_percentage': '0.0%',
        'guninthalu_percentage': '44.4%'
    },
    'guninthalu_details': [
        (1, 'ె', 'e'),   # Position 1: ె (e)
        (3, 'ు', 'u'),   # Position 3: ు (u)
        (5, 'ు', 'u'),   # Position 5: ు (u)
        (8, 'ా', 'aa')   # Position 8: ా (aa)
    ]
}
```

## 🚀 Usage

### Basic Usage

```python
from enhanced_telugu_ocr import EnhancedTeluguOCR
from PIL import Image

# Initialize OCR
ocr = EnhancedTeluguOCR()

# Load image
image = Image.open('telugu_page.jpg')

# Extract text with automatic engine selection
result = ocr.extract_text(image)

print(f"Text: {result['text']}")
print(f"Engine: {result['engine']}")
print(f"Confidence: {result['confidence']:.2%}")
print(f"Complexity: {result['complexity']:.1f}")

# Telugu analysis
if result['telugu_analysis']:
    analysis = result['telugu_analysis']
    print(f"Telugu chars: {analysis['telugu_chars']}")
    print(f"Vatulu: {analysis['vatulu_count']}")
    print(f"Guninthalu: {analysis['guninthalu_count']}")
```

### Force Specific Engine

```python
# Force EasyOCR for complex page
result = ocr.extract_text(image, force_engine='easyocr')

# Force Tesseract for simple page
result = ocr.extract_text(image, force_engine='tesseract')
```

### Telugu Text Analysis Only

```python
from telugu_text_processor import TeluguTextProcessor

processor = TeluguTextProcessor()

# Analyze Telugu text
text = "తెలుగు భాష"
stats = processor.get_statistics(text)

print(f"Total characters: {stats['total_characters']}")
print(f"Vatulu: {stats['vatulu_count']}")
print(f"Guninthalu: {stats['guninthalu_count']}")

# Extract specific features
vatulu = processor.extract_vatulu(text)
guninthalu = processor.extract_guninthalu(text)
complex_chars = processor.identify_complex_characters(text)
```

## 📝 Telugu Character Reference

### Guninthalu (Vowel Modifiers)
| Character | Unicode | Transliteration | Example |
|-----------|---------|-----------------|---------|
| ా | U+0C3E | aa | కా (kaa) |
| ి | U+0C3F | i | కి (ki) |
| ీ | U+0C40 | ii | కీ (kii) |
| ు | U+0C41 | u | కు (ku) |
| ూ | U+0C42 | uu | కూ (kuu) |
| ృ | U+0C43 | r | కృ (kr) |
| ె | U+0C46 | e | కె (ke) |
| ే | U+0C47 | ee | కే (kee) |
| ై | U+0C48 | ai | కై (kai) |
| ొ | U+0C4A | o | కొ (ko) |
| ో | U+0C4B | oo | కో (koo) |
| ౌ | U+0C4C | au | కౌ (kau) |

### Vatulu (Subscript Consonants)
| Character | Unicode | Name | Example |
|-----------|---------|------|---------|
| ్ | U+0C4D | Virama/Halant | క్ష (ksha) |

## 🔧 Configuration

### Enable/Disable Features

Edit `src/config.py`:

```python
# Telugu Text Processing
ENABLE_TELUGU_PROCESSING = True   # Enable Telugu analysis
ANALYZE_VATULU = True              # Detect vatulu
ANALYZE_GUNINTHALU = True          # Detect guninthalu

# Adaptive OCR
ENABLE_ADAPTIVE_OCR = True         # Enable automatic engine selection
ADAPTIVE_SIMPLE_THRESHOLD = 45     # Tesseract threshold
ADAPTIVE_COMPLEX_THRESHOLD = 60    # EasyOCR threshold

# OCR Engine
OCR_ENGINE = 'easyocr'             # Primary engine
HYBRID_PRIMARY = 'easyocr'         # Hybrid mode primary
HYBRID_FALLBACK = 'tesseract'      # Hybrid mode fallback
```

### EasyOCR Settings

```python
EASYOCR_USE_GPU = False            # Use CPU (stable)
EASYOCR_LANG = 'te+en'             # Telugu + English
EASYOCR_MIN_SIZE = 8               # Minimum text size
EASYOCR_TEXT_THRESHOLD = 0.4       # Detection threshold
EASYOCR_MAG_RATIO = 2.0            # Magnification for accuracy
```

## 🎯 Benefits

### 1. **Improved Accuracy**
- Vatulu and Guninthalu detection ensures correct character recognition
- Complex character analysis prevents misinterpretation
- Dual OCR engines provide redundancy and accuracy

### 2. **Intelligent Processing**
- Automatic engine selection based on page complexity
- Fast processing for simple pages (Tesseract)
- Accurate processing for complex pages (EasyOCR)

### 3. **Better Telugu Support**
- Comprehensive character analysis
- Proper handling of combining characters
- Unicode normalization for consistency

### 4. **Detailed Analytics**
- Character-level statistics
- Confidence scores
- Complexity metrics
- Feature detection (tables, lines, etc.)

## 📦 Dependencies

Updated `requirements.txt`:
```
Flask==3.0.0
PyMuPDF==1.23.8
Pillow==10.1.0
pytesseract==0.3.10
easyocr==1.7.2
opencv-python==4.8.1.78
numpy==1.26.2
pandas==2.1.3
ebooklib==0.18
# ... other dependencies
```

## 🚀 Getting Started

### Windows
```batch
scripts\start.bat
```

### Linux/WSL
```bash
bash scripts/start.sh
```

Both scripts will:
1. Create virtual environment (if needed)
2. Install dependencies (including EasyOCR, pytesseract)
3. Display Telugu features information
4. Start the enhanced OCR server

## 🧪 Testing

### Test Telugu Text Processor
```bash
python src/telugu_text_processor.py
```

### Test Enhanced OCR
```bash
python src/enhanced_telugu_ocr.py
```

### Expected Output
```
Testing Telugu Text Processor...
============================================================

Text Analysis:
  Total characters: 10
  Telugu characters: 9
  Vatulu count: 0
  Guninthalu count: 4

Guninthalu found:
  Position 1: ె (e)
  Position 3: ు (u)
  Position 5: ు (u)
  Position 8: ా (aa)

✅ Telugu Text Processor test complete!
```

## 📚 Integration with TeluguOCR-develop

This implementation integrates concepts from the TeluguOCR-develop project:

- **Character Encoding**: Supports 541 vatulu/guninthalu combinations
- **Model Architecture**: Character + V_G dual model approach
- **Unicode Mapping**: Complete Telugu Unicode range (U+0C00 - U+0C7F)

### Optional: Use TeluguOCR Encoding Files

If you have the TeluguOCR encoding files:

```python
from enhanced_telugu_ocr import EnhancedTeluguOCR

# Point to encoding directory
encoding_dir = "path/to/TeluguOCR-develop/old_models/Encoding"
ocr = EnhancedTeluguOCR(encoding_dir=encoding_dir)
```

## 🔍 Troubleshooting

### Issue: EasyOCR not available
**Solution**: Install EasyOCR
```bash
pip install easyocr
```

### Issue: Telugu characters not displaying
**Solution**: Windows console encoding issue - output is still correct in files

### Issue: Low confidence scores
**Solution**: 
- Check image quality (use 300 DPI)
- Verify page complexity threshold settings
- Try forcing EasyOCR for complex pages

## 📊 Performance

| Page Type | Engine | Speed | Accuracy | Telugu Features |
|-----------|--------|-------|----------|-----------------|
| Simple text | Tesseract | ⚡ Fast | ✓ Good | ✓ Full |
| Medium complexity | EasyOCR | ⚡ Medium | ✓✓ Better | ✓ Full |
| Complex/Tables | EasyOCR | ⚡ Medium | ✓✓✓ Best | ✓ Full |

## 🎉 Summary

The enhanced Telugu OCR system provides:

✅ **Intelligent OCR**: Automatic selection between Tesseract and EasyOCR  
✅ **Vatulu Detection**: Identifies subscript consonants  
✅ **Guninthalu Detection**: Identifies vowel modifiers  
✅ **Complex Character Analysis**: Breaks down compound characters  
✅ **Adaptive Processing**: Complexity-based engine selection  
✅ **Comprehensive Statistics**: Detailed text analysis  
✅ **High Accuracy**: Dual-engine approach with Telugu-specific enhancements  

---

**Version**: 2.1 (Enhanced Telugu OCR)  
**Date**: 2026-02-08  
**Status**: Production Ready ✅
