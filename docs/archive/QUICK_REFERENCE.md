# 🚀 Quick Reference Card - Enhanced Telugu OCR

## ⚡ Quick Start

### Windows
```batch
scripts\start.bat
```

### Linux/WSL
```bash
bash scripts/start.sh
```

Server: **http://localhost:5001**

---

## 📖 Key Documentation

| File | Purpose |
|------|---------|
| **PROJECT_COMPLETE.md** | 🎉 Complete summary & testing results |
| **TELUGU_OCR_FEATURES.md** | 📚 Comprehensive feature guide |
| **INTEGRATION_SUMMARY.md** | 📋 What was added/changed |
| **ARCHITECTURE.md** | 🏗️ System architecture diagrams |

---

## 🎯 Main Features

### ✅ Vatulu Detection (వత్తులు)
Detects subscript consonants in Telugu text
```python
processor.extract_vatulu("క్ష")
# Returns: [(1, '్', 'క్ష')]
```

### ✅ Guninthalu Detection (గుణింతాలు)
Detects vowel modifiers in Telugu text
```python
processor.extract_guninthalu("తెలుగు")
# Returns: [(1, 'ె', 'e'), (3, 'ు', 'u')]
```

### ✅ Adaptive OCR Selection
Automatically chooses best OCR engine
```python
result = ocr.extract_text(image)
# Simple (< 45) → Tesseract (fast)
# Complex (> 60) → EasyOCR (accurate)
```

---

## 💻 Code Examples

### Basic Usage
```python
from enhanced_telugu_ocr import EnhancedTeluguOCR
from PIL import Image

ocr = EnhancedTeluguOCR()
image = Image.open('document.jpg')
result = ocr.extract_text(image)

print(result['text'])           # Extracted text
print(result['engine'])         # OCR engine used
print(result['confidence'])     # Confidence score
print(result['complexity'])     # Page complexity
```

### Telugu Analysis
```python
if result['telugu_analysis']:
    analysis = result['telugu_analysis']
    print(f"Vatulu: {analysis['vatulu_count']}")
    print(f"Guninthalu: {analysis['guninthalu_count']}")
    print(f"Complex chars: {analysis['complex_chars']}")
```

### Force Specific Engine
```python
# Force EasyOCR
result = ocr.extract_text(image, force_engine='easyocr')

# Force Tesseract
result = ocr.extract_text(image, force_engine='tesseract')
```

---

## 🔧 Configuration

Edit `src/config.py`:

```python
# OCR Engine
OCR_ENGINE = 'easyocr'              # Primary engine

# Telugu Processing
ENABLE_TELUGU_PROCESSING = True     # Enable analysis
ANALYZE_VATULU = True               # Detect vatulu
ANALYZE_GUNINTHALU = True           # Detect guninthalu

# Adaptive OCR
ENABLE_ADAPTIVE_OCR = True          # Auto selection
ADAPTIVE_SIMPLE_THRESHOLD = 45      # Tesseract threshold
ADAPTIVE_COMPLEX_THRESHOLD = 60     # EasyOCR threshold

# EasyOCR Settings
EASYOCR_USE_GPU = False             # CPU mode
EASYOCR_LANG = 'te+en'              # Telugu + English
```

---

## 📊 Output Format

```json
{
  "text": "తెలుగు భాష",
  "original_text": "...",
  "engine": "easyocr",
  "confidence": 0.92,
  "complexity": 35.4,
  "char_count": 10,
  "telugu_analysis": {
    "telugu_chars": 9,
    "vatulu_count": 0,
    "guninthalu_count": 4,
    "complex_chars": 4,
    "has_vatulu": false,
    "has_guninthalu": true,
    "vatulu_percentage": "0.0%",
    "guninthalu_percentage": "44.4%"
  },
  "guninthalu_details": [
    [1, "ె", "e"],
    [3, "ు", "u"],
    [5, "ు", "u"],
    [8, "ా", "aa"]
  ]
}
```

---

## 🧪 Testing

```bash
# Test Telugu processor
python src/telugu_text_processor.py

# Test enhanced OCR
python src/enhanced_telugu_ocr.py
```

---

## 📝 Telugu Characters

### Guninthalu (Vowel Modifiers)
| Char | Trans | Char | Trans | Char | Trans |
|------|-------|------|-------|------|-------|
| ా | aa | ి | i | ీ | ii |
| ు | u | ూ | uu | ృ | r |
| ె | e | ే | ee | ై | ai |
| ొ | o | ో | oo | ౌ | au |

### Vatulu
| Char | Name | Example |
|------|------|---------|
| ్ | Virama | క్ష (ksha) |

---

## 🎯 OCR Engine Selection

```
Page Complexity Analysis
         ↓
    ┌────┴────┐
    │ < 45    │ → Tesseract (Fast)
    │ 45-60   │ → EasyOCR (Preferred)
    │ > 60    │ → EasyOCR (Required)
    └─────────┘
```

---

## 📦 New Files

### Core Modules
- `src/telugu_text_processor.py` - Telugu analysis
- `src/enhanced_telugu_ocr.py` - Intelligent OCR

### Documentation
- `PROJECT_COMPLETE.md` - Complete summary
- `TELUGU_OCR_FEATURES.md` - Feature guide
- `INTEGRATION_SUMMARY.md` - Integration details
- `ARCHITECTURE.md` - System architecture

---

## ✅ Status

| Component | Status |
|-----------|--------|
| Telugu Processor | ✅ Working |
| Enhanced OCR | ✅ Working |
| Tesseract | ✅ Available |
| EasyOCR | ✅ Available |
| Adaptive Selection | ✅ Enabled |
| Documentation | ✅ Complete |
| Testing | ✅ Passed |

---

## 🆘 Troubleshooting

### Issue: Module not found
```bash
pip install -r requirements.txt
```

### Issue: EasyOCR not available
```bash
pip install easyocr
```

### Issue: Tesseract not found
**Windows**: Install from https://github.com/UB-Mannheim/tesseract/wiki  
**Linux**: `sudo apt-get install tesseract-ocr tesseract-ocr-tel`

---

## 📞 Support

1. Read `PROJECT_COMPLETE.md` for overview
2. Check `TELUGU_OCR_FEATURES.md` for details
3. See `ARCHITECTURE.md` for system design
4. Run tests to verify installation

---

**Version**: 2.1 (Enhanced Telugu OCR)  
**Date**: 2026-02-08  
**Status**: ✅ Production Ready

---

**🎊 Quick Tip**: Start with `PROJECT_COMPLETE.md` for a complete overview!
