"""
Page Complexity Analyzer
Analyzes page images to determine layout complexity and recommend OCR engines.
"""
import numpy as np
import cv2
from PIL import Image
import logging
from typing import Dict, List, Tuple, Any, Optional
import config

logger = logging.getLogger(__name__)

class PageComplexityAnalyzer:
    """Analyzes image content to estimate OCR difficulty and layout complexity."""
    
    def __init__(self):
        self.complex_threshold = getattr(config, 'ADAPTIVE_COMPLEX_THRESHOLD', 70)
        self.simple_threshold = getattr(config, 'ADAPTIVE_SIMPLE_THRESHOLD', 30)
        try:
            from layout_analyzer import LayoutAnalyzer
            self.layout_analyzer = LayoutAnalyzer()
        except ImportError:
            self.layout_analyzer = None

    def find_text_region(self, img_gray: np.ndarray, binary: np.ndarray,
                         image_regions: List[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int]]:
        """
        Find the vertical bounds (y_start, y_end) of the text-only region,
        excluding illustration areas at the top/bottom.
        
        Uses horizontal projection profile: rows with many black pixels = text,
        rows with few black pixels = whitespace or illustration boundary.
        
        Args:
            img_gray: Grayscale numpy array of the page
            binary: Binary (inverted) numpy array
            image_regions: List of (x, y, w, h) illustration bounding boxes
            
        Returns:
            (text_start_y, text_end_y) or None if no clear text region found
        """
        h, w = img_gray.shape
        
        if not image_regions:
            return None  # No illustration to mask — whole page is text
        
        # Find the bottom edge of all illustration regions
        illustration_bottom = 0
        illustration_top = h
        for (ix, iy, iw, ih) in image_regions:
            region_bottom = iy + ih
            region_top = iy
            # Illustration at top of page (starts in top 40%)
            if iy < h * 0.4:
                illustration_bottom = max(illustration_bottom, region_bottom)
            # Illustration at bottom of page (starts in bottom 40%)
            if (iy + ih) > h * 0.6:
                illustration_top = min(illustration_top, region_top)
        
        # Use horizontal projection to refine: find where text actually starts
        # after the illustration
        h_proj = np.sum(binary, axis=1)  # Sum of black pixels per row
        text_threshold = np.max(h_proj) * 0.05  # Rows with >5% of max = text
        
        # Search downward from illustration bottom to find text start
        text_start_y = illustration_bottom
        # Add a small margin (2% of height) to skip any illustration border residue
        search_from = min(illustration_bottom + int(h * 0.02), h - 1)
        
        for y in range(search_from, h):
            if h_proj[y] > text_threshold:
                text_start_y = y
                break
        
        # Search upward from illustration top (if bottom illustration exists)
        text_end_y = h
        if illustration_top < h:
            for y in range(illustration_top, 0, -1):
                if h_proj[y] > text_threshold:
                    text_end_y = y
                    break
        
        # Validate: text region should be at least 20% of the page
        text_height = text_end_y - text_start_y
        if text_height < h * 0.2:
            logger.debug(f"Text region too small ({text_height}px / {h}px), ignoring")
            return None
        
        # DEBUG: fires on every page with an illustration — routine measurement.
        logger.debug(f"  📏 Text region: y={text_start_y} to y={text_end_y} "
                    f"({text_height}px, {text_height/h*100:.0f}% of page)")
        return (text_start_y, text_end_y)

    def estimate_line_count(self, binary: np.ndarray, text_region: Optional[Tuple[int, int]] = None) -> int:
        """
        Estimate the number of text lines on the page using horizontal projection.
        
        Args:
            binary: Binary (inverted) image
            text_region: Optional (y_start, y_end) to restrict search
            
        Returns:
            Estimated number of lines
        """
        if text_region:
            y_start, y_end = text_region
            region = binary[y_start:y_end, :]
        else:
            region = binary
            
        h_proj = np.sum(region, axis=1)
        max_val = np.max(h_proj) if h_proj.size > 0 else 0
        if max_val == 0:
            return 0
            
        # Lines are rows where pixel density > 6% of max.
        # NOTE: Was 10% but that merged adjacent dense Telugu lines.
        # Telugu text lines pack vatulu/guninthalu tightly — a 6% threshold
        # better distinguishes individual line peaks in the projection profile.
        threshold = max_val * 0.06
        is_line_pixel = h_proj > threshold
        
        # Count transitions from False to True (start of a line)
        line_count = 0
        in_line = False
        for val in is_line_pixel:
            if val and not in_line:
                line_count += 1
                in_line = True
            elif not val and in_line:
                in_line = False
                
        return line_count

    @staticmethod
    def get_text_line_count(text: str) -> int:
        """Count actual non-empty lines in a string."""
        if not text:
            return 0
        return len([line for line in text.split('\n') if line.strip()])

    def find_column_gutter(self, binary: np.ndarray,
                           text_region: Optional[Tuple[int, int]] = None,
                           min_gutter_width: int = 12) -> Optional[int]:
        """
        Find the X position of the column gutter in a multicolumn layout.
        
        Looks for a sustained band of whitespace (low pixel density) in the
        center region. More robust than just finding a single minimum.
        
        Args:
            binary: Binary (inverted) numpy array
            text_region: (y_start, y_end) to limit analysis to text area only
            min_gutter_width: Minimum number of consecutive low-density columns
                              to qualify as a real gutter (default 12px)
            
        Returns:
            X position of gutter center, or None if no gutter found
        """
        h, w = binary.shape
        
        # Restrict to text region if available
        if text_region:
            y_start, y_end = text_region
            region = binary[y_start:y_end, :]
        else:
            region = binary
        
        # Vertical projection: sum of black pixels per column
        v_proj = np.sum(region, axis=0)
        
        # Search in center 40% of page (30% to 70%)
        search_start = int(w * 0.30)
        search_end = int(w * 0.70)
        
        # Normalize to 0-1 range using max within search area to avoid margin border inflation!
        v_max = np.max(v_proj[search_start:search_end])
        if v_max == 0:
            return None
        v_norm = v_proj / v_max
        
        # Find all intervals where v_norm is low (below 15% of maximum column density)
        gutter_threshold = 0.15
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
        best_run_score = 0
        
        # Calculate dynamic minimum width (1.2% of page width, or min_gutter_width)
        dynamic_min_width = max(min_gutter_width, int(w * 0.012))
        
        total_sum = np.sum(v_proj)
        if total_sum == 0:
            return None
            
        for start_idx, length in runs:
            end_idx = start_idx + length
            
            # Check text presence on both sides to avoid margin false-positives
            left_sum = np.sum(v_proj[0 : start_idx])
            right_sum = np.sum(v_proj[end_idx : w])
            
            left_pct = left_sum / total_sum
            right_pct = right_sum / total_sum
            
            center = start_idx + length // 2
            
            # Require at least 15% of the total page ink on BOTH sides of the gutter
            if left_pct >= 0.15 and right_pct >= 0.15:
                if length >= dynamic_min_width:
                    # Score candidates based on width and horizontal balance (closer to 50/50 is better)
                    balance_factor = 1.0 - abs(left_pct - right_pct)
                    score = length * balance_factor
                    logger.debug(
                        f"  Candidate gutter at x={center} (width {length}px): "
                        f"left={left_pct*100:.1f}%, right={right_pct*100:.1f}%, score={score:.3f}"
                    )
                    if score > best_run_score:
                        best_run_score = score
                        best_run_center = center
                        
        if best_run_center:
            # DEBUG: fires on every multi-column page — routine measurement.
            logger.debug(f"  📐 Column gutter selected at x={best_run_center} (score={best_run_score:.3f})")
            return best_run_center
            
        logger.debug("No valid Column gutter found meeting width and balance criteria")
        return None

    def _detect_toc_patterns(self, binary: np.ndarray) -> bool:
        """
        Detect Table of Contents (TOC) using horizontal projection.
        Looks for lines with ink on left/right and high-frequency dot transitions in the middle.
        Robust across different DPIs and scan qualities.
        """
        h, w = binary.shape
        
        # Analyze page in small row strips
        toc_like_rows = 0
        # Optimization: Analyze ~100 horizontal strips (increased from 300)
        step = max(15, h // 100) 
        
        for y in range(0, h - step, step):
            row = binary[y:y+step, :]
            row_sum = np.sum(row, axis=0) # pixels in each column
            
            # 1. Check for ink distribution across the row
            # Left area (10-25% of width) - typically index numbers/titles
            left_ink = np.sum(row_sum[int(w*0.05):int(w*0.25)] > 0)
            # Right area (75-95% of width) - typically page numbers
            right_ink = np.sum(row_sum[int(w*0.75):int(w*0.95)] > 0)
            # Middle area (30-70% of width) - typically dot leaders
            middle_row = row_sum[int(w*0.3):int(w*0.7)]
            
            # A TOC line must have content on both ends
            if left_ink > 3 and right_ink > 3:
                # 2. Check for high-frequency transitions in the middle (dots)
                # Count transitions from black to white columns
                is_ink = middle_row > 0
                transitions = np.sum(np.diff(is_ink.astype(int)) != 0)
                
                # TOC dot leaders usually have 10-40+ transitions depending on density
                if transitions >= 8:
                    toc_like_rows += 1
        
        # Threshold: > 25% of analyzed strips look like TOC lines (Raised from 10%)
        # This prevents dense body text from being mis-detected as a TOC
        total_analyzed = h // step
        ratio = toc_like_rows / total_analyzed if total_analyzed > 0 else 0
        
        if ratio > 0.25: 
            # DEBUG: routine measurement detail (still visible via the "standard"
            # vs "toc" page_type in the page_analysis structured event either way).
            logger.debug(f"  📖 TOC detected via horizontal projection: {ratio*100:.1f}% of rows follow pattern")
            return True
            
        # 3. Fast keyword check in top 20% would go here if needed
        # (Keeping it simple for now as the projection is very reliable)
        return False

    def analyze(self, image: Image.Image,
                figure_regions: Optional[List[Tuple[int, int, int, int]]] = None) -> Dict[str, Any]:
        """
        Analyze page image and return complexity score (0-100).
        Enhanced to detect TOCs, tables, grids, and complex layouts.

        Args:
            image: page image to analyze. May already have illustrations painted
                   white (the caller's text-mask) — in that case the internal
                   contour detector cannot see the illustrations, so pass their
                   boxes via ``figure_regions``.
            figure_regions: optional list of (x, y, w, h) illustration boxes in
                   ORIGINAL-page coordinates (e.g. the layout analyzer's
                   figure_coords). Used only to locate the text region so the
                   column gutter is found within the real two-column band rather
                   than across the whole page height.
        """
        try:
            # Optimization: Downscale image for analysis phase (layout/complexity)
            # High-resolution (300+ DPI) is not needed for layout analysis
            # and makes morphology operations extremely slow.
            w, h = image.size
            if h > 1000:
                scale = 1000.0 / h
                new_w = int(w * scale)
                image_ana = image.resize((new_w, 1000), Image.Resampling.NEAREST)
            else:
                scale = 1.0
                image_ana = image
                
            # Convert to grayscale numpy array
            img_gray = np.array(image_ana.convert('L'))
            h, w = img_gray.shape
            
            # 1. Edge Density (Text/Graphics density)
            edges = cv2.Canny(img_gray, 50, 150)
            edge_density = np.sum(edges > 0) / (h * w) * 100
            
            # 2. Layout Analysis (Columns/Blocks) using adaptive thresholding
            # Robust against page color shading and white border padding margins
            binary = cv2.adaptiveThreshold(
                img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 21, 10
            )
            
            # Vertical projection profile to detect columns
            v_proj = np.sum(binary, axis=0)
            center_area = v_proj[int(w*0.3):int(w*0.7)]
            # Stricter fast check: with adaptive thresholding, we look for center density below 15% of local center max
            has_center_gutter = np.min(center_area) < (np.max(center_area) * 0.15) if len(center_area) > 0 else False
            
            # 3. Component count (Connected components)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
            
            # 4. TOC DETECTION (Strictly obey config.ENABLE_TOC_DETECTION)
            is_toc = False
            if getattr(config, 'ENABLE_TOC_DETECTION', False):
                is_toc = self._detect_toc_patterns(binary)
            
            page_type = 'toc' if is_toc else 'standard'
            
            # 5. TABLE DETECTION - Detect horizontal and vertical lines
            # Use longer kernels (80px) to avoid picking up Telugu character strokes
            # Horizontal lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (80, 1))
            detect_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            h_lines = np.sum(detect_horizontal > 0)
            
            # Vertical lines
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 80))
            detect_vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            v_lines = np.sum(detect_vertical > 0)
            
            # Grid/table indicator
            # Strictly obey config.ENABLE_TABLE_DETECTION
            if getattr(config, 'ENABLE_TABLE_DETECTION', True):
                has_table = (h_lines > 15000 and v_lines > 15000)
            else:
                has_table = False
                logger.info("  🚫 Table detection disabled via config")
            
            # num_labels already calculated above at line 295
            pass
            
            # 5. Detect boxes/rectangles (common in charts/tables)
            contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            rect_count = 0
            
            # --- LAYOUT ANALYSIS FOR IMAGES/FIGURES ---
            # If the caller already ran layout analysis on this same page image
            # (pdf_to_epub_converter_optimized_v2.py's layout-first routing step
            # does, via LayoutAnalyzer.extract_figures(), passing the result here
            # as figure_regions), reuse it instead of re-running the ~5-8s,
            # globally-locked PP-DocLayout inference a second time on an
            # identical image for no new information. Only re-run it here when
            # no caller-supplied regions exist (other/standalone call sites).
            image_regions = []
            if figure_regions is not None:
                # figure_regions arrives in ORIGINAL-page coordinates (see
                # docstring); image_regions must be in image_ana's downscaled
                # space to match img_gray/binary below.
                image_regions = [
                    (int(fx * scale), int(fy * scale), int(fw * scale), int(fh * scale))
                    for (fx, fy, fw, fh) in figure_regions
                ]
            elif self.layout_analyzer:
                layout = self.layout_analyzer.analyze(image_ana)
                for box in layout.get('figure', []):
                    # convert [x1, y1, x2, y2] to [x, y, w, h]
                    x1, y1, x2, y2 = map(int, box['coordinate'])
                    image_regions.append((x1, y1, x2 - x1, y2 - y1))
            
            # Fallback to legacy contour heuristic only if LayoutAnalysis didn't find anything
            if not image_regions:
                # RETR_TREE returns nested contours for anti-aliased borders/frames
                # (several near-identical concentric rectangles). Without this guard,
                # each one independently pays the expensive per-candidate analysis
                # below (threshold + connectedComponentsWithStats + Canny), even
                # though they all describe the same physical region.
                processed_boxes = []
                for cnt in contours:
                    approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
                    x, y, bw, bh = cv2.boundingRect(cnt)

                    # Logic for Boxes/Charts
                    if len(approx) == 4 and bw > 30 and bh > 30:
                        rect_count += 1

                    # Logic for Illustrations/Photos (Large non-text blocks)
                    # IMPROVED: Distinguish decorative borders from actual images
                    if bw > (w * 0.15) and bh > (h * 0.15):
                        # Skip near-duplicate nested contours already analyzed
                        if any(abs(x - px) < 20 and abs(y - py) < 20 and
                               abs(bw - pw) < 20 and abs(bh - ph) < 20
                               for (px, py, pw, ph) in processed_boxes):
                            continue
                        processed_boxes.append((x, y, bw, bh))

                        # Filter out the whole-page box
                        if bw < (w * 0.98) or bh < (h * 0.98):
                            # NEW APPROACH: Check if this is a thin rectangular outline (frame)
                            # vs a filled region (actual image)
                        
                            # Method: Compare contour area to bounding box area
                            # - Decorative frames: contour area << bounding box area (hollow)
                            # - Actual images: contour area ≈ bounding box area (filled)
                        
                            contour_area = cv2.contourArea(cnt)
                            bbox_area = bw * bh
                            fill_ratio = contour_area / bbox_area if bbox_area > 0 else 0

                            # Also check if contour is approximately rectangular
                            # (decorative borders are usually perfect rectangles)
                            perimeter = cv2.arcLength(cnt, True)
                            expected_rect_perimeter = 2 * (bw + bh)
                            perimeter_ratio = perimeter / expected_rect_perimeter if expected_rect_perimeter > 0 else 0

                            # ── STEP 1: Candidate decorative-border test ──────────────────────
                            # A true decorative border is hollow (low fill) AND rectangular.
                            is_hollow_frame = (fill_ratio < 0.20)
                            is_perfect_rectangle = (0.95 < perimeter_ratio < 1.05)
                            is_candidate_border = is_hollow_frame or (fill_ratio < 0.30 and is_perfect_rectangle)

                            # ── STEP 2: PENCIL/PEN DRAWING RESCUE ─────────────────────────────
                            # Yantras, geometric diagrams, and sketch illustrations look like
                            # hollow frames to the contour detector (thin lines, low fill_ratio,
                            # roughly rectangular bounding box).  BUT they have MANY internal
                            # connected components (strokes, curves, dots) — far more than a
                            # simple rectangular border which has just 1-2 components.
                            #
                            # If a candidate "border" has high internal complexity (>30 labels
                            # in its crop OR high edge density), it's really a drawing.
                            is_pen_drawing = False
                            if is_candidate_border:
                                region_crop = img_gray[y:y+bh, x:x+bw]
                                if region_crop.size > 0:
                                    # Count connected components inside the bounding box
                                    _, crop_bin = cv2.threshold(
                                        region_crop, 127, 255,
                                        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
                                    )
                                    n_labels, _, _, _ = cv2.connectedComponentsWithStats(crop_bin)
                                    crop_edges = cv2.Canny(region_crop, 30, 120)
                                    crop_edge_density = np.sum(crop_edges > 0) / region_crop.size

                                    # A plain rectangular border has ~1-5 components and very
                                    # low internal edge density.  A drawing has many more.
                                    # Threshold: >30 components OR edge density > 0.04 inside
                                    # the "hollow" region → it's a real drawing, not a border.
                                    if n_labels > 30 or crop_edge_density > 0.04:
                                        is_pen_drawing = True
                                        logger.info(
                                            f"  ✏️ Pen/pencil drawing rescued at ({x},{y},{bw}x{bh}) "
                                            f"- internal_labels={n_labels}, edge_density={crop_edge_density:.3f}, "
                                            f"fill={fill_ratio:.3f}"
                                        )

                            is_decorative_border = is_candidate_border and not is_pen_drawing

                            if not is_decorative_border:
                                # Count text-like glyphs inside the region
                                region_binary = binary[y:y+bh, x:x+bw]
                                crop_n_labels, _, crop_stats, _ = cv2.connectedComponentsWithStats(region_binary)
                                text_like_glyphs = 0
                                for i in range(1, crop_n_labels):
                                    cw = crop_stats[i, cv2.CC_STAT_WIDTH]
                                    ch = crop_stats[i, cv2.CC_STAT_HEIGHT]
                                    carea = crop_stats[i, cv2.CC_STAT_AREA]
                                    # In 1000px height page, characters are usually 3-60px wide/high
                                    if 3 <= cw <= 60 and 3 <= ch <= 60 and 8 <= carea <= 2000:
                                        text_like_glyphs += 1

                                region_crop = img_gray[y:y+bh, x:x+bw]
                                region_edges = cv2.Canny(region_crop, 50, 150)
                                region_edge_density = np.sum(region_edges > 0) / (bw * bh) if (bw * bh) > 0 else 0
                                gray_variance = np.var(region_crop) if region_crop.size > 0 else 0

                                # A region is text if it contains more than 25 text-like glyphs (characters)
                                is_likely_text = (text_like_glyphs > 25)

                                if is_likely_text:
                                    logger.info(
                                        f"  ⊘ Skipping text region at ({x},{y},{bw}x{bh}) "
                                        f"- glyphs={text_like_glyphs}, edges={region_edge_density:.3f}, var={gray_variance:.0f}"
                                    )
                                else:
                                    # Real illustration: photo, painting, or pen/pencil drawing
                                    image_regions.append((x, y, bw, bh))
                                    kind = "pen/pencil drawing" if is_pen_drawing else "illustration/diagram"
                                    logger.info(
                                        f"  🎨 Detected {kind} at ({x},{y},{bw}x{bh}) "
                                        f"- fill={fill_ratio:.3f}, edges={region_edge_density:.3f}, "
                                        f"var={gray_variance:.0f}"
                                    )
                        else:
                            logger.debug(
                                f"Skipping decorative border at ({x},{y}) "
                                f"- fill_ratio={fill_ratio:.3f}, perim_ratio={perimeter_ratio:.3f}"
                            )
            
            has_many_boxes = rect_count > 20
            has_illustrations = len(image_regions) > 0

            # --- IMAGE DOMINANCE RATIO ---
            # Sum of all illustration bounding-box pixel areas divided by page area.
            # Capped at 1.0 (overlapping regions can exceed 100% in theory).
            # Example: two 45%-area paintings → ratio ≈ 0.90 → definitely an image page.
            page_pixel_area = h * w
            total_illustration_area = sum(rw * rh for (rx, ry, rw, rh) in image_regions)
            image_dominant_ratio = min(1.0, total_illustration_area / page_pixel_area) if page_pixel_area > 0 else 0.0
            
            # --- Text region & column gutter detection ---
            # image_regions already holds the caller-supplied figure_regions
            # (scaled above) when present — needed here because when the caller
            # passes a text-masked image (illustrations whited out), the contour
            # detector above finds nothing on its own, so find_text_region would
            # otherwise have no way to exclude the illustration band and would
            # search for the column gutter across the whole page height.
            text_region = self.find_text_region(img_gray, binary, image_regions)
            column_gutter_x = None
            num_columns = 1
            
            if has_center_gutter and getattr(config, 'ENABLE_COLUMN_OCR', True):
                column_gutter_x = self.find_column_gutter(binary, text_region)
                if column_gutter_x is not None:
                    num_columns = 2
                    # DEBUG: fires on every multi-column page — routine measurement.
                    # is_multicolumn is still surfaced at INFO via the page_analysis
                    # structured event / engine routing decision downstream.
                    logger.debug(f"  📰 Detected {num_columns}-column layout")

            # A genuine, sustained vertical gutter means this is a real multi-column
            # layout — NOT a single-column table of contents. Dot-leader TOCs
            # ("Title .......... 42") have no clean empty gutter (the dots fill the
            # centre), so find_column_gutter would not have fired. The TOC heuristic,
            # however, frequently false-positives on dense two-column body text
            # (both columns put ink left+right with many centre transitions). Left
            # uncorrected, that misclassification forces PSM 6 and DISABLES column
            # splitting downstream, so the two columns get read straight across and
            # merged. Trust the gutter and drop the TOC label here.
            if column_gutter_x is not None and is_toc:
                logger.info("  ↩️  Column gutter present — overriding TOC misclassification "
                            "(treating as multi-column body text, enabling column split).")
                is_toc = False
                page_type = 'standard'

            # NEW: Detect mixed content (text + illustrations on same page)
            # This is critical — pages with both need image preservation
            # even when OCR extracts substantial text
            has_mixed_content = has_illustrations and (text_region is not None or not has_center_gutter)
            
            # Calculate scores with improved weights
            # NOTE: component_score was /60 (max 30) — too high for dense Telugu text.
            # Dense single-column Telugu pages have 200-400 components naturally,
            # scoring 10-20 pts just for being  text-heavy. Reduced to /120 (max 15).
            edge_score = min(edge_density * 5, 35)
            component_score = min(num_labels / 120, 15)   # was /60, max 30
            layout_score = 20 if has_center_gutter else 0
            table_score = 30 if has_table else 0
            box_score = 15 if has_many_boxes else 0
            illustration_score = 25 if has_illustrations else 0
            mixed_content_score = 15 if has_mixed_content else 0  # Extra complexity for hybrid pages
            
            # Plus a TOC boost: Tesseract finds TOCs harder, but we'll try multi-PSM first
            toc_boost = 10 if is_toc else 0
            
            total_complexity = edge_score + component_score + layout_score + table_score + box_score + illustration_score + mixed_content_score + toc_boost
            
            # Recommendation with table/image/Gemini awareness
            gemini_threshold = getattr(config, 'GEMINI_COMPLEXITY_THRESHOLD', 80)
            gemini_available = getattr(config, 'GEMINI_AVAILABLE', False)
            
            if total_complexity >= gemini_threshold and gemini_available:
                engine = 'gemini'
                reason = f"Very complex page (score {total_complexity:.0f} >= {gemini_threshold})"
                is_very_complex = True
            elif has_table or (has_many_boxes and total_complexity > 50) or has_illustrations:
                engine = 'tesseract'  # Replaced easyocr with tesseract (speed override)
                reason = "Structure/Image detected"
                total_complexity = max(total_complexity, 75)
                is_very_complex = False
            elif total_complexity > self.complex_threshold:
                engine = 'tesseract'  # Replaced easyocr with tesseract (speed override)
                reason = "High density/Complex layout"
                is_very_complex = False
            elif total_complexity < self.simple_threshold:
                engine = 'tesseract'
                reason = "Simple text (high clarity)"
                is_very_complex = False
            else:
                engine = 'tesseract'
                reason = "Standard layout"
                is_very_complex = False
            
            # --- INTELLIGENT PSM MAPPING ---
            # Each page type has a different optimal Page Segmentation Mode.
            # The analyzer has already identified the layout — now we use that knowledge.
            #
            # PSM Reference:
            #   PSM 3  = Fully automatic page segmentation (safe fallback for unknown layouts)
            #   PSM 4  = Single column of text of variable sizes (★ best for book pages)
            #   PSM 6  = Assume a single uniform block of text (good for TOC, tables, forms)
            #
            # Decision Tree:
            #   TOC pages         → PSM 6  (dot-leader rows are uniform)
            #   Table/Grid pages  → PSM 6  (uniform cell rows)
            #   Multi-column      → PSM 4  (each column is a single-column stream)
            #   Standard book     → PSM 4  (paragraphs with indents, headers — variable sizes)
            #   Cover / Unknown   → PSM 3  (auto — unpredictable layout)

            if page_type == 'toc':
                # TOC rows are structurally uniform: title...dots...page_num
                recommended_psm = 6
                psm_reason = "TOC detected → PSM 6 (uniform rows)"

            elif has_table:
                # Tables have a uniform grid structure
                recommended_psm = 6
                psm_reason = "Table detected → PSM 6 (uniform block)"

            elif num_columns > 1:
                # Multi-column: each split column is handled as a single-column stream
                # The converter splits the image before OCR, so PSM 4 applies per-column
                recommended_psm = 4
                psm_reason = f"{num_columns}-column layout → PSM 4 (per-column single stream)"

            elif has_illustrations and text_region is not None:
                # Mixed content: text region cropped out — treat as single column
                recommended_psm = 4
                psm_reason = "Mixed content (text region cropped) → PSM 4"

            elif has_illustrations and text_region is None:
                # Illustration detected but we couldn't isolate text region cleanly
                # Use auto segmentation to be safe
                recommended_psm = 3
                psm_reason = "Illustration (no clean text region) → PSM 3 (auto)"

            else:
                # Standard book page: single column with paragraphs, indents, and headers.
                # PSM 4 handles variable text sizes (chapter headers vs body text)
                # and does NOT require the block to be perfectly uniform (unlike PSM 6).
                recommended_psm = 4
                psm_reason = "Standard book page → PSM 4 (single column, variable sizes)"

            # DEBUG: fires on every page — routine measurement, not a decision or
            # problem (the actual PSM value is already part of the returned dict
            # and the page_analysis structured event).
            logger.debug(f"  🎯 Smart PSM: {psm_reason}")

            # Line count is a resolution-independent count — compute it on the
            # downscaled binary/text_region before we rescale coordinates.
            estimated_lines = self.estimate_line_count(binary, text_region)

            # All layout coordinates above are in the downscaled analysis space.
            # The caller crops the FULL-resolution page at column_gutter_x, so
            # convert the gutter and the text region back to original-page coords.
            inv = 1.0 / scale if scale else 1.0
            out_gutter_x = int(round(column_gutter_x * inv)) if column_gutter_x is not None else None
            out_text_region = (
                (int(round(text_region[0] * inv)), int(round(text_region[1] * inv)))
                if text_region is not None else None
            )

            return {
                'complexity_score': total_complexity,
                'recommended_engine': engine,
                'recommended_psm': recommended_psm,
                'page_type': page_type,
                'edge_density': edge_density,
                'num_components': num_labels,
                'is_multicolumn': (column_gutter_x is not None),
                'has_table': has_table,
                'has_boxes': has_many_boxes,
                'has_illustrations': has_illustrations,
                'has_mixed_content': has_mixed_content,
                'is_very_complex': is_very_complex,
                'image_regions': image_regions,
                'image_dominant_ratio': image_dominant_ratio,
                'text_region': out_text_region,
                'column_gutter_x': out_gutter_x,
                'num_columns': num_columns,
                'estimated_lines': estimated_lines,
                'reasoning': reason
            }
        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}")
            return {'complexity_score': 50, 'recommended_engine': 'tesseract', 'reasoning': 'Analysis error'}

    @staticmethod
    def _compute_oov_ratio(clean_text: str) -> Dict[str, Any]:
        """
        Fraction of dictionary-eligible words in `clean_text` that are NOT in the
        Telugu dictionary (TeluguSpellChecker.is_known_word — O(1) exact-set lookup,
        NOT .suggest(), which is fuzzy/expensive and meant for correction, not
        detection). Catches structurally-valid-but-nonsense hallucinated words that
        avg_word_len/symbol_ratio/artifact_ratio/grapheme_validity_score all miss,
        since every character involved is a legitimate Telugu codepoint in valid
        grammatical position — the failure mode that's most common on faint/
        low-contrast scans where the OCR engine confidently mis-reads one real-
        looking word for another.
        """
        result = {'oov_ratio': 0.0, 'oov_checked_count': 0, 'oov_unknown_count': 0}
        try:
            from telugu_text_processor import get_telugu_text_processor, dictionary_lookup_candidate
            from telugu_spell_checker import get_telugu_spell_checker
        except ImportError:
            return result  # dependency unavailable — skip this signal only

        text_processor = get_telugu_text_processor()
        spell_checker = get_telugu_spell_checker()

        checked = 0
        unknown = 0
        for word in clean_text.split():
            candidate = dictionary_lookup_candidate(word, text_processor)
            if candidate is None:
                continue
            checked += 1
            if not spell_checker.is_known_word(candidate):
                unknown += 1

        if checked > 0:
            result['oov_ratio'] = unknown / checked
        result['oov_checked_count'] = checked
        result['oov_unknown_count'] = unknown
        return result

    @staticmethod
    def is_junk_text(text: str, diagnostics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Heuristic to detect junk/garbage OCR output (common in Tesseract's failures).
        Returns True if text is likely garbage.

        `diagnostics`, if given, is populated with every intermediate signal value
        (including the OOV ratio, which is always computed regardless of whether
        ENABLE_TELUGU_OOV_JUNK_SIGNAL is on) — used by the caller to log calibration
        data before that flag is ever trusted to affect the verdict.
        """
        if not text:
            return False
            
        clean_text = text.strip()
        if len(clean_text) < 50:
            return False
            
        lines = [l for l in clean_text.split('\n') if l.strip()]
        if not lines:
            return False
            
        words = clean_text.split()
        if not words:
            return False
            
        # 1. Average word length (Telugu words include secondary vowel marks, so they are usually long)
        # Garbage text often has lots of single-letter "words" or fragments.
        avg_word_len = sum(len(w) for w in words) / len(words)
        
        # 2. Character-per-line ratio
        # Standard book text usually has 30-60 characters per line.
        # Junk text often has tiny fragments scattered across many lines.
        avg_chars_per_line = len(clean_text) / len(lines)
        
        # 3. Numeric/Symbol density
        import re
        # Count non-alphabetic characters (excluding spaces/newlines)
        # Match only Telugu characters and standard alpha
        alpha_only = re.sub(r'[^a-zA-Z\u0c00-\u0c7f]', '', clean_text)
        symbol_ratio = 1.0 - (len(alpha_only) / len(clean_text.replace(" ", "").replace("\n", ""))) if len(clean_text) > 0 else 0
        
        # 4. Tesseract Artifacts check (specifically for Telugu)
        # Tesseract often adds random ' or " or : at the start/end of words
        # e.g. "'సాంగత్యంవల్ల" instead of "సాంగత్యంవల్ల"
        artifact_words = 0
        for word in words:
            # Check if word starts or ends with a common Tesseract artifact
            if len(word) > 2:
                if word[0] in ("'", '"', ':', '`', '.') or word[-1] in ("'", '"', ':', '`'):
                    artifact_words += 1
        
        artifact_ratio = artifact_words / len(words) if words else 0

        # 5. Grapheme-level validity (catches what symbol-ratio checks miss)
        # Checks 1-4 above classify characters by Unicode-block membership, so a
        # floating vowel sign (matra) or dangling virama — grammatically
        # impossible in real Telugu, but a hallmark of PaddleOCR/Tesseract
        # hallucination on faint/old scans — still counts as "real Telugu
        # content" to them. This check looks at grammar instead of symbols.
        grapheme_ratio = 0.0
        grapheme_invalid_count = 0
        try:
            from telugu_text_processor import get_telugu_text_processor
            grapheme_score = get_telugu_text_processor().grapheme_validity_score(clean_text)
            grapheme_ratio = grapheme_score['invalid_ratio']
            grapheme_invalid_count = grapheme_score['invalid_count']
        except ImportError:
            pass  # telugu_text_processor unavailable — skip this signal only

        # 6. Dictionary out-of-vocabulary ratio (catches structurally-valid but
        # wrong words — real graphemes, correct grammar shape, just the wrong
        # word. Always computed for calibration logging; only contributes to
        # `is_junk` below when ENABLE_TELUGU_OOV_JUNK_SIGNAL is on, since unlike
        # grapheme_ratio this has no real-page calibration data yet — see
        # OOV_JUNK_RATIO_THRESHOLD's comment in config.py.
        oov_info = PageComplexityAnalyzer._compute_oov_ratio(clean_text)
        oov_ratio = oov_info['oov_ratio']
        oov_checked_count = oov_info['oov_checked_count']
        oov_unknown_count = oov_info['oov_unknown_count']

        # JUNK THRESHOLDS: (Relaxed for Telugu)
        # - Very short average word length + many lines
        # - High symbol ratio + low average word length
        # - High artifact ratio (indicates Tesseract failure)
        # - Multiple orphaned matras/viramas (structurally invalid Telugu)
        #
        # grapheme_ratio threshold calibrated 2026-07-04 against ~4,700 real
        # pages after fixing find_invalid_grapheme_sequences to stop counting
        # word/line-boundary viramas: PaddleOCR/Tesseract baseline output
        # (~80-90% accurate) routinely scores 1.5-2% from ordinary noise and
        # is still perfectly readable/usable — flagging that band as junk
        # was sending most pages to Gemini for no benefit. Manual review of
        # sampled pages found the 3%+ band consistently unreadable/garbled,
        # while 1.5-2% pages were readable with only minor glitches. 2.5%
        # sits at the transition and matches the ~top 7% (tail) of the
        # observed distribution.
        is_junk = (
            (avg_word_len < 1.8 and len(lines) > 8)  # More tolerant of short fragments
            or (avg_chars_per_line < 8 and len(lines) > 15)
            or (symbol_ratio > 0.60 and avg_word_len < 2.5) # More tolerant of symbols/punctuation
            or (artifact_ratio > 0.40 and len(words) > 10) # NEW: High frequency of Tesseract artifacts
            or (grapheme_ratio > 0.025 and grapheme_invalid_count >= 5) # NEW: orphaned matras/viramas
            or (  # NEW: dictionary OOV ratio — off by default, uncalibrated (see config.py)
                getattr(config, 'ENABLE_TELUGU_OOV_JUNK_SIGNAL', False)
                and oov_checked_count >= getattr(config, 'OOV_JUNK_MIN_WORDS', 8)
                and oov_ratio > getattr(config, 'OOV_JUNK_RATIO_THRESHOLD', 0.5)
            )
        )

        if diagnostics is not None:
            diagnostics.update({
                'avg_word_len': avg_word_len,
                'avg_chars_per_line': avg_chars_per_line,
                'symbol_ratio': symbol_ratio,
                'artifact_ratio': artifact_ratio,
                'grapheme_ratio': grapheme_ratio,
                'grapheme_invalid_count': grapheme_invalid_count,
                'oov_ratio': oov_ratio,
                'oov_checked_count': oov_checked_count,
                'oov_unknown_count': oov_unknown_count,
            })

        if is_junk:
            logger.warning(f"  🔍 Junk detected: avg_word={avg_word_len:.2f}, avg_line={avg_chars_per_line:.2f}, "
                           f"symbol={symbol_ratio:.2f}, artifact={artifact_ratio:.2f}, "
                           f"grapheme_invalid={grapheme_invalid_count} ({grapheme_ratio*100:.1f}%), "
                           f"oov={oov_unknown_count}/{oov_checked_count} ({oov_ratio*100:.1f}%)")
            return True

        return False
