"""
Page Splitter Module
Detects and splits double-page scans into single pages
"""
import cv2
import numpy as np
from PIL import Image
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class PageSplitter:
    """Detect and split double-page scans"""
    
    def __init__(self, aspect_ratio_threshold: float = 1.15, require_spine_confirmation: bool = True):
        """
        Initialize page splitter

        Args:
            aspect_ratio_threshold: Width/height ratio to consider as double-page
                                   (e.g., 1.2 means width is 1.2x height)
            require_spine_confirmation: If True (default), a wide page is only split
                                   when a genuine central spine gutter is also found —
                                   this protects corpora that mix double-page spreads
                                   with single wide multi-column pages (e.g. magazine
                                   scans). Set False for corpora where every wide page
                                   is known to be a real double-page spread (e.g. book
                                   photocopies with faint/worn gutters that a pixel-
                                   projection spine check can miss) — see
                                   `_has_central_spine` for why that check has a ceiling.
        """
        self.aspect_ratio_threshold = aspect_ratio_threshold
        self.require_spine_confirmation = require_spine_confirmation
        logger.info(f"Page Splitter initialized (aspect_ratio_threshold={aspect_ratio_threshold}, "
                    f"require_spine_confirmation={require_spine_confirmation})")
    
    def _has_central_spine(self, image: Image.Image,
                           band: Tuple[float, float] = (0.40, 0.60),
                           min_run_frac: float = 0.55,
                           window: int = 6) -> bool:
        """
        Verify a genuine book-spine gutter exists near the horizontal center.

        A true double-page spread has a near-full-height band of whitespace (or a
        uniform spine shadow) where the two facing pages meet. A single page that
        merely happens to be wide — e.g. a magazine page with two text columns and
        an illustration (common in Chandamama scans) — has NO such central gap:
        text and images fill the middle, and any vertical whitespace is only the
        column gutter, which is short and off-centre.

        Returns True only if some column window inside `band` (fraction of width,
        centred on the page) contains a continuous run of empty rows covering at
        least `min_run_frac` of the page height.
        """
        try:
            gray = np.array(image.convert('L'))
            # Downscale tall scans so the row-scan stays cheap at 300+ DPI.
            h0, w0 = gray.shape
            if h0 > 1000:
                scale = 1000.0 / h0
                gray = cv2.resize(gray, (max(1, int(w0 * scale)), 1000),
                                  interpolation=cv2.INTER_NEAREST)
            h, w = gray.shape

            # Adaptive threshold (inverted): ink/shadow-edges = 255, paper = 0.
            # A uniform spine shadow reads as paper here (locally flat → below the
            # offset), so this run test catches both white gutters and shadow spines.
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 21, 10
            )

            x_start, x_end = int(w * band[0]), int(w * band[1])
            required = int(h * min_run_frac)

            for x in range(x_start, x_end, 2):
                win = binary[:, max(0, x - window):x + window]
                row_ink = np.sum(win, axis=1)
                cur = 0
                for r in row_ink:
                    if r == 0:
                        cur += 1
                        if cur >= required:
                            return True
                    else:
                        cur = 0
            return False
        except Exception as e:
            # Fail safe: preserve legacy behaviour (split on wide aspect) if the
            # spine check itself errors out.
            logger.warning(f"Central-spine check failed: {e}; assuming spine present")
            return True

    def is_double_page(self, image: Image.Image) -> bool:
        """
        Check if image is a double-page scan

        Args:
            image: PIL Image object

        Returns:
            True if image appears to be double-page (landscape with 2 pages)
        """
        width, height = image.size
        aspect_ratio = width / height

        # A wide aspect ratio is necessary but NOT sufficient. Single magazine
        # pages with two text columns are also wide, so wide-aspect alone
        # previously mis-split them right down the column gutter, bypassing the
        # column-aware OCR path. Require a genuine central spine as confirmation.
        if aspect_ratio <= self.aspect_ratio_threshold:
            return False

        if self.require_spine_confirmation and not self._has_central_spine(image):
            logger.info(
                f"  📄 Wide page {width}×{height} (ratio {aspect_ratio:.2f}) has no "
                f"central spine — treating as single page (likely multi-column)."
            )
            return False

        logger.info(f"  📖 Double-page detected: {width}×{height} (ratio: {aspect_ratio:.2f})")
        return True
    
    def find_split_point(self, image: Image.Image) -> Optional[int]:
        """
        Find the vertical line where pages should be split. 
        Improved to be more robust against wide margins and shadows.
        """
        try:
            # Convert to grayscale
            gray = np.array(image.convert('L'))
            height, width = gray.shape
            
            # Analyze vertical strips (average brightness of each column)
            column_brightness = np.mean(gray, axis=0)
            
            # Calculate column variance (standard deviation) to identify text-free zones
            # High variance = text/images, Low variance = white space or solid gutter
            column_variance = np.std(gray, axis=0)
            
            # Search bounds: For a standard double page, the gutter is near 50%.
            # For multi-page (recursive), we search a wider area (20% to 80%).
            search_start = int(width * 0.2)
            search_end = int(width * 0.8)
            search_area_brightness = column_brightness[search_start:search_end]
            search_area_variance = column_variance[search_start:search_end]
            
            # SCORING SYSTEM:
            # We want high brightness (white) AND low variance (empty) 
            # AND proximity to geometric center.
            
            indices = np.arange(search_start, search_end)
            center = width // 2
            
            # Use Gaussian centered at 0.5 width for proximity score.
            # Widened to sigma = 0.18 * width (was 0.1) so a genuine gutter that
            # sits noticeably off-center (e.g. centre-right, from an uneven scan
            # or asymmetric binding) isn't out-voted just for not being exactly
            # at 50% — the true discriminator should be the flat/empty column
            # signal (variance), with proximity only as a tie-breaker.
            sigma = width * 0.18
            proximity_score = np.exp(-((indices - center) ** 2) / (2 * sigma ** 2))

            # Brightness score: Normalized 0 to 1
            b_min, b_max = np.min(search_area_brightness), np.max(search_area_brightness)
            brightness_norm = (search_area_brightness - b_min) / max(1, b_max - b_min)

            # Variance score: 1 - Normalized variance (we want low variance)
            v_min, v_max = np.min(search_area_variance), np.max(search_area_variance)
            variance_inv_norm = 1.0 - ((search_area_variance - v_min) / max(1, v_max - v_min))

            # Combine scores. Proximity weight lowered from 0.4 to 0.3 (and the
            # slack moved onto variance, the strongest signal for a real empty
            # gutter/line) so a strong off-center candidate can still win instead
            # of being forced back toward the exact geometric center.
            final_score = (brightness_norm * 0.28) + (variance_inv_norm * 0.42) + (proximity_score * 0.3)

            # Check for "Spine Shadow": If the center is dark but very consistent
            # (low variance), it's likely the fold of the book.
            spine_score = (1.0 - brightness_norm) * 0.3 + (variance_inv_norm * 0.4) + (proximity_score * 0.3)
            
            # Combine scores to find the globally best candidate
            # We want to favor the spine score if the brightness is low at center
            best_combined_idx = np.argmax(final_score + spine_score)
            split_x = search_start + best_combined_idx

            logger.info(f"  ✂️  Split point found at x={split_x} (center: {center})")
            return split_x
            
        except Exception as e:
            logger.warning(f"Could not find split point: {e}, using center")
            return image.width // 2
    
    def split_page(self, image: Image.Image, split_x: Optional[int] = None) -> Tuple[Image.Image, Image.Image]:
        """
        Split double-page image into two single pages
        
        Args:
            image: PIL Image object (double-page)
            split_x: Optional X-coordinate to split at (if None, auto-detect)
            
        Returns:
            Tuple of (left_page, right_page)
        """
        width, height = image.size
        
        # Auto-detect split point if not provided
        if split_x is None:
            split_x = self.find_split_point(image)
            if split_x is None:
                split_x = width // 2  # Fallback to center
        
        # Split into left and right pages
        left_page = image.crop((0, 0, split_x, height))
        right_page = image.crop((split_x, 0, width, height))
        
        logger.info(f"  ✓ Split into: Left ({left_page.width}×{left_page.height}) + "
                   f"Right ({right_page.width}×{right_page.height})")
        
        return left_page, right_page
    
    def process_image(self, image: Image.Image, force_split: bool = False) -> List[Image.Image]:
        """
        Process image - split if double-page (or multi-page), otherwise return as-is.
        Uses recursive splitting to handle 3, 4 or more pages in one scan.
        
        Args:
            image: PIL Image object
            force_split: Force split even if not detected as double-page
            
        Returns:
            List of page images (1 if single, 2 if double, N if multi-page)
        """
        # Check if double-page or wider
        if force_split or self.is_double_page(image):
            left, right = self.split_page(image)
            
            # Recursively process the results (to handle 3, 4+ pages)
            # We don't force_split the children; they split only if they are still wide.
            final_pages = []
            final_pages.extend(self.process_image(left))
            final_pages.extend(self.process_image(right))
            return final_pages
        else:
            # Base case: Just one page
            logger.debug(f"  ✓ Found individual page: {image.width}×{image.height}")
            return [image]

    def get_page_slices(self, image: Image.Image, start_rel: float = 0.0, end_rel: float = 1.0) -> List[Tuple[float, float]]:
        """
        Recursively find relative split columns (normalized 0.0 to 1.0) for a wide image.
        """
        if self.is_double_page(image):
            split_x = self.find_split_point(image)
            if split_x is None:
                split_x = image.width // 2
            
            # Crop left and right locally
            left_page = image.crop((0, 0, split_x, image.height))
            right_page = image.crop((split_x, 0, image.width, image.height))
            
            # Calculate the relative split coordinate in the parent
            rel_split = start_rel + (split_x / image.width) * (end_rel - start_rel)
            
            # Recurse
            slices = []
            slices.extend(self.get_page_slices(left_page, start_rel, rel_split))
            slices.extend(self.get_page_slices(right_page, rel_split, end_rel))
            return slices
        else:
            return [(start_rel, end_rel)]



def test_page_splitter():
    """Test page splitter functionality"""
    splitter = PageSplitter()
    
    # Test with dummy image
    print("✓ Page Splitter initialized")
    print(f"  Aspect ratio threshold: {splitter.aspect_ratio_threshold}")
    
    # Create test double-page image (landscape)
    test_double = Image.new('RGB', (2000, 1000), 'white')
    is_double = splitter.is_double_page(test_double)
    print(f"  Test double-page (2000×1000): {is_double}")
    
    # Create test single-page image (portrait)
    test_single = Image.new('RGB', (1000, 1400), 'white')
    is_single = splitter.is_double_page(test_single)
    print(f"  Test single-page (1000×1400): {not is_single}")


if __name__ == "__main__":
    test_page_splitter()
