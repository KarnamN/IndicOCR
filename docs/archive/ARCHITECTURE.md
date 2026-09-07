# Enhanced Telugu OCR Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT IMAGE                              │
│                    (Telugu Document/PDF)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              PAGE COMPLEXITY ANALYZER                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  • Edge Detection (Canny)                                │   │
│  │  • Horizontal Line Detection                             │   │
│  │  • Vertical Line Detection                               │   │
│  │  • Complexity Score Calculation (0-100)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              ADAPTIVE OCR ENGINE SELECTOR                        │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Complexity   │    │ Complexity   │    │ Complexity   │      │
│  │    < 45      │    │   45-60      │    │    > 60      │      │
│  │   (Simple)   │    │  (Medium)    │    │  (Complex)   │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Tesseract   │    │   EasyOCR    │    │   EasyOCR    │      │
│  │   (Fast)     │    │ (Preferred)  │    │  (Required)  │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OCR PROCESSING                                │
│                                                                  │
│  ┌────────────────────┐              ┌────────────────────┐     │
│  │   TESSERACT OCR    │              │    EASYOCR         │     │
│  ├────────────────────┤              ├────────────────────┤     │
│  │ • Fast extraction  │              │ • Line removal     │     │
│  │ • PSM 6 mode       │              │ • Preprocessing    │     │
│  │ • Telugu+English   │              │ • Telugu+English   │     │
│  │ • Confidence data  │              │ • High accuracy    │     │
│  └────────┬───────────┘              └────────┬───────────┘     │
│           │                                   │                 │
│           └───────────────┬───────────────────┘                 │
│                           │                                     │
│                           ▼                                     │
│              ┌────────────────────────┐                         │
│              │   RAW OCR TEXT         │                         │
│              │   + Confidence Score   │                         │
│              └────────────┬───────────┘                         │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              TELUGU TEXT PROCESSOR                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 1: Text Normalization                             │   │
│  │  • Unicode NFC normalization                            │   │
│  │  • Whitespace cleanup                                   │   │
│  │  • Character validation                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 2: Character Analysis                             │   │
│  │  • Identify Telugu characters (U+0C00 - U+0C7F)         │   │
│  │  • Classify: Vowels, Consonants, Modifiers              │   │
│  │  • Extract Unicode codes                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 3: Vatulu Detection (వత్తులు)                     │   │
│  │  • Detect virama/halant (్)                              │   │
│  │  • Identify subscript consonants                        │   │
│  │  • Track position and context                           │   │
│  │  • Count and calculate percentage                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 4: Guninthalu Detection (గుణింతాలు)              │   │
│  │  • Detect 15 vowel modifiers (matras)                   │   │
│  │  • Map to transliteration (aa, i, ii, u, uu, etc.)      │   │
│  │  • Track position in text                               │   │
│  │  • Count and calculate percentage                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 5: Complex Character Analysis                     │   │
│  │  • Identify consonant + vattu combinations              │   │
│  │  • Identify consonant + gunintham combinations          │   │
│  │  • Identify consonant + vattu + gunintham               │   │
│  │  • Provide detailed breakdown                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  STEP 6: Statistics Generation                          │   │
│  │  • Total character count                                │   │
│  │  • Telugu character count                               │   │
│  │  • Vatulu count and percentage                          │   │
│  │  • Guninthalu count and percentage                      │   │
│  │  • Complex character count                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENHANCED OUTPUT                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  {                                                       │   │
│  │    "text": "తెలుగు భాష",                                │   │
│  │    "original_text": "...",                              │   │
│  │    "engine": "easyocr",                                 │   │
│  │    "confidence": 0.92,                                  │   │
│  │    "complexity": 35.4,                                  │   │
│  │    "char_count": 10,                                    │   │
│  │    "telugu_analysis": {                                 │   │
│  │      "telugu_chars": 9,                                 │   │
│  │      "vatulu_count": 0,                                 │   │
│  │      "guninthalu_count": 4,                             │   │
│  │      "complex_chars": 4,                                │   │
│  │      "has_vatulu": false,                               │   │
│  │      "has_guninthalu": true,                            │   │
│  │      "vatulu_percentage": "0.0%",                       │   │
│  │      "guninthalu_percentage": "44.4%"                   │   │
│  │    },                                                   │   │
│  │    "guninthalu_details": [                              │   │
│  │      [1, "ె", "e"],                                     │   │
│  │      [3, "ు", "u"],                                     │   │
│  │      [5, "ు", "u"],                                     │   │
│  │      [8, "ా", "aa"]                                     │   │
│  │    ]                                                    │   │
│  │  }                                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Page Complexity Analyzer
- **Input**: PIL Image
- **Output**: Complexity score (0-100)
- **Algorithm**:
  - Canny edge detection
  - Morphological operations for line detection
  - Weighted scoring: edges (40%) + h_lines (30%) + v_lines (30%)

