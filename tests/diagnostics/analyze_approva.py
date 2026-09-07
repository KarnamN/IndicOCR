import sys
import os
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.append('src')

from layout_analyzer import LayoutAnalyzer
from page_complexity_analyzer import PageComplexityAnalyzer

img_path = Path('images/ApprovaSuodham.png')
print(f"Checking if {img_path.absolute()} exists: {img_path.exists()}")

if img_path.exists():
    image = Image.open(img_path)
    print(f"Image format: {image.format}, size: {image.size}, mode: {image.mode}")
    
    # 1. Run Layout Analyzer
    print("\n--- Running LayoutAnalyzer ---")
    analyzer = LayoutAnalyzer()
    layout = analyzer.analyze(image)
    print("Detected Layout components:")
    for key, boxes in layout.items():
        print(f"  {key}: {len(boxes)} boxes")
        for i, box in enumerate(boxes):
            print(f"    Box {i+1}: {box}")
            
    # 2. Extract Figures
    print("\n--- Extracting Figures ---")
    crops, coords = analyzer.extract_figures(image)
    print(f"Extracted {len(crops)} figures:")
    for i, coord in enumerate(coords):
        print(f"  Figure {i+1} coordinates: {coord}")

    # 3. Run PageComplexityAnalyzer
    print("\n--- Running PageComplexityAnalyzer ---")
    complexity_analyzer = PageComplexityAnalyzer()
    analysis = complexity_analyzer.analyze(image)
    print("Page Complexity Analysis:")
    for k, v in list(analysis.items())[:20]: # Print first 20 items to see details
        if k != 'image_regions' and k != 'text_region' and k != 'center_area':
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: [length/shape: {len(v) if v is not None else None}]")
    
    # Print the rest of key metrics
    print(f"  is_multicolumn: {analysis.get('is_multicolumn')}")
    print(f"  num_columns: {analysis.get('num_columns')}")
    print(f"  column_gutter_x: {analysis.get('column_gutter_x')}")
    print(f"  recommended_engine: {analysis.get('recommended_engine')}")
    print(f"  complexity_score: {analysis.get('complexity_score')}")
else:
    print("Image file not found")
