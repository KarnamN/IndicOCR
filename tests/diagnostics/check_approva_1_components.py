import sys
import os
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.append('src')

# Inject config
import config_v5 as config_module
sys.modules['config'] = config_module

from layout_analyzer import LayoutAnalyzer

img_path = Path('images/ApprovaSuodham_1.png')
if img_path.exists():
    image = Image.open(img_path)
    
    analyzer = LayoutAnalyzer()
    layout = analyzer.analyze(image)
    
    print("Detected Layout components on ApprovaSuodham_1.png:")
    for key, boxes in layout.items():
        print(f"  {key}: {len(boxes)} boxes")
        for i, box in enumerate(boxes):
            print(f"    Box {i+1}: {box}")
            
    crops, coords, _ = analyzer.extract_figures(image)
    print(f"\nExtracted figures count: {len(crops)}")
    for i, c in enumerate(coords):
         print(f"  Figure {i+1}: {c}")
else:
    print("Image not found")