### 2. Adaptive OCR Selector
- **Input**: Complexity score
- **Output**: Selected engine ('tesseract' or 'easyocr')
- **Logic**:
  ```python
  if complexity < 45:
      return 'tesseract'  # Fast for simple pages
  elif complexity > 60:
      return 'easyocr'    # Accurate for complex pages
  else:
      return 'easyocr' if available else 'tesseract'
  ```

### 3. OCR Processing

#### Tesseract Path
```
Image → Tesseract → image_to_data() → Extract confidence
                 → image_to_string() → Extract text
                 → Return (text, confidence)
```

#### EasyOCR Path
```
Image → Preprocess (line removal) → Convert to array
      → EasyOCR.readtext() → Extract text + confidence
      → Return (text, confidence)
```

### 4. Telugu Text Processor

#### Character Classification
```
Input Character
    ↓
Is Telugu? (U+0C00 - U+0C7F)
    ↓
┌───┴───┬───────┬──────────┬──────────┐
│       │       │          │          │
Vowel  Consonant Vattu  Gunintham  Other
(అ-ఔ)  (క-హ)    (్)     (ా-ౌ)
```

#### Complex Character Detection
```
Scan text character by character
    ↓
Found consonant?
    ↓
Check next character
    ↓
┌───────┴────────┐
│                │
Vattu (్)?      Gunintham (ా-ౌ)?
│                │
└────────┬───────┘
         │
    Build complex character
    {base, vattu, gunintham}
```

## Data Flow Example

### Input
```
Image: "తెలుగు భాష.jpg"
```

### Processing Steps

1. **Complexity Analysis**
   ```
   Edge density: 12.3%
   H-line density: 0.8%
   V-line density: 0.5%
   → Complexity: 35.4 (Simple)
   → Selected: Tesseract
   ```

2. **OCR Extraction**
   ```
   Tesseract → "తెలుగు భాష"
   Confidence: 87.3%
   ```

3. **Telugu Analysis**
   ```
   Character scan:
   త (ta) + ె (e) → తె (complex)
   ల (la) + ు (u) → లు (complex)
   గ (ga) + ు (u) → గు (complex)
   [space]
   భ (bha) + ా (aa) → భా (complex)
   ష (sha)
   
   Statistics:
   - Total chars: 10
   - Telugu chars: 9
   - Vatulu: 0
   - Guninthalu: 4 (ె, ు, ు, ా)
   - Complex chars: 4
   ```

4. **Enhanced Output**
   ```json
   {
     "text": "తెలుగు భాష",
     "engine": "tesseract",
     "confidence": 0.873,
     "complexity": 35.4,
     "telugu_analysis": {
       "guninthalu_count": 4,
       "guninthalu_percentage": "44.4%"
     }
   }
   ```

## Performance Characteristics

| Component | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| Complexity Analysis | O(n*m) | O(n*m) |
| OCR (Tesseract) | O(n*m) | O(k) |
| OCR (EasyOCR) | O(n*m) | O(k) |
| Telugu Analysis | O(n) | O(n) |
| Total | O(n*m) | O(n*m) |

Where:
- n = image width
- m = image height
- k = text length

## Integration Points

### Web Application (app.py)
```python
from enhanced_telugu_ocr import EnhancedTeluguOCR

ocr = EnhancedTeluguOCR()
result = ocr.extract_text(image)
# Use result in EPUB generation
```

### PDF Processing
```python
for page in pdf:
    image = convert_page_to_image(page)
    result = ocr.extract_text(image)
    
    # Use enhanced text
    text = result['text']
    confidence = result['confidence']
    
    # Access Telugu features
    if result['telugu_analysis']:
        vatulu = result['telugu_analysis']['vatulu_count']
        guninthalu = result['telugu_analysis']['guninthalu_count']
```

---

**Architecture Version**: 2.1  
**Last Updated**: 2026-02-08
