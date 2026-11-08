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
    
    img_gray = np.array(image.convert('L'))
    
    # 1. Global Otsu Thresholding
    _, binary_otsu = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    # 2. Adaptive Thresholding
    # We use a block size of 15-25 (must be odd) and constant C around 10
    binary_adaptive = cv2.adaptiveThreshold(
        img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 21, 10
    )
    
    # Let's count white pixels in both
    total = binary_otsu.size
    white_otsu = np.sum(binary_otsu == 255)
    white_adaptive = np.sum(binary_adaptive == 255)
    
    print(f"Otsu Binary: {white_otsu} white pixels ({white_otsu/total*100:.1f}%)")
    print(f"Adaptive Binary: {white_adaptive} white pixels ({white_adaptive/total*100:.1f}%)")
    
    # Save both images to see the difference
    cv2.imwrite('scratch/binary_otsu.png', binary_otsu)
    cv2.imwrite('scratch/binary_adaptive.png', binary_adaptive)
    print("Saved outputs to scratch/binary_otsu.png and scratch/binary_adaptive.png")
    
    # Check vertical projection profile for adaptive thresholding
    v_proj = np.sum(binary_adaptive, axis=0) / 255
    print("\nAdaptive Thresholding Vertical projection (50px bands):")
    for i in range(0, w, 50):
        end = min(i + 50, w)
        avg_val = np.mean(v_proj[i:end])
        print(f"  Col {i:4d} to {end:4d}: {avg_val:.1f} rows")
        
    # Run column gutter detection using adaptive binary
    # We need text_region from complexity analyzer
    from layout_analyzer import LayoutAnalyzer
    layout_analyzer = LayoutAnalyzer()
    crops, coords, _ = layout_analyzer.extract_figures(image)
    
    # Mask figures in adaptive binary
    binary_adaptive_masked = binary_adaptive.copy()
    for (x1, y1, x2, y2) in coords:
        binary_adaptive_masked[y1:y2, x1:x2] = 0
        
    from page_complexity_analyzer import PageComplexityAnalyzer
    pca = PageComplexityAnalyzer()
    text_region = pca.find_text_region(img_gray, binary_adaptive_masked, coords)
    
    if text_region:
        y_start, y_end = text_region
        region = binary_adaptive_masked[y_start:y_end, :]
    else:
        region = binary_adaptive_masked
        
    v_proj_region = np.sum(region, axis=0)
    v_max = np.max(v_proj_region)
    v_norm = v_proj_region / v_max if v_max > 0 else v_proj_region
    
    # Find low density intervals in search region
    search_start = int(w * 0.30)
    search_end = int(w * 0.70)
    low_intervals = []
    current_start = -1
    for x in range(search_start, search_end):
        val = v_norm[x]
        if val < 0.15: # slightly higher threshold for adaptive noise
            if current_start == -1:
                current_start = x
        else:
            if current_start != -1:
                low_intervals.append((current_start, x - 1, x - current_start))
                current_start = -1
    if current_start != -1:
        low_intervals.append((current_start, search_end - 1, search_end - current_start))
        
    print("\nLow density intervals with Adaptive Thresholding (< 0.15):")
    for start, end, length in low_intervals:
        left_sum = np.sum(v_proj_region[0:start])
        right_sum = np.sum(v_proj_region[end+1:w])
        total_sum = np.sum(v_proj_region)
        left_pct = (left_sum / total_sum * 100) if total_sum > 0 else 0
        right_pct = (right_sum / total_sum * 100) if total_sum > 0 else 0
        print(f"  Range: {start}-{end} | Width: {length}px | Left text: {left_pct:.1f}% | Right text: {right_pct:.1f}%")
        
else:
    print("Image not found")
