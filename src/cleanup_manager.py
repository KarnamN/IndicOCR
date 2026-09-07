"""
Cleanup Manager
Manages memory and temporary file cleanup during heavy OCR tasks.
"""
import os
import gc
import glob
import psutil
import logging
from pathlib import Path
import config

logger = logging.getLogger(__name__)

class CleanupManager:
    """Monitors system resources and triggers cleanup to prevent OOM."""
    
    @staticmethod
    def check_memory():
        """Log current memory usage."""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        logger.debug(f"Current Memory Usage: {mem_info.rss / (1024 * 1024):.2f} MB")
        
        # If memory usage is high (>80% of system), trigger aggressive GC
        sys_mem = psutil.virtual_memory()
        if sys_mem.percent > 85:
            logger.warning(f"System memory critical ({sys_mem.percent}%). Aggressive cleanup...")
            CleanupManager.force_cleanup()

    @staticmethod
    def force_cleanup():
        """Force garbage collection and clear caches."""
        gc.collect()
        # If using torch or other backends, specific cache clears would go here
        logger.info("Garbage collection forced.")

    @staticmethod
    def cleanup_temp_files(temp_dir):
        """Clean up temporary images."""
        if not config.CLEANUP_TEMP_FILES:
            return
            
        try:
            for f in os.listdir(temp_dir):
                if f.endswith(('.png', '.jpg', '.tmp')):
                    os.remove(os.path.join(temp_dir, f))
        except Exception as e:
            logger.error(f"Temp cleanup failed: {e}")

    @staticmethod
    def cleanup_tesseract_leaks(search_dirs: list = None):
        """
        Remove leaked Tesseract temp files (tess_*.txt, *.osd) from the project root.
        
        These files are created when Tesseract's TEMP/TMP environment variable
        resolves to the wrong directory under WSL path mapping on Windows.
        Should be called at startup and after each conversion session.
        
        Args:
            search_dirs: List of directories to scan. Defaults to project root.
        """
        if search_dirs is None:
            # Default: project root (two levels up from src/)
            project_root = Path(__file__).parent.parent
            search_dirs = [str(project_root)]

        total_removed = 0
        for directory in search_dirs:
            try:
                patterns = [
                    os.path.join(directory, 'CUsers*.txt'),   # WSL-mangled path temp files
                    os.path.join(directory, 'CUsers*.osd'),   # orientation detection files
                    os.path.join(directory, 'tess_*.txt'),    # standard Tesseract temp files
                ]
                for pattern in patterns:
                    for f in glob.glob(pattern):
                        try:
                            os.remove(f)
                            total_removed += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Tesseract leak cleanup failed for {directory}: {e}")

        if total_removed > 0:
            logger.info(f"🧹 Cleaned {total_removed} leaked Tesseract temp file(s)")
        else:
            logger.debug("🧹 No Tesseract temp leaks found")
        return total_removed
