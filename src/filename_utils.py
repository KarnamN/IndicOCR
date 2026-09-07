"""
Filename Utilities
Handles filename processing including Telugu to English transliteration
"""
import re
from pathlib import Path


# Telugu to English transliteration mapping (improved for readability)
TELUGU_TO_ENGLISH = {
    # Vowels (independent)
    'అ': 'a', 'ఆ': 'aa', 'ఇ': 'i', 'ఈ': 'ee', 'ఉ': 'u', 'ఊ': 'oo',
    'ఋ': 'ru', 'ౠ': 'ruu', 'ఌ': 'lu', 'ౡ': 'luu',
    'ఎ': 'e', 'ఏ': 'e', 'ఐ': 'ai', 'ఒ': 'o', 'ఓ': 'o', 'ఔ': 'au',
    
    # Consonants (with inherent 'a' sound)
    'క': 'ka', 'ఖ': 'kha', 'గ': 'ga', 'ఘ': 'gha', 'ఙ': 'nga',
    'చ': 'cha', 'ఛ': 'chha', 'జ': 'ja', 'ఝ': 'jha', 'ఞ': 'nya',
    'ట': 'ta', 'ఠ': 'tha', 'డ': 'da', 'ఢ': 'dha', 'ణ': 'na',
    'త': 'ta', 'థ': 'tha', 'ద': 'da', 'ధ': 'dha', 'న': 'na',
    'ప': 'pa', 'ఫ': 'pha', 'బ': 'ba', 'భ': 'bha', 'మ': 'ma',
    'య': 'ya', 'ర': 'ra', 'ల': 'la', 'వ': 'va',
    'శ': 'sha', 'ష': 'sha', 'స': 'sa', 'హ': 'ha',
    'ళ': 'la', 'క్ష': 'ksha', 'ఱ': 'ra',
    
    # Vowel signs (matras) - these modify the preceding consonant
    'ా': 'a', 'ి': 'i', 'ీ': 'i', 'ు': 'u', 'ూ': 'u',
    'ృ': 'ru', 'ౄ': 'ru', 'ౢ': 'lu', 'ౣ': 'lu',
    'ె': 'e', 'ే': 'e', 'ై': 'ai', 'ొ': 'o', 'ో': 'o', 'ౌ': 'au',
    
    # Special characters
    'ం': 'm', 'ః': 'h', '్': '', 'ఁ': '',
    
    # Numbers
    '౦': '0', '౧': '1', '౨': '2', '౩': '3', '౪': '4',
    '౫': '5', '౬': '6', '౭': '7', '౮': '8', '౯': '9',
}


# English to Telugu transliteration mappings (for file/folder dual names)
ENG_TO_TELUGU_CONSONANTS = {
    'ksh': 'క్ష',
    'ch': 'చ',
    'sh': 'శ',
    'th': 'త',
    'dh': 'ద',
    'kh': 'ఖ',
    'gh': 'ఘ',
    'bh': 'భ',
    'ph': 'ఫ',
    'tr': 'త్ర',
    'b': 'బ',
    'c': 'క',
    'd': 'డ',
    'f': 'ఫ',
    'g': 'గ',
    'h': 'హ',
    'j': 'జ',
    'k': 'క',
    'l': 'ల',
    'm': 'మ',
    'n': 'న',
    'p': 'ప',
    'q': 'క',
    'r': 'ర',
    's': 'స',
    't': 'ట',
    'v': 'వ',
    'w': 'వ',
    'x': 'క్ష',
    'y': 'య',
    'z': 'జ'
}

ENG_TO_TELUGU_VOWELS = {
    'aa': ('ఆ', 'ా'),
    'ee': ('ఈ', 'ీ'),
    'oo': ('ఊ', 'ూ'),
    'ai': ('ఐ', 'ై'),
    'au': ('ఔ', 'ౌ'),
    'ou': ('ఔ', 'ౌ'),
    'ea': ('ఈ', 'ీ'),
    'a': ('అ', 'ా'),
    'e': ('ఎ', 'ే'),
    'i': ('ఇ', 'ి'),
    'o': ('ఒ', 'ో'),
    'u': ('ఉ', 'ు'),
    'y': ('ఇ', 'ి')
}


