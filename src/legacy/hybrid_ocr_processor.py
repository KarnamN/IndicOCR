"""
Hybrid OCR Processor
Combines PaddleOCR and Tesseract results with intelligent fallback.
"""
import logging
from typing import List, Dict, Any
import config
import gc

logger = logging.getLogger(__name__)

class HybridOCRProcessor:
    """Combines high-accuracy PaddleOCR with high-speed Tesseract fallback."""
    
    def __init__(self, paddle_proc, tesseract_proc):
        self.paddle = paddle_proc
        self.tesseract = tesseract_proc
        self.enable_fallback = getattr(config, 'ENABLE_FALLBACK', True)

    def extract_text(self, image) -> str:
        """嘗試 PaddleOCR，如果為空則回退到 Tesseract。"""
        # 1. Try PaddleOCR first (AI-powered)
        text = self.paddle.extract_text(image)
        
        # 2. Check if text is valid and substantial
        if not text.strip() or len(text.strip()) < 10:
            if self.enable_fallback:
                logger.info("PaddleOCR yielded low results, falling back to Tesseract...")
                text = self.tesseract.extract_text(image)
            else:
                logger.warning("PaddleOCR yielded low results, fallback disabled.")
        
        # Explicitly clear image from memory if possible (GC hint)
        if getattr(config, 'PADDLE_ENABLE_GC', True):
            gc.collect()
            
        return text

    def extract_text_with_boxes(self, image) -> List[Dict[str, Any]]:
        # Usually we want either Paddle or Tesseract boxes, not both merged
        # Default to Paddle for high quality layout
        results = self.paddle.extract_text_with_boxes(image)
        if not results and self.enable_fallback:
            results = self.tesseract.extract_text_with_boxes(image)
        return results
