"""
Text Cleaner - Clean and normalize OCR extracted text
"""
import re
import logging
from typing import List

from .config import REMOVE_PAGE_NUMBERS, PAGE_NUMBER_PATTERNS

logger = logging.getLogger(__name__)


class TextCleaner:
    """Clean and normalize OCR extracted text"""
    
    def __init__(self, remove_page_numbers: bool = REMOVE_PAGE_NUMBERS):
        """
        Initialize text cleaner
        
        Args:
            remove_page_numbers: Whether to remove page number patterns
        """
        self.remove_page_numbers = remove_page_numbers
        self.page_number_patterns = [re.compile(pattern, re.IGNORECASE) 
                                     for pattern in PAGE_NUMBER_PATTERNS]
    
    def remove_page_number_patterns(self, text: str) -> str:
        """
        Remove page number patterns from text
        
        Args:
            text: Input text
        
        Returns:
            Text with page numbers removed
        """
        if not self.remove_page_numbers:
            return text
        
        cleaned_text = text
        for pattern in self.page_number_patterns:
            cleaned_text = pattern.sub('', cleaned_text)
        
        return cleaned_text
    
    def normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text
        
        Args:
            text: Input text
        
        Returns:
            Text with normalized whitespace
        """
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        
        # Replace multiple newlines with double newline (paragraph break)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Remove spaces at start/end of lines
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    def fix_common_ocr_errors(self, text: str) -> str:
        """
        Fix common OCR errors
        
        Args:
            text: Input text
        
        Returns:
            Text with common errors fixed
        """
        # Fix common character substitutions
        replacements = {
            'l': 'I',  # lowercase L to uppercase I in certain contexts
            '0': 'O',  # zero to O in certain contexts
        }
        
        # This is a basic implementation
        # For Telugu-specific corrections, you could add more rules
        
        return text
    
    def remove_header_footer(self, text: str, header_lines: int = 2, footer_lines: int = 2) -> str:
        """
        Remove potential header/footer lines
        
        Args:
            text: Input text
            header_lines: Number of lines to remove from top
            footer_lines: Number of lines to remove from bottom
        
        Returns:
            Text with header/footer removed
        """
        lines = text.split('\n')
        
        if len(lines) <= (header_lines + footer_lines):
            return text
        
        # Remove header and footer
        if header_lines > 0:
            lines = lines[header_lines:]
        if footer_lines > 0:
            lines = lines[:-footer_lines]
        
        return '\n'.join(lines)
    
    def clean_text(self, text: str, remove_headers: bool = False) -> str:
        """
        Apply all cleaning operations
        
        Args:
            text: Input text
            remove_headers: Whether to remove header/footer lines
        
        Returns:
            Cleaned text
        """
        # Remove page numbers
        text = self.remove_page_number_patterns(text)
        
        # Remove headers/footers if requested
        if remove_headers:
            text = self.remove_header_footer(text)
        
        # Normalize whitespace
        text = self.normalize_whitespace(text)
        
        return text
    
    def clean_pages(self, page_texts: List[str]) -> List[str]:
        """
        Clean multiple pages of text
        
        Args:
            page_texts: List of text strings (one per page)
        
        Returns:
            List of cleaned text strings
        """
        logger.info(f"Cleaning {len(page_texts)} pages of text")
        
        cleaned_texts = []
        for i, text in enumerate(page_texts, start=1):
            cleaned = self.clean_text(text)
            cleaned_texts.append(cleaned)
            logger.debug(f"Cleaned page {i}")
        
        logger.info("Text cleaning complete")
        return cleaned_texts
    
    def merge_pages(self, page_texts: List[str], separator: str = '\n\n') -> str:
        """
        Merge multiple pages into single text
        
        Args:
            page_texts: List of text strings
            separator: Separator between pages
        
        Returns:
            Merged text
        """
        return separator.join(page_texts)
