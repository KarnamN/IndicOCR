"""
Optimized PDF to EPUB Converter
Performance improvements for large books with low-quality scans
"""
import fitz  # PyMuPDF
from PIL import Image
import io
import os
import logging
import gc
import time
import joblib
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple, Any
import argparse
import uuid
import shutil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import numpy as np

import config
from ocr_processor import OCRProcessor
from fast_table_detector import FastTableDetector
from epub_builder import EPUBBuilder
from page_splitter import PageSplitter
from adaptive_ocr_factory import AdaptiveOCRFactory
from page_complexity_analyzer import PageComplexityAnalyzer
from layout_analyzer import LayoutAnalyzer
from telugu_post_processor import post_process_telugu, post_process_telugu_with_corrections
from cleanup_manager import CleanupManager

from logging_config import get_logger
logger = get_logger(__name__)
class OptimizedPDFToEPUBConverter:
    """Optimized PDF to EPUB converter with streaming and parallel processing"""
    
    def __init__(self, language: str = None, dpi: int = None,
                 detect_tables: bool = True, preserve_images: bool = True,
                 skip_empty_cells: bool = True, max_workers: int = None,
                 split_double_pages: bool = True, split_threshold: float = None,
                 require_spine_confirmation: bool = True,
                 enable_parallel: bool = True, batch_size: int = None,
                 skip_ocr_pages: list = None,
                 only_pages: list = None,
                 session_id: str = None,
                 enable_rescue: bool = True,
                 progress_callback: Optional[Callable[[str, int, int], None]] = None):
        """
        Initialize optimized converter
        
        Args:
            language: OCR language code
            dpi: DPI for PDF to image conversion
            detect_tables: Whether to detect tables
            preserve_images: Whether to preserve images
            skip_empty_cells: Skip OCR on empty cells (performance boost)
            max_workers: Number of parallel workers for OCR
            split_double_pages: Auto-detect and split double-page scans
            require_spine_confirmation: Require a detected central spine gutter before
                splitting a wide page (default True). Set False for corpora that are
                always genuine double-page spreads but have faint/worn gutters that
                the pixel-projection spine check can miss.
            enable_parallel: Enable parallel page processing
            batch_size: Number of pages to process in parallel (auto-calculated if None)
            skip_ocr_pages: List of page numbers to skip OCR (preserve as images only)
            only_pages: List of page numbers to process (if specified, ALL other pages are ignored)
            progress_callback: Optional callback function(stage, current, total)
        """
        self.language = language or config.DEFAULT_OCR_LANGUAGE
        self.dpi = dpi or config.DEFAULT_DPI
        self.detect_tables = detect_tables
        self.preserve_images = preserve_images
        self.skip_empty_cells = skip_empty_cells
        self.max_workers = max_workers or (config.MAX_WORKERS or 4)
        self.split_double_pages = split_double_pages
        self.enable_parallel = enable_parallel
        self.batch_size = batch_size or self._calculate_batch_size()
        self.skip_ocr_pages = set(skip_ocr_pages or [])  # Convert to set for O(1) lookup
        self.only_pages = set(only_pages or [])  # Convert to set for O(1) lookup
        self.progress_callback = progress_callback
        
        # Cancellation support
        import threading
        self._cancelled = threading.Event()
        self._cancel_lock = threading.Lock()
        
        # Disk-backing for RAM reduction - will be set during convert_streaming
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.temp_results_dir = None  # Will be created with title in convert_streaming
        self.page_result_paths = {}  # Map page_num -> file_path
        self.book_title = None  # Will be set during conversion
        
        # Initialize processors
        self.adaptive_factory = AdaptiveOCRFactory()
        self.ocr_processor = OCRProcessor(language=self.language) # Default for rotation/simple tasks
        self.layout_analyzer = LayoutAnalyzer()  # Layout-first router
        # Strictly obey config.ENABLE_TABLE_DETECTION
        is_table_enabled = detect_tables and getattr(config, 'ENABLE_TABLE_DETECTION', True)
        self.table_detector = FastTableDetector() if is_table_enabled else None
        self.page_splitter = PageSplitter(
            aspect_ratio_threshold=split_threshold or 1.15,
            require_spine_confirmation=require_spine_confirmation,
        ) if split_double_pages else None
        
        # QUALITY AUDIT & ANALYTICS
        self.rescue_report = []  # List of dicts for each rescued page
        self.quality_warnings = []  # List of general quality warnings
        self.ocr_discrepancies = 0  # Counter for pages with skipped lines
        self.gemini_stats = {"direct": 0, "rescue": 0}  # Tracking Gemini usage
        self.tesseract_pages = 0
        self.enable_rescue_toggle = enable_rescue
        
        # PADDLE HEALTH MONITORING
        self._paddle_degraded = False      # True once crash threshold hit
        self._alert_emitted   = False      # Prevent duplicate alerts
        self._pages_processed = 0         # Count of pages completed (for Gemini % calc)
        self._gemini_pages    = 0         # Count of Gemini-handled pages
        self.alert_callback   = None      # Set by app.py: fn(job_id, alert_dict)
        
        # ADAPTIVE TESSERACT_MIN_SAFE_LINES TRACKER
        self._clean_page_line_counts = []
        self._line_count_lock = threading.Lock()

        # STAGE-2 (OCR) CONCURRENCY SUB-THROTTLE
        # The outer thread pool (self.max_workers, sized in convert_streaming) caps
        # total concurrent pages, which naturally bounds Stage-1 (analysis +
        # enhancement) concurrency too — it isn't lock-bound, so no separate gate
        # is needed there. Stage 2 (the actual OCR call) IS bound by a single
        # engine lock in paddle_v5_processor.py on the WSL/Paddle-primary path, so
        # more Stage-2 concurrency just queues rather than adding throughput. This
        # semaphore lets Stage 1 run at the outer pool's full width while capping
        # how many pages can be inside the OCR portion at once, independent of that.
        stage2_workers = int(os.environ.get(
            'OCR_STAGE2_WORKERS', getattr(config, 'STAGE2_WORKERS', self.max_workers)))
        self._stage2_semaphore = threading.Semaphore(max(1, stage2_workers))
        self._stage1_memory_floor_gb = getattr(config, 'STAGE1_MEMORY_FLOOR_GB', 1.5)
        logger.info(f"Stage concurrency: analysis≈{self.max_workers} (outer pool), "
                    f"OCR≤{stage2_workers} (sub-throttle)")

        # STRUCTURED EVENT LOG (converter_events.jsonl) — see _log_event(). Guarded
        # by an explicit lock rather than relying on OS-level atomic-append
        # guarantees, since temp_results_dir lives under WSL's /mnt/c (a DrvFs/9p
        # mount), where those guarantees are less certain than on a native
        # Linux filesystem.
        self._events_log_lock = threading.Lock()

        logger.info(f"Optimized Converter initialized: language={self.language}, "
                   f"dpi={self.dpi}, workers={self.max_workers}")
        logger.info(f"preserve_images={self.preserve_images}, detect_tables={self.detect_tables}")
        logger.info(f"parallel_processing={self.enable_parallel}, batch_size={self.batch_size}")
        
        # Auto-clean leaked Tesseract temp files at startup
        CleanupManager.cleanup_tesseract_leaks()
        if self.skip_ocr_pages:
            logger.info(f"Skip OCR on pages: {sorted(self.skip_ocr_pages)}")
        if self.only_pages:
            logger.info(f"ONLY processing pages: {sorted(self.only_pages)}")
    
    def cancel(self):
        """Cancel the current conversion. Safe to call from any thread."""
        self._cancelled.set()
        logger.warning("🛑 Cancellation requested — will stop after current batch completes")

    def emit_health_alert(self, alert_type: str, **kwargs):
        """Emit a health alert to the UI via the alert_callback set by app.py."""
        if self.alert_callback:
            try:
                self.alert_callback(alert_type, kwargs)
            except Exception as e:
                logger.warning(f"Alert callback error: {e}")
    
    @property
    def is_cancelled(self) -> bool:
        """Check if conversion has been cancelled."""
        return self._cancelled.is_set()
    
    def _calculate_batch_size(self) -> int:
        """
        Calculate optimal batch size based on available RAM
        
        Returns:
            Optimal batch size for parallel processing
        """
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024**3)
            # Conservative: assume 10MB per page, use 30% of available RAM
            calculated = min(self.max_workers, max(2, int(available_gb * 0.3 / 0.01)))
            logger.info(f"[batch-size] Auto-calculated batch size: {calculated} (available RAM: {available_gb:.1f}GB, assumes 10MB/page)")
            return calculated
        except ImportError:
            logger.warning("psutil not available, using default batch size")
            return 4  # Safe default
        except Exception as e:
            logger.warning(f"Failed to calculate batch size: {e}, using default")
            return 4
    
    def _save_page_result(self, page_result: Dict) -> Path:
        """Save a page result to disk and return the path."""
        page_num = page_result['page_num']
        sub_idx = page_result.get('sub_idx', 0)
        # Use sub_idx in filename to prevent overwrites on split pages
        file_path = self.temp_results_dir / f"page_{page_num}_{sub_idx}.jbl"
        joblib.dump(page_result, file_path)
        return file_path

    
    def _load_page_result(self, file_path: Path) -> Dict:
        """Load a page result from disk."""
        return joblib.load(file_path)
    
    def _cleanup_memory(self):
        """Aggressive memory cleanup to prevent OOM in WSL"""
        import gc
        
        # Force garbage collection multiple times for thorough cleanup
        for _ in range(3):
            gc.collect()
        
        # Clear PyTorch cache if available (EasyOCR uses PyTorch)
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"PyTorch cache clear failed: {e}")
        
        logger.debug("Aggressive memory cleanup completed")

    def _stage1_memory_preflight(self, page_num: int):
        """
        Live memory check before a page starts Stage 1 (analysis+enhancement).

        Unlike the three pre-existing static per-worker memory guesses elsewhere
        in this file (10MB/page, 1.1GB/worker, 600MB/page — none ever empirically
        validated, none have ever fired in this project's log history), this is a
        real-time check against a measured floor. It's a no-op in the normal case
        (this project has never actually hit memory pressure) and only matters for
        the tail case of an unusually memory-hungry page or external WSL pressure.
        Bounded backoff — never waits forever, so it can't deadlock the pipeline.
        """
        try:
            import psutil
        except ImportError:
            return
        max_wait_s = 30
        waited_s = 0
        warned = False
        while waited_s < max_wait_s:
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
            if available_gb >= self._stage1_memory_floor_gb:
                return
            if not warned:
                logger.warning(
                    f"⚠️ [stage1-preflight] Low Memory Alert: {available_gb:.1f}GB available "
                    f"(floor {self._stage1_memory_floor_gb}GB) — Page {page_num + 1} "
                    f"backing off Stage 1 until memory recovers"
                )
                self._log_event('memory_backoff', page_num=page_num + 1,
                                available_gb=round(available_gb, 2),
                                floor_gb=self._stage1_memory_floor_gb,
                                resolved=False)
                warned = True
            time.sleep(1)
            waited_s += 1
        if warned:
            logger.warning(
                f"⚠️ Page {page_num + 1}: proceeding after {max_wait_s}s memory "
                f"backoff — memory still below floor, continuing anyway rather "
                f"than hanging indefinitely"
            )
            self._log_event('memory_backoff', page_num=page_num + 1,
                            available_gb=round(psutil.virtual_memory().available / (1024**3), 2),
                            floor_gb=self._stage1_memory_floor_gb,
                            resolved=False, gave_up_after_s=max_wait_s)

    def _log_event(self, event_type: str, **fields):
        """
        Append one structured JSON event to converter_events.jsonl — the
        machine/agent-parseable sidecar to the human-readable converter.log.
        One JSON object per line (json.loads()-able independently), so an agent
        can answer questions like "what's broken" or "how did memory/timing
        behave" by loading this file directly instead of regex-scraping free
        text. Streams in real time (unlike quality_report.json, which is only
        written once at the very end and would be missing if a run crashes
        partway through). Fire-and-forget: a logging failure must never break
        page processing, so exceptions are swallowed (logged at DEBUG only).
        """
        if self.temp_results_dir is None:
            return
        try:
            import json as _json
            record = {
                'timestamp': time.time(),
                'event_type': event_type,
                'book_title': self.book_title,
            }
            record.update(fields)
            line = _json.dumps(record, ensure_ascii=False, default=str)
            events_path = self.temp_results_dir / "converter_events.jsonl"
            with self._events_log_lock:
                with open(events_path, 'a', encoding='utf-8') as f:
                    f.write(line + "\n")
        except Exception as e:
            logger.debug(f"Failed to write structured event ({event_type}): {e}")

    def _log_memory_usage(self, stage: str):
        """Log current memory usage and return available MB"""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            
            vm = psutil.virtual_memory()
            available_mb = vm.available / (1024 * 1024)
            percent_used = vm.percent
            
            logger.info(f"📊 [{stage}] Process: {mem_mb:.0f}MB | Available: {available_mb:.0f}MB | System: {percent_used}% used")
            return available_mb
        except Exception as e:
            logger.debug(f"Memory logging failed: {e}")
            return 4096 # Fallback to assume plenty of memory
            
    def _get_dynamic_batch_size(self, requested_batch_size: int) -> int:
        """Calculate batch size based on available system memory to prevent OOM"""
        try:
            import psutil
            vm = psutil.virtual_memory()
            available_gb = vm.available / (1024 * 1024 * 1024)
            
            # Heuristic: Each parallel page takes ~400-600MB
            # We want to keep at least 1GB free for system safety
            safe_available = max(0, available_gb - 1.0)
            target_batch = int(safe_available / 0.6) # 600MB per page
            
            # Clamp between 1 and the requested batch size
            final_batch = max(1, min(target_batch, requested_batch_size))
            
            if final_batch < requested_batch_size:
                logger.warning(f"⚠️ [dynamic-batch] Low Memory Alert: {available_gb:.1f}GB available (assumes 600MB/page). Throttling batch size {requested_batch_size} → {final_batch}")
            
            return final_batch
        except Exception:
            return requested_batch_size
    
    def _export_page_text_json(self, page_result: Dict) -> Path:
        """Export page text to JSON for debugging/archival."""
        page_num = page_result['page_num']
        sub_idx = page_result.get('sub_idx', 0)
        json_path = self.temp_results_dir / f"page_{page_num}_{sub_idx}_text.json"
        
        import json
        export_data = {
            'page_num': page_num,
            'sub_idx': sub_idx,
            'text': page_result.get('text', ''),
            'text_length': len(page_result.get('text', '')),
            'ocr_engine': page_result.get('ocr_engine', 'unknown'),
            'complexity_score': round(page_result.get('complexity_score', 0.0), 1),
            'skipped_ocr': page_result.get('skipped_ocr', False),
            'tables_count': len(page_result.get('tables', [])),
            'images_count': len(page_result.get('images', [])),
            'is_cover': page_result.get('is_cover', False),
            'reasoning': page_result.get('reasoning', ''),
            # Dictionary spell-correction review status — see
            # docs/TELUGU_SPELL_CORRECTION_TODO.md. Empty/False when the feature is
            # off or this page had no corrections.
            'dictionary_corrections': page_result.get('dictionary_corrections', []),
            'needs_manual_review': page_result.get('needs_manual_review', False),
            'needs_gemini_validation': page_result.get('needs_gemini_validation', False),
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return json_path

    def _update_progress(self, stage: str, current: int, total: int):
        """Update progress via callback"""
        if self.progress_callback:
            try:
                self.progress_callback(stage, current, total)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
    def _is_cell_empty(self, image: Image.Image, threshold: float = 0.95) -> bool:
        """
        Check if cell is mostly whitespace
        
        Args:
            image: Cell image
            threshold: Fraction of white pixels to consider empty
            
        Returns:
            True if cell is empty
        """
        try:
            gray = np.array(image.convert('L'))
            white_pixels = np.sum(gray > 240)
            total_pixels = gray.size
            
            is_empty = (white_pixels / total_pixels) > threshold
            return is_empty
        except Exception:
            return False
    
    def _run_escalation_ladder(self, image: Image.Image, thread_id: str, 
                               primary_psm: int, threshold: float, page_num: int, 
                               current_text: str, estimated_lines: int) -> Tuple[str, bool, str]:
        """Escalates OCR to higher-tier engines if the primary pass was unsatisfactory."""
        best_text = current_text
        best_lines = PageComplexityAnalyzer.get_text_line_count(current_text)
        is_currently_junk = self._is_text_junk(current_text)
        
        # Build escalation engines
        ladder = []
        
        # Level 1: Tesseract Fallback (flip PSM)
        fallback_psm = 6 if primary_psm == 3 else 3
        ladder.append((f'tesseract_psm{fallback_psm}', 'tesseract'))
        
        # Level 2: Gemini (Rescue tier)
        if getattr(config, 'ENABLE_GEMINI_OCR', False) and getattr(config, 'GEMINI_AVAILABLE', False):
            ladder.append(('gemini', 'gemini'))

        if not ladder:
            return current_text, False, ''

        # --- AUDIT LOGGING (The "Human Verification" Chance) ---
        if not getattr(config, 'ENABLE_AUTOMATIC_GEMINI_RESCUE', False):
            # Only allow Tesseract fallback, block Gemini unless authorized
            logger.warning(f"  [Page {page_num}] 🔎 AUDIT: Escalation triggered (hallucination or missing lines).")
            logger.warning(f"             Tesseract junk: {is_currently_junk}")
            logger.warning(f"             Lines: {best_lines} / ~{estimated_lines} estimated.")
            
            # Filter gemini out of the ladder if automatic rescue is blocked
            ladder = [e for e in ladder if 'gemini' not in e[0]]
            if not ladder: return current_text, False, ''

        for engine_name, engine_type in ladder:
            # TRACKING: Count Gemini rescue attempts
            if 'gemini' in engine_name:
                self.gemini_stats["rescue"] += 1
                
            try:
                proc = self.adaptive_factory._get_cached_processor(engine_type, self.language)
                current_page_label = f"[Page {page_num}]"
                
                # Standard extraction only (No DeepScan to save budget)
                if engine_type == 'tesseract':
                    res_text = proc.extract_text(image, psm=fallback_psm, page_label=current_page_label)
                elif engine_type == 'gemini' and getattr(config, 'ENABLE_GEMINI_REFERENCE_GROUNDING', False):
                    ref_paddle_text, ref_tess_text = self._get_reference_texts(image, page_label=current_page_label)
                    res_text = proc.extract_text_with_references(
                        image, ref_paddle_text, ref_tess_text, page_label=current_page_label)
                else:
                    res_text = proc.extract_text(image, page_label=current_page_label)
                
                res_lines = PageComplexityAnalyzer.get_text_line_count(res_text)
                res_is_junk = self._is_text_junk(res_text)
                
                # BUDGET-FRIENDLY ACCEPTANCE LOGIC:
                if engine_type == 'gemini':
                    if not res_is_junk and res_lines > 0:
                        # Check for quality gap
                        if res_lines < (estimated_lines * threshold):
                            logger.warning(
                                f"    {current_page_label} ⚠️ Quality below {threshold*100:.0f}% "
                                f"({res_lines}/{estimated_lines} lines). "
                                f"Accepting anyway — Gemini gave best available result."
                            )
                            # Note: estimated_lines is a heuristic from horizontal projection
                            # and can overcount (sub-character strokes, illustration borders).
                            # A gap warning does NOT mean the text is wrong — just that fewer
                            # lines were detected vs the projection estimate.
                        else:
                            logger.info(f"    {current_page_label} ✅ Gemini rescue successful ({res_lines} lines).")

                        return res_text, True, engine_name
                
                # Tesseract Acceptance — two-tier logic:
                # Tier 1 (Strong): PSM fallback meets the full rescue threshold → accept.
                # Tier 2 (Soft):   PSM fallback is a significant improvement (≥30% more lines
                #                  than primary AND ≥45% of estimated) → accept and skip Gemini.
                #                  This saves an expensive Gemini call for pages where Tesseract
                #                  is doing much better on the 2nd try.
                if is_currently_junk:
                    if not res_is_junk and res_lines > (estimated_lines * 0.2):
                        logger.info(f"    {current_page_label} ✅ Accepted ({engine_name.upper()}) - CLEAN text found ({res_lines} lines)")
                        return res_text, True, engine_name
                else:
                    # Tier 1: strong acceptance — meets full threshold
                    if not res_is_junk and res_lines > best_lines and res_lines >= (estimated_lines * threshold):
                        logger.info(f"    {current_page_label} ✅ Accepted ({engine_name.upper()}) - meets threshold ({res_lines}/{estimated_lines} lines)")
                        return res_text, True, engine_name
                    
                    # Tier 2: soft acceptance — significant improvement, skip Gemini
                    # Only applies to Tesseract PSM fallback (not Gemini logic)
                    if engine_type == 'tesseract' and not res_is_junk:
                        is_significant_improvement = (
                            res_lines > best_lines * 1.3          # ≥30% more lines than primary
                            and res_lines >= estimated_lines * 0.45  # ≥45% of total estimated
                        )
                        if is_significant_improvement:
                            logger.info(f"    {current_page_label} ✅ Accepted ({engine_name.upper()}) - significant improvement "
                                        f"({best_lines}→{res_lines} lines, {res_lines/max(estimated_lines,1)*100:.0f}% of est.) — skipping Gemini")
                            return res_text, True, engine_name
                    
                    # Track best Tesseract result even if not accepted,
                    # so if Gemini later fails we return the best Tesseract result
                    if engine_type == 'tesseract' and not res_is_junk and res_lines > best_lines:
                        best_text = res_text
                        best_lines = res_lines
                        logger.info(f"    {current_page_label} 📈 PSM fallback improved ({PageComplexityAnalyzer.get_text_line_count(current_text)}→{res_lines} lines) "
                                    f"but below threshold ({res_lines/max(estimated_lines,1)*100:.0f}% < {threshold*100:.0f}%) — trying Gemini...")
                
            except Exception as e:
                logger.error(f"    [Page {page_num}] ❌ Rescue failed with {engine_name}: {e}")
                
        return best_text, False, ''

    def _get_reference_texts(self, image: Image.Image, page_label: str = "") -> Tuple[str, str]:
        """
        Fresh, independent Paddle + Tesseract reads of `image`, for Gemini
        reference-grounding (see ENABLE_GEMINI_REFERENCE_GROUNDING). Mirrors
        the existing _log_ocr_comparison() pattern of a dedicated re-run rather
        than threading intermediate state through _ocr_single_image/
        extract_with_fallback's return contracts — both engines run locally
        (no API cost), so a small amount of duplicate work here is a simpler
        trade than touching every caller of those methods.

        Returns (paddle_text, tesseract_text) — either may be '' on failure.
        """
        paddle_text = ''
        tess_text = ''
        try:
            tess_proc = self.adaptive_factory._get_cached_processor('tesseract', self.language)
            tess_text = tess_proc.extract_text(image, page_label=page_label)
        except Exception as e:
            logger.warning(f"{page_label} RefGround: Tesseract reference failed: {e}")
        try:
            paddle_proc = self.adaptive_factory._get_cached_processor('paddle', self.language)
            if hasattr(paddle_proc, 'extract_paddle_only'):
                paddle_text = paddle_proc.extract_paddle_only(image, page_label=page_label)
        except Exception as e:
            logger.warning(f"{page_label} RefGround: PaddleOCR reference failed: {e}")
        return paddle_text, tess_text

    def _ocr_single_image(self, image: Image.Image, processor: OCRProcessor,
                         engine: str, thread_id: str, label: str = "", psm: int = 3, page_label: str = "") -> Tuple[str, bool, str]:
        """OCR a single image/fragment and determine if it failed."""
        try:
            # If using a high-level engine like Gemini, use its direct method
            if engine == 'gemini':
                # Increment direct count
                self.gemini_stats["direct"] += 1

                # We use the factory's cached gemini instance
                gemini_proc = self.adaptive_factory._get_cached_processor('gemini', self.language)
                if getattr(config, 'ENABLE_GEMINI_REFERENCE_GROUNDING', False):
                    paddle_text, tess_text = self._get_reference_texts(image, page_label=f"[{page_label}]")
                    text = gemini_proc.extract_text_with_references(
                        image, paddle_text, tess_text, page_label=f"[{page_label}]")
                else:
                    text = gemini_proc.extract_text(image, page_label=f"[{page_label}]")
                return text, len(text.strip()) == 0, 'gemini'
            
            # 'fusion' (src/fusion_ocr_processor.py, config.ENABLE_FUSION_OCR) shares
            # PaddleV5Processor's extract_with_fallback() contract, so it takes the
            # same branch -- see docs/CURRENT_STATE.md, "Configuration-Driven OCR
            # Engine Selection".
            if engine in ('paddle', 'fusion') and hasattr(processor, 'extract_with_fallback'):
                result = processor.extract_with_fallback(image, preprocess=True, psm=psm, page_label=page_label)
                return result.get('text', ''), len(result.get('text', '').strip()) == 0, result.get('engine', 'paddle')
            
            # Default: Tesseract
            text = processor.extract_text(image, psm=psm, page_label=page_label)
            return text, len(text.strip()) == 0, engine
        except Exception as e:
            logger.error(f"[{page_label}] {label} OCR Error: {e}")
            return "", True, engine

    def _log_ocr_comparison(self, image: Image.Image, page_num: int, sub_idx: int,
                             gemini_text: str, final_engine: str, psm: int = 3) -> None:
        """
        Analysis-only capture, does NOT affect what goes in the EPUB. Whenever
        Gemini ends up contributing a page's final text (direct or rescue),
        also run isolated Tesseract and PaddleOCR passes on the same image and
        save each alongside the page's normal page_{page_num}_{sub_idx}_text.json
        (same page_num/sub_idx, so the three files line up per page):
          page_{page_num}_{sub_idx}_text_paddleocr.json
          page_{page_num}_{sub_idx}_text_tesseract.json
        The EPUB keeps using whatever process_page_optimized already decided
        (Gemini's text here, or the merged Tesseract+PaddleOCR text on
        non-Gemini pages) — this only exists so we can later mine per-page
        files for patterns, e.g. whether Gemini's accuracy edge is
        concentrated on specific page types rather than uniform, which would
        let us route to it more selectively. Best-effort: any failure here
        must never break page processing.
        """
        if self.temp_results_dir is None:
            return
        try:
            tesseract_text = ""
            paddle_text = ""

            try:
                tess_proc = self.adaptive_factory._get_cached_processor('tesseract', self.language)
                tesseract_text = tess_proc.extract_text(image, psm=psm, page_label=f"[Page {page_num} cmp]")
            except Exception as e:
                logger.debug(f"[Page {page_num}] comparison Tesseract pass failed: {e}")

            try:
                paddle_proc = self.adaptive_factory._get_cached_processor('paddle', self.language)
                if hasattr(paddle_proc, 'extract_paddle_only'):
                    paddle_text = paddle_proc.extract_paddle_only(image, page_label=f"[Page {page_num} cmp]")
            except Exception as e:
                logger.debug(f"[Page {page_num}] comparison PaddleOCR pass failed: {e}")

            import json as _json
            base = self.temp_results_dir / f"page_{page_num}_{sub_idx}_text"
            for suffix, engine_text, engine_label in (
                ('paddleocr', paddle_text, 'paddle'),
                ('tesseract', tesseract_text, 'tesseract'),
            ):
                export_data = {
                    'page_num': page_num,
                    'sub_idx': sub_idx,
                    'ocr_engine': engine_label,
                    'text': engine_text,
                    'text_length': len(engine_text),
                    'final_engine_used_in_epub': final_engine,
                }
                with open(f"{base}_{suffix}.json", 'w', encoding='utf-8') as f:
                    _json.dump(export_data, f, ensure_ascii=False, indent=2)

            # Lightweight metadata-only trace (no large text blobs) so this is
            # also visible in the real-time converter_events.jsonl stream.
            # Agreement ratios (word-level, via ocr_text_diff) give visibility
            # into how much Gemini's final text diverges from each raw engine,
            # and how much the two raw engines agree with each other —
            # calibration data for ENABLE_GEMINI_REFERENCE_GROUNDING, logged
            # regardless of whether that flag is on.
            from ocr_text_diff import agreement_ratio
            self._log_event(
                'ocr_comparison',
                page_num=page_num,
                sub_idx=sub_idx,
                final_engine=final_engine,
                gemini_chars=len(gemini_text.strip()),
                tesseract_chars=len(tesseract_text.strip()),
                paddle_chars=len(paddle_text.strip()),
                gemini_vs_tesseract_agreement=round(agreement_ratio(gemini_text, tesseract_text), 3),
                gemini_vs_paddle_agreement=round(agreement_ratio(gemini_text, paddle_text), 3),
                tesseract_vs_paddle_agreement=round(agreement_ratio(tesseract_text, paddle_text), 3),
            )
        except Exception as e:
            logger.debug(f"[Page {page_num}] OCR comparison logging failed: {e}")

    def _clean_ocr_text(self, text: str) -> str:
        """
        Clean OCR text by removing unwanted artifacts like "Page"
        
        Args:
            text: Raw OCR text
            
        Returns:
            Cleaned text
        """
        import re
        
        # Remove the word "Page" (case-insensitive, standalone word)
        # This will match "Page", "page", "PAGE" etc. as standalone words
        # Also handle surrounding whitespace intelligently
        cleaned = re.sub(r'\s*\bPage\b\s*', ' ', text, flags=re.IGNORECASE)
        
        # Clean up extra whitespace that may result from removal
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)  # Multiple blank lines to double
        cleaned = re.sub(r' +', ' ', cleaned)  # Multiple spaces to single
        cleaned = re.sub(r'^\s+', '', cleaned, flags=re.MULTILINE)  # Leading spaces on lines
        
        return cleaned.strip()
    
    def _is_text_junk(self, text: str) -> bool:
        """
        Analyze text to see if it's primarily junk OCR characters.
        Junk = high ratio of symbols/punctuation vs Telugu/English alphabets.
        """
        if not text:
            return True
        
        # Strip all whitespace for accurate density analysis
        clean_text = "".join(text.split())
        if not clean_text:
            return True
            
        # Count primary character types
        # Telugu Unicode range: 0x0C00 - 0x0C7F
        telugu_chars = sum(1 for c in clean_text if 0x0C00 <= ord(c) <= 0x0C7F)
        english_chars = sum(1 for c in clean_text if 'a' <= c.lower() <= 'z')
        digit_chars = sum(1 for c in clean_text if c.isdigit())
        
        total_visible = len(clean_text)
        real_content = telugu_chars + english_chars + digit_chars
        
        # User defined 70% rule: If real content < 30% of total visible characters, it's junk
        real_ratio = real_content / total_visible if total_visible > 0 else 0
        
        # Symbols check: Many | + [ ] / ( ) etc are signs of diagram OCR junk
        junk_chars = total_visible - real_content
        junk_ratio = junk_chars / total_visible if total_visible > 0 else 0
        
        # DECISION: Junk if real characters are less than 30% or symbols are over 70%
        # Also check for "Stutter/Fragment" pages where text length is > 50 
        # but real content is very low.
        is_junk = real_ratio < 0.30 or junk_ratio >= 0.70
        
        if is_junk:
            logger.info(f"  🔍 Text Analysis: Real={real_content}/{total_visible} ({real_ratio*100:.0f}%), Junk={junk_ratio*100:.0f}%")
            
        return is_junk

    def _convert_single_page(self, pdf_path: Path, page_num: int) -> Image.Image:
        """
        Convert a single PDF page to image (streaming)
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            
        Returns:
            PIL Image of the page
        """
        try:
            # Use PyMuPDF (fitz) to convert single page - MUCH faster than pdf2image
            doc = fitz.open(pdf_path)
            page = doc.load_page(page_num)
            
            # Calculate zoom based on DPI (72 is default PDF DPI)
            zoom = self.dpi / 72

            # Some scan-to-PDF tools declare a page box in points 1:1 with the source
            # image's pixel count instead of converting through a real scan DPI, so a
            # normal-looking page can claim to be 40-50+ "inches" wide. Found 2026-09-25
            # on a real book: DPI-based zoom alone rendered pages at 175-327 megapixels
            # each. Cap the rendered side instead of trusting the page box blindly --
            # MAX_RENDER_DIM is generous enough that real large physical pages (up to
            # ~17.5in at 400dpi, e.g. A3) are unaffected; it only kicks in for this
            # mis-declared-page-box case.
            MAX_RENDER_DIM = 7000
            render_w, render_h = page.rect.width * zoom, page.rect.height * zoom
            if max(render_w, render_h) > MAX_RENDER_DIM:
                zoom *= MAX_RENDER_DIM / max(render_w, render_h)
            mat = fitz.Matrix(zoom, zoom)

            # Get pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            doc.close()
            return img
            
        except Exception as e:
            logger.error(f"Failed to convert page {page_num + 1}: {e}")
            return None
    
    def _ocr_cells_parallel(self, cells: List[List[Image.Image]]) -> List[List[str]]:
        """
        OCR table cells in parallel
        
        Args:
            cells: 2D list of cell images
            
        Returns:
            2D list of cell text
        """
        # Flatten cells with coordinates
        cell_tasks = []
        for row_idx, row_cells in enumerate(cells):
            for col_idx, cell_img in enumerate(row_cells):
                # Skip empty cells if enabled
                if self.skip_empty_cells and self._is_cell_empty(cell_img):
                    cell_tasks.append((row_idx, col_idx, ""))
                else:
                    cell_tasks.append((row_idx, col_idx, cell_img))
        
        # Separate empty and non-empty cells
        ocr_tasks = [(r, c, img) for r, c, img in cell_tasks if img != ""]
        empty_cells = {(r, c): "" for r, c, img in cell_tasks if img == ""}
        
        # OCR non-empty cells in parallel
        results = {}
        if ocr_tasks:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_cell = {
                    executor.submit(self.ocr_processor.extract_text, img): (r, c)
                    for r, c, img in ocr_tasks
                }
                
                for future in as_completed(future_to_cell):
                    r, c = future_to_cell[future]
                    try:
                        text = future.result()
                        results[(r, c)] = text.strip()
                    except Exception as e:
                        logger.warning(f"OCR failed for cell ({r},{c}): {e}")
                        results[(r, c)] = ""
        
        # Combine results
        results.update(empty_cells)
        
        # Reconstruct 2D array
        table_data = []
        for row_idx in range(len(cells)):
            row_data = []
            for col_idx in range(len(cells[0])):
                row_data.append(results.get((row_idx, col_idx), ""))
            table_data.append(row_data)
        
        return table_data
    
    def process_page_optimized(self, page_image: Image.Image, page_num: int,
                               total_pages: int = 0, sub_idx: int = 0) -> Dict:
        """
        Process a single page with optimizations
        
        Args:
            page_image: PIL Image of page
            page_num: Page number
            total_pages: Total number of pages (for progress)
            
        Returns:
            Dictionary with processed content
        """
        if total_pages > 0:
            progress = int(20 + (page_num / total_pages) * 60)
            self._update_progress(f"Processing page {page_num + 1}/{total_pages}", 
                                progress, 100)
        
        import threading
        thread_id = threading.current_thread().name
        logger.debug(f"[{thread_id}] 📄 Processing page {page_num + 1}...")
        
        result = {
            'page_num': page_num,
            'text': '',
            'tables': [],
            'images': []
        }
        
        # STAGE 2 (OCR) concurrency sub-throttle tracker. Stage 1 (analysis +
        # enhancement, below) is bounded only by the outer thread pool's own size
        # (self.max_workers) — it isn't lock-bound, so no separate gate is needed.
        # Stage 2 IS gated by self._stage2_semaphore, acquired right before the OCR
        # portion begins and released in the `finally` below on every exit path
        # (normal return, early return, or exception).
        stage2_gate_held = False

        try:
            # Live memory check before starting Stage 1 — a no-op in the normal
            # case (see _stage1_memory_preflight docstring), real backoff only if
            # memory is genuinely tight.
            self._stage1_memory_preflight(page_num)

            # Auto-rotate page if needed (handles rotated scans)
            try:
                page_image = self.ocr_processor.auto_rotate(page_image)
            except Exception as e:
                logger.warning(f"Auto-rotation failed for page {page_num + 1}: {e}")
            
            # Detect tables if enabled
            if self.detect_tables and self.table_detector:
                tables = self.table_detector.detect_tables(page_image)
                
                for table in tables:
                    # Extract table cells
                    cells = self.table_detector.extract_cells(
                        table['image'],
                        table['row_positions'],
                        table['col_positions']
                    )
                    
                    # OCR cells in parallel
                    table_data = self._ocr_cells_parallel(cells)
                    
                    result['tables'].append({
                        'data': table_data,
                        'rows': table['rows'],
                        'cols': table['cols']
                    })
                    
                    logger.info(f"  ✓ Processed table: {table['rows']}×{table['cols']}")
            
            # ── LAYOUT-FIRST ROUTING ─────────────────────────────────────────
            # 1. Run layout analysis BEFORE complexity scoring.
            # 2. Crop & save detected figure regions directly (precise, not full-page).
            # 3. Build a text-masked image (figures blanked to white) for complexity
            #    analysis so image pixels no longer inflate the complexity score.
            # This prevents a small logo from pushing a text-heavy page to Gemini.
            layout_figure_crops: List[Image.Image] = []
            figure_coords: List[Tuple[int,int,int,int]] = []
            image_for_analysis = page_image  # default: use original

            try:
                layout_figure_crops, figure_coords = self.layout_analyzer.extract_figures(page_image)
                if layout_figure_crops:
                    logger.info(
                        f"  ✂️  Layout: {len(layout_figure_crops)} figure(s) pre-extracted. "
                        f"Masking for complexity analysis."
                    )
                    # Save the precise figure crops into the result now
                    result['images'].extend(layout_figure_crops)
                    # Pass text-only image to complexity scorer
                    image_for_analysis = self.layout_analyzer.get_text_mask(
                        page_image, figure_coords
                    )
            except Exception as _le:
                logger.warning(f"Layout pre-extraction failed (non-fatal): {_le}")

            # Get appropriate OCR processor based on page complexity
            # NOTE: We pass image_for_analysis (figures blanked) so the complexity
            # score reflects TEXT difficulty only — not image presence.
            # We ALSO pass figure_coords so column/text-region detection can still
            # locate the real two-column band (the illustrations are white in
            # image_for_analysis and would otherwise be invisible to it, pushing
            # the gutter to the wrong x and merging the columns).
            ocr_processor, analysis = self.adaptive_factory.get_processor_for_page(
                image_for_analysis, self.language, figure_regions=figure_coords
            )
            # Store figure coords in analysis for downstream use
            analysis['layout_figure_coords'] = figure_coords
            
            # --- DETECT MOSTLY-GRAPHIC PAGES (Drawings, Yantras, Diagrams, Plates) ---
            # If a page is mostly a drawing/illustration, skip OCR entirely and capture
            # the full page as an image to preserve it faithfully in the EPUB.
            has_illustrations = bool(analysis.get('has_illustrations', False))
            image_dominant_ratio = analysis.get('image_dominant_ratio', 0.0)
            estimated_lines = analysis.get('estimated_lines', 0)
            is_mostly_graphic = False

            # ONLY run the legacy OpenCV heuristics if the AI Layout Analyzer is completely disabled.
            # The legacy OpenCV logic often confuses text borders for giant illustrations.
            if not getattr(config, 'ENABLE_LAYOUT_ANALYZER', True):
                # Criteria 1: Giant single illustration (> 60% of page area)
                for (rx, ry, rw, rh) in analysis.get('image_regions', []):
                    if (rw * rh) > (page_image.width * page_image.height * 0.60):
                        is_mostly_graphic = True
                        logger.info(f"  🎨 Criteria-1: Single illustration covers >{60}% of page area.")
                        break

                # Criteria 2: Illustrations detected AND text is minimal (< 8 lines)
                if not is_mostly_graphic and has_illustrations:
                    complexity = analysis.get('complexity_score', 0)
                    if estimated_lines < 8 and (complexity > 25 or has_illustrations):
                        is_mostly_graphic = True
                        logger.info(f"  🎨 Criteria-2: Illustration + minimal text ({estimated_lines} lines).")

                # Criteria 3: COMBINED illustration area exceeds the dominance threshold.
                _dominance_thresh = getattr(config, 'IMAGE_PAGE_DOMINANT_RATIO', 0.55)
                if not is_mostly_graphic and image_dominant_ratio >= _dominance_thresh:
                    is_mostly_graphic = True
                    logger.info(
                        f"  🎨 Criteria-3: Combined illustration area = {image_dominant_ratio*100:.0f}% "
                        f"(>= {_dominance_thresh*100:.0f}% threshold). Full-plate image page — skipping OCR."
                    )

                # Criteria 4: Even with a few caption lines, if illustrations overwhelmingly dominate.
                if not is_mostly_graphic and image_dominant_ratio >= 0.70 and estimated_lines <= 15:
                    is_mostly_graphic = True
                    logger.info(
                        f"  🎨 Criteria-4: Illustrations dominate {image_dominant_ratio*100:.0f}% "
                        f"with only {estimated_lines} caption lines — capturing as image page."
                    )

            if is_mostly_graphic:
                logger.info(f"  🎨 Detected mostly-graphic page (drawing/diagram). Capturing snapshot and SKIPPING OCR.")
                
                # Apply Two-Stage DPI for storage efficiency
                storage_image = page_image
                target_dpi = getattr(config, 'STORAGE_DPI', 150)
                if self.dpi > target_dpi:
                    scale = target_dpi / self.dpi
                    w, h = page_image.size
                    storage_image = page_image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                
                return {
                    'page_num': page_num,
                    'text': '',
                    'tables': [],
                    'images': [storage_image],
                    'is_cover': False,
                    'skipped_ocr': True,
                    'ocr_engine': 'skipped (mostly-graphic)'
                }

            # Log OCR engine selection with thread info
            import threading
            import json as _json
            thread_id = threading.current_thread().name
            engine_name = analysis.get('actual_engine', analysis.get('recommended_engine', 'unknown'))
            complexity = analysis.get('complexity_score', 0)
            logger.debug(f"[{thread_id}] 📄 Page {page_num + 1}: Using {engine_name.upper()} (complexity: {complexity:.1f})")
            
            # Emit page analysis data for UI complexity dashboard AND the
            # converter_events.jsonl structured log (unconditionally — an agent
            # analyzing logs later shouldn't depend on whether a UI was attached
            # during the run).
            import time as _time
            engine_display = {
                'paddle': 'PaddleOCR',
                'tesseract': 'Tesseract',
                'gemini': 'Gemini Vision',
                'merged': 'Mixed (PaddleOCR + Tesseract)',
                'none': 'None (Failed)'
            }.get(engine_name.lower(), engine_name)

            page_analysis_fields = {
                "page_num": page_num + 1,
                "complexity_score": round(complexity, 1),
                "engine": engine_display,
                "has_table": bool(analysis.get('has_table', False)),
                "has_illustrations": bool(analysis.get('has_illustrations', False)),
                "has_mixed_content": bool(analysis.get('has_mixed_content', False)),
                "is_multicolumn": bool(analysis.get('is_multicolumn', False)),
                "is_very_complex": bool(analysis.get('is_very_complex', False)),
                "reasoning": analysis.get('reasoning', ''),
                "timestamp": _time.time()
            }
            self._log_event('page_analysis', phase='initial', **page_analysis_fields)
            if self.progress_callback:
                # Initial analysis emission
                self.progress_callback(
                    _json.dumps({"page_analysis": page_analysis_fields}),
                    page_num + 1, max(total_pages, 1))
            
            # We only preserve the full page if explicitly requested by the user.
            # We NO LONGER force-preserve full pages based on complexity, as it 
            # causes unwanted full-page image dumps for pages with decorative borders.
            preserve_image_for_this_page = self.preserve_images
            
            # --- COLUMN-AWARE OCR ---
            # Crop to text-only region (excludes illustrations) and split columns
            # if multicolumn layout detected. This prevents:
            #   1. Junk characters from illustrations
            #   2. Garbled cross-column text mixing
            
            ocr_image = page_image
            text_region = analysis.get('text_region')      # (y_start, y_end) or None
            column_gutter_x = analysis.get('column_gutter_x')  # X position or None
            num_columns = analysis.get('num_columns', 1)
            estimated_lines = analysis.get('estimated_lines', 0)
            recommended_psm = analysis.get('recommended_psm', 3)
            
            # Step 1: Prepare OCR Image (Masking Figures)
            # We use the text-masked image (image_for_analysis) where layout figures
            # are painted white. This prevents OCR from hallucinating text inside images
            # WITHOUT physically cropping the page (which often chops off valid text).
            
            ocr_image = image_for_analysis
            
            # Fallback masking if layout analyzer didn't run but old analyzer found regions
            if not analysis.get('layout_figure_coords') and analysis.get('image_regions'):
                import cv2
                ocr_arr = np.array(ocr_image)
                masked_count = 0
                for (rx, ry, rw, rh) in analysis['image_regions']:
                    ocr_arr[ry:ry+rh, rx:rx+rw] = 255
                    masked_count += 1
                ocr_image = Image.fromarray(ocr_arr)
                logger.debug(f"  🎭 Fallback masking {masked_count} illustration region(s)")
            # Optimization: Avoid downscaling! Tesseract fundamentally requires 300+ DPI
            # Downscaling destroys Vatulu and Guninthalu on simple textbook pages.
            pass
            
            # Image enhancement: deskew + sharpen for better OCR accuracy
            if getattr(config, 'ENABLE_DESKEW', False) or getattr(config, 'ENABLE_SHARPEN', False):
                try:
                    import cv2
                    from PIL import ImageEnhance
                    
                    if getattr(config, 'ENABLE_DESKEW', False):
                        # Deskew: detect and correct tilt
                        img_gray = np.array(ocr_image.convert('L'))
                        edges = cv2.Canny(img_gray, 50, 150, apertureSize=3)
                        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                                minLineLength=100, maxLineGap=10)
                        if lines is not None:
                            angles = []
                            for line in lines:
                                x1, y1, x2, y2 = line[0]
                                if x2 - x1 != 0:
                                    angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                                    if abs(angle) < 15:
                                        angles.append(angle)
                            if angles:
                                median_angle = np.median(angles)
                                # Threshold raised from 0.3 to 1.5, 2026-09-25: found live that
                                # 0.3 is far too sensitive on dense Telugu text -- Hough lines
                                # picked up from character strokes (not the real page edge) on a
                                # genuinely straight page produced a spurious 0.53 degree "tilt"
                                # from 137 detected lines. Rotating a straight page by even that
                                # small an angle still resamples (BICUBIC) every character, which
                                # reproduced the exact confidently-wrong, single-letter-substitution
                                # misreads seen in a real book page (see
                                # ocr_comparison/No616_page15/NOTES.md) -- this "correction" was
                                # actively causing the OCR errors it was meant to prevent. A real,
                                # visible scan tilt is normally well above 1 degree; 1.5 is a
                                # conservative floor so genuinely skewed pages are still corrected.
                                DESKEW_MIN_ANGLE = 1.5
                                if abs(median_angle) > DESKEW_MIN_ANGLE:
                                    ocr_image = ocr_image.rotate(-median_angle,
                                        resample=Image.Resampling.BICUBIC,
                                        expand=False, fillcolor=(255, 255, 255))
                                    logger.debug(f"  📐 Deskewed by {median_angle:.1f}°")
                    
                    if getattr(config, 'ENABLE_SHARPEN', False):
                        enhancer = ImageEnhance.Sharpness(ocr_image)
                        ocr_image = enhancer.enhance(2.0)
                        
                except Exception as e:
                    logger.warning(f"  ⚠️ Image enhancement failed: {e}")
            
            # IMPROVEMENT: Engine-specific preprocessing for Tesseract
            # Tesseract struggles with tiny Telugu glyphs (Vatulu) and skips lines
            # if contrast is low. We boost contrast only for the Tesseract engine.
            if engine_name == 'tesseract':
                try:
                    from PIL import ImageEnhance, ImageFilter
                    # NOTE: Keep contrast boost moderate (1.4x).
                    # Too high (1.8x+) over-saturates faint text lines on old print,
                    # causing Tesseract to skip them entirely.
                    enhancer = ImageEnhance.Contrast(ocr_image)
                    ocr_image = enhancer.enhance(1.4)  # Moderate boost - balanced for faint old print
                    ocr_image = ocr_image.filter(ImageFilter.SHARPEN) # Sharpen glyph edges
                    ocr_image = ocr_image.convert('L') # Convert to L (grayscale)
                    logger.debug(f"  ✨ Tesseract-specific enhancement applied (Page {page_num+1})")
                except Exception as e:
                    logger.warning(f"  ⚠️ Tesseract-specific enhancement failed: {e}")

            # --- STAGE 2 GATE ---
            # Everything from here on is the OCR portion. Acquire the Stage-2
            # sub-throttle now (Stage 1 above ran at the outer pool's full width);
            # released in the `finally` at the end of this function on every exit
            # path. This is what actually bounds concurrent OCR-engine-lock
            # contention, independent of how many pages are concurrently analyzing.
            self._stage2_semaphore.acquire()
            stage2_gate_held = True

            # Step 2: Column-aware OCR
            text = ""
            ocr_failed = False

            # Skip splitting columns for Table of Contents pages because they should be read row-by-row
            is_toc_page = (analysis.get('page_type') == 'toc')
            if num_columns >= 2 and column_gutter_x and getattr(config, 'ENABLE_COLUMN_OCR', True) and not is_toc_page:
                # MULTICOLUMN: Split into columns and OCR each separately

                ocr_w, ocr_h = ocr_image.size

                # Adjust gutter X if we cropped the text region (gutter X is
                # relative to the full page, not the cropped region)
                adj_gutter_x = column_gutter_x  # Already in full-page coords

                # Clamp to image bounds
                adj_gutter_x = max(10, min(adj_gutter_x, ocr_w - 10))

                img_left = ocr_image.crop((0, 0, adj_gutter_x, ocr_h))
                img_right = ocr_image.crop((adj_gutter_x, 0, ocr_w, ocr_h))

                logger.debug(f"  📰 Splitting into 2 columns at x={adj_gutter_x}: "
                           f"Left={img_left.size}, Right={img_right.size}")

                estimated_per_col = estimated_lines if estimated_lines > 0 else 0

                primary_psm = getattr(config, 'TESSERACT_PSM', 3)
                # Run left/right column OCR concurrently instead of sequentially.
                # Safe for every engine this can dispatch to: Tesseract uses
                # per-call temp files with unique names (no shared state); Paddle
                # calls just queue on the existing global _engine_lock (harmless
                # serialization, same as already happens across concurrent
                # pages); Gemini has its own internal rate-limit lock.
                with ThreadPoolExecutor(max_workers=2) as _col_pool:
                    _fut_left = _col_pool.submit(
                        self._ocr_single_image, img_left, ocr_processor, engine_name,
                        thread_id, "Left Column", psm=recommended_psm,
                        page_label=f"Page {page_num+1}")
                    _fut_right = _col_pool.submit(
                        self._ocr_single_image, img_right, ocr_processor, engine_name,
                        thread_id, "Right Column", psm=recommended_psm,
                        page_label=f"Page {page_num+1}")
                    text_left, failed_left, engine_left = _fut_left.result()
                    text_right, failed_right, engine_right = _fut_right.result()

                # If either side fell back to tesseract, we consider the whole page tesseract
                if 'tesseract' in (engine_left, engine_right):
                    engine_name = 'tesseract'

                ocr_failed = failed_left and failed_right

                # Combine: left column first, then right column
                parts = []
                if text_left.strip():
                    parts.append(text_left.strip())
                if text_right.strip():
                    parts.append(text_right.strip())
                text = "\n\n".join(parts)

                logger.debug(f"[{thread_id}] ✓ Column OCR: {len(text_left)} + {len(text_right)} = {len(text)} chars")

            else:
                # SINGLE COLUMN: Run primary OCR with recommended PSM
                text, ocr_failed, engine_name = self._ocr_single_image(
                    ocr_image, ocr_processor, engine_name, thread_id,
                    "Full page", psm=recommended_psm, page_label=f"Page {page_num+1}")
                
                if ocr_failed:
                    preserve_image_for_this_page = True

            # Clean the text to remove unwanted artifacts like "Page"
            text = self._clean_ocr_text(text)
            
            # --- UNIFIED ACCURACY ESCALATION LADDER ---
            estimated_lines = analysis.get('estimated_lines', 0)
            actual_lines = PageComplexityAnalyzer.get_text_line_count(text)
            
            # --- DYNAMIC ACCURACY THRESHOLD ---
            # Using 80% (0.80) for complex, multicol, or illustration pages (high precision required)
            # Using 30% (0.30) for standard book text (budget friendly)
            
            is_toc = (analysis.get('page_type') == 'toc')
            has_illustrations = analysis.get('has_illustrations', False)
            is_multicolumn = analysis.get('is_multicolumn', False)
            
            base_threshold = getattr(config, 'GEMINI_RESCUE_THRESHOLD', 0.65)

            if is_toc:
                # TOC: slightly above base
                threshold = min(base_threshold + 0.10, 0.80)
                logger.debug(f"  📋 [TOC Mode] Setting rescue threshold to {threshold*100:.0f}%")
            elif has_illustrations or is_multicolumn:
                # Was hardcoded 0.80 -- now follows config with +5% boost for complex pages
                threshold = min(base_threshold + 0.05, 0.75)
                logger.info(f"  🏢 [High-Precision Mode] Illustration/Columns detected. "
                          f"Setting rescue threshold to {threshold*100:.0f}% (base={base_threshold*100:.0f}%)")
            else:
                # Standard book pages -- use config directly
                threshold = base_threshold
                logger.debug(f"  📖 [Standard Mode] Body text. "
                           f"Setting rescue threshold to {threshold*100:.0f}%")
            
            # --- QUALITY & BUDGET CHECK ---
            text_is_junk = PageComplexityAnalyzer.is_junk_text(text)
            
            # Additional check for "stuttering" or extremely low character count vs lines
            # If we found lines but almost no characters, it's probably noise/lines.
            # For bilingual / multilingual text, we check all non-whitespace characters to prevent
            # false positives on English pages (where telugu_chars is naturally 0).
            char_count = len(text.strip())
            non_space_chars = len("".join(text.split()))
            
            # If we have 5+ lines but fewer than 5 characters per line on average, it's probably junk/noise
            is_fragmented = actual_lines > 5 and (non_space_chars < actual_lines * 5)

            # Record line counts for clean pages to dynamically learn book line-height statistics
            if not text_is_junk and not is_fragmented and actual_lines > 0:
                with self._line_count_lock:
                    self._clean_page_line_counts.append(actual_lines)
                    if len(self._clean_page_line_counts) > 30:
                        self._clean_page_line_counts.pop(0)

            # --- ADAPTIVE SOLID EXTRACTION SAFEGUARD ---
            # Dynamically adjust min_safe_lines based on the statistics of clean pages processed so far.
            # Once we have >= 5 clean pages, we use 75% of the median lines as our dynamic min safe lines.
            config_min_safe_lines = getattr(config, 'TESSERACT_MIN_SAFE_LINES', 22)
            min_safe_lines = config_min_safe_lines
            median_lines_val = 0.0
            
            with self._line_count_lock:
                clean_counts = list(self._clean_page_line_counts)
                
            if len(clean_counts) >= 5:
                # Calculate median to be robust against outliers (short preface/title pages)
                sorted_counts = sorted(clean_counts)
                n = len(sorted_counts)
                if n % 2 == 1:
                    median_lines_val = float(sorted_counts[n // 2])
                else:
                    median_lines_val = (sorted_counts[n // 2 - 1] + sorted_counts[n // 2]) / 2.0
                
                # Dynamic safe min is 75% of the median clean lines, capped between 10 and 22
                dynamic_min = int(median_lines_val * 0.75)
                min_safe_lines = max(10, min(22, dynamic_min))
            
            avg_chars_per_line = non_space_chars / max(1, actual_lines)
            is_solid_extraction = (not text_is_junk) and (not is_fragmented) and (
                actual_lines >= min_safe_lines
                or (actual_lines >= 10 and avg_chars_per_line >= 25)
            )

            # NOTE: Upper bound raised from 3x to 5x to avoid false junk-discard
            # when line estimator underestimates (common on dense Telugu pages).
            needs_rescue = (text_is_junk or is_fragmented or (actual_lines < estimated_lines * threshold) or (actual_lines > estimated_lines * 5)) and not is_solid_extraction
            
            if is_solid_extraction and (actual_lines < estimated_lines * threshold):
                reason_str = (
                    f"lines {actual_lines} >= adaptive_min {min_safe_lines} (median {median_lines_val:.1f})"
                    if (len(clean_counts) >= 5 and actual_lines >= min_safe_lines)
                    else (f"lines {actual_lines} >= safe_min {min_safe_lines}" if actual_lines >= min_safe_lines else f"lines {actual_lines} >= 10 with high density ({avg_chars_per_line:.1f} chars/line)")
                )
                logger.info(
                    f"  🛡️ Safeguard: Tesseract got a solid extraction ({reason_str}). "
                    f"Bypassing Gemini rescue despite estimated {estimated_lines} lines."
                )
            
            # LEVEL 2: Run Escalation Ladder (if enabled)
            # Use global config OR per-run toggle
            auto_rescue_enabled = getattr(config, 'ENABLE_AUTOMATIC_GEMINI_RESCUE', False) and self.enable_rescue_toggle
            
            if needs_rescue and text.strip() and auto_rescue_enabled:
                # LEVEL 2: Run Escalation Ladder
                text_rescue, rescue_success, esc_engine_name = self._run_escalation_ladder(
                    ocr_image, thread_id, recommended_psm, threshold, page_num+1, text, estimated_lines)
                
                if rescue_success:
                    text = text_rescue
                    engine_name = esc_engine_name
            
            # Increment Tesseract counter if it was the final engine
            if 'tesseract' in engine_name.lower() and text.strip():
                self.tesseract_pages += 1

            # Clean the text to remove unwanted artifacts like "Page"
            text = self._clean_ocr_text(text)

            # Level 3: Final Junk Check & Summary Tracking
            # diagnostics captures every signal (incl. the always-on-but-not-yet-
            # gating OOV ratio) for calibration logging below, regardless of
            # whether ENABLE_TELUGU_OOV_JUNK_SIGNAL actually affects is_junk.
            oov_diagnostics: Dict[str, Any] = {}
            is_junk = PageComplexityAnalyzer.is_junk_text(text, diagnostics=oov_diagnostics)
            
            # If despite escalation the result is STILL junk AND it's not from Gemini, discard it
            # (Gemini often correctly extracts TOCs which trigger false positives for 'junk' due to short words and dots)
            if text.strip() and is_junk and 'gemini' not in engine_name.lower():
                logger.warning(f"  🗑️ Final text remains junk from {engine_name} on Page {page_num+1}. Discarding text.")
                text = "" # Discard text to avoid broken characters in EPUB
                preserve_image_for_this_page = True # Ensure image is kept as fallback

            # Analysis-only: whenever Gemini contributed the final text, capture what
            # Tesseract/PaddleOCR alone would have produced for later comparison.
            # Does not change `text`/`engine_name` — the EPUB still gets what was
            # already decided above. Uses the same page_num/sub_idx as
            # page_{page_num}_{sub_idx}_text.json so the files line up per page.
            if text.strip() and 'gemini' in engine_name.lower():
                self._log_ocr_comparison(ocr_image, page_num, sub_idx, gemini_text=text,
                                          final_engine=engine_name, psm=recommended_psm)

            # Record discrepancies for Audit report
            if text.strip() == "" or (estimated_lines > 5 and actual_lines < (estimated_lines * threshold)):
                self.ocr_discrepancies += 1
                reason_str = "JUNK result (erased)" if text.strip() == "" else ("TOC line-skip" if is_toc else "line-skip")
                
                # If we were in Audit mode, this page probably skipped escalation
                if not getattr(config, 'ENABLE_AUTOMATIC_GEMINI_RESCUE', False):
                    logger.warning(f"  [Page {page_num+1}] 🔎 AUDIT: Junk/Incomplete results. Manual review recommended.")
                
                # Report for tracking if failed (don't recount successes here as they're added in _run_escalation_ladder)
                rescue_entry = {
                    'page_num': page_num + 1,
                    'engine': engine_name,
                    'is_junk': is_junk,
                    'actual_lines': actual_lines,
                    'estimated_lines': estimated_lines,
                    'reason': reason_str,
                    'status': 'FAILED'
                }
                self.rescue_report.append(rescue_entry)
                # Streamed immediately (unlike quality_report.json's rescue_report,
                # which is only written once at the very end) so an agent can see
                # quality problems in real time, or recover this data even from a
                # run that crashed before reaching the end-of-book summary.
                self._log_event('escalation', **rescue_entry)

            
            # Telugu post-processing: fix known OCR misreads
            if getattr(config, 'ENABLE_TELUGU_POST_PROCESSING', False) and text:
                original_text = text
                if getattr(config, 'ENABLE_TELUGU_DICTIONARY_CORRECTION', False):
                    # Also capture the dictionary-correction change-log so this page
                    # can be routed to Gemini auto-validation (many corrections) or
                    # flagged for manual review (few corrections) — see
                    # docs/TELUGU_SPELL_CORRECTION_TODO.md. post_process_telugu_with_corrections
                    # is safe to call concurrently (returns fresh data, no shared state).
                    text, dictionary_corrections = post_process_telugu_with_corrections(text)
                    result['dictionary_corrections'] = dictionary_corrections
                    if dictionary_corrections:
                        threshold = getattr(config, 'DICTIONARY_CORRECTION_GEMINI_THRESHOLD', 10)
                        if len(dictionary_corrections) >= threshold:
                            # TODO(docs/TELUGU_SPELL_CORRECTION_TODO.md #2): Gemini
                            # auto-validation not implemented yet. Until it is, treat
                            # this the same as needs_manual_review so nothing silently
                            # skips review.
                            result['needs_manual_review'] = True
                            result['needs_gemini_validation'] = True
                        else:
                            result['needs_manual_review'] = True
                else:
                    text = post_process_telugu(text)
                if text != original_text:
                    logger.debug(f"  🔤 Telugu post-processing applied")
            result['text'] = text
            
            # --- CHARACTER ANALYSIS FOR UI ---
            telugu_chars = sum(1 for c in text if 0x0C00 <= ord(c) <= 0x0C7F)
            english_chars = sum(1 for c in text if 'a' <= c.lower() <= 'z')
            digits = sum(1 for c in text if c.isdigit())
            
            # Finalized analysis (engine might have changed on retry) — update UI
            # AND the converter_events.jsonl structured log unconditionally, same
            # reasoning as the initial emission above.
            engine_display = {
                'paddle': 'PaddleOCR',
                'tesseract': 'Tesseract',
                'gemini': 'Gemini Vision',
                'merged': 'Mixed (PaddleOCR + Tesseract)',
                'none': 'None (Failed)'
            }.get(engine_name.lower(), engine_name)

            page_analysis_fields = {
                "page_num": page_num + 1,
                "complexity_score": round(complexity, 1),
                "engine": engine_display,
                "char_analysis": {
                    "total": len(text),
                    "telugu": telugu_chars,
                    "english": english_chars,
                    "digits": digits
                },
                "debug_info": {
                    "raw_engine": engine_name,
                    "estimated_lines": estimated_lines,
                    "actual_lines": actual_lines,
                    "is_junk": bool(is_junk),
                    "is_fragmented": bool(is_fragmented),
                    "is_solid": bool(is_solid_extraction),
                    "dynamic_threshold": round(threshold, 2),
                    "min_safe_lines": min_safe_lines,
                    "oov_ratio": round(oov_diagnostics.get('oov_ratio', 0.0), 4),
                    "oov_checked_count": oov_diagnostics.get('oov_checked_count', 0),
                    "oov_unknown_count": oov_diagnostics.get('oov_unknown_count', 0)
                },
                "timestamp": _time.time()
            }
            self._log_event('page_analysis', phase='final', **page_analysis_fields)
            if self.progress_callback:
                self.progress_callback(
                    _json.dumps({"page_analysis": page_analysis_fields}),
                    page_num + 1, max(total_pages, 1))
            
            # Store complexity score for later use
            result['complexity_score'] = complexity
            result['ocr_engine'] = engine_name

            # ── PADDLE HEALTH MONITORING ───────────────────────────────────────
            self._pages_processed += 1
            if 'gemini' in engine_name.lower():
                self._gemini_pages += 1

            if not self._alert_emitted:
                try:
                    from paddle_v5_processor import get_crash_stats
                    stats = get_crash_stats()
                    crash_thresh  = getattr(config, 'PADDLE_CRASH_ALERT_THRESHOLD', 3)
                    gemini_thresh = getattr(config, 'GEMINI_HIGH_USAGE_THRESHOLD', 0.40)

                    # Alert 1: Hard crash threshold hit
                    if stats['hard_crashes'] >= crash_thresh:
                        self._paddle_degraded = True
                        self._alert_emitted = True
                        msg = (
                            f"PaddleOCR has crashed {stats['hard_crashes']} times "
                            f"(threshold: {crash_thresh}). Tesseract fallback is active. "
                            f"Telugu accuracy may be degraded. "
                            f"Recommend STOPPING the job to diagnose the root cause."
                        )
                        logger.error(f"🚨 PADDLE HEALTH ALERT: {msg}")
                        self.emit_health_alert(
                            'paddle_crash',
                            severity='critical',
                            hard_crashes=stats['hard_crashes'],
                            soft_fails=stats['soft_fails'],
                            message=msg,
                            recommendation='stop'
                        )

                    # Alert 2: Gemini usage is unusually high (possible Paddle degradation)
                    elif (self._pages_processed >= 10 and
                          self._gemini_pages / self._pages_processed > gemini_thresh):
                        self._alert_emitted = True
                        pct = int(self._gemini_pages / self._pages_processed * 100)
                        msg = (
                            f"Gemini is handling {pct}% of pages "
                            f"({self._gemini_pages}/{self._pages_processed}). "
                            f"This is higher than expected (threshold: {int(gemini_thresh*100)}%). "
                            f"Check if PaddleOCR is producing low-quality results."
                        )
                        logger.warning(f"\u26a0\ufe0f GEMINI HIGH USAGE ALERT: {msg}")
                        self.emit_health_alert(
                            'gemini_high_usage',
                            severity='warning',
                            gemini_pages=self._gemini_pages,
                            total_processed=self._pages_processed,
                            percentage=pct,
                            message=msg,
                            recommendation='continue'
                        )
                except Exception as _he:
                    logger.debug(f"Health check error (non-fatal): {_he}")

            
            # --- IMAGE EXTRACTION LOGIC (Strict Priority) ---
            # 1. Classification
            text_content = text.strip()
            text_len = len(text_content)
            page_w, page_h = page_image.size
            page_area = page_w * page_h
            is_table = analysis.get('has_table', False)
            
            # Is this a "Full Page Picture" (mostly image, very little text)?
            # IMPROVED: Be more conservative - require BOTH low text AND very large image region
            # This prevents treating "text in a decorative box" as an image
            is_mostly_img = False
            
            # Only consider as "mostly image" if:
            # 1. Very little text (< 200 chars) AND high complexity, OR
            # 2. A single image region covers >70% of the page
            if text_len < 200 and complexity > 60:
                # Check if there's actually a large image region
                for region in analysis.get('image_regions', []):
                    if (region[2] * region[3]) > (page_area * 0.7):
                        is_mostly_img = True
                        break
            
            # Additional safeguard: If we have substantial text (>500 chars), 
            # it's definitely NOT a pure image page, even with decorative borders
            if text_len > 500:
                is_mostly_img = False

            # 2. Decision Path
            # Skip full-page snapshot if layout already extracted precise figure crops.
            layout_already_saved = bool(analysis.get('layout_figure_coords'))

            if not layout_already_saved and (is_table or is_mostly_img or analysis.get('image_regions')):
                # mode: Full Page Capture (fallback when layout extraction unavailable)
                storage_image = page_image
                use_two_stage = getattr(config, 'USE_TWO_STAGE_DPI', True)
                
                # Dynamic DPI Selection
                if use_two_stage:
                    if is_table:
                        target_dpi = getattr(config, 'STORAGE_DPI', 150)
                    elif is_mostly_img:
                        target_dpi = getattr(config, 'STORAGE_DPI', 150)
                    else:
                        target_dpi = getattr(config, 'TEXT_BACKUP_DPI', 50)
                        
                    if self.dpi > target_dpi:
                        scale = target_dpi / self.dpi
                        new_w, new_h = int(page_w * scale), int(page_h * scale)
                        storage_image = page_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        logger.debug(f"  📉 Captured Full Page Snapshot: Resized to {target_dpi} DPI ({scale*100:.1f}%)")
                
                result['images'].append(storage_image)
                type_name = "Table" if is_table else ("Illustration" if is_mostly_img else "Hybrid")
                logger.debug(f"  🖼️ Captured Full Page ({type_name}). Switched from extraction to full-page capture.")

            
            elif preserve_image_for_this_page:
                # Mode C: Standard Full Page (User requested, but no specific structure found)
                # CRITICAL FIX: Apply DPI reduction based on text content
                storage_image = page_image
                use_two_stage = getattr(config, 'USE_TWO_STAGE_DPI', True)
                
                if use_two_stage and self.dpi > 50:  # Only reduce if we're above minimum
                    # Choose DPI based on text content
                    if text_len >= 300:
                        # Substantial text - use aggressive compression (TEXT_BACKUP_DPI)
                        target_dpi = getattr(config, 'TEXT_BACKUP_DPI', 50)
                        logger.debug(f"  🗜️ Using TEXT_BACKUP_DPI ({target_dpi}) - substantial text extracted")
                    else:
                        # Little/no text - use standard compression (STORAGE_DPI)
                        target_dpi = getattr(config, 'STORAGE_DPI', 150)
                    
                    if self.dpi > target_dpi:
                        scale = target_dpi / self.dpi
                        new_w, new_h = int(page_w * scale), int(page_h * scale)
                        storage_image = page_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        logger.debug(f"  📉 Reduced image: {page_w}x{page_h} @ {self.dpi}dpi → {new_w}x{new_h} @ {target_dpi}dpi ({scale*100:.0f}%)")
                
                result['images'].append(storage_image)
                logger.debug(f"  📄 Preserved full page (complexity: {complexity:.0f}, text: {text_len} chars).")
            else:
                logger.debug(f"  • Skipping image preservation for simple page")

            # ── BUILD CONTENT BLOCKS for positional EPUB layout ───────────────
            # If layout analysis ran and found figure regions, we can reconstruct
            # the exact page reading order: text above/below/between images.
            # Each block has: {type, y, content|image}
            # Sorted by Y so EPUB renders top→bottom matching the original page.
            layout_figure_coords = analysis.get('layout_figure_coords', [])
            if layout_figure_coords and layout_figure_crops:
                try:
                    # Get full layout from analyzer (already ran earlier — reuse engine cache)
                    full_layout = self.layout_analyzer.analyze(page_image)
                    page_h_for_blocks = page_image.height
                    content_blocks = []

                    # Add figure crops as image blocks (use their top Y coordinate)
                    for (x1, y1, x2, y2), crop_img in zip(layout_figure_coords, layout_figure_crops):
                        content_blocks.append({
                            'type': 'image',
                            'y': y1,
                            'image': crop_img,
                            'width_pct': (crop_img.width / max(1, page_image.width)) * 100
                        })

                    # Add title regions as title blocks
                    for box in full_layout.get('title', []):
                        y_top = int(box['coordinate'][1])
                        # Skip if overlaps a figure region
                        if not any(y1 <= y_top <= y2 for (_, y1, _, y2) in layout_figure_coords):
                            content_blocks.append({
                                'type': 'title',
                                'y': y_top,
                                'content': ''  # Title text comes from OCR of that region
                            })

                    # Distribute text across regions between figures MORE PRECISELY.
                    # We use the text bounding boxes from full_layout to see how much text
                    # ACTUALLY exists before and after each figure, rather than just splitting
                    # by the page height proportion (which is inaccurate for large figures/spaces).
                    text_lines = text.splitlines()
                    
                    text_boxes = full_layout.get('text', []) + full_layout.get('title', [])
                    
                    if figure_y_pcts and text_lines and text_boxes:
                        # Calculate total height of all text on the page
                        total_text_h = sum(max(1, box['coordinate'][3] - box['coordinate'][1]) for box in text_boxes)
                        
                        # Find the proportion of text BEFORE each figure
                        text_splits = [0.0]
                        for fy_start in figure_y_pcts:
                            fy_px = fy_start * page_h_for_blocks
                            text_h_before = sum(
                                max(1, min(box['coordinate'][3], fy_px) - box['coordinate'][1]) 
                                for box in text_boxes if box['coordinate'][1] < fy_px
                            )
                            text_splits.append(min(1.0, text_h_before / max(1.0, total_text_h)))
                        text_splits.append(1.0)
                        
                        # Split lines based on these precise text proportions
                        for seg_idx in range(len(text_splits) - 1):
                            seg_start = text_splits[seg_idx]
                            seg_end   = text_splits[seg_idx + 1]
                            # The Y coordinate to assign this block
                            seg_y     = int((figure_y_pcts[seg_idx-1] if seg_idx > 0 else 0.0) * page_h_for_blocks)
                            
                            start_line = int(seg_start * len(text_lines))
                            end_line   = int(seg_end   * len(text_lines))
                            seg_text = '\n'.join(text_lines[start_line:end_line]).strip()
                            if seg_text:
                                content_blocks.append({
                                    'type': 'text',
                                    'y': seg_y,
                                    'content': seg_text
                                })
                    else:
                        # No figures or no text layout info — add as single block
                        if text.strip():
                            content_blocks.append({'type': 'text', 'y': 0, 'content': text})

                    # Sort all blocks by Y position (top to bottom)
                    content_blocks.sort(key=lambda b: b['y'])
                    result['content_blocks'] = content_blocks
                    logger.debug(
                        f"  📑 Built {len(content_blocks)} content blocks "
                        f"({sum(1 for b in content_blocks if b['type']=='image')} images, "
                        f"{sum(1 for b in content_blocks if b['type']=='text')} text segments)"
                    )
                except Exception as _cb_e:
                    logger.debug(f"content_blocks build failed (non-fatal): {_cb_e}")

        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {e}")
            self._log_event('page_error', page_num=page_num + 1, error=str(e),
                            error_type=type(e).__name__)
        finally:
            # Guaranteed release on every exit path above: normal completion,
            # the early mostly-graphic-page return, or any exception — Python
            # runs `finally` in all three cases before the function actually
            # returns/re-raises. Only release if we actually acquired (pages
            # that short-circuit before the Stage-2 gate never touch it).
            if stage2_gate_held:
                self._stage2_semaphore.release()

        return result

    
    def _process_single_page_wrapper(self, pdf_path: Path, page_num: int,
                                     total_pages: int, skip_first_pages: int) -> List[Dict]:
        """
        Process a single PDF page (with potential splitting)
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            total_pages: Total number of pages
            skip_first_pages: Number of first pages to preserve as cover images
            
        Returns:
            List of processed page results (1 if single page, 2 if split)
        """
        page_start = time.time()
        
        # Check if this page should skip OCR (user-specified problematic pages)
        # IMPORTANT: Check against original PDF page number (before splitting)
        if (page_num + 1) in self.skip_ocr_pages:  # +1 because page_num is 0-indexed
            logger.warning(f"⚠️ Page {page_num + 1}: SKIPPING OCR (user-specified)")
            logger.info(f"  📸 Preserving page {page_num + 1} as image only (no OCR)")
            
            # Convert PDF page to image
            page_image = self._convert_single_page(pdf_path, page_num)
            if page_image is None:
                logger.warning(f"Skipping page {page_num + 1} (conversion failed)")
                return []
            
            # Preserve full page as image (no splitting for skipped pages)
            result = {
                'page_num': page_num,
                'sub_idx': 0,
                'text': '',
                'tables': [],
                'images': [page_image],
                'is_cover': False,
                'skipped_ocr': True
            }
            
            # Free memory
            del page_image
            gc.collect()
            
            logger.info(f"✅ Page {page_num + 1} completed (image only, no OCR)")
            return [result]
        
        # Convert PDF page to image
        page_image = self._convert_single_page(pdf_path, page_num)
        if page_image is None:
            logger.warning(f"Skipping page {page_num + 1} (conversion failed)")
            return []
        
        # Split double-page scans if enabled
        page_images_to_process = []
        if self.page_splitter:
            split_pages = self.page_splitter.process_image(page_image)
            page_images_to_process = split_pages
        else:
            page_images_to_process = [page_image]
        
        results = []
        
        # Process each page (1 if single, 2 if split from double-page)
        for sub_idx, sub_page_image in enumerate(page_images_to_process):
            # We keep the original page_num but track sub_idx to prevent collisions
            # during parallel collection and build.
            effective_page_num = page_num
            log_label = f"Page {page_num + 1}.{sub_idx + 1}" if len(page_images_to_process) > 1 else f"Page {page_num + 1}"
            
            # --- CACHE REUSE & RESCUE LOGIC ---
            # Look for new naming (page_N_sub.jbl) or old naming (page_N.jbl)
            cache_file = self.temp_results_dir / f"page_{page_num}_{sub_idx}.jbl"
            old_cache_file = self.temp_results_dir / f"page_{page_num}.jbl"
            
            if not cache_file.exists() and sub_idx == 0 and old_cache_file.exists():
                cache_file = old_cache_file

            if cache_file.exists():
                try:
                    cached_result = self._load_page_result(cache_file)
                    cached_text = cached_result.get('text', '')
                    
                    # Analyze the actual image to get estimated lines (for comparison)
                    analysis = self.adaptive_factory.analyzer.analyze(sub_page_image)
                    estimated_lines = analysis.get('estimated_lines', 0)
                    actual_lines = PageComplexityAnalyzer.get_text_line_count(cached_text)
                    
                    # Determine if this cached result is "Good" or needs "Rescue"
                    is_junk = PageComplexityAnalyzer.is_junk_text(cached_text)
                    was_rescued = 'gemini' in cached_result.get('ocr_engine', '').lower()
                    
                    # NEW: Quality check even for cached results
                    # If it's not junk, we also check if it's missing significant lines
                    rescue_thresh = getattr(config, 'GEMINI_RESCUE_THRESHOLD', 0.50)
                    is_missing_text = (estimated_lines > 10 and actual_lines < (estimated_lines * rescue_thresh))
                    
                    # Check for character contamination (mixed English-Telugu words) in cached results
                    is_contaminated = False
                    if cached_text.strip():
                        words = cached_text.split()
                        mixed_count = 0
                        import re
                        for w in words:
                            if re.search(r'[\u0C00-\u0C7F]', w) and re.search(r'[a-zA-Z]', w):
                                mixed_count += 1
                        
                        max_mixed = getattr(config, 'PADDLE_MAX_MIXED_WORDS', 3)
                        max_ratio = getattr(config, 'PADDLE_MAX_MIXED_RATIO', 0.02)
                        ratio = mixed_count / len(words) if words else 0
                        if mixed_count > max_mixed or ratio > max_ratio:
                            is_contaminated = True
                    
                    # If it's already a Gemini result, or it's non-junk Tesseract with enough lines and not contaminated, reuse it
                    if was_rescued or (cached_text.strip() and not is_junk and not is_missing_text and not is_contaminated):
                        logger.info(f"  ⏭️  Reusing CACHED result for {log_label} (Engine: {cached_result.get('ocr_engine', 'Unknown')})")
                        
                        # Update stats even for cached results
                        engine = cached_result.get('ocr_engine', '').lower()
                        if 'gemini' in engine:
                            if 'rescue' in engine or cached_result.get('rescue_success'):
                                self.gemini_stats['rescue'] += 1
                            else:
                                self.gemini_stats['direct'] += 1
                        elif 'tesseract' in engine:
                            self.tesseract_pages += 1
                            
                        results.append(cached_result)
                        continue 
                    else:
                        if is_junk:
                            reason = "junk detected"
                        elif is_contaminated:
                            reason = f"mixed_word_contamination (got {mixed_count} mixed words)"
                        else:
                            reason = "missing text"
                        logger.info(f"  🩺  Cached result for {log_label} is poor quality ({reason}). Triggering REPROCESS/RESCUE...")
                except Exception as e:
                    logger.warning(f"Failed to load cache for {log_label}: {e}")

            # Check if this is a cover page (skip OCR for first and last pages)
            is_first_pages = page_num < skip_first_pages
            is_last_pages = page_num >= (total_pages - skip_first_pages)
            
            if is_first_pages or is_last_pages:
                position_label = "First" if is_first_pages else "Back"
                logger.info(f"Page {page_num + 1}.{sub_idx + 1} - {position_label} cover page (preserving as image only)")
                
                # Resize cover image if Two-Stage DPI is enabled
                storage_image = sub_page_image
                use_two_stage = getattr(config, 'USE_TWO_STAGE_DPI', True)
                storage_dpi = getattr(config, 'STORAGE_DPI', 150)
                
                if use_two_stage and self.dpi > storage_dpi:
                    scale = storage_dpi / self.dpi
                    w, h = sub_page_image.size
                    storage_image = sub_page_image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                
                result = {
                    'page_num': page_num,
                    'sub_idx': sub_idx,
                    'text': '',
                    'tables': [],
                    'images': [storage_image],
                    'is_cover': True
                }
            else:
                # Process page with OCR
                result = self.process_page_optimized(sub_page_image, page_num, total_pages, sub_idx=sub_idx)
                result['sub_idx'] = sub_idx
            
            results.append(result)
            
            # Free memory for sub-page
            del sub_page_image
        
        # Free memory for original page
        del page_image
        
        # Aggressive memory cleanup after each page
        gc.collect()
        
        # Log timing
        page_time = time.time() - page_start
        import threading
        thread_id = threading.current_thread().name
        logger.info(f"[Page {page_num+1}] ✅ Completed in {page_time:.1f}s")
        
        return results
    
    def _process_single_page_thread_worker(self, pdf_path: Path, page_num: int,
                                           total_pages: int, skip_first_pages: int) -> Tuple[List[Path], List[Dict]]:
        """
        Worker function executed in ThreadPoolExecutor.
        Processes a single page and writes results directly to disk as .jbl files.
        Returns a tuple of (list of Path to saved .jbl files, list of dict containing UI metadata).
        """
        results = self._process_single_page_wrapper(
            pdf_path=pdf_path,
            page_num=page_num,
            total_pages=total_pages,
            skip_first_pages=skip_first_pages
        )

        saved_paths = []
        ui_metadata = []

        for res in results:
            sub_idx = res.get('sub_idx', 0)
            file_path = self.temp_results_dir / f"page_{page_num}_{sub_idx}.jbl"
            
            # Save result to disk immediately
            joblib.dump(res, file_path)
            saved_paths.append(file_path)
            
            # Extract UI metadata
            ui_metadata.append({
                'page_num': page_num + 1,
                'sub_idx': sub_idx,
                'complexity_score': res.get('complexity_score', 0.0),
                'ocr_engine': res.get('ocr_engine', 'unknown'),
                'has_table': len(res.get('tables', [])) > 0,
                'has_illustrations': len(res.get('images', [])) > 0,
                'skipped_ocr': res.get('skipped_ocr', False),
                'is_cover': res.get('is_cover', False),
                'reasoning': res.get('reasoning', '')
            })
            
            # Free memory immediately
            del res
            
        return saved_paths, ui_metadata
    
    def convert_streaming(self, pdf_path: Path, output_path: Path,
                         title: str = None, author: str = None,
                         max_pages: int = None, skip_first_pages: int = 0,
                         only_pages: list = None) -> bool:
        """
        Convert PDF to EPUB with streaming (one page at a time)
        
        Args:
            pdf_path: Path to input PDF
            output_path: Path to output EPUB
            title: Book title
            author: Book author
            max_pages: Maximum pages to process (for testing, e.g. 10)
            skip_first_pages: Number of first pages to preserve as cover images (no OCR)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            start_time = time.time()
            logger.info(f"Starting optimized conversion: {pdf_path}")
            
            # Verify Telugu support
            if not self.ocr_processor.verify_telugu_support():
                logger.warning("Telugu OCR support not verified!")
            
            # Open PDF to get page count
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            
            # Limit pages if specified (for testing)
            if max_pages:
                total_pages = min(total_pages, max_pages)
                logger.info(f"Processing first {total_pages} pages (test mode)")
            
            # Create title-based working directory for intermediate files
            self.book_title = title or Path(pdf_path).stem
            safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in self.book_title)
            safe_title = safe_title.replace(' ', '_')[:50]  # Limit length
            
            # --- SMART RESUME: Search for existing run with same title ---
            target_dir = None
            if config.TEMP_FOLDER.exists():
                # Look for directories starting with this title (ignoring session suffix)
                existing_dirs = [d for d in config.TEMP_FOLDER.iterdir() 
                               if d.is_dir() and d.name.startswith(safe_title)]
                if existing_dirs:
                    # Sort by modification time to get the latest run
                    existing_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                    target_dir = existing_dirs[0]
                    logger.info(f"♻️  SMART RESUME: Found existing results in {target_dir.name}")
            
            # Use existing dir if found, otherwise create new one
            if target_dir:
                self.temp_results_dir = target_dir
                # Also sync session_id if we want to be perfect, but temp_results_dir is what matters
            else:
                self.temp_results_dir = config.TEMP_FOLDER / f"{safe_title}_{self.session_id}"
                self.temp_results_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"📁 Working directory: {self.temp_results_dir}")
            logger.info(f"Total pages to process: {total_pages}")
            
            if skip_first_pages > 0:
                logger.info(f"First {skip_first_pages} pages will be preserved as cover images (no OCR)")
            
            # Log initial memory state
            self._log_memory_usage("Start of Conversion")
            
            # Process pages
            processed_pages = []
            
            # Determine which page indices to process
            effective_only_pages = only_pages if only_pages else (list(self.only_pages) if self.only_pages else None)
            
            if effective_only_pages:
                # Filter to only the requested pages (1-indexed translates to 0-indexed)
                target_pages = [p-1 for p in effective_only_pages if 0 <= p-1 < total_pages]
                if not target_pages:
                    logger.error(f"None of the requested pages {sorted(effective_only_pages)} exist (Total: {total_pages})")
                    return False
                page_indices = sorted(list(set(target_pages))) # Unique and sorted
                total_pages_to_process = len(page_indices)
                logger.info(f"Filtering: Processing {total_pages_to_process} specific pages out of {total_pages}")
            else:
                page_indices = list(range(total_pages))
                total_pages_to_process = total_pages
            
            # Use dynamic batch size based on current system memory
            current_batch_size = self._get_dynamic_batch_size(self.batch_size)
            batches = [page_indices[i:i + current_batch_size] 
                      for i in range(0, total_pages_to_process, current_batch_size)]
            
            if current_batch_size != self.batch_size:
                logger.info(f"📦 Optimized for memory: Using batch size {current_batch_size} (requested {self.batch_size})")
            
            # Initial progress
            if self.progress_callback:
                self.progress_callback("Reading PDF pages...", 0, total_pages_to_process)
            
            if self.enable_parallel and total_pages_to_process > 1:
                # Determine config module override name
                try:
                    config_module_name = config.__name__
                except Exception:
                    config_module_name = 'config'

                # Use dynamic batch size calculation to throttle max workers if RAM is low
                try:
                    import psutil
                    available_gb = psutil.virtual_memory().available / (1024**3)
                    safe_processes = max(1, int((available_gb - 2.0) / 1.1))
                    active_workers = min(self.max_workers, safe_processes)
                    if active_workers < self.max_workers:
                        logger.warning(f"⚠️ [worker-throttle] Low Memory Alert: {available_gb:.1f}GB available (assumes 1.1GB/worker). Throttling thread workers {self.max_workers} → {active_workers}")
                except Exception:
                    active_workers = self.max_workers

                logger.info(f"Using rolling ThreadPool: {active_workers} workers across {total_pages_to_process} pages")
                
                pages_processed_count = 0
                last_gc_count = 0  # Track when to run GC
                
                with ThreadPoolExecutor(max_workers=active_workers) as executor:
                    # Submit all pages at once; the executor manages concurrency
                    futures = {
                        executor.submit(
                            self._process_single_page_thread_worker,
                            pdf_path, page_num, total_pages, skip_first_pages
                        ): page_num
                        for page_num in page_indices
                    }
                    
                    for future in as_completed(futures):
                        # Check cancellation
                        if self._cancelled.is_set():
                            logger.warning("🛑 Conversion CANCELLED by user — cancelling pending futures...")
                            for f in futures:
                                f.cancel()
                            break
                        
                        page_num = futures[future]
                        try:
                            saved_paths, ui_metadata = future.result()
                            
                            # Register the saved paths in the main process
                            for path in saved_paths:
                                parts = path.split('_') if isinstance(path, str) else path.stem.split('_')
                                sub_idx = int(parts[2])
                                self.page_result_paths[(page_num, sub_idx)] = path
                                
                                # Read text for json export / tracking (lightweight, doesn't load full image)
                                try:
                                    res = self._load_page_result(path)
                                    self._export_page_text_json(res)
                                    del res
                                except Exception:
                                    pass
                                    
                            # Emit progress callbacks sequentially in parent process,
                            # AND log unconditionally to converter_events.jsonl (same
                            # reasoning as the other two page_analysis emission sites).
                            import json as _json
                            for meta in ui_metadata:
                                engine_display = {
                                    'paddle': 'PaddleOCR',
                                    'tesseract': 'Tesseract',
                                    'gemini': 'Gemini Vision',
                                    'merged': 'Mixed (PaddleOCR + Tesseract)',
                                    'none': 'None (Failed)'
                                }.get(meta['ocr_engine'].lower(), meta['ocr_engine'])

                                page_analysis_fields = {
                                    "page_num": meta['page_num'],
                                    "complexity_score": round(meta['complexity_score'], 1),
                                    "engine": engine_display,
                                    "has_table": meta['has_table'],
                                    "has_illustrations": meta['has_illustrations'],
                                    "has_mixed_content": False,
                                    "is_multicolumn": False,
                                    "is_very_complex": False,
                                    "reasoning": meta['reasoning'],
                                    "timestamp": time.time()
                                }
                                self._log_event('page_analysis', phase='batch', **page_analysis_fields)
                                if self.progress_callback:
                                    self.progress_callback(
                                        _json.dumps({"page_analysis": page_analysis_fields}),
                                        meta['page_num'], max(total_pages, 1))

                        except Exception as e:
                            logger.error(f"Failed to process page {page_num + 1} in process pool: {e}")
                            self._log_event('page_error', page_num=page_num + 1, error=str(e),
                                            error_type=type(e).__name__, context='batch_future')
                        
                        pages_processed_count += 1
                        
                        # Progress + ETA
                        elapsed = time.time() - start_time
                        avg_time = elapsed / pages_processed_count
                        remaining = total_pages_to_process - pages_processed_count
                        eta = avg_time * remaining
                        logger.info(f"📊 Progress: {pages_processed_count}/{total_pages_to_process} pages | ⏱️ ETA: {eta:.0f}s ({eta/60:.1f}min)")
                        
                        # Periodic GC every 10 pages to prevent RAM build-up
                        if pages_processed_count - last_gc_count >= 10:
                            self._cleanup_memory()
                            last_gc_count = pages_processed_count
                        
            else:
                # Sequential processing (fallback or single page)
                if not self.enable_parallel:
                    logger.info("Using sequential processing (parallel disabled)")
                else:
                    logger.info("Using sequential processing (single page)")
                
                pages_processed_count = 0
                for batch_idx, batch_pages in enumerate(batches):
                    for page_num in batch_pages:
                        # Check cancellation
                        if self._cancelled.is_set():
                            logger.warning(f"🛑 Conversion CANCELLED by user at page {page_num + 1}")
                            break
                        
                        results = self._process_single_page_wrapper(pdf_path, page_num, total_pages, skip_first_pages)
                        for res in results:
                            path = self._save_page_result(res)
                            self.page_result_paths[(page_num, res.get('sub_idx', 0))] = path
                            self._export_page_text_json(res)
                            del res
                        
                        pages_processed_count += 1
                        
                        # Log timing
                        elapsed = time.time() - start_time
                        avg_time = elapsed / max(pages_processed_count, 1)
                        remaining = total_pages_to_process - pages_processed_count
                        eta = avg_time * remaining
                        
                        logger.info(f"Progress: {pages_processed_count}/{total_pages_to_process} pages | ETA: {eta:.0f}s ({eta/60:.1f}min)")
                    
                    if self._cancelled.is_set():
                        break
            
            # Check if cancelled — do NOT build EPUB/MOBI with incomplete pages
            if self._cancelled.is_set():
                pages_processed = len(self.page_result_paths)
                logger.warning(f"🛑 Conversion cancelled by user after processing {pages_processed}/{total_pages} pages — skipping EPUB/MOBI build")
                # Cleanup temp results
                if config.CLEANUP_TEMP_FILES:
                    try:
                        shutil.rmtree(self.temp_results_dir)
                        logger.info(f"✓ Cleaned up temp directory: {self.temp_results_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp results: {e}")
                return False
            
            # ────────────────────────────────────────────────────────────
            #  OCR ENGINE SUMMARY REPORT
            # ────────────────────────────────────────────────────────────
            # Build engine stats from saved .jbl results
            _ocr_counts = {'paddle': [], 'tesseract': [], 'gemini': [], 'image': [], 'other': []}
            for page_key, jbl_path in sorted(self.page_result_paths.items()):
                try:
                    _r = self._load_page_result(jbl_path)
                    _pg = _r.get('page_num', page_key[0]) + 1
                    if _r.get('is_cover') or _r.get('skipped_ocr'):
                        _ocr_counts['image'].append(_pg)
                    else:
                        _eng = (_r.get('ocr_engine') or '').lower()
                        if 'gemini' in _eng:
                            _ocr_counts['gemini'].append(_pg)
                        elif 'tesseract' in _eng or 'paddle' in _eng or 'merged' in _eng:
                            # paddle engine label is kept even when Tesseract did the actual work
                            # Check text presence as proxy
                            _ocr_counts['tesseract' if 'tesseract' in _eng else 'paddle'].append(_pg)
                        elif _eng:
                            _ocr_counts['other'].append(_pg)
                        else:
                            _ocr_counts['image'].append(_pg)
                except Exception:
                    pass

            logger.info("")
            logger.info("=" * 60)
            logger.info("  📊 OCR ENGINE SUMMARY REPORT")
            logger.info("=" * 60)
            logger.info(f"  🏘️  Image only (cover/back)  : {len(_ocr_counts['image'])} pages  {_ocr_counts['image']}")
            logger.info(f"  🏏  Paddle PP-OCRv5          : {len(_ocr_counts['paddle'])} pages  {_ocr_counts['paddle']}")
            logger.info(f"  🔧  Tesseract fallback       : {len(_ocr_counts['tesseract'])} pages  {_ocr_counts['tesseract']}")
            logger.info(f"  🤖  Gemini Vision            : {len(_ocr_counts['gemini'])} pages  {_ocr_counts['gemini']}")
            if _ocr_counts['other']:
                logger.info(f"  ❓  Other                   : {len(_ocr_counts['other'])} pages  {_ocr_counts['other']}")
            logger.info("-" * 60)
            logger.info(f"  Gemini direct calls      : {self.gemini_stats['direct']}")
            logger.info(f"  Gemini rescue calls      : {self.gemini_stats['rescue']}")
            logger.info("=" * 60)
            logger.info("")

            # ── Expose counts to app.py (read via getattr after convert_streaming returns) ──
            self.paddle_pages     = len(_ocr_counts['paddle'])
            self.tesseract_pages  = len(_ocr_counts['tesseract'])
            self.gemini_pages     = len(_ocr_counts['gemini'])
            self.image_only_pages = len(_ocr_counts['image'])

            # ── QUALITY REPORT ──────────────────────────────────────────────
            # self.rescue_report/self.quality_warnings/self.ocr_discrepancies were
            # already being collected per-page (see the Level-3 junk-discard check
            # above) but were never written anywhere — persist them once here so
            # the data is actually usable after the run instead of discarded when
            # the process exits.
            if self.temp_results_dir is not None:
                try:
                    import json
                    quality_report = {
                        'book_title': self.book_title,
                        'total_pages': len(self.page_result_paths),
                        'engine_summary': {
                            'image_only': _ocr_counts['image'],
                            'paddle': _ocr_counts['paddle'],
                            'tesseract': _ocr_counts['tesseract'],
                            'gemini': _ocr_counts['gemini'],
                            'other': _ocr_counts['other'],
                        },
                        'gemini_stats': self.gemini_stats,
                        'tesseract_pages': self.tesseract_pages,
                        'ocr_discrepancies': self.ocr_discrepancies,
                        'quality_warnings': self.quality_warnings,
                        'rescue_report': self.rescue_report,
                    }
                    quality_report_path = self.temp_results_dir / "quality_report.json"
                    with open(quality_report_path, 'w', encoding='utf-8') as _qf:
                        json.dump(quality_report, _qf, indent=2, ensure_ascii=False)
                    logger.info(f"  📋 Quality report written: {quality_report_path}")
                except Exception as e:
                    logger.warning(f"Failed to write quality report: {e}")

            # ── Dictionary-correction review gate ───────────────────────────
            # Pages with unreviewed dictionary corrections (see
            # docs/TELUGU_SPELL_CORRECTION_TODO.md) block the automatic build —
            # loaded from disk (not tracked in-memory during the loop above)
            # because page processing can run via process pool, thread pool, or
            # sequential fallback, and .jbl results are the one place all three
            # paths reliably converge. Exposed via getattr after this method
            # returns, same convention as self.paddle_pages/self.tesseract_pages
            # above — avoids changing this method's bool return type.
            self.pages_pending_review = []
            if getattr(config, 'ENABLE_TELUGU_DICTIONARY_CORRECTION', False) and self.page_result_paths:
                for (page_num, sub_idx), path in sorted(self.page_result_paths.items()):
                    try:
                        page_data = joblib.load(path)
                    except Exception:
                        continue
                    if page_data.get('needs_manual_review'):
                        self.pages_pending_review.append(page_num + 1)  # 1-indexed for display

            if self.pages_pending_review:
                logger.info(
                    f"⏸️ Deferring automatic EPUB build — {len(self.pages_pending_review)} "
                    f"page(s) have dictionary corrections needing manual review: "
                    f"{self.pages_pending_review}"
                )
                return True

            # Step 4: Build EPUB
            # Streaming conversion only saves pages to disk; rebuild_book_from_results handles the actual EPUB compilation.
            logger.info("🛠️ Building final EPUB from processed results...")
            return self.rebuild_book_from_results(output_path, title, author)
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return False

    def rebuild_book_from_results(self, output_path: Path, title: str = None, author: str = None) -> bool:
        """
        Rebuild the final EPUB and MOBI from existing .jbl results in temp_results_dir.
        Useful for applying manual corrections or reworks.
        """
        try:
            if not self.temp_results_dir or not self.temp_results_dir.exists():
                logger.error("Cannot rebuild book: temp_results_dir missing")
                return False

            # Refresh page_result_paths from disk if it's empty
            if not self.page_result_paths:
                for f in sorted(self.temp_results_dir.glob("page_*.jbl")):
                    parts = f.stem.replace("page_", "").split("_")
                    page_num = int(parts[0])
                    sub_idx = int(parts[1]) if len(parts) > 1 else 0
                    self.page_result_paths[(page_num, sub_idx)] = f

            logger.info(f"Building EPUB from {len(self.page_result_paths)} results...")
            
            builder = EPUBBuilder(
                title=title or config.EPUB_METADATA['title'],
                author=author or config.EPUB_METADATA['author'],
                language=self.language
            )
            
            # Add content
            sorted_page_nums = sorted(self.page_result_paths.keys())
            for page_num_key in sorted_page_nums:
                path = self.page_result_paths[page_num_key]
                page_result = self._load_page_result(path)
                
                is_cover = page_result.get('is_cover', False)
                chapter_title = f"Page {page_num_key[0] + 1}" if not is_cover else "Cover"
                
                # ── POSITIONAL CONTENT BLOCKS (from layout analysis) ──────────
                # If the page was processed with layout-first routing, content_blocks
                # contains ordered text/image/title segments sorted by Y position.
                # Use create_chapter_from_blocks to preserve the exact reading order
                # (e.g. logo at top → text → diagram in middle → text below).
                content_blocks = page_result.get('content_blocks')
                if content_blocks:
                    chapter = builder.create_chapter_from_blocks(
                        title=chapter_title,
                        content_blocks=content_blocks
                    )
                else:
                    # Legacy: plain text + images appended after text
                    content_parts = []
                    if page_result.get('text'):
                        content_parts.append(f"<div>{page_result['text'].replace(chr(10), '<br/>')}</div>")
                    chapter = builder.create_chapter(
                        title=chapter_title,
                        content="".join(content_parts),
                        images=page_result.get('images', [])
                    )
                builder.add_chapter(chapter)

                del page_result
                gc.collect()
            
            epub_success = builder.build(output_path)
            
            # MOBI conversion
            if epub_success and config.ENABLE_MOBI_CONVERSION:
                try:
                    from mobi_converter import MOBIConverter
                    mobi_converter = MOBIConverter()
                    if mobi_converter.is_available():
                        mobi_converter.convert(str(output_path), str(output_path.with_suffix('.mobi')))
                except Exception: pass
            
            return epub_success
        except Exception as e:
            logger.error(f"Rebuild failed: {e}")
            return False

    def rework_page(self, pdf_path: Path, page_num: int, engine_name: str = 'gemini',
                    sub_idx: int = 0) -> Dict:
        """
        Re-run OCR for a single already-converted page with a specific engine,
        for the manual correction dashboard's REWORK button. Bypasses the normal
        complexity-based adaptive routing entirely — an explicit engine choice
        from the correction UI should be honored exactly, not reinterpreted.

        Args:
            pdf_path: Path to the original PDF (page_num is 0-indexed into this,
                matching process_page_optimized()'s convention — NOT repair_book()'s
                1-indexed EPUB-chapter convention)
            page_num: 0-indexed PDF page number
            engine_name: 'gemini', 'google_vision', or 'tesseract'
            sub_idx: which half of a double-page-split spread to target (0 or 1).
                Re-runs the same page_splitter split process_page_optimized() used
                originally and picks this half, rather than OCRing the whole raw
                page — getting this wrong would silently mix both columns' text
                into one result instead of reworking just the flagged half.

        Returns:
            {'page_num': int, 'sub_idx': int, 'text': str, 'ocr_engine': str}

        Raises:
            RuntimeError/ValueError on conversion failure or an unknown engine —
            deliberately not caught here, so the caller's error message reflects
            what actually went wrong instead of a generic failure.
        """
        raw_image = self._convert_single_page(pdf_path, page_num)
        if raw_image is None:
            raise RuntimeError(f"Failed to convert PDF page {page_num} for rework")

        if self.page_splitter:
            split_pages = self.page_splitter.process_image(raw_image)
        else:
            split_pages = [raw_image]
        if sub_idx >= len(split_pages):
            raise ValueError(
                f"Page {page_num} only has {len(split_pages)} sub-page(s) "
                f"(no splitting detected this time) — sub_idx {sub_idx} doesn't exist"
            )
        target_image = split_pages[sub_idx]

        engine_name = (engine_name or 'gemini').lower()
        if engine_name == 'gemini':
            from gemini_ocr_processor import GeminiOCRProcessor
            processor = GeminiOCRProcessor()
            if not processor.is_available:
                raise RuntimeError("Gemini OCR not available — set GEMINI_API_KEY in .env file")
            text = processor.extract_text(target_image, page_label=f"Rework Page {page_num + 1}")
        elif engine_name == 'google_vision':
            from google_vision_processor import GoogleVisionProcessor
            processor = GoogleVisionProcessor()
            if not processor.is_available:
                raise RuntimeError("Google Vision OCR not available — check GOOGLE_VISION_SERVICE_ACCOUNT")
            text = processor.extract_text(target_image)
        elif engine_name == 'tesseract':
            text = self.ocr_processor.extract_text(target_image, page_label=f"Rework Page {page_num + 1}")
        else:
            raise ValueError(f"Unknown rework engine: {engine_name!r} (expected gemini, google_vision, or tesseract)")

        if getattr(config, 'ENABLE_TELUGU_POST_PROCESSING', False) and text:
            text = post_process_telugu(text)

        # Persist back to the saved page result so REBUILD EBOOK picks up the
        # rework — same effect as a manual edit via save_corrected_page().
        target_path = self.page_result_paths.get((page_num, sub_idx))
        if target_path is None and self.temp_results_dir:
            candidate = self.temp_results_dir / f"page_{page_num}_{sub_idx}.jbl"
            if candidate.exists():
                target_path = candidate
        if target_path and target_path.exists():
            page_data = joblib.load(target_path)
            page_data['text'] = text
            page_data['ocr_engine'] = engine_name
            page_data['manual_correction'] = True
            joblib.dump(page_data, target_path)

            json_path = target_path.with_name(target_path.stem + "_text.json")
            if json_path.exists():
                import json as _json
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = _json.load(f)
                meta['text'] = text
                meta['text_length'] = len(text)
                meta['ocr_engine'] = engine_name
                meta['manual_correction'] = True
                with open(json_path, 'w', encoding='utf-8') as f:
                    _json.dump(meta, f, ensure_ascii=False, indent=2)

        return {'page_num': page_num, 'sub_idx': sub_idx, 'text': text, 'ocr_engine': engine_name}

    def repair_book(self, epub_path: Path, pdf_path: Path, repair_pages: List[int],
                    title: str = None, author: str = None, output_basename: str = None) -> Dict:
        """
        Surgically repair an existing EPUB by replacing specific pages with fresh OCR.

        Args:
            epub_path: Path to the existing EPUB file (may be a temp-saved copy with a
                generated prefix — pass output_basename separately for a clean output name)
            pdf_path: Path to the original PDF
            repair_pages: List of 1-indexed page numbers to re-OCR
            title: Optional new title
            author: Optional new author
            output_basename: Filename stem to use for the output (defaults to
                epub_path.stem, which is wrong when epub_path is a temp-saved copy —
                callers uploading a temp copy should pass the user's original filename)

        Returns:
            {'success': bool, 'output_path': Path|None, 'mobi_path': Path|None,
             'pages_needing_review': [int, ...], 'warning': str|None}
            output_path/mobi_path are the actual paths written — callers should use these
            directly rather than reconstructing the filename themselves (a prior version of
            this method returned only a bool, and the caller's independent filename guess
            didn't match what was actually written, so no download link ever worked).
        """
        from ebooklib import epub
        import shutil

        logger.info(f"🛠️ Starting surgical repair on {epub_path.name}")
        logger.info(f"🔧 Target pages for fresh OCR: {repair_pages}")

        empty_result = {
            'success': False, 'output_path': None, 'mobi_path': None,
            'pages_needing_review': [], 'warning': None,
        }

        try:
            # 1. Load existing EPUB
            book = epub.read_epub(str(epub_path))
            existing_items = []

            # Extract HTML items (chapters/pages)
            for item in book.get_items():
                if item.get_type() == epub.ITEM_DOCUMENT:
                    existing_items.append(item)

            # Sort items by filename (assuming chapter_001.xhtml etc)
            existing_items.sort(key=lambda x: x.file_name)

            # 2. Setup output builder
            builder = EPUBBuilder(
                title=title or book.get_metadata('DC', 'title')[0][0],
                author=author or book.get_metadata('DC', 'creator')[0][0],
                language=self.language
            )

            total_pages = len(existing_items)
            repair_set = set(repair_pages)

            # KNOWN LIMITATION: this assumes EPUB chapter index N corresponds exactly
            # to 0-indexed PDF page N. That's false whenever the original conversion
            # split double-page spreads (default on, see split_double_pages) or skipped
            # pages — either changes the chapter:PDF-page ratio, silently misaligning
            # which PDF page gets re-OCR'd for a given "page number" the user typed.
            # Detected here (chapter count vs. actual PDF page count) and surfaced as a
            # warning rather than blocking, since a correct fix needs the original
            # per-chapter PDF page number, which isn't stored in the EPUB today. If the
            # original data/temp/<book>_<session> results folder still exists, resuming
            # from it (see /api/correction/resume) reads real per-page numbers from the
            # saved .jbl results instead of guessing, and doesn't have this problem.
            warning = None
            try:
                import fitz
                with fitz.open(str(pdf_path)) as _doc:
                    actual_pdf_pages = len(_doc)
                if actual_pdf_pages != total_pages:
                    warning = (
                        f"This EPUB has {total_pages} page(s) but the PDF has "
                        f"{actual_pdf_pages} — they likely don't line up 1:1 (the original "
                        f"conversion may have split double-page spreads or skipped pages). "
                        f"Page numbers you specified may repair the wrong PDF page. If the "
                        f"original conversion's results folder still exists, use 'Resume "
                        f"from folder' instead for reliable page numbering."
                    )
                    logger.warning(f"⚠️ {warning}")
            except Exception as e:
                logger.debug(f"Could not verify PDF/EPUB page count alignment: {e}")

            pages_needing_review: List[int] = []

            # 3. Process pages
            for i, item in enumerate(existing_items):
                page_num_1indexed = i + 1

                if page_num_1indexed in repair_set:
                    logger.info(f"🔄 Repairing Page {page_num_1indexed} with fresh OCR...")
                    # Perform fresh OCR from PDF
                    img = self._convert_single_page(pdf_path, i) # 0-indexed for PDF
                    if img:
                        result = self.process_page_optimized(img, i, total_pages)
                        new_text = result['text']
                        new_images = result.get('images', [])
                        if result.get('needs_manual_review'):
                            pages_needing_review.append(page_num_1indexed)

                        chapter = builder.create_chapter(
                            title=f"Page {page_num_1indexed} (Repaired)",
                            content=new_text,
                            images=new_images
                        )
                    else:
                        logger.error(f"Failed to convert PDF page {i} for repair")
                        # Fallback to existing if PDF fail? No, let's keep it clean
                        chapter = builder.create_chapter(
                            title=f"Page {page_num_1indexed} (Repair Failed)",
                            content="[Repair Failed: Could not read source PDF page]"
                        )
                else:
                    # Keep existing content
                    # We need to extract the raw body content from the XHTML
                    from lxml import html
                    raw_content = item.get_content().decode('utf-8')
                    tree = html.fromstring(raw_content)
                    
                    # Try to find the body content (excluding title/h1 if our tool added them)
                    body = tree.xpath('//body')
                    if body:
                        # Extract everything inside body
                        inner_html = "".join([html.tostring(child).decode('utf-8') for child in body[0].getchildren()])
                        
                        # Strip standard H1 if it's just the page number we added
                        import re
                        inner_html = re.sub(r'<h1>Page \d+</h1>', '', inner_html)
                    else:
                        inner_html = raw_content
                        
                    chapter = builder.create_chapter(
                        title=f"Page {page_num_1indexed}",
                        content=inner_html
                    )
                
                builder.add_chapter(chapter)

            # 4. Final Build
            # We use the same name but with '_repaired' suffix for the new file.
            # output_basename (the user's original filename) is used when given —
            # epub_path may be a temp-saved copy with a generated prefix that
            # shouldn't leak into the user-facing output filename.
            output_name = (output_basename or epub_path.stem) + "_repaired.epub"
            output_path = config.OUTPUT_FOLDER / output_name

            success = builder.build(str(output_path))

            mobi_path = None
            if success and config.ENABLE_MOBI_CONVERSION:
                try:
                    from mobi_converter import MOBIConverter
                    mobi_converter = MOBIConverter()
                    if mobi_converter.is_available():
                        candidate_mobi = output_path.with_suffix('.mobi')
                        if mobi_converter.convert(str(output_path), str(candidate_mobi)):
                            mobi_path = candidate_mobi
                except Exception as e:
                    logger.warning(f"Repaired MOBI conversion failed: {e}")

            return {
                'success': success,
                'output_path': output_path if success else None,
                'mobi_path': mobi_path,
                'pages_needing_review': pages_needing_review,
                'warning': warning,
            }
        except Exception as e:
            logger.error(f"Book repair failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {**empty_result, 'warning': str(e)}


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description='Optimized PDF to EPUB converter for large books'
    )
    
    parser.add_argument('input', type=str, help='Input PDF file')
    parser.add_argument('output', type=str, help='Output EPUB file')
    parser.add_argument('--language', type=str, default='tel+eng',
                       help='OCR language code (default: tel+eng)')
    parser.add_argument('--dpi', type=int, default=250,
                       help='DPI for PDF conversion (default: 250 for balanced mode)')
    parser.add_argument('--max-pages', type=int, default=None,
                       help='Process only first N pages (for testing, e.g. 10)')
    parser.add_argument('--no-tables', action='store_true',
                       help='Disable table detection')
    parser.add_argument('--no-skip-empty', action='store_true',
                       help='Do not skip empty cells (slower but more thorough)')
    parser.add_argument('--workers', type=int, default=None,
                       help='Number of parallel OCR workers (default: config.MAX_WORKERS)')
    parser.add_argument('--title', type=str, help='Book title')
    parser.add_argument('--author', type=str, help='Book author')
    parser.add_argument('--skip-first-pages', type=int, default=0,
                       help='Skip OCR on first N pages (preserve as cover images, e.g. 2)')
    parser.add_argument('--no-split-pages', action='store_true',
                       help='Disable automatic double-page splitting')
    parser.add_argument('--split-threshold', type=float, default=1.15,
                       help='Aspect ratio threshold for double-page detection (default: 1.15)')
    parser.add_argument('--assume-double-page-spreads', action='store_true',
                       help='Split every wide page without requiring a detected spine gutter. '
                            'Use for corpora that are always genuine double-page scans but have '
                            'faint/worn gutters (e.g. old book photocopies).')
    parser.add_argument('--no-parallel', action='store_true',
                       help='Disable parallel page processing (use sequential)')
    parser.add_argument('--batch-size', type=int, default=None,
                       help='Number of pages to process in parallel (auto-calculated if not specified)')
    
    args = parser.parse_args()
    
    # Create converter
    converter = OptimizedPDFToEPUBConverter(
        language=args.language,
        dpi=args.dpi,
        detect_tables=not args.no_tables,
        preserve_images=True,
        skip_empty_cells=not args.no_skip_empty,
        max_workers=args.workers,
        split_double_pages=not args.no_split_pages,
        split_threshold=args.split_threshold,
        require_spine_confirmation=not args.assume_double_page_spreads,
        enable_parallel=not args.no_parallel,
        batch_size=args.batch_size
    )
    
    # Convert
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
    
    success = converter.convert_streaming(
        input_path,
        output_path,
        title=args.title,
        author=args.author,
        max_pages=args.max_pages,
        skip_first_pages=args.skip_first_pages
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
