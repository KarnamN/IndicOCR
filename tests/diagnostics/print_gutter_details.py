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
    _, binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    from layout_analyzer import LayoutAnalyzer
    layout_analyzer = LayoutAnalyzer()
    crops, coords, _ = layout_analyzer.extract_figures(image)
    
    binary_masked = binary.copy()
    for (x1, y1, x2, y2) in coords:
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
    
    print("v_norm around the true gutter (440 to 480):")
    for x in range(440, 480):
        print(f"  x={x}: v_norm={v_norm[x]:.4f} (v_proj={v_proj[x]})")
        
else:
    print("Image not found")
