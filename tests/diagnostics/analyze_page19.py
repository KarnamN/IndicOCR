import sys
import joblib
from PIL import Image
from pathlib import Path

# Add src to path
sys.path.append('src')

from page_complexity_analyzer import PageComplexityAnalyzer

img_path = Path('page19.png')
jbl_path = Path('data/temp/శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ__1a55ba2e/page_18_0.jbl')

if img_path.exists() and jbl_path.exists():
    image = Image.open(img_path)
    data = joblib.load(jbl_path)
    cached_text = data.get('text', '')
    
    analyzer = PageComplexityAnalyzer()
    analysis = analyzer.analyze(image)
    
    estimated_lines = analysis.get('estimated_lines', 0)
    actual_lines = PageComplexityAnalyzer.get_text_line_count(cached_text)
    is_junk = PageComplexityAnalyzer.is_junk_text(cached_text)
    
    rescue_thresh = 0.50
    is_missing_text = (estimated_lines > 10 and actual_lines < (estimated_lines * rescue_thresh))
    
    print(f"Estimated Lines: {estimated_lines}")
    print(f"Actual Lines: {actual_lines}")
    print(f"Ratio: {actual_lines/estimated_lines:.2f}")
    print(f"Is Junk: {is_junk}")
    print(f"Is Missing Text: {is_missing_text}")
    print(f"Trigger Rescue? {is_junk or is_missing_text}")
else:
    print("Files not found")
