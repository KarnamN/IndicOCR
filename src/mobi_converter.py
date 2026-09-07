"""
MOBI Converter Module
Converts EPUB files to MOBI format using Calibre's ebook-convert
"""
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable
import shutil
import config

# Logging is configured centrally by logging_config.setup_logging() (invoked at
# app.py's import time) — this module just gets its own named logger from
# whatever root configuration is already in place.
logger = logging.getLogger(__name__)


class MOBIConverter:
    """Convert EPUB to MOBI using Calibre"""
    
    def __init__(self, calibre_path: str = None):
        """
        Initialize MOBI converter
        
        Args:
            calibre_path: Path to ebook-convert executable
        """
        self.calibre_path = calibre_path or self._find_calibre()
        self.available = self.calibre_path is not None
        
        if self.available:
            logger.info(f"MOBI Converter initialized with Calibre at: {self.calibre_path}")
        else:
            logger.warning("Calibre not found. MOBI conversion will not be available.")
    
    def _find_calibre(self) -> Optional[str]:
        """
        Find Calibre's ebook-convert executable
        
        Returns:
            Path to ebook-convert or None if not found
        """
        # Try common paths
        possible_paths = [
            'ebook-convert',  # In PATH
            '/usr/bin/ebook-convert',  # Linux
            '/usr/local/bin/ebook-convert',  # Linux/Mac
            'C:\\Program Files\\Calibre2\\ebook-convert.exe',  # Windows
            'C:\\Program Files (x86)\\Calibre2\\ebook-convert.exe',  # Windows
        ]
        
        for path in possible_paths:
            if shutil.which(path) or Path(path).exists():
                return path
        
        return None
    
    def is_available(self) -> bool:
        """
        Check if MOBI conversion is available
        
        Returns:
            True if Calibre is installed, False otherwise
        """
        return self.available
    
    def convert(self, epub_path: Path, mobi_path: Path, 
                progress_callback: Optional[Callable[[str, int, int], None]] = None) -> bool:
        """
        Convert EPUB to MOBI
        
        Args:
            epub_path: Path to input EPUB file
            mobi_path: Path to output MOBI file
            progress_callback: Optional callback function(stage, current, total)
            
        Returns:
            True if conversion successful, False otherwise
        """
        if not self.available:
            logger.error("Calibre not available. Cannot convert to MOBI.")
            return False
        
        # Convert to Path objects if strings are provided
        if isinstance(epub_path, str):
            epub_path = Path(epub_path)
        if isinstance(mobi_path, str):
            mobi_path = Path(mobi_path)
        
        if not epub_path.exists():
            logger.error(f"EPUB file not found: {epub_path}")
            return False
        
        try:
            logger.info(f"Converting EPUB to MOBI: {epub_path} -> {mobi_path}")
            
            if progress_callback:
                progress_callback("Converting to MOBI", 0, 100)
            
            # Build command with valid options only
            cmd = [
                self.calibre_path,
                str(epub_path),
                str(mobi_path),
                '--no-inline-toc',  # Don't add inline TOC
            ]
            
            # Note: --mobi-compression-level is not a valid option
            # Calibre handles compression automatically
            
            # Run conversion
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor progress
            progress = 0
            for line in process.stdout:
                # Calibre outputs progress information
                if progress_callback and progress < 90:
                    progress += 10
                    progress_callback("Converting to MOBI", progress, 100)
                logger.debug(line.strip())
            
            # Wait for completion
            return_code = process.wait()
            
            if return_code == 0:
                if progress_callback:
                    progress_callback("Converting to MOBI", 100, 100)
                logger.info(f"MOBI conversion successful: {mobi_path}")
                return True
            else:
                stderr = process.stderr.read()
                logger.error(f"MOBI conversion failed: {stderr}")
                return False
        
        except Exception as e:
            logger.error(f"MOBI conversion error: {e}")
            return False
    
    def get_version(self) -> Optional[str]:
        """
        Get Calibre version
        
        Returns:
            Version string or None
        """
        if not self.available:
            return None
        
        try:
            result = subprocess.run(
                [self.calibre_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get Calibre version: {e}")
            return None


def test_mobi_converter():
    """Test MOBI converter functionality"""
    converter = MOBIConverter()
    
    if converter.is_available():
        print("MOBI Converter is available")
        version = converter.get_version()
        if version:
            print(f"  Calibre version: {version}")
    else:
        print("MOBI Converter is not available")
        print("  Please install Calibre to enable MOBI conversion")
        print("  Linux: sudo apt-get install calibre")
        print("  Mac: brew install calibre")
        print("  Windows: Download from https://calibre-ebook.com/download")


if __name__ == "__main__":
    test_mobi_converter()
