"""
Fast Table Detector - Optimized for Speed
Adds quick pre-checks to skip expensive detection on non-table pages
"""
import cv2
import numpy as np
from PIL import Image
import logging
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import config

# Logging is configured centrally by logging_config.setup_logging() (invoked at
# app.py's import time) — this module just gets its own named logger from
# whatever root configuration is already in place.
logger = logging.getLogger(__name__)


class FastTableDetector:
    """Fast table detector with pre-screening"""
    
    def __init__(self, min_rows: int = None, min_cols: int = None):
        """
        Initialize fast table detector
        
        Args:
            min_rows: Minimum number of rows to consider as table
            min_cols: Minimum number of columns to consider as table
        """
        self.min_rows = min_rows or config.MIN_TABLE_ROWS
        self.min_cols = min_cols or config.MIN_TABLE_COLS
        logger.info(f"Fast Table Detector initialized (min_rows={self.min_rows}, min_cols={self.min_cols})")
    
    def has_table_structure(self, image: Image.Image, downsample_factor: int = 4) -> bool:
        """
        Quick check if page likely has a table (pre-screening)
        
        Args:
            image: PIL Image object
            downsample_factor: Factor to downsample image for faster check
            
        Returns:
            True if page likely has table structure
        """
        try:
            # Downsample for speed
            small_img = image.resize(
                (image.width // downsample_factor, image.height // downsample_factor),
                Image.Resampling.LANCZOS
            )
            
            # Convert to grayscale and binary
            img_array = np.array(small_img.convert('L'))
            _, binary = cv2.threshold(img_array, 128, 255, cv2.THRESH_BINARY_INV)
            
            # Quick line detection with smaller kernels
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 1))
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
            
            h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
            v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
            
            # Count line pixels
            h_count = np.sum(h_lines > 0)
            v_count = np.sum(v_lines > 0)
            
            # Threshold: if very few line pixels, no table
            min_line_pixels = 100  # Adjust based on downsampled size
            
            has_table = h_count > min_line_pixels and v_count > min_line_pixels
            
            if not has_table:
                logger.info("  ⚡ No table structure detected (skipping expensive detection)")
            
            return has_table
            
        except Exception as e:
            logger.warning(f"Pre-screening failed: {e}, proceeding with full detection")
            return True  # If pre-check fails, assume table might exist
    
    def preprocess_for_table_detection(self, image: Image.Image) -> np.ndarray:
        """
        Preprocess image for table detection
        
        Args:
            image: PIL Image object
            
        Returns:
            Preprocessed image as numpy array
        """
        # Convert to numpy array
        img_array = np.array(image)
        
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Apply binary thresholding
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
        
        return binary
    
    def detect_lines(self, binary_image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect horizontal and vertical lines in image
        
        Args:
            binary_image: Binary image as numpy array
            
        Returns:
            Tuple of (horizontal_lines, vertical_lines)
        """
        # Detect horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Detect vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        return horizontal_lines, vertical_lines
    
    def find_table_regions(self, image: Image.Image) -> List[Dict]:
        """
        Find table regions in image
        
        Args:
            image: PIL Image object
            
        Returns:
            List of dictionaries containing table region information
        """
        try:
            # Preprocess image
            binary = self.preprocess_for_table_detection(image)
            
            # Detect lines
            horizontal_lines, vertical_lines = self.detect_lines(binary)
            
            # Combine horizontal and vertical lines
            table_mask = cv2.add(horizontal_lines, vertical_lines)
            
            # Find contours
            contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter and extract table regions
            table_regions = []
            
            for i, contour in enumerate(contours):
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                
                # Filter by size (must be reasonably large)
                if area > 10000:  # Minimum area threshold
                    table_regions.append({
                        'id': i,
                        'x': x,
                        'y': y,
                        'width': w,
                        'height': h,
                        'area': area,
                        'contour': contour
                    })
            
            # Sort by position (top to bottom)
            table_regions.sort(key=lambda r: r['y'])
            
            logger.info(f"Found {len(table_regions)} potential table regions")
            return table_regions
            
        except Exception as e:
            logger.error(f"Table region detection failed: {e}")
            return []
    
    def extract_table_image(self, image: Image.Image, region: Dict) -> Image.Image:
        """
        Extract table region from image
        
        Args:
            image: PIL Image object
            region: Dictionary with region coordinates
            
        Returns:
            Cropped table image
        """
        x, y, w, h = region['x'], region['y'], region['width'], region['height']
        
        # Add some padding
        padding = 10
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(image.width - x, w + 2 * padding)
        h = min(image.height - y, h + 2 * padding)
        
        # Crop image
        table_image = image.crop((x, y, x + w, y + h))
        
        return table_image
    
    def detect_table_structure(self, binary_image: np.ndarray) -> Tuple[List[int], List[int]]:
        """
        Detect table structure (rows and columns)
        
        Args:
            binary_image: Binary image of table
            
        Returns:
            Tuple of (row_positions, column_positions)
        """
        # Detect horizontal lines for rows
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Detect vertical lines for columns
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # Find row positions
        row_positions = []
        for i in range(horizontal_lines.shape[0]):
            if np.sum(horizontal_lines[i, :]) > horizontal_lines.shape[1] * 0.5 * 255:
                row_positions.append(i)
        
        # Find column positions
        col_positions = []
        for j in range(vertical_lines.shape[1]):
            if np.sum(vertical_lines[:, j]) > vertical_lines.shape[0] * 0.5 * 255:
                col_positions.append(j)
        
        # Remove duplicates (lines close to each other)
        row_positions = self._merge_close_positions(row_positions, threshold=10)
        col_positions = self._merge_close_positions(col_positions, threshold=10)
        
        return row_positions, col_positions
    
    def _merge_close_positions(self, positions: List[int], threshold: int = 10) -> List[int]:
        """
        Merge positions that are close to each other
        
        Args:
            positions: List of positions
            threshold: Distance threshold for merging
            
        Returns:
            Merged positions
        """
        if not positions:
            return []
        
        merged = [positions[0]]
        
        for pos in positions[1:]:
            if pos - merged[-1] > threshold:
                merged.append(pos)
        
        return merged
    
    def extract_cells(self, image: Image.Image, row_positions: List[int],
                     col_positions: List[int]) -> List[List[Image.Image]]:
        """
        Extract individual cells from table
        
        Args:
            image: PIL Image of table
            row_positions: List of row boundary positions
            col_positions: List of column boundary positions
            
        Returns:
            2D list of cell images
        """
        cells = []
        
        for i in range(len(row_positions) - 1):
            row_cells = []
            for j in range(len(col_positions) - 1):
                y1, y2 = row_positions[i], row_positions[i + 1]
                x1, x2 = col_positions[j], col_positions[j + 1]
                
                cell_image = image.crop((x1, y1, x2, y2))
                row_cells.append(cell_image)
            
            cells.append(row_cells)
        
        return cells
    
    def is_valid_table(self, row_positions: List[int], col_positions: List[int]) -> bool:
        """
        Check if detected structure is a valid table
        
        Args:
            row_positions: List of row positions
            col_positions: List of column positions
            
        Returns:
            True if valid table, False otherwise
        """
        num_rows = len(row_positions) - 1
        num_cols = len(col_positions) - 1
        
        is_valid = num_rows >= self.min_rows and num_cols >= self.min_cols
        
        if is_valid:
            logger.info(f"Valid table detected: {num_rows} rows × {num_cols} columns")
        
        return is_valid
    
    def detect_tables(self, image: Image.Image, skip_precheck: bool = False) -> List[Dict]:
        """
        Detect all tables in image with structure information
        
        Args:
            image: PIL Image object
            skip_precheck: Skip pre-screening (force full detection)
            
        Returns:
            List of dictionaries containing table information
        """
        # Quick pre-check to skip expensive detection
        if not skip_precheck and not self.has_table_structure(image):
            return []  # No tables, skip expensive detection
        
        tables = []
        
        # Find table regions
        regions = self.find_table_regions(image)
        
        for region in regions:
            try:
                # Extract table image
                table_image = self.extract_table_image(image, region)
                
                # Preprocess for structure detection
                binary = self.preprocess_for_table_detection(table_image)
                
                # Detect table structure
                row_positions, col_positions = self.detect_table_structure(binary)
                
                # Validate table
                if self.is_valid_table(row_positions, col_positions):
                    tables.append({
                        'region': region,
                        'image': table_image,
                        'rows': len(row_positions) - 1,
                        'cols': len(col_positions) - 1,
                        'row_positions': row_positions,
                        'col_positions': col_positions
                    })
            
            except Exception as e:
                logger.warning(f"Failed to process table region: {e}")
                continue
        
        logger.info(f"Detected {len(tables)} valid tables")
        return tables
