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

# Let's test on pdf_page.png and chakra.png and others in the workspace
images_to_test = ['images/pdf_page.png', 'images/chakra.png', 'images/book name.png']

pca = PageComplexityAnalyzer()

for img_name in images_to_test:
    img_path = Path(img_name)
    if img_path.exists():
        image = Image.open(img_path)
        res = pca.analyze(image)
        print(f"\nImage: {img_name} (size: {image.size})")
        print(f"  num_columns: {res.get('num_columns')}")
        print(f"  column_gutter_x: {res.get('column_gutter_x')}")
        print(f"  is_multicolumn: {res.get('is_multicolumn')}")
    else:
        print(f"Image {img_name} not found")
