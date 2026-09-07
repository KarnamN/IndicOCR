import sys
import os
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.append('src')

# Inject config
import config_v5 as config_module
sys.modules['config'] = config_module

from page_complexity_analyzer import PageComplexityAnalyzer

img_path = Path('images/ApprovaSuodham_1.png')
print(f"Checking if {img_path.absolute()} exists: {img_path.exists()}")

if img_path.exists():
    image = Image.open(img_path)
    print(f"Image size: {image.size}")
    
    pca = PageComplexityAnalyzer()
    res = pca.analyze(image)
    
    print("\nPage Complexity Analysis for ApprovaSuodham_1.png:")
    for k, v in res.items():
        if k not in ('image_regions', 'text_region', 'center_area'):
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: [length/shape: {len(v) if v is not None else None}]")
            
else:
    print("Image not found")
