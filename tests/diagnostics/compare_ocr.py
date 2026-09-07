#!/usr/bin/env python3
"""
Enhanced OCR Comparison Script
Compares: Baseline Tesseract vs Enhanced Tesseract vs EasyOCR

Enhancements tested:
  1. tessdata_best (higher quality LSTM models)
  2. Image deskewing (fix tilted scans)
  3. Image sharpening (crisper text edges)
  4. Adaptive PSM mode (auto vs block vs sparse)
  5. Noise removal (median blur)

Usage:
    python compare_ocr.py <pdf_path> <page_number> [--dpi 300] [--language te+en]
    
Examples:
    python compare_ocr.py /path/to/document.pdf 17
    python compare_ocr.py /path/to/document.pdf 17 --dpi 150
    python compare_ocr.py /path/to/document.pdf 5 10 17 22   # Multiple pages
"""

import sys
import os
import time
import argparse
import gc
import subprocess

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import fitz  # PyMuPDF
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
import cv2
import io


# ═══════════════════════════════════════════════════════
#  IMAGE PREPROCESSING ENHANCEMENTS
# ═══════════════════════════════════════════════════════

def deskew_image(image: Image.Image) -> Image.Image:
    """
    Deskew (straighten) a tilted scan.
    Uses Hough line detection to find the dominant angle and rotate.
    """
    try:
        img_gray = np.array(image.convert('L'))
        
        # Edge detection
        edges = cv2.Canny(img_gray, 50, 150, apertureSize=3)
        
        # Hough line detection
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=100, maxLineGap=10)
        
        if lines is None or len(lines) == 0:
            return image  # No lines found, skip
        
        # Calculate angles of detected lines
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 != 0:  # Avoid division by zero
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                # Only consider near-horizontal lines (within ±15°)
                if abs(angle) < 15:
                    angles.append(angle)
        
        if not angles:
            return image  # No suitable lines
        
        # Median angle (robust to outliers)
        median_angle = np.median(angles)
        
        if abs(median_angle) < 0.3:
            return image  # Already straight enough
        
        # Rotate image to correct skew
        print(f"   📐 Deskewing by {median_angle:.1f}°")
        return image.rotate(-median_angle, resample=Image.Resampling.BICUBIC,
                           expand=False, fillcolor=(255, 255, 255))
    except Exception as e:
        print(f"   ⚠️ Deskew failed: {e}")
        return image


def sharpen_image(image: Image.Image) -> Image.Image:
    """Apply sharpening to make text edges crisper for OCR."""
    enhancer = ImageEnhance.Sharpness(image)
    return enhancer.enhance(2.0)  # 2x sharpening


def remove_noise(image: Image.Image) -> Image.Image:
    """Remove noise using median blur (good for scanned documents)."""
    img_array = np.array(image)
    # Median blur with small kernel (3x3) - removes salt-and-pepper noise
    denoised = cv2.medianBlur(img_array, 3)
    return Image.fromarray(denoised)


def enhance_contrast(image: Image.Image) -> Image.Image:
    """Enhance contrast for faded text."""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(1.5)


def binarize_adaptive(image: Image.Image) -> Image.Image:
    """Adaptive binarization - better for uneven lighting in scans."""
    gray = np.array(image.convert('L'))
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )
    return Image.fromarray(binary).convert('RGB')


def full_preprocess(image: Image.Image, verbose: bool = True) -> Image.Image:
    """Apply all preprocessing enhancements."""
    if verbose:
        print("   🔄 Preprocessing pipeline:")
    
    # Step 1: Deskew
    image = deskew_image(image)
    if verbose:
        print("      ✓ Deskew")
    
    # Step 2: Noise removal
    image = remove_noise(image)
    if verbose:
        print("      ✓ Noise removal")
    
    # Step 3: Contrast enhancement
    image = enhance_contrast(image)
    if verbose:
        print("      ✓ Contrast enhancement")
    
    # Step 4: Sharpening
    image = sharpen_image(image)
    if verbose:
        print("      ✓ Sharpening")
    
    return image


