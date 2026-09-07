"""
Google Cloud Vision OCR Processor
Legacy premium OCR engine for high-reliability text extraction.
Handles 1000 calls per month in the free tier.
"""
import io
import time
import logging
from typing import Optional
from PIL import Image

import config
from logging_config import get_logger
from usage_tracker import UsageTracker

logger = get_logger(__name__)

class GoogleVisionProcessor:
    """
    OCR processor using Google Cloud Vision API.
    
    Excellent for:
    - Printed text with high accuracy
    - Document structure detection
    - High-quality Telugu extraction
    """
    
    def __init__(self):
        self.api_key = getattr(config, 'GOOGLE_VISION_API_KEY', '')
        self.service_account_path = getattr(config, 'GOOGLE_VISION_SERVICE_ACCOUNT', '')
        
        self.usage_tracker = UsageTracker()
        
        # Initialize client
        self._client = None
        self._initialized = False
        
        try:
            from google.cloud import vision
            
            if self.service_account_path:
                self._client = vision.ImageAnnotatorClient.from_service_account_json(self.service_account_path)
                self._initialized = True
                logger.info("🤖 Google Vision initialized via Service Account")
            elif self.api_key:
                # Note: google-cloud-vision doesn't support API keys directly in the constructor easily
                # but we can use the environment variable if they set it.
                # For now, we prefer Service Account or environment setup.
                logger.warning("Google Vision API Key provided, but Service Account JSON is preferred.")
                self._client = vision.ImageAnnotatorClient()
                self._initialized = True
                logger.info("🤖 Google Vision initialized (using default credentials/API key)")
        except ImportError:
            logger.warning("google-cloud-vision package not installed. Run: pip install google-cloud-vision")
        except Exception as e:
            logger.error(f"Failed to initialize Google Vision client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if Google Vision is ready and has quota."""
        if not (self._initialized and self._client is not None):
            return False
            
        return self.usage_tracker.has_quota('google_vision')

    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """Convert PIL Image to bytes for API upload."""
        buf = io.BytesIO()
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        image.save(buf, format='JPEG', quality=85)
        return buf.getvalue()

    def extract_text(self, image: Image.Image) -> str:
        """
        Extract text from a page image using Google Cloud Vision.
        """
        if not self.is_available:
            logger.warning("Google Vision OCR not available (or quota exceeded) — returning empty text")
            return ""
        
        # Convert image to bytes
        image_bytes = self._image_to_bytes(image)
        
        try:
            from google.cloud import vision
            
            image_cloud = vision.Image(content=image_bytes)
            
            # Increment usage BEFORE call to be safe
            self.usage_tracker.increment('google_vision')
            
            # Perform Document Text Detection (Dense Text)
            response = self._client.document_text_detection(image=image_cloud)
            
            if response.error.message:
                logger.error(f"Google Vision API Error: {response.error.message}")
                return ""
            
            text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            if text:
                logger.info(f"  🤖 Google Vision extracted {len(text)} chars")
            else:
                logger.warning("  🤖 Google Vision returned empty text")
                
            return text.strip()
            
        except Exception as e:
            logger.error(f"  🤖 Google Vision OCR failed: {e}")
            return ""

    def extract_text_with_semaphore(self, image: Image.Image, semaphore) -> str:
        with semaphore:
            return self.extract_text(image)

    def verify_telugu_support(self) -> bool:
        return True

    def get_available_languages(self) -> list:
        return ['tel', 'eng', 'tel+eng']
        
    def get_stats(self) -> dict:
        return self.usage_tracker.get_usage('google_vision')
