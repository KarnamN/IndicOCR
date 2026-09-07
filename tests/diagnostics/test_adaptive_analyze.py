import sys
import os
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

# Add src to path
sys.path.append('src')

# Define modified PageComplexityAnalyzer with adaptive thresholding
from page_complexity_analyzer import PageComplexityAnalyzer

class AdaptiveComplexityAnalyzer(PageComplexityAnalyzer):
    def analyze(self, image: Image.Image) -> dict:
        # We override analyze to use adaptive thresholding for binary creation
        try:
            w, h = image.size
            if h > 1000:
                scale = 1000.0 / h
                new_w = int(w * scale)
                image_ana = image.resize((new_w, 1000), Image.Resampling.NEAREST)
            else:
                image_ana = image
                
            img_gray = np.array(image_ana.convert('L'))
            h, w = img_gray.shape
            
            # 1. Edge Density
            edges = cv2.Canny(img_gray, 50, 150)
            edge_density = np.sum(edges > 0) / (h * w) * 100
            
            # 2. Layout Analysis (Columns/Blocks) USING ADAPTIVE THRESHOLDING
            binary = cv2.adaptiveThreshold(
                img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 21, 10
            )
            
            # Vertical projection profile to detect columns
            v_proj = np.sum(binary, axis=0)
            center_area = v_proj[int(w*0.3):int(w*0.7)]
            has_center_gutter = np.min(center_area) < (np.max(v_proj) * 0.15) if len(center_area) > 0 else False
            
            # 3. Component count
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
            
            # 4. TOC DETECTION
            is_toc = False
            if getattr(config_module, 'ENABLE_TOC_DETECTION', False):
                is_toc = self._detect_toc_patterns(binary)
            
            page_type = 'toc' if is_toc else 'standard'
            
            # 5. TABLE DETECTION
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (80, 1))
            detect_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            h_lines = np.sum(detect_horizontal > 0)
            
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 80))
            detect_vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            v_lines = np.sum(detect_vertical > 0)
            
            if getattr(config_module, 'ENABLE_TABLE_DETECTION', True):
                has_table = (h_lines > 15000 and v_lines > 15000)
            else:
                has_table = False
            
            # 5. Detect boxes/rectangles
            contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            rect_count = 0
            
            # --- NEW LAYOUT ANALYSIS FOR IMAGES/FIGURES ---
            image_regions = []
            if self.layout_analyzer:
                layout = self.layout_analyzer.analyze(image_ana)
                for box in layout.get('figure', []):
                    x1, y1, x2, y2 = map(int, box['coordinate'])
                    image_regions.append((x1, y1, x2 - x1, y2 - y1))
            
            # Fallback to contours
            if not image_regions:
                for cnt in contours:
                    approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
                    x, y, bw, bh = cv2.boundingRect(cnt)
                    if len(approx) == 4 and bw > 30 and bh > 30: 
                        rect_count += 1
                    if bw > (w * 0.15) and bh > (h * 0.15):
                        if bw < (w * 0.98) or bh < (h * 0.98):
                            contour_area = cv2.contourArea(cnt)
                            bbox_area = bw * bh
                            fill_ratio = contour_area / bbox_area if bbox_area > 0 else 0
                            perimeter = cv2.arcLength(cnt, True)
                            expected_rect_perimeter = 2 * (bw + bh)
                            perimeter_ratio = perimeter / expected_rect_perimeter if expected_rect_perimeter > 0 else 0
                            is_hollow_frame = (fill_ratio < 0.20)
                            is_perfect_rectangle = (0.95 < perimeter_ratio < 1.05)
                            is_candidate_border = is_hollow_frame or (fill_ratio < 0.30 and is_perfect_rectangle)
                            is_pen_drawing = False
                            if is_candidate_border:
                                region_crop = img_gray[y:y+bh, x:x+bw]
                                if region_crop.size > 0:
                                    _, crop_bin = cv2.threshold(region_crop, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
                                    n_labels, _, _, _ = cv2.connectedComponentsWithStats(crop_bin)
                                    crop_edges = cv2.Canny(region_crop, 30, 120)
                                    crop_edge_density = np.sum(crop_edges > 0) / region_crop.size
                                    if n_labels > 30 or crop_edge_density > 0.04:
                                        is_pen_drawing = True
                            
                            is_decorative_border = is_candidate_border and not is_pen_drawing
                            if not is_decorative_border:
                                region_binary = binary[y:y+bh, x:x+bw]
                                crop_n_labels, _, crop_stats, _ = cv2.connectedComponentsWithStats(region_binary)
                                text_like_glyphs = 0
                                for idx in range(1, crop_n_labels):
                                    cw = crop_stats[idx, cv2.CC_STAT_WIDTH]
                                    ch = crop_stats[idx, cv2.CC_STAT_HEIGHT]
                                    carea = crop_stats[idx, cv2.CC_STAT_AREA]
                                    if 3 <= cw <= 60 and 3 <= ch <= 60 and 8 <= carea <= 2000:
                                        text_like_glyphs += 1
                                is_likely_text = (text_like_glyphs > 25)
                                if not is_likely_text:
                                    image_regions.append((x, y, bw, bh))
            
            has_many_boxes = rect_count > 20
            has_illustrations = len(image_regions) > 0
            page_pixel_area = h * w
            total_illustration_area = sum(rw * rh for (rx, ry, rw, rh) in image_regions)
            image_dominant_ratio = min(1.0, total_illustration_area / page_pixel_area) if page_pixel_area > 0 else 0.0
            
            text_region = self.find_text_region(img_gray, binary, image_regions)
            column_gutter_x = None
            num_columns = 1
            
            if has_center_gutter and getattr(config_module, 'ENABLE_COLUMN_OCR', True):
                column_gutter_x = self.find_column_gutter(binary, text_region)
                if column_gutter_x is not None:
                    num_columns = 2
            
            has_mixed_content = has_illustrations and (text_region is not None or not has_center_gutter)
            
            edge_score = min(edge_density * 5, 35)
            component_score = min(num_labels / 120, 15)
            layout_score = 20 if has_center_gutter else 0
            table_score = 30 if has_table else 0
            box_score = 15 if has_many_boxes else 0
            illustration_score = 25 if has_illustrations else 0
            mixed_content_score = 15 if has_mixed_content else 0
            toc_boost = 10 if is_toc else 0
            
            total_complexity = edge_score + component_score + layout_score + table_score + box_score + illustration_score + mixed_content_score + toc_boost
            
            # Engine recommendation
            gemini_threshold = getattr(config_module, 'GEMINI_COMPLEXITY_THRESHOLD', 80)
            gemini_available = getattr(config_module, 'GEMINI_AVAILABLE', False)
            if total_complexity >= gemini_threshold and gemini_available:
                engine = 'gemini'
                reason = f"Very complex page (score {total_complexity:.0f} >= {gemini_threshold})"
                is_very_complex = True
            else:
                engine = 'tesseract'
                reason = "Standard layout"
                is_very_complex = False
                
            return {
                'complexity_score': total_complexity,
                'recommended_engine': engine,
                'page_type': page_type,
                'is_multicolumn': has_center_gutter,
                'has_table': has_table,
                'has_illustrations': has_illustrations,
                'column_gutter_x': column_gutter_x,
                'num_columns': num_columns,
                'estimated_lines': self.estimate_line_count(binary, text_region),
                'reasoning': reason
            }
        except Exception as e:
            return {'error': str(e)}

# Inject config
import config_v5 as config_module
sys.modules['config'] = config_module

img_path = Path('images/ApprovaSuodham.png')
if img_path.exists():
    image = Image.open(img_path)
    
    # 1. Run Original Complexity Analyzer
    print("--- Running Original PageComplexityAnalyzer (Otsu) ---")
    pca_orig = PageComplexityAnalyzer()
    res_orig = pca_orig.analyze(image)
    print(f"  Complexity: {res_orig.get('complexity_score'):.1f}")
    print(f"  Recommended engine: {res_orig.get('recommended_engine')}")
    print(f"  is_multicolumn: {res_orig.get('is_multicolumn')}")
    print(f"  num_columns: {res_orig.get('num_columns')}")
    print(f"  column_gutter_x: {res_orig.get('column_gutter_x')}")
    print(f"  estimated_lines: {res_orig.get('estimated_lines')}")
    
    # 2. Run Adaptive Complexity Analyzer
    print("\n--- Running Modified PageComplexityAnalyzer (Adaptive) ---")
    pca_adapt = AdaptiveComplexityAnalyzer()
    res_adapt = pca_adapt.analyze(image)
    print(f"  Complexity: {res_adapt.get('complexity_score'):.1f}")
    print(f"  Recommended engine: {res_adapt.get('recommended_engine')}")
    print(f"  is_multicolumn: {res_adapt.get('is_multicolumn')}")
    print(f"  num_columns: {res_adapt.get('num_columns')}")
    print(f"  column_gutter_x: {res_adapt.get('column_gutter_x')}")
    print(f"  estimated_lines: {res_adapt.get('estimated_lines')}")
    
else:
    print("Image not found")