# ═══════════════════════════════════════════════════════
#  TESSDATA CHECK
# ═══════════════════════════════════════════════════════

def check_tessdata_best() -> dict:
    """Check which tessdata version is installed for Telugu."""
    info = {
        'tel_installed': False,
        'tel_path': None,
        'tessdata_dir': None,
        'is_best': None
    }
    
    try:
        # Find tessdata directory
        result = subprocess.run(['tesseract', '--print-parameters'],
                              capture_output=True, text=True, timeout=5)
        
        # Try common tessdata paths
        common_paths = [
            '/usr/share/tesseract-ocr/4.00/tessdata',
            '/usr/share/tesseract-ocr/5/tessdata',
            '/usr/share/tessdata',
            '/usr/local/share/tessdata',
        ]
        
        # Also check TESSDATA_PREFIX env
        env_path = os.environ.get('TESSDATA_PREFIX')
        if env_path:
            common_paths.insert(0, env_path)
        
        for path in common_paths:
            tel_file = os.path.join(path, 'tel.traineddata')
            if os.path.exists(tel_file):
                info['tel_installed'] = True
                info['tel_path'] = tel_file
                info['tessdata_dir'] = path
                
                # Check file size to guess if it's "best" or "fast"
                # tessdata_best/tel.traineddata ≈ 5-10 MB
                # tessdata_fast/tel.traineddata ≈ 1-3 MB
                size_mb = os.path.getsize(tel_file) / (1024 * 1024)
                info['size_mb'] = round(size_mb, 1)
                
                if size_mb > 4:
                    info['is_best'] = True
                    info['quality'] = 'tessdata_best (high quality LSTM)'
                elif size_mb > 2:
                    info['is_best'] = False
                    info['quality'] = 'tessdata (standard)'
                else:
                    info['is_best'] = False
                    info['quality'] = 'tessdata_fast (speed optimized)'
                break
        
    except Exception as e:
        info['error'] = str(e)
    
    return info


# ═══════════════════════════════════════════════════════
#  OCR ENGINES
# ═══════════════════════════════════════════════════════

def extract_page_image(pdf_path: str, page_num: int, dpi: int = 300) -> Image.Image:
    """Extract a single page from PDF as an image."""
    doc = fitz.open(pdf_path)
    
    if page_num < 1 or page_num > len(doc):
        print(f"❌ Page {page_num} is out of range. PDF has {len(doc)} pages.")
        sys.exit(1)
    
    page = doc[page_num - 1]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()
    
    return img


def run_tesseract(image: Image.Image, language: str, psm: int = 6, label: str = "Tesseract") -> tuple:
    """Run Tesseract OCR with given config."""
    try:
        import pytesseract
        
        # Try to set path from config
        try:
            import config
            if hasattr(config, 'TESSERACT_PATH'):
                pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
        except:
            pass
        
        # Map language codes
        lang_map = {'te': 'tel', 'en': 'eng', 'te+en': 'tel+eng', 'tel+eng': 'tel+eng'}
        tess_lang = lang_map.get(language, language)
        
        tess_config = f'--oem 3 --psm {psm}'
        
        start = time.time()
        text = pytesseract.image_to_string(image, lang=tess_lang, config=tess_config)
        elapsed = time.time() - start
        
        return text.strip(), elapsed
        
    except Exception as e:
        return f"[ERROR: {e}]", 0.0


def run_easyocr(image: Image.Image, language: str) -> tuple:
    """Run EasyOCR."""
    try:
        from easy_ocr_processor import EasyOCRProcessor
        
        start_init = time.time()
        processor = EasyOCRProcessor(language=language, use_gpu=False)
        init_time = time.time() - start_init
        
        start = time.time()
        text = processor.extract_text(image, timeout=120)
        elapsed = time.time() - start
        
        processor.cleanup()
        gc.collect()
        
        return text.strip(), elapsed
        
    except Exception as e:
        return f"[ERROR: {e}]", 0.0


# ═══════════════════════════════════════════════════════
#  COMPARISON & OUTPUT
# ═══════════════════════════════════════════════════════

