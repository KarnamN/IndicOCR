import re

# English to Telugu transliteration mapping
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
    return char.isalpha() and char.lower() not in ['a', 'e', 'i', 'o', 'u']

def transliterate_english_to_telugu(text):
    if not text:
        return text
    
    # split words by non-alphabetic characters (preserving them)
    words = re.split(r'([a-zA-Z]+)', text)
    result = []
    
    for word in words:
        if not word or not word.isalpha():
            result.append(word)
            continue
            
        word_lower = word.lower()
        
        # 1. Handle silent ending 'e' (e.g. name, file, sample)
        # If word ends with 'e' (but not 'ee', 'ae', 'oe', 'ie', 'ue') and has length > 2
        if len(word_lower) > 2 and word_lower.endswith('e') and not any(word_lower.endswith(x) for x in ['ee', 'ae', 'oe', 'ie', 'ue']):
            # Strip the silent 'e'. The preceding consonant will naturally get a virama.
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
                
                # Check for special vowel rules
                if sub == 'a':
                    # Rule A: Trailing 'a' at the end of word is inherent/short (no matra)
                    if i + v_len == n:
                        dependent = ''
                    else:
                        # Rule B: 'a' followed by a consonant cluster (2+ consonants) is inherent/short
                        # Count consecutive consonants following this 'a'
                        consonant_count = 0
                        k = i + v_len
                        while k < n and is_consonant(word_lower[k]):
                            # Skip ahead for consonant combinations like 'sh', 'ch' etc.
                            # Just count raw consonant characters to see if it's a cluster
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
            
            # If no match, copy the character
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

# Test cases
test_cases = [
    "kumar",
    "suresh",
    "sharma",
    "krishna",
    "sample_file.txt",
    "Report_v2",
    "Telugu book name"
]

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("Testing English to Telugu Transliteration:")
for test in test_cases:
    res = transliterate_english_to_telugu(test)
    print(f"English: {test:<20} -> Telugu: {res}")
