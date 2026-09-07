#!/usr/bin/env python3
"""
Test script for verifying the text cleaning logic
"""
import re


def clean_ocr_text(text: str) -> str:
    """
    Clean OCR text by removing unwanted artifacts like "Page"
    
    Args:
        text: Raw OCR text
        
    Returns:
        Cleaned text
    """
    # Remove the word "Page" (case-insensitive, standalone word)
    # This will match "Page", "page", "PAGE" etc. as standalone words
    # Also handle surrounding whitespace intelligently
    cleaned = re.sub(r'\s*\bPage\b\s*', ' ', text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace that may result from removal
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)  # Multiple blank lines to double
    cleaned = re.sub(r' +', ' ', cleaned)  # Multiple spaces to single
    cleaned = re.sub(r'^\s+', '', cleaned, flags=re.MULTILINE)  # Leading spaces on lines
    
    return cleaned.strip()


def test_page_removal():
    """Test cases for page removal"""
    
    test_cases = [
        # Test 1: Simple "Page" word
        ("This is Page 1 content", "This is 1 content"),
        
        # Test 2: Case insensitive
        ("This is page 2 content", "This is 2 content"),
        ("This is PAGE 3 content", "This is 3 content"),
        
        # Test 3: Multiple occurrences
        ("Page 1\nSome text\nPage appears here", "1\nSome text appears here"),
        
        # Test 4: Should not remove "Page" as part of another word
        ("Homepage content", "Homepage content"),
        ("Webpage design", "Webpage design"),
        
        # Test 5: Extra whitespace cleanup
        ("Page   multiple   spaces", "multiple spaces"),
        
        # Test 6: Empty result
        ("Page", ""),
        
        # Test 7: No "Page" word
        ("Regular content without the word", "Regular content without the word"),
    ]
    
    print("Running text cleaning tests...\n")
    passed = 0
    failed = 0
    
    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = clean_ocr_text(input_text)
        if result == expected:
            print(f"✓ Test {i} passed")
            passed += 1
        else:
            print(f"✗ Test {i} failed")
            print(f"  Input:    '{input_text}'")
            print(f"  Expected: '{expected}'")
            print(f"  Got:      '{result}'")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    return failed == 0


if __name__ == "__main__":
    success = test_page_removal()
    exit(0 if success else 1)