def run_all_comparisons(image: Image.Image, language: str, page_num: int):
    """Run all OCR variants and display results."""
    
    results = {}
    enhanced_image = full_preprocess(image.copy())
    
    # ── Test 1: Baseline Tesseract (PSM 6) ──
    print(f"\n🔧 [1/6] Tesseract Baseline (PSM 6, original image)...")
    text, t = run_tesseract(image, language, psm=6)
    results['tess_baseline'] = {'text': text, 'time': t, 'label': 'Tesseract Baseline (PSM 6)'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    # ── Test 2: Tesseract PSM 3 (auto layout) ──
    print(f"\n🔧 [2/6] Tesseract Auto-Layout (PSM 3, original image)...")
    text, t = run_tesseract(image, language, psm=3)
    results['tess_psm3'] = {'text': text, 'time': t, 'label': 'Tesseract Auto-Layout (PSM 3)'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    # ── Test 3: Tesseract PSM 4 (single column) ──
    print(f"\n🔧 [3/6] Tesseract Single-Column (PSM 4, original image)...")
    text, t = run_tesseract(image, language, psm=4)
    results['tess_psm4'] = {'text': text, 'time': t, 'label': 'Tesseract Single-Column (PSM 4)'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    # ── Test 4: Tesseract Enhanced (PSM 6 + preprocessing) ──
    print(f"\n🔧 [4/6] Tesseract Enhanced (PSM 6 + deskew/sharpen/denoise)...")
    text, t = run_tesseract(enhanced_image, language, psm=6)
    results['tess_enhanced'] = {'text': text, 'time': t, 'label': 'Tesseract Enhanced (PSM 6 + preprocess)'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    # ── Test 5: Tesseract Enhanced (PSM 4 + preprocessing) ──
    print(f"\n🔧 [5/6] Tesseract Enhanced (PSM 4 + deskew/sharpen/denoise)...")
    text, t = run_tesseract(enhanced_image, language, psm=4)
    results['tess_enhanced_psm4'] = {'text': text, 'time': t, 'label': 'Tesseract Enhanced (PSM 4 + preprocess)'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    # ── Test 6: EasyOCR ──
    print(f"\n🚀 [6/6] EasyOCR (original image)...")
    text, t = run_easyocr(image, language)
    results['easyocr'] = {'text': text, 'time': t, 'label': 'EasyOCR'}
    print(f"   ✓ {len(text)} chars in {t:.2f}s")
    
    return results


def print_summary_table(results: dict):
    """Print a summary comparison table."""
    print(f"\n{'═' * 90}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'═' * 90}")
    print(f"  {'Engine':<45} {'Time':>8} {'Chars':>8} {'Lines':>8}")
    print(f"  {'─' * 45} {'─' * 8} {'─' * 8} {'─' * 8}")
    
    for key, r in results.items():
        text = r['text']
        lines = len(text.splitlines()) if text else 0
        chars = len(text) if text else 0
        marker = " 🏆" if chars == max(len(v['text']) for v in results.values()) else ""
        print(f"  {r['label']:<45} {r['time']:>7.2f}s {chars:>7} {lines:>7}{marker}")
    
    print(f"{'═' * 90}")
    
    # Find best
    most_chars = max(results.items(), key=lambda x: len(x[1]['text']))
    fastest = min(results.items(), key=lambda x: x[1]['time'] if x[1]['time'] > 0 else 999)
    
    print(f"\n  ⚡ Fastest:   {fastest[1]['label']} ({fastest[1]['time']:.2f}s)")
    print(f"  📝 Most text: {most_chars[1]['label']} ({len(most_chars[1]['text'])} chars)")


def save_all_outputs(results: dict, page_num: int, output_dir: str):
    """Save all OCR outputs to files."""
    page_dir = os.path.join(output_dir, f"page{page_num}")
    os.makedirs(page_dir, exist_ok=True)
    
    for key, r in results.items():
        filename = os.path.join(page_dir, f"{key}.txt")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# {r['label']}\n")
            f.write(f"# Time: {r['time']:.2f}s | Chars: {len(r['text'])} | Lines: {len(r['text'].splitlines())}\n")
            f.write(f"# {'=' * 60}\n\n")
            f.write(r['text'])
    
    print(f"\n📁 All outputs saved to: {page_dir}/")
    print(f"   Files: {', '.join(f'{k}.txt' for k in results.keys())}")


def print_full_outputs(results: dict):
    """Print full text output of each engine."""
    for key, r in results.items():
        print(f"\n{'─' * 80}")
        print(f"  {r['label']} ({r['time']:.2f}s, {len(r['text'])} chars)")
        print(f"{'─' * 80}")
        # Show first 1500 chars to keep terminal manageable
        text = r['text']
        if len(text) > 1500:
            print(text[:1500])
            print(f"\n   ... [{len(text) - 1500} more characters - see saved file] ...")
        else:
            print(text if text else "[EMPTY - No text extracted]")


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Compare OCR engines with Telugu enhancement tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python compare_ocr.py document.pdf 17
  python compare_ocr.py document.pdf 5 10 17 22
  python compare_ocr.py document.pdf 17 --dpi 150 --language en
        """
    )
    parser.add_argument('pdf_path', help="Path to the PDF file")
    parser.add_argument('pages', type=int, nargs='+', help="Page number(s) to test (1-indexed)")
    parser.add_argument('--dpi', type=int, default=300, help="DPI for rendering (default: 300)")
    parser.add_argument('--language', default='te+en', help="Language (default: te+en)")
    parser.add_argument('--output-dir', default='ocr_comparison', help="Output directory")
    parser.add_argument('--no-save', action='store_true', help="Don't save output files")
    parser.add_argument('--full-output', action='store_true', help="Print full OCR text in terminal")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"❌ File not found: {args.pdf_path}")
        sys.exit(1)
    
    # Header
    print(f"{'═' * 70}")
    print(f"  🔍 OCR Engine Comparison Tool")
    print(f"{'═' * 70}")
    print(f"  PDF:      {os.path.basename(args.pdf_path)}")
    print(f"  Pages:    {args.pages}")
    print(f"  DPI:      {args.dpi}")
    print(f"  Language: {args.language}")
    
    # Check tessdata quality
    print(f"\n📦 Tessdata Check:")
    tess_info = check_tessdata_best()
    if tess_info['tel_installed']:
        quality_icon = "🟢" if tess_info.get('is_best') else "🟡"
        print(f"   {quality_icon} Telugu model: {tess_info.get('quality', 'unknown')}")
        print(f"      File: {tess_info['tel_path']} ({tess_info.get('size_mb', '?')} MB)")
        if not tess_info.get('is_best'):
            print(f"   💡 TIP: Upgrade to tessdata_best for ~30% better Telugu accuracy:")
            print(f"      sudo wget -O {tess_info['tel_path']} \\")
            print(f"        https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata")
    else:
        print(f"   🔴 Telugu model NOT installed!")
        print(f"      Install: sudo apt install tesseract-ocr-tel")
    
    # Process each page
    for page_num in args.pages:
        print(f"\n{'▓' * 70}")
        print(f"  PAGE {page_num}")
        print(f"{'▓' * 70}")
        
        # Extract page
        image = extract_page_image(args.pdf_path, page_num, args.dpi)
        print(f"📄 Extracted: {image.size[0]}x{image.size[1]} @ {args.dpi} DPI")
        
        # Run all comparisons
        results = run_all_comparisons(image, args.language, page_num)
        
        # Summary table
        print_summary_table(results)
        
        # Full outputs (optional)
        if args.full_output:
            print_full_outputs(results)
        
        # Save outputs
        if not args.no_save:
            save_all_outputs(results, page_num, args.output_dir)
    
    print(f"\n{'═' * 70}")
    print(f"  ✅ Done! Tested {len(args.pages)} page(s)")
    print(f"{'═' * 70}")


if __name__ == '__main__':
    main()