def is_consonant(char):
    """Check if character is an English consonant"""
    return char.isalpha() and char.lower() not in ['a', 'e', 'i', 'o', 'u']


def transliterate_english_to_telugu(text):
    """
    Transliterate English text to Telugu phonetically.
    Useful for dual-language names in content HTML representation.
    """
    if not text:
        return text
    
    # split words by alphabetic sequences (preserving spaces/punctuation/digits)
    words = re.split(r'([a-zA-Z]+)', text)
    result = []
    
    for word in words:
        if not word or not word.isalpha():
            result.append(word)
            continue
            
        word_lower = word.lower()
        
        # 1. Handle silent ending 'e' (e.g. name -> nam, file -> fil, sample -> sampl)
        if len(word_lower) > 2 and word_lower.endswith('e') and not any(word_lower.endswith(x) for x in ['ee', 'ae', 'oe', 'ie', 'ue']):
            word_lower = word_lower[:-1]
            
        telugu_word = []
        i = 0
        n = len(word_lower)
        last_was_consonant = False
        
        while i < n:
            # 2. Try to match a vowel combo
            vowel_match = None
            for v_len in [2, 1]:
                if i + v_len <= n:
                    sub = word_lower[i:i+v_len]
                    if sub in ENG_TO_TELUGU_VOWELS:
                        vowel_match = (sub, v_len)
                        break
            
            if vowel_match:
                sub, v_len = vowel_match
                independent, dependent = ENG_TO_TELUGU_VOWELS[sub]
                
                # Apply special vowel rules
                if sub == 'a':
                    # Trailing 'a' at the end of word is inherent/short (no matra)
                    if i + v_len == n:
                        dependent = ''
                    else:
                        # 'a' followed by a consonant cluster (2+ consonants) is inherent/short
                        consonant_count = 0
                        k = i + v_len
                        while k < n and is_consonant(word_lower[k]):
                            consonant_count += 1
                            k += 1
                        if consonant_count >= 2:
                            dependent = ''
                
                if last_was_consonant:
                    telugu_word.append(dependent)
                else:
                    telugu_word.append(independent)
                last_was_consonant = False
                i += v_len
                continue
                
            # 3. Try to match a consonant combo
            consonant_match = None
            for c_len in [3, 2, 1]:
                if i + c_len <= n:
                    sub = word_lower[i:i+c_len]
                    if sub in ENG_TO_TELUGU_CONSONANTS:
                        consonant_match = (sub, c_len)
                        break
            
            if consonant_match:
                sub, c_len = consonant_match
                consonant = ENG_TO_TELUGU_CONSONANTS[sub]
                
                if last_was_consonant:
                    # Previous consonant was not followed by a vowel, so add virama
                    telugu_word.append('్')
                
                telugu_word.append(consonant)
                last_was_consonant = True
                i += c_len
                continue
            
            # If no match, copy the character as is
            if last_was_consonant:
                telugu_word.append('్')
            telugu_word.append(word_lower[i])
            last_was_consonant = False
            i += 1
            
        # If the word ends with a consonant, add virama
        if last_was_consonant:
            telugu_word.append('్')
            
        result.append(''.join(telugu_word))
        
    return ''.join(result)


def contains_telugu(text):
    """
    Check if text contains Telugu characters
    
    Args:
        text: String to check
        
    Returns:
        True if Telugu characters are found, False otherwise
    """
    # Telugu Unicode range: 0C00-0C7F
    telugu_pattern = re.compile(r'[\u0C00-\u0C7F]+')
    return bool(telugu_pattern.search(text))


