"""
Test script to verify decorative border detection with detailed debugging
"""
from PIL import Image
import sys
from pathlib import Path
import numpy as np
import cv2

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from page_complexity_analyzer import PageComplexityAnalyzer

def analyze_border_manually(image_path):
    """Manually analyze the border to understand the values"""
    
    print(f"\n{'='*60}")
    print(f"Manual Border Analysis")
    print(f"{'='*60}\n")
    
    # Load and convert image
    image = Image.open(image_path)
    img_gray = np.array(image.convert('L'))
    h, w = img_gray.shape
    
    print(f"Image size: {w}x{h}")
    
    # Binarize
    _, binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    print(f"\nFound {len(contours)} contours")
    print(f"\nAnalyzing large regions (>15% of page):\n")
    
    for i, cnt in enumerate(contours):
        x, y, bw, bh = cv2.boundingRect(cnt)
        
        # Only check large regions
        if bw > (w * 0.15) and bh > (h * 0.15):
            # Filter out whole-page box
            if bw < (w * 0.98) or bh < (h * 0.98):
                print(f"Region {i}: ({x}, {y}) {bw}x{bh}")
                print(f"  Size: {bw}x{bh} ({bw*bh/(w*h)*100:.1f}% of page)")
                
                # Calculate fill ratio
                contour_area = cv2.contourArea(cnt)
                bbox_area = bw * bh
                fill_ratio = contour_area / bbox_area if bbox_area > 0 else 0
                
                # Calculate perimeter ratio
                perimeter = cv2.arcLength(cnt, True)
                expected_rect_perimeter = 2 * (bw + bh)
                perimeter_ratio = perimeter / expected_rect_perimeter if expected_rect_perimeter > 0 else 0
                
                print(f"  Contour area: {contour_area:.0f}")
                print(f"  Bounding box area: {bbox_area}")
                print(f"  Fill ratio: {fill_ratio:.3f}")
                print(f"  Perimeter: {perimeter:.1f}")
                print(f"  Expected rect perimeter: {expected_rect_perimeter}")
                print(f"  Perimeter ratio: {perimeter_ratio:.3f}")
                
                # Check against thresholds
                is_hollow_frame = (fill_ratio < 0.20)
                is_perfect_rectangle = (0.95 < perimeter_ratio < 1.05)
                is_decorative = is_hollow_frame or (fill_ratio < 0.30 and is_perfect_rectangle)
                
                print(f"  Is hollow frame: {is_hollow_frame}")
                print(f"  Is perfect rectangle: {is_perfect_rectangle}")
                print(f"  Is decorative border: {is_decorative}")
                print()

def test_border_detection(image_path):
    """Test if decorative borders are properly detected and filtered"""
    
    print(f"\n{'='*60}")
    print(f"Testing Border Detection with Analyzer")
    print(f"{'='*60}\n")
    
    # Load image
    print(f"Loading image: {image_path}")
    image = Image.open(image_path)
    print(f"Image size: {image.size}")
    
    # Analyze
    analyzer = PageComplexityAnalyzer()
    result = analyzer.analyze(image)
    
    # Display results
    print(f"\n{'='*60}")
    print(f"Analysis Results:")
    print(f"{'='*60}")
    print(f"Complexity Score: {result['complexity_score']:.1f}")
    print(f"Recommended Engine: {result['recommended_engine']}")
    print(f"Reasoning: {result['reasoning']}")
    print(f"Has Table: {result['has_table']}")
    print(f"Has Boxes: {result['has_boxes']}")
    print(f"Has Illustrations: {result['has_illustrations']}")
    print(f"Number of Image Regions: {len(result['image_regions'])}")
    
    if result['image_regions']:
        print(f"\nImage Regions Detected:")
        for i, (x, y, w, h) in enumerate(result['image_regions']):
            area_pct = (w * h) / (image.size[0] * image.size[1]) * 100
            print(f"  Region {i+1}: ({x}, {y}) {w}x{h} ({area_pct:.1f}% of page)")
    else:
        print(f"\nNo image regions detected (decorative borders filtered out)")
    
    print(f"\n{'='*60}\n")
    
    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Use the uploaded image
        image_path = r"C:/Users/navee/.gemini/antigravity/brain/bfd81912-2a4b-4eb6-aa55-14ae24aaf66e/uploaded_media_1769417866090.png"
    
    # First do manual analysis
    analyze_border_manually(image_path)
    
    # Then test with analyzer
    result = test_border_detection(image_path)
    
    # Verdict
    print("VERDICT:")
    if result['has_illustrations']:
        print("FAIL: Page will be treated as having illustrations (will save as image)")
    else:
        print("PASS: Decorative border correctly filtered out (will use OCR text only)")
