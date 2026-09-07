import os
# Force disable MKLDNN to prevent PIR oneDNN crashes on CPU
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_mkldnn_cache_capacity"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

import cv2
import numpy as np
from PIL import Image
import threading
from typing import List, Dict, Any, Tuple, Optional
from logging_config import get_logger
import config

logger = get_logger(__name__)

# Global singleton
_layout_engine = None
_layout_lock = threading.Lock()

def _get_layout_engine():
    global _layout_engine
    if _layout_engine is not None:
        return _layout_engine
    
    with _layout_lock:
        if _layout_engine is None:
            try:
                from paddleocr import LayoutDetection
                model_name = getattr(config, 'PADDLE_LAYOUT_MODEL', 'PP-DocLayout_plus-L')
                logger.info(f"🚀 Loading Layout Analysis model: {model_name}")
                # enable_mkldnn=False to prevent OneDNN crashes
                _layout_engine = LayoutDetection(model_name=model_name, enable_mkldnn=False)
                logger.info(f"✅ Layout Analysis model {model_name} loaded successfully")
            except ImportError:
                logger.warning("PaddleOCR not installed or LayoutDetection unavailable.")
                _layout_engine = False
            except Exception as e:
                logger.error(f"Failed to load LayoutDetection: {e}")
                _layout_engine = False
                
    return _layout_engine


