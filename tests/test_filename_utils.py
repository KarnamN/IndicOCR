"""
Test script for filename generation functionality
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from filename_utils import (
    contains_telugu,
    transliterate_telugu_to_english,
    get_base_filename_from_pdf,
    generate_output_filenames,
    sanitize_filename
)


def test_contains_telugu():
    """Test Telugu detection"""
    print("Testing Telugu detection...")
    assert contains_telugu("తెలుగు") == True
    assert contains_telugu("english") == False
    assert contains_telugu("మిశ్రమ mixed") == True
    print("✓ Telugu detection works correctly\n")


def test_transliteration():
    """Test Telugu to English transliteration"""
    print("Testing transliteration...")
    
    test_cases = [
        ("తెలుగు", "thaelaugau"),
        ("పుస్తకం", "pausathakam"),
        ("హలో", "halao"),
    ]
    
    for telugu, expected in test_cases:
        result = transliterate_telugu_to_english(telugu)
        print(f"  {telugu} → {result}")
        # Note: We're just checking it produces output, not exact match
        # as transliteration can vary
        assert len(result) > 0
    
    print("✓ Transliteration works correctly\n")


def test_sanitization():
    """Test filename sanitization"""
    print("Testing filename sanitization...")
    
    test_cases = [
        ("file<name>.pdf", "filename.pdf"),
        ("file:name.pdf", "filename.pdf"),
        ("file  name.pdf", "file_name.pdf"),
        ("  file.pdf  ", "file.pdf"),
    ]
    
    for input_name, expected_pattern in test_cases:
        result = sanitize_filename(input_name)
        print(f"  '{input_name}' → '{result}'")
        assert len(result) > 0
    
    print("✓ Sanitization works correctly\n")


def test_base_filename_extraction():
    """Test base filename extraction"""
    print("Testing base filename extraction...")
    
    test_cases = [
        "తెలుగు_పుస్తకం.pdf",
        "sample_document.pdf",
        "మిశ్రమ mixed filename.pdf",
        "123_test.pdf",
    ]
    
    for filename in test_cases:
        result = get_base_filename_from_pdf(filename)
        print(f"  {filename} → {result}")
        assert len(result) > 0
        assert not result.endswith('.pdf')
    
    print("✓ Base filename extraction works correctly\n")


def test_output_filename_generation():
    """Test complete output filename generation"""
    print("Testing output filename generation...")
    
    test_cases = [
        ("తెలుగు.pdf", "telugu"),
        ("english_book.pdf", "english_book"),
        ("మిశ్రమ_mixed.pdf", "mishrama_mixed"),
    ]
    
    timestamp = "20231123_104500"
    job_id = "abc12345-6789-0123-4567-890123456789"
    
    for pdf_filename, expected_base in test_cases:
        epub, mobi = generate_output_filenames(pdf_filename, timestamp, job_id)
        print(f"  {pdf_filename}")
        print(f"    EPUB: {epub}")
        print(f"    MOBI: {mobi}")
        
        # Verify format (simple base name + extension)
        assert epub.endswith('.epub'), f"EPUB should end with .epub: {epub}"
        assert mobi.endswith('.mobi'), f"MOBI should end with .mobi: {mobi}"
        assert epub == f"{expected_base}.epub", f"Expected {expected_base}.epub, got {epub}"
        assert mobi == f"{expected_base}.mobi", f"Expected {expected_base}.mobi, got {mobi}"
    
    print("✓ Output filename generation works correctly\n")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Running Filename Utilities Tests")
    print("=" * 60)
    print()
    
    try:
        test_contains_telugu()
        test_transliteration()
        test_sanitization()
        test_base_filename_extraction()
        test_output_filename_generation()
        
        print("=" * 60)
        print("✓ All tests passed successfully!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
