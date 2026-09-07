import sys
import os
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

# Add src to path
sys.path.append('src')

# Import base configuration
import config_v5 as config_module
sys.modules['config'] = config_module

from page_complexity_analyzer import PageComplexityAnalyzer

class FullyAdaptiveComplexityAnalyzer(PageComplexityAnalyzer):
    def find_column_gutter(self, binary: np.ndarray,
                           text_region: tuple = None,
                           min_gutter_width: int = 12) -> int:
        h, w = binary.shape
        
        # Restrict to text region if available
        if text_region:
            y_start, y_end = text_region
            region = binary[y_start:y_end, :]
        else:
            region = binary
        
        # Vertical projection: sum of black pixels per column
        v_proj = np.sum(region, axis=0)
        
        # Normalize to 0-1 range
        v_max = np.max(v_proj)
        if v_max == 0:
            return None
        v_norm = v_proj / v_max
        
        # Search in center 40% of page (30% to 70%)
        search_start = int(w * 0.30)
        search_end = int(w * 0.70)
        
        # Find all intervals where v_norm is low
        gutter_threshold = 0.15  # slightly higher threshold for adaptive noise
        is_low = v_norm[search_start:search_end] < gutter_threshold
        
        # Find consecutive low runs and evaluate them
        runs = []
        current_start = -1
        current_length = 0
        
        for i, low in enumerate(is_low):
            if low:
                if current_start == -1:
                    current_start = i
                current_length += 1
            else:
                if current_length > 0:
                    runs.append((search_start + current_start, current_length))
                current_start = -1
                current_length = 0
        if current_length > 0:
            runs.append((search_start + current_start, current_length))
            
        # Filter and rank candidate gutters
        best_run_center = None
        best_run_len = 0
        best_run_balance = 1.0 # 0.0 is perfectly balanced (50-50)
        
        # Calculate dynamic minimum width (more sensible: 1.5% of page width, or min_gutter_width)
        dynamic_min_width = max(min_gutter_width, int(w * 0.015))
        
        total_sum = np.sum(v_proj)
        
        print(f"Candidates with dynamic_min_width={dynamic_min_width}:")
        for start_idx, length in runs:
            end_idx = start_idx + length
            
            # Check text presence on both sides
            left_sum = np.sum(v_proj[0 : start_idx])
            right_sum = np.sum(v_proj[end_idx : w])
            
            left_pct = left_sum / total_sum if total_sum > 0 else 0
            right_pct = right_sum / total_sum if total_sum > 0 else 0
            
            # Print details of each candidate
            center = start_idx + length // 2
            print(f"  Gutter at x={center} (width {length}px): left_text={left_pct*100:.1f}%, right_text={right_pct*100:.1f}%")
            
            # Require at least 15% text on BOTH sides to prevent detecting margins as gutters
            if left_pct >= 0.15 and right_pct >= 0.15:
                if length >= dynamic_min_width:
                    balance = abs(left_pct - right_pct)
                    # We prefer wider runs; if lengths are similar, we prefer more balanced runs
                    # Rank score: weight length positive, balance negative
                    if length > best_run_len or (abs(length - best_run_len) < 5 and balance < best_run_balance):
                        best_run_len = length
                        best_run_center = center
                        best_run_balance = balance
                        
        if best_run_center:
            print(f"Selected Column gutter at x={best_run_center} (width={best_run_len}px)")
        else:
            print("No valid Column gutter found")
            
        return best_run_center

    def analyze(self, image: Image.Image) -> dict:
        w, h = image.size
        img_gray = np.array(image.convert('L'))
        
        # 1. Layout figures
        from layout_analyzer import LayoutAnalyzer
        layout_analyzer = LayoutAnalyzer()
        crops, coords = layout_analyzer.extract_figures(image)
        
        # 2. Adaptive binary masked
        binary = cv2.adaptiveThreshold(
            img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 10
        )
        for (x1, y1, x2, y2) in coords:
            binary[y1:y2, x1:x2] = 0
            
        # 3. Find text region
        text_region = self.find_text_region(img_gray, binary, coords)
        
        # 4. Find column gutter
        column_gutter_x = self.find_column_gutter(binary, text_region)
        num_columns = 2 if column_gutter_x is not None else 1
        
        return {
            'text_region': text_region,
            'column_gutter_x': column_gutter_x,
            'num_columns': num_columns,
            'estimated_lines': self.estimate_line_count(binary, text_region)
        }

img_path = Path('images/ApprovaSuodham.png')
if img_path.exists():
    image = Image.open(img_path)
    analyzer = FullyAdaptiveComplexityAnalyzer()
    res = analyzer.analyze(image)
    print("\nFinal Results:")
    print(f"  text_region: {res['text_region']}")
    print(f"  column_gutter_x: {res['column_gutter_x']}")
    print(f"  num_columns: {res['num_columns']}")
    print(f"  estimated_lines: {res['estimated_lines']}")
else:
    print("Image not found")