class LayoutAnalyzer:
    """
    Analyzes document layouts using PaddleOCR's PP-Structure LayoutDetection.
    Identifies headers, paragraphs, figures, and tables.
    """
    def __init__(self):
        self.engine = _get_layout_engine()
        
    def analyze(self, image: Image.Image) -> Dict[str, List[Dict]]:
        """
        Analyzes the given PIL image and returns categorized bounding boxes.
        
        Returns a dict with keys:
        - 'title': List of title/header boxes
        - 'text': List of standard text/paragraph boxes
        - 'figure': List of image/illustration boxes
        - 'table': List of table boxes
        - 'garbage': List of header/footer/page number boxes to ignore
        
        Each box is a dict: {'coordinate': [x1, y1, x2, y2], 'score': float, 'label': str}
        """
        result_dict = {
            'title': [],
            'text': [],
            'figure': [],
            'table': [],
            'garbage': []
        }
        
        if not self.engine:
            return result_dict
            
        try:
            # Convert PIL image to BGR for PaddleX
            img_rgb = image.convert('RGB')
            img_bgr = cv2.cvtColor(np.array(img_rgb), cv2.COLOR_RGB2BGR)
            
            # CRITICAL: PaddleX models are not thread-safe for concurrent inference
            # (see the identical warning/fix in paddle_v5_processor.py). predict()
            # can be lazy/generator-backed, so the real forward-pass may not happen
            # until the result is first consumed — materialize it as a list here,
            # still inside the lock, or the actual computation runs unprotected
            # after the lock is released and can corrupt/interleave with another
            # thread's concurrent call on this same shared engine.
            with _layout_lock:
                results = list(self.engine.predict(input=img_bgr))

            if not results:
                return result_dict

            res = results[0]
            boxes = res.get('boxes', []) if isinstance(res, dict) else getattr(res, 'boxes', [])
            
            for box in boxes:
                label = box.get('label', '').lower()
                # Map PP-DocLayout_plus labels to our categories
                if 'title' in label or ('header' in label and 'text' not in label):
                    if 'header' in label and box['coordinate'][1] < img_bgr.shape[0] * 0.1:
                        result_dict['garbage'].append(box)
                    else:
                        result_dict['title'].append(box)
                elif 'text' in label or 'content' in label:
                    result_dict['text'].append(box)
                elif 'figure' in label or 'image' in label or 'picture' in label:
                    result_dict['figure'].append(box)
                elif 'table' in label:
                    result_dict['table'].append(box)
                elif 'footer' in label or 'page' in label:
                    result_dict['garbage'].append(box)
                else:
                    result_dict['text'].append(box)
                    
            logger.debug(
                f"Layout Analysis: {len(result_dict['title'])} titles, "
                f"{len(result_dict['text'])} texts, "
                f"{len(result_dict['figure'])} figures, "
                f"{len(result_dict['garbage'])} garbage"
            )
                    
        except Exception as e:
            logger.warning(f"Layout analysis failed: {e}")
            
        return result_dict

    def extract_figures(self, image: Image.Image) -> Tuple[List[Image.Image], List[Tuple[int, int, int, int]]]:
        """
        Run layout analysis and return precisely cropped figure images.

        Returns:
            crops  — list of PIL Images, one per detected figure region
            coords — list of (x1, y1, x2, y2) tuples for each crop

        If the layout model is unavailable, returns ([], []).
        """
        crops: List[Image.Image] = []
        coords: List[Tuple[int, int, int, int]] = []

        layout = self.analyze(image)
        img_w, img_h = image.size

        for box in layout.get('figure', []):
            try:
                x1, y1, x2, y2 = [int(v) for v in box['coordinate']]
                x1 = max(0, x1); y1 = max(0, y1)
                x2 = min(img_w, x2); y2 = min(img_h, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = image.crop((x1, y1, x2, y2))
                
                # VERIFICATION: Ensure this isn't just a block of text misclassified as a figure.
                # Run a fast Tesseract check on the crop. If it contains significant text, REJECT it.
                import pytesseract
                try:
                    # This is a coarse density probe, not real extraction — downscale
                    # to a small side length and use PSM 6 (uniform block) instead of
                    # the default full-page auto-segmentation, which is far slower and
                    # unnecessary for just counting characters.
                    check_crop = crop
                    if max(crop.size) > 800:
                        ratio = 800 / max(crop.size)
                        check_crop = crop.resize(
                            (max(1, int(crop.width * ratio)), max(1, int(crop.height * ratio))),
                            Image.Resampling.NEAREST
                        )
                    crop_text = pytesseract.image_to_string(check_crop, lang='eng+tel', config='--psm 6')
                    clean_chars = sum(1 for c in crop_text if not c.isspace())

                    # Density computed against the ORIGINAL crop area (not the
                    # downscaled check image) so the accept/reject boundary is
                    # unaffected by the resize.
                    area = (x2 - x1) * (y2 - y1)
                    density = clean_chars / max(1, area)
                    
                    # Reject only if it's clearly a dense block of text masquerading as a figure
                    if clean_chars > 100 and density > 0.0004:
                        logger.warning(
                            f"  🚫 REJECTED false-positive figure at ({x1},{y1})-({x2},{y2}): "
                            f"Found {clean_chars} text chars (density {density:.5f}). Reclassifying as TEXT."
                        )
                        continue
                except Exception as ex:
                    logger.debug(f"Figure text verification failed, assuming it's a valid figure: {ex}")

                crops.append(crop)
                coords.append((x1, y1, x2, y2))
                logger.debug(f"  ✂️  Figure cropped at ({x1},{y1})-({x2},{y2}) [{x2-x1}×{y2-y1}px]")
            except Exception as e:
                logger.warning(f"Figure crop failed: {e}")

        return crops, coords

    def get_text_mask(self, image: Image.Image,
                      figure_coords: Optional[List[Tuple[int, int, int, int]]] = None) -> Image.Image:
        """
        Return a copy of the page with all figure regions painted white.
        Passing this masked image to PageComplexityAnalyzer prevents figure
        pixels from inflating the complexity score and triggering Gemini.

        Args:
            image         — original full-page PIL Image
            figure_coords — pre-computed coords from extract_figures(); if None,
                            layout analysis is run internally (saves a second call
                            if you already have the coords).

        Returns:
            New PIL Image with figure regions blanked to white.
        """
        if figure_coords is None:
            _, figure_coords = self.extract_figures(image)

        if not figure_coords:
            return image  # nothing to mask — return original unchanged

        masked = image.copy().convert('RGB')
        img_array = np.array(masked)

        for (x1, y1, x2, y2) in figure_coords:
            img_array[y1:y2, x1:x2] = 255  # paint white

        return Image.fromarray(img_array)
