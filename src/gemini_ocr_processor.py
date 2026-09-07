"""
Gemini Vision OCR Processor
Premium-tier OCR using Google Gemini Vision API for complex pages.
Handles Telugu + English bilingual text extraction with layout preservation.
"""
import io
import base64
import time
import logging
from typing import Optional
from PIL import Image

import threading
import config
from logging_config import get_logger
from usage_tracker import UsageTracker

logger = get_logger(__name__)


class GeminiOCRProcessor:
    """
    OCR processor using Google Gemini Vision API.
    
    Designed for complex pages that Tesseract/EasyOCR struggle with:
    - Mixed text + illustration layouts
    - Tables and charts
    - Heavily degraded scans
    - Complex Telugu compound characters
    
    Implements the same `extract_text(image)` interface as other processors.
    """
    
    # Telugu+English OCR prompt — optimized for document text extraction
    OCR_PROMPT = """You are an expert OCR system for Telugu (తెలుగు) and English documents.

Extract ALL text from this scanned document page. Follow these rules strictly:

1. **Telugu text**: Preserve all Telugu characters exactly. Pay attention to:
   - Compound characters (vattu/guninthaalu like క్ష, జ్ఞ, శ్రీ)
   - Vowel signs (matras like ా, ి, ీ, ు, ూ, ె, ే, ొ, ో, ౌ)
   - Danda marks (। and ॥)
   
2. **English text**: Extract any English words, numbers, or labels as-is.

3. **Reading order**: Follow natural reading order:
   - For single column: top to bottom
   - For two columns: left column fully, then right column fully
   - For tables: row by row, left to right

4. **Formatting & Line Preservation**: 
   - PRESERVE exact line breaks as they appear in the image.
   - Do NOT merge lines or paragraphs.
   - Use double newlines only where there is a clear physical gap in the image.
   - Do NOT add page numbers, headers, or footers (skip them entirely).
   - Do NOT describe images or illustrations.
   - Do NOT add any commentary or explanations.

5. **Output**: Return ONLY the extracted text, nothing else. No markdown, no labels, no prefixes."""

    # Deep-scan prompt: used as Escalation Level 2 when Level 1 misses significant lines.
    # More aggressive — asks the model to look harder for faint/small text.
    DEEP_SCAN_PROMPT = """You are a forensic-grade OCR system for Telugu (తెలుగు) and English documents.

This page was processed by a standard OCR engine, but it likely MISSED some lines or sections of text.
Your task is to perform a THOROUGH, DEEP SCAN — Look carefully at EVERY part of the image:

1. **Find hidden text**: Look for faint ink, small-font text in margins, footnotes, page numbers,
   subscripts/superscripts, captions below illustrations, and text near the edges of the page.
   
2. **Telugu text**: Preserve ALL Telugu characters exactly. Pay special attention to:
   - Compound characters (vattu/guninthaalu like క్ష, జ్ఞ, శ్రీ)
   - Vowel signs (matras like ా, ి, ీ, ు, ూ, ె, ే, ొ, ో, ౌ)
   - Half-characters that may appear faint or blurred
   - Danda marks (। and ॥)
   
3. **Reading order**: Follow natural reading order:
   - For single column: top to bottom, including any header/footer text
   - For two columns: left column fully, then right column fully
   - For tables: row by row, left to right, including all cell content

4. **Line Preservation**: 
   - PRESERVE exact line breaks. Do NOT merge lines.
   - Include every line, even if it looks like a header, footer, or caption.
   - Do NOT skip any visible text.

5. **Output**: Return ONLY the extracted text, nothing else. No markdown, no labels."""

    # Reference-grounded prompt: used when two other OCR engines' independent
    # readings of the same page are already available. Anchoring the model
    # against concrete candidate text — instead of transcribing from a blank
    # slate — is meant to curb a confirmed failure mode: given no reference,
    # Gemini can produce a fluent, grammatically valid Telugu sentence that is
    # simply the WRONG content (e.g. substituting an unusual person's name
    # with a more common-sounding phrase) on a page an unreferenced Tesseract
    # pass read almost perfectly. The prompt explicitly instructs the model to
    # prefer a given reading when uncertain, rather than invent an alternative.
    REFERENCE_GROUNDED_PROMPT = """You are an expert OCR system for Telugu (తెలుగు) and English documents.

Two other OCR engines already attempted to read this exact page. Their readings
were extracted directly from what is visually on the page, but may contain
errors (dropped characters, misread glyphs, garbled fragments):

Reading A (PaddleOCR):
{paddle_text}

Reading B (Tesseract):
{tesseract_text}

The two readings disagree in the following places:
{diff_summary}

Your task: carefully compare BOTH readings against what you can actually see in
the image, and produce the most accurate transcription.

1. Where you can visually confirm which reading (if either) matches the image,
   use that reading.
2. Where neither reading matches what you see, transcribe exactly what is
   visible.
3. **CRITICAL — do not hallucinate**: if a specific word, name, or phrase is
   unclear, faint, or ambiguous in the image, and one of the two readings above
   is a plausible match for that spot, PREFER that reading over inventing a
   different, more common or more expected-sounding alternative. Do not
   substitute a "more likely" word for something that just looks unusual —
   unusual names and words are common in fiction and are not errors. Only
   deviate from BOTH readings when you have high visual confidence in a
   specific alternative you can actually see in the image.
4. Preserve Telugu compound characters (vattu/guninthaalu like క్ష, జ్ఞ, శ్రీ),
   vowel signs (matras), and danda marks (। and ॥) exactly.
5. Preserve exact line breaks as they appear in the image. Do not merge lines.
   Do not add page numbers, headers, footers, or commentary.

**Output**: Return ONLY the final corrected text, nothing else. No markdown, no
labels, no explanation of what you changed."""

    # Global rate limiting state shared across all instances/workers
    _last_call_time = 0
    _lock = threading.Lock()
    _min_interval = 10.0  # Increased to 10s to be safe with image-based OCR

    def __init__(self):
        self.api_key = getattr(config, 'GEMINI_API_KEY', '')
        self.model_name = getattr(config, 'GEMINI_MODEL', 'gemini-2.0-flash')
        self.timeout = getattr(config, 'GEMINI_TIMEOUT', 30)
        self.max_retries = getattr(config, 'GEMINI_MAX_RETRIES', 5)
        self.rate_limit_rpm = getattr(config, 'GEMINI_RATE_LIMIT_RPM', 10)
        
        # Update class-level interval based on config (min 2s for safety)
        GeminiOCRProcessor._min_interval = max((60.0 / self.rate_limit_rpm) + 0.2, 2.0)
        
        # Telemetry via UsageTracker
        self.usage_tracker = UsageTracker()
        self.total_retries = 0
        
        # Initialize the Gemini client
        self._client = None
        self._initialized = False
        
        if self.api_key and self.api_key != 'your-api-key-here':
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                self._initialized = True
                logger.info(f"🤖 Gemini OCR initialized (model: {self.model_name}, "
                           f"rate: {self.rate_limit_rpm} RPM)")
            except ImportError:
                logger.warning("google-genai package not installed. Run: pip install google-genai")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
        else:
            logger.info("Gemini OCR not configured (no API key)")
    
    @property
    def is_available(self) -> bool:
        """Check if Gemini is ready to use and has quota."""
        if not (self._initialized and self._client is not None):
            return False
            
        return self.usage_tracker.has_quota('gemini')
    
    def _rate_limit_wait(self):
        """
        Enforce thread-safe rate limiting to stay under RPM limit.
        Uses a lock to prevent parallel workers from bursting requests simultaneously.
        """
        # Be slightly more conservative than exactly 60/RPM to account for network jitter
        safe_interval = (60.0 / self.rate_limit_rpm) + 0.5 
        
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < safe_interval:
                wait_time = safe_interval - elapsed
                logger.info(f"  ⏳ Gemini Rate Limiter: waiting {wait_time:.1f}s (Queueing workers...)")
                time.sleep(wait_time)
            
            # Update the last call time BEFORE releasing the lock
            self._last_call_time = time.time()
    
    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """
        Convert PIL Image to JPEG bytes for Gemini API upload.

        WHY WE RESIZE:
        Gemini Vision charges tokens per 768×768 tile:
            tokens = 258 + (ceil(W/768) × ceil(H/768)) × 258
        A 400-DPI A4 page (3307×4677) costs ~9,288 tokens per image.
        At 10 RPM free-tier that's ~92,880 TPM — easily exceeds the limit.
        Capping at 1536px longest side → ≤ 4 tiles → ~1,290 tokens: 7× cheaper.
        OCR quality is not affected because Gemini up-samples internally.

        Config knob: GEMINI_MAX_IMAGE_PIXELS (default 1536)
        """
        orig_w, orig_h = image.size
        max_dim = getattr(config, 'GEMINI_MAX_IMAGE_PIXELS', 1536)

        if orig_w > max_dim or orig_h > max_dim:
            ratio = min(max_dim / orig_w, max_dim / orig_h)
            new_size = (int(orig_w * ratio), int(orig_h * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(
                f"  📐 Gemini resize: {orig_w}×{orig_h} → {new_size[0]}×{new_size[1]} "
                f"(max_dim={max_dim})"
            )

        buf = io.BytesIO()
        # Convert to RGB if needed (RGBA/P modes can't be saved as JPEG)
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        # quality=72: still excellent for Telugu OCR (Gemini upsamples),
        # but saves ~30% bytes vs q=85, reducing inline payload significantly.
        jpeg_quality = getattr(config, 'GEMINI_JPEG_QUALITY', 72)
        image.save(buf, format='JPEG', quality=jpeg_quality)
        payload = buf.getvalue()
        logger.debug(
            f"  📦 Gemini payload: {len(payload)/1024:.0f} KB "
            f"(q={jpeg_quality}, {image.size[0]}×{image.size[1]}px)"
        )
        return payload
    
    def extract_text(self, image: Image.Image, page_label: str = "") -> str:
        """
        Extract text from a page image using Gemini Vision.
        
        Args:
            image: PIL Image of the document page
            page_label: Optional label for logging (e.g., "[Page 19]")
            
        Returns:
            Extracted text string (empty string on failure)
        """
        if not self.is_available:
            logger.warning(f"{page_label} Gemini OCR not available — returning empty text")
            return ""
        
        # Conversion to bytes is fast and doesn't need to be locked
        image_bytes = self._image_to_bytes(image)
        
        # Retry loop — lock is acquired PER ATTEMPT, not for the entire session.
        # Sleep after a 429 happens OUTSIDE the lock so other threads can proceed.
        # _last_call_time is stamped before releasing, ensuring the next thread's
        # interval check sees the correct last-call time.
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                self.total_retries += 1
            else:
                self.usage_tracker.increment('gemini')
            
            wait_after = 0.0  # sleep time to apply AFTER releasing the lock
            result_text = None
            
            with GeminiOCRProcessor._lock:
                try:
                    # Enforce rate-limit interval
                    elapsed = time.time() - GeminiOCRProcessor._last_call_time
                    if elapsed < GeminiOCRProcessor._min_interval:
                        wait_time = GeminiOCRProcessor._min_interval - elapsed
                        logger.info(f"  ⏳ {page_label} Gemini Rate Limiter: waiting {wait_time:.1f}s")
                        time.sleep(wait_time)
                    
                    # Stamp time BEFORE the call so next thread knows a call is imminent
                    GeminiOCRProcessor._last_call_time = time.time()
                    
                    from google.genai import types
                    response = self._client.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                                    types.Part.from_text(text=self.OCR_PROMPT)
                                ]
                            )
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            max_output_tokens=8192,
                        )
                    )
                    # Stamp again after completion to account for processing time
                    GeminiOCRProcessor._last_call_time = time.time()
                    result_text = response.text.strip() if response.text else ""
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    # Always stamp on error so next thread waits the full interval
                    GeminiOCRProcessor._last_call_time = time.time()

                    # ── 404: wrong model name — fail immediately, do NOT retry ──────
                    # Retrying a 404 is pointless and wastes time burning through the
                    # rate-limit wait period for nothing.
                    if '404' in error_msg or 'not found' in error_msg or 'invalid model' in error_msg:
                        logger.error(
                            f"  🤖 {page_label} Gemini 404 — model '{self.model_name}' not found. "
                            f"Check GEMINI_MODEL in config.py. Error: {e}"
                        )
                        return ""

                    # ── 429 / resource exhausted: back off and retry ───────────────
                    elif '429' in error_msg or 'resource_exhausted' in error_msg or 'quota' in error_msg:
                        wait_after = GeminiOCRProcessor._min_interval
                        logger.warning(
                            f"  🤖 {page_label} Rate limited (attempt {attempt + 1}), "
                            f"releasing lock and waiting {wait_after:.1f}s..."
                        )

                    # ── Transient error: retry with short delay ────────────────────
                    elif attempt < self.max_retries:
                        wait_after = 5.0
                        logger.warning(
                            f"  🤖 {page_label} Gemini error (attempt {attempt + 1}): {e}, "
                            f"retrying in {wait_after}s..."
                        )
                    else:
                        logger.error(f"  🤖 {page_label} Gemini OCR failed after {attempt + 1} attempts: {e}")
                        return ""
            
            # --- Lock released here --- other threads can now acquire it ---
            
            if result_text is not None:
                if result_text:
                    logger.info(f"  🤖 {page_label} Gemini extracted {len(result_text)} chars (attempt {attempt + 1})")
                else:
                    logger.warning(f"  🤖 {page_label} Gemini returned empty text (attempt {attempt + 1})")
                return result_text
            
            if wait_after > 0:
                time.sleep(wait_after)  # Sleep WITHOUT holding the lock
        
        return ""
    
    def extract_text_deep(self, image: Image.Image, page_label: str = "") -> str:
        """
        Deep-scan variant of extract_text.
        Uses a more aggressive prompt and slightly higher temperature.
        Called as Escalation Level 2 when the standard Gemini pass misses significant lines.
        """
        if not self.is_available:
            logger.warning(f"{page_label} Gemini OCR not available — returning empty text")
            return ""
        
        image_bytes = self._image_to_bytes(image)
        
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                self.total_retries += 1
            else:
                self.usage_tracker.increment('gemini')
            
            wait_after = 0.0
            result_text = None
            
            with GeminiOCRProcessor._lock:
                try:
                    elapsed = time.time() - GeminiOCRProcessor._last_call_time
                    if elapsed < GeminiOCRProcessor._min_interval:
                        wait_time = GeminiOCRProcessor._min_interval - elapsed
                        logger.info(f"  ⏳ {page_label} Gemini DeepScan Rate Limiter: waiting {wait_time:.1f}s")
                        time.sleep(wait_time)
                    
                    GeminiOCRProcessor._last_call_time = time.time()
                    
                    from google.genai import types
                    response = self._client.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                                    types.Part.from_text(text=self.DEEP_SCAN_PROMPT)
                                ]
                            )
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            max_output_tokens=8192,
                        )
                    )
                    GeminiOCRProcessor._last_call_time = time.time()
                    result_text = response.text.strip() if response.text else ""
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    GeminiOCRProcessor._last_call_time = time.time()

                    # ── 404: wrong model name — fail immediately ───────────────────
                    if '404' in error_msg or 'not found' in error_msg or 'invalid model' in error_msg:
                        logger.error(
                            f"  🔬 {page_label} DeepScan 404 — model '{self.model_name}' not found. "
                            f"Check GEMINI_MODEL in config.py. Error: {e}"
                        )
                        return ""

                    # ── 429 / resource exhausted: back off and retry ───────────────
                    elif '429' in error_msg or 'resource_exhausted' in error_msg or 'quota' in error_msg:
                        wait_after = GeminiOCRProcessor._min_interval
                        logger.warning(
                            f"  🔬 {page_label} DeepScan rate limited (attempt {attempt + 1}), "
                            f"releasing lock and waiting {wait_after:.1f}s..."
                        )

                    # ── Transient error: retry with short delay ────────────────────
                    elif attempt < self.max_retries:
                        wait_after = 5.0
                        logger.warning(
                            f"  🔬 {page_label} Gemini DeepScan error (attempt {attempt + 1}): {e}, "
                            f"retrying in {wait_after}s..."
                        )
                    else:
                        logger.error(f"  🔬 {page_label} Gemini DeepScan failed after {attempt + 1} attempts: {e}")
                        return ""
            
            # --- Lock released --- other threads can now proceed ---
            
            if result_text is not None:
                if result_text:
                    logger.info(f"  🔬 {page_label} Gemini DeepScan extracted {len(result_text)} chars (attempt {attempt + 1})")
                else:
                    logger.warning(f"  🔬 {page_label} Gemini DeepScan returned empty text (attempt {attempt + 1})")
                return result_text
            
            if wait_after > 0:
                time.sleep(wait_after)  # Sleep WITHOUT holding the lock
        
        return ""
    
    def extract_text_with_references(self, image: Image.Image, paddle_text: str,
                                      tesseract_text: str, page_label: str = "") -> str:
        """
        Reference-grounded variant of extract_text: gives Gemini the page image
        PLUS PaddleOCR's and Tesseract's independent readings of it, and asks it
        to reconcile them against what it actually sees rather than transcribe
        from scratch. See REFERENCE_GROUNDED_PROMPT for the rationale. Gated by
        ENABLE_GEMINI_REFERENCE_GROUNDING (config.py) at the call site.
        """
        if not self.is_available:
            logger.warning(f"{page_label} Gemini OCR not available — returning empty text")
            return ""

        from ocr_text_diff import compute_word_diff_spans, summarize_diff_spans
        diff_spans = compute_word_diff_spans(paddle_text, tesseract_text)
        diff_summary = summarize_diff_spans(diff_spans, label_a='Paddle', label_b='Tesseract')
        prompt = self.REFERENCE_GROUNDED_PROMPT.format(
            paddle_text=paddle_text or '(empty — this engine produced no text)',
            tesseract_text=tesseract_text or '(empty — this engine produced no text)',
            diff_summary=diff_summary,
        )

        image_bytes = self._image_to_bytes(image)

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                self.total_retries += 1
            else:
                self.usage_tracker.increment('gemini')

            wait_after = 0.0
            result_text = None

            with GeminiOCRProcessor._lock:
                try:
                    elapsed = time.time() - GeminiOCRProcessor._last_call_time
                    if elapsed < GeminiOCRProcessor._min_interval:
                        wait_time = GeminiOCRProcessor._min_interval - elapsed
                        logger.info(f"  ⏳ {page_label} Gemini RefGround Rate Limiter: waiting {wait_time:.1f}s")
                        time.sleep(wait_time)

                    GeminiOCRProcessor._last_call_time = time.time()

                    from google.genai import types
                    response = self._client.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                                    types.Part.from_text(text=prompt)
                                ]
                            )
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            max_output_tokens=8192,
                        )
                    )
                    GeminiOCRProcessor._last_call_time = time.time()
                    result_text = response.text.strip() if response.text else ""

                except Exception as e:
                    error_msg = str(e).lower()
                    GeminiOCRProcessor._last_call_time = time.time()

                    # ── 404: wrong model name — fail immediately ───────────────────
                    if '404' in error_msg or 'not found' in error_msg or 'invalid model' in error_msg:
                        logger.error(
                            f"  🧭 {page_label} RefGround 404 — model '{self.model_name}' not found. "
                            f"Check GEMINI_MODEL in config.py. Error: {e}"
                        )
                        return ""

                    # ── 429 / resource exhausted: back off and retry ───────────────
                    elif '429' in error_msg or 'resource_exhausted' in error_msg or 'quota' in error_msg:
                        wait_after = GeminiOCRProcessor._min_interval
                        logger.warning(
                            f"  🧭 {page_label} RefGround rate limited (attempt {attempt + 1}), "
                            f"releasing lock and waiting {wait_after:.1f}s..."
                        )

                    # ── Transient error: retry with short delay ────────────────────
                    elif attempt < self.max_retries:
                        wait_after = 5.0
                        logger.warning(
                            f"  🧭 {page_label} Gemini RefGround error (attempt {attempt + 1}): {e}, "
                            f"retrying in {wait_after}s..."
                        )
                    else:
                        logger.error(f"  🧭 {page_label} Gemini RefGround failed after {attempt + 1} attempts: {e}")
                        return ""

            # --- Lock released --- other threads can now proceed ---

            if result_text is not None:
                if result_text:
                    logger.info(f"  🧭 {page_label} Gemini RefGround extracted {len(result_text)} chars (attempt {attempt + 1})")
                else:
                    logger.warning(f"  🧭 {page_label} Gemini RefGround returned empty text (attempt {attempt + 1})")
                return result_text

            if wait_after > 0:
                time.sleep(wait_after)  # Sleep WITHOUT holding the lock

        return ""

    def extract_text_with_semaphore(self, image: Image.Image, semaphore) -> str:
        """
        Extract text with a semaphore for concurrency control.
        Compatible with the AdaptiveOCRFactory interface.
        """
        with semaphore:
            return self.extract_text(image)
    
    def verify_telugu_support(self) -> bool:
        """Gemini natively supports Telugu — always returns True."""
        return True
    
    def get_available_languages(self) -> list:
        """Return supported languages."""
        return ['tel', 'eng', 'tel+eng']
    
    def auto_rotate(self, image: Image.Image) -> Image.Image:
        """Pass-through — Gemini handles rotation internally."""
        return image

    def get_stats(self) -> dict:
        """Return API usage statistics."""
        stats = self.usage_tracker.get_usage('gemini')
        return {
            'total_calls': stats['calls'],
            'total_retries': self.total_retries,
            'quota': stats['quota']
        }
