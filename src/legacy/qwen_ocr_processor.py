"""
Qwen OCR Processor via Ollama
Calls Qwen2.5-VL running in Ollama on Windows from WSL over HTTP.
Handles mid-complexity pages (30-80%): TOC, mixed image+text, word/line anomalies.
"""
import io
import base64
import time
import logging
import socket
import requests
from typing import Optional
from PIL import Image

import config
from logging_config import get_logger

logger = get_logger(__name__)


def _get_ollama_host() -> str:
    """
    Auto-detect the Windows host IP from WSL.
    Falls back to localhost if running natively on Windows or if detection fails.
    """
    # If explicitly configured, use that
    configured = getattr(config, 'QWEN_OLLAMA_HOST', '')
    if configured:
        return configured

    # On Windows, always use localhost
    if getattr(config, 'IS_WINDOWS', True):
        return 'localhost'

    # Try to detect host IP in WSL/Linux
    try:
        # Method 1: Get gateway from 'ip route' (most reliable in WSL2)
        import subprocess
        cmd = "ip route show default | awk '{print $3}'"
        res = subprocess.check_output(cmd, shell=True, text=True).strip()
        if res:
            logger.debug(f"Detected Windows host IP via ip route: {res}")
            return res
    except Exception:
        pass

    # Method 2: Fallback to /etc/resolv.conf
    try:
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if line.startswith('nameserver'):
                    ip = line.split()[1].strip()
                    logger.debug(f"Detected Windows host IP from resolv.conf: {ip}")
                    return ip
    except (FileNotFoundError, IndexError):
        pass

    return 'localhost'


class QwenOCRProcessor:
    """
    OCR processor using Qwen2.5-VL via Ollama HTTP API.

    Designed for mid-complexity pages that Tesseract struggles with but
    don't justify spending precious Gemini/Google Vision quota:
    - TOC pages (table of contents with dot leaders etc.)
    - Pages with word/line count anomalies
    - Mixed image + text pages
    - Multi-column layouts with moderate complexity
    """

    # Telugu+English OCR prompt for Qwen (cold — no prior OCR available)
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
   - For tables/TOC: preserve the row structure with tab spacing

4. **Formatting & Line Preservation**:
   - PRESERVE exact line breaks as they appear in the image.
   - Do NOT merge lines or paragraphs.
   - Use double newlines only where there is a clear physical gap in the image.
   - Do NOT add page numbers, headers, or footers (skip them entirely).
   - Do NOT describe images or illustrations.
   - Do NOT add any commentary or explanations.

5. **Output**: Return ONLY the extracted text, nothing else. No markdown, no labels, no prefixes."""

    # Correction prompt — used when Tesseract draft text is available.
    # Qwen acts as a proofreader: it sees BOTH the image and the draft and
    # corrects misreads, missing lines, and garbled Telugu characters.
    OCR_CORRECTION_PROMPT_TEMPLATE = """You are an expert Telugu (తెలుగు) and English OCR correction system.

You are given:
1. A scanned document page image.
2. A DRAFT OCR text produced by Tesseract (may contain errors).

Your job is to CORRECT the draft using the image as the authoritative source. Rules:

1. **Fix Telugu errors**: Correct misread compound characters, vowel signs, and danda marks.
   - Common Tesseract mistakes: Sn/Fu/En for శ్లో, garbled vattu/guninthaalu.
2. **Fix English errors**: Correct obvious misread English words and numbers.
3. **Restore missing lines**: If the draft skipped lines visible in the image, add them in the correct position.
4. **Preserve correct parts**: DO NOT change text that appears correctly in the draft.
5. **Reading order**: Top to bottom for single column; left then right for two-column layouts.
6. **Do NOT add** page numbers, headers, footers, commentary, or markdown.
7. **Output**: Return ONLY the corrected text — no explanations, no labels, no prefixes.

--- TESSERACT DRAFT (correct this using the image) ---
{tesseract_draft}
--- END OF DRAFT ---