def transliterate_telugu_to_english(text):
    """
    Transliterate Telugu text to English with proper syllable handling
    
    Args:
        text: String containing Telugu characters
        
    Returns:
        Transliterated string in English
    """
    result = []
    i = 0
    
    while i < len(text):
        # Check for two-character combinations first (like క్ష)
        if i < len(text) - 1:
            two_char = text[i:i+2]
            if two_char in TELUGU_TO_ENGLISH:
                result.append(TELUGU_TO_ENGLISH[two_char])
                i += 2
                continue
        
        char = text[i]
        
        # If it's a Telugu character
        if char in TELUGU_TO_ENGLISH:
            transliterated = TELUGU_TO_ENGLISH[char]
            
            # Special handling for consonants followed by virama or matras
            if i < len(text) - 1:
                next_char = text[i + 1]
                
                # If next is virama (్), the consonant has no inherent 'a'
                if next_char == '్':
                    # Remove the inherent 'a' from consonant if it ends with 'a'
                    if transliterated.endswith('a') and len(transliterated) > 1:
                        transliterated = transliterated[:-1]
                    result.append(transliterated)
                    i += 2  # Skip both consonant and virama
                    continue
                
                # If next is a matra (vowel sign), handle it
                elif next_char in ['ా', 'ి', 'ీ', 'ు', 'ూ', 'ృ', 'ౄ', 'ౢ', 'ౣ', 'ె', 'ే', 'ై', 'ొ', 'ో', 'ౌ']:
                    # Remove inherent 'a' from consonant
                    if transliterated.endswith('a') and len(transliterated) > 1:
                        transliterated = transliterated[:-1]
                    result.append(transliterated)
                    # The matra will be added in the next iteration
                    i += 1
                    continue
            
            result.append(transliterated)
        else:
            # Keep non-Telugu characters as is
            result.append(char)
        
        i += 1
    
    return ''.join(result)


def sanitize_filename(filename):
    """
    Sanitize filename by removing or replacing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', '_', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length (keep extension)
    if len(filename) > 200:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:200] + ('.' + ext if ext else '')
    
    return filename


def get_base_filename_from_pdf(pdf_filename):
    """
    Extract base filename from PDF, transliterating Telugu to English if needed
    
    Args:
        pdf_filename: Original PDF filename (with or without extension)
        
    Returns:
        Base filename in English, suitable for output files
    """
    # Remove extension
    path = Path(pdf_filename)
    base_name = path.stem
    
    # Check if contains Telugu
    if contains_telugu(base_name):
        base_name = transliterate_telugu_to_english(base_name)
    
    # Sanitize the filename
    base_name = sanitize_filename(base_name)
    
    # If empty after sanitization, use default
    if not base_name or base_name.strip() == '':
        base_name = 'converted_document'
    
    return base_name


def generate_output_filenames(pdf_filename, timestamp, job_id):
    """
    Generate output filenames for EPUB and MOBI based on input PDF filename
    
    Args:
        pdf_filename: Original PDF filename
        timestamp: Timestamp string for uniqueness
        job_id: Job ID for uniqueness
        
    Returns:
        Tuple of (epub_filename, mobi_filename)
    """
    base_name = get_base_filename_from_pdf(pdf_filename)
    
    # Generate unique filenames with timestamp and job_id
    epub_filename = f"{base_name}.epub"
    mobi_filename = f"{base_name}.mobi"
    
    return epub_filename, mobi_filename


if __name__ == "__main__":
    # Test cases
    test_cases = [
        "తెలుగు_పుస్తకం.pdf",
        "sample_document.pdf",
        "మిశ్రమ mixed filename.pdf",
        "123_test.pdf",
        "తెలుగు.pdf"
    ]
    
    print("Testing Telugu to English transliteration:")
    print("-" * 60)
    
    for test in test_cases:
        base = get_base_filename_from_pdf(test)
        epub, mobi = generate_output_filenames(test, "20231123_104500", "abc12345")
        print(f"Input:  {test}")
        print(f"Base:   {base}")
        print(f"EPUB:   {epub}")
        print(f"MOBI:   {mobi}")
        print("-" * 60)
