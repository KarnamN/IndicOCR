import sys
import os
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

# Add src to path
sys.path.append('src')

img_path = Path('images/ApprovaSuodham.png')
if img_path.exists():
    image = Image.open(img_path).convert('RGB')
    w, h = image.size
    
    # Preprocess similar to page_complexity_analyzer
    img_gray = np.array(image.convert('L'))
    _, binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    # Get layout figures to mask them out (as done in the actual converter pipeline)
    from layout_analyzer import LayoutAnalyzer
    layout_analyzer = LayoutAnalyzer()
    crops, coords, _ = layout_analyzer.extract_figures(image)
    
    # Mask out the figures
    binary_masked = binary.copy()
    for (x1, y1, x2, y2) in coords:
        # Since coords are in full image space, we can zero them in binary_masked (meaning white space)
        binary_masked[y1:y2, x1:x2] = 0
        
    from page_complexity_analyzer import PageComplexityAnalyzer
    pca = PageComplexityAnalyzer()
    text_region = pca.find_text_region(img_gray, binary_masked, coords)
    
    if text_region:
        y_start, y_end = text_region
        region = binary_masked[y_start:y_end, :]
    else:
        region = binary_masked
        
    v_proj = np.sum(region, axis=0)
    v_max = np.max(v_proj)
    v_norm = v_proj / v_max if v_max > 0 else v_proj
    
    # Search in center 40%
    search_start = int(w * 0.30)
    search_end = int(w * 0.70)
    
    print(f"Image width: {w}, height: {h}")
    print(f"Text region: {text_region}")
    print(f"Search range: {search_start} to {search_end}")
    
    # Let's print out sections of v_norm that are low density
    low_intervals = []
    current_start = -1
    for x in range(search_start, search_end):
        val = v_norm[x]
        if val < 0.10:
            if current_start == -1:
                current_start = x
        else:
            if current_start != -1:
                low_intervals.append((current_start, x - 1, x - current_start))
                current_start = -1
    if current_start != -1:
        low_intervals.append((current_start, search_end - 1, search_end - current_start))
        
    print("\nLow density intervals in search area (< 0.10):")
    for start, end, length in low_intervals:
        left_sum = np.sum(v_proj[0:start])
        right_sum = np.sum(v_proj[end+1:w])
        total_sum = np.sum(v_proj)
        left_pct = (left_sum / total_sum * 100) if total_sum > 0 else 0
        right_pct = (right_sum / total_sum * 100) if total_sum > 0 else 0
        
        print(f"  Range: {start}-{end} | Width: {length}px | Left text: {left_pct:.1f}% | Right text: {right_pct:.1f}%")
        
else:
    print("Image not found")