Now output the corrected text:"""

    def __init__(self):
        self.model = getattr(config, 'QWEN_MODEL', 'qwen2.5vl:7b')
        self.port = getattr(config, 'QWEN_OLLAMA_PORT', 11434)
        self.timeout = getattr(config, 'QWEN_TIMEOUT', 60)

        self._host = _get_ollama_host()
        self._base_url = f"http://{self._host}:{self.port}"
        self._available = None  # Lazy check

    @property
    def is_available(self) -> bool:
        """Check if Ollama is reachable and the model is loaded."""
        if self._available is None:
            self._available = self._check_ollama()
        return self._available

    def _check_ollama(self) -> bool:
        """Ping Ollama to verify connectivity and model availability."""
        try:
            response = requests.get(
                f"{self._base_url}/api/tags",
                timeout=5
            )
            if response.status_code != 200:
                logger.warning(f"Ollama reachable but returned status {response.status_code}")
                return False

            models = [m['name'] for m in response.json().get('models', [])]
            
            # Check if our model (or a prefix match) is available
            model_base = self.model.split(':')[0]
            match = any(m.startswith(model_base) for m in models)
            
            if match:
                logger.info(f"🧩 Qwen via Ollama ready at {self._base_url} (model: {self.model})")
            else:
                logger.warning(
                    f"Ollama running but model '{self.model}' not found. "
                    f"Available: {models}. Run: ollama pull {self.model}"
                )
            return match

        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Ollama not reachable at {self._base_url}. "
                f"Start Ollama on Windows with OLLAMA_HOST=0.0.0.0"
            )
            return False
        except Exception as e:
            logger.warning(f"Ollama availability check failed: {e}")
            return False

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to Base64-encoded JPEG string for Ollama."""
        # Resize if very large to keep payload small
        w, h = image.size
        max_dim = 768  # Further reduced for performance (timeout safety)
        if w > max_dim or h > max_dim:
            ratio = min(max_dim / w, max_dim / h)
            image = image.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        image.save(buf, format='JPEG', quality=85)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    def extract_text(self, image: Image.Image, tesseract_hint: str = "") -> str:
        """
        Extract text from a page image using Qwen2.5-VL via Ollama.

        Args:
            image:           PIL Image of the document page.
            tesseract_hint:  Optional Tesseract draft text.  When provided
                             (and QWEN_USE_TESSERACT_HINT=True in config),
                             Qwen acts as a correction engine rather than
                             doing a cold OCR pass, significantly improving
                             accuracy on Telugu compound characters.

        Returns:
            Extracted (or corrected) text string; empty string on failure.
        """
        if not self.is_available:
            logger.warning("Qwen OCR (Ollama) not available — returning empty text")
            return ""

        image_b64 = self._image_to_base64(image)

        # Choose prompt: correction mode when hint provided and feature enabled
        use_hint = (
            bool(tesseract_hint and tesseract_hint.strip())
            and getattr(config, 'QWEN_USE_TESSERACT_HINT', True)
        )

        if use_hint:
            prompt = self.OCR_CORRECTION_PROMPT_TEMPLATE.format(
                tesseract_draft=tesseract_hint.strip()
            )
            logger.info(
                f"  🧩 Qwen: correction mode — Tesseract draft ({len(tesseract_hint)} chars) "
                f"sent as hint alongside image"
            )
        else:
            prompt = self.OCR_PROMPT
            logger.debug("  🧩 Qwen: cold OCR mode (no Tesseract hint)")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
                "num_ctx": 1024,
            }
        }

        try:
            start = time.time()
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            elapsed = time.time() - start

            if response.status_code != 200:
                err_msg = response.text[:500]
                if "requires more system memory" in err_msg:
                    logger.error(f"  🧩 Qwen OOM (Out of Memory): {err_msg}")
                    raise RuntimeError(f"Qwen OOM: {err_msg}")
                else:
                    logger.error(f"  🧩 Qwen API error {response.status_code}: {err_msg}")
                    raise RuntimeError(f"Qwen API error {response.status_code}")

            text = response.json().get('response', '').strip()

            if text:
                mode_tag = "corrected" if use_hint else "extracted"
                logger.info(f"  🧩 Qwen {mode_tag} {len(text)} chars in {elapsed:.1f}s")
            else:
                logger.warning("  🧩 Qwen returned empty text")

            return text

        except requests.exceptions.Timeout:
            logger.error(f"  🧩 Qwen OCR timed out after {self.timeout}s")
            return ""
        except Exception as e:
            logger.error(f"  🧩 Qwen OCR failed: {e}")
            raise

    def extract_text_with_semaphore(self, image: Image.Image, semaphore,
                                     tesseract_hint: str = "") -> str:
        """Extract text with semaphore for concurrency control."""
        with semaphore:
            return self.extract_text(image, tesseract_hint=tesseract_hint)

    def verify_telugu_support(self) -> bool:
        """Qwen2.5-VL natively supports Telugu — returns True."""
        return True

    def get_available_languages(self) -> list:
        return ['tel', 'eng', 'tel+eng']

    def auto_rotate(self, image: Image.Image) -> Image.Image:
        """Pass-through — Qwen handles rotation via vision understanding."""
        return image

    def get_stats(self) -> dict:
        return {
            'host': self._host,
            'model': self.model,
            'available': self._available
        }
