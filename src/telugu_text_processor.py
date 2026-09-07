"""
Telugu Text Processor
Advanced Telugu text processing with Vatulu and Guninthalu identification
Integrated from TeluguOCR-develop project
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class TeluguTextProcessor:
    """
    Advanced Telugu text processor with Vatulu and Guninthalu detection
    
    Features:
    - Identifies Vatulu (వత్తులు) - subscript consonants
    - Identifies Guninthalu (గుణింతాలు) - vowel modifiers
    - Normalizes Telugu text
    - Provides detailed character analysis
    """
    
    # Telugu Unicode ranges
    TELUGU_RANGE = (0x0C00, 0x0C7F)
    
    # Vatulu (Subscript consonants) - Unicode range
    VATULU_CHARS = {
        '\u0C4D': 'virama/halant',  # ్ (combining mark)
    }
    
    # Guninthalu (Vowel modifiers/matras) - Unicode range
    GUNINTHALU_CHARS = {
        '\u0C3E': 'aa',   # ా
        '\u0C3F': 'i',    # ి
        '\u0C40': 'ii',   # ీ
        '\u0C41': 'u',    # ు
        '\u0C42': 'uu',   # ూ
        '\u0C43': 'r',    # ృ
        '\u0C44': 'rr',   # ౄ
        '\u0C46': 'e',    # ె
        '\u0C47': 'ee',   # ే
        '\u0C48': 'ai',   # ై
        '\u0C4A': 'o',    # ొ
        '\u0C4B': 'oo',   # ో
        '\u0C4C': 'au',   # ౌ
        '\u0C62': 'l',    # ౢ
        '\u0C63': 'll',   # ౣ
    }
    
    # Telugu consonants (base characters)
    CONSONANTS = {
        '\u0C15': 'ka', '\u0C16': 'kha', '\u0C17': 'ga', '\u0C18': 'gha', '\u0C19': 'nga',
        '\u0C1A': 'cha', '\u0C1B': 'chha', '\u0C1C': 'ja', '\u0C1D': 'jha', '\u0C1E': 'nya',
        '\u0C1F': 'ta', '\u0C20': 'tha', '\u0C21': 'da', '\u0C22': 'dha', '\u0C23': 'na',
        '\u0C24': 'ta', '\u0C25': 'tha', '\u0C26': 'da', '\u0C27': 'dha', '\u0C28': 'na',
        '\u0C2A': 'pa', '\u0C2B': 'pha', '\u0C2C': 'ba', '\u0C2D': 'bha', '\u0C2E': 'ma',
        '\u0C2F': 'ya', '\u0C30': 'ra', '\u0C31': 'rra', '\u0C32': 'la', '\u0C33': 'lla',
        '\u0C34': 'llla', '\u0C35': 'va', '\u0C36': 'sha', '\u0C37': 'ssa', '\u0C38': 'sa',
        '\u0C39': 'ha',
    }
    
    # Telugu vowels (independent)
    VOWELS = {
        '\u0C05': 'a', '\u0C06': 'aa', '\u0C07': 'i', '\u0C08': 'ii',
        '\u0C09': 'u', '\u0C0A': 'uu', '\u0C0B': 'r', '\u0C0C': 'l',
        '\u0C0E': 'e', '\u0C0F': 'ee', '\u0C10': 'ai',
        '\u0C12': 'o', '\u0C13': 'oo', '\u0C14': 'au',
    }
    
    def __init__(self, encoding_dir: Optional[Path] = None):
        """
        Initialize Telugu text processor
        
        Args:
            encoding_dir: Optional directory containing encoding files from TeluguOCR
        """
        self.encoding_dir = encoding_dir
        self.char_encoding = {}
        self.vg_encoding = {}
        
        # Load encoding files if available
        if encoding_dir and Path(encoding_dir).exists():
            self._load_encodings()
        
        logger.info("Telugu Text Processor initialized")
    
    def _load_encodings(self):
        """Load character and vatulu/guninthalu encodings from files"""
        try:
            char_file = Path(self.encoding_dir) / "char.txt"
            vg_file = Path(self.encoding_dir) / "vattu_gunintam.txt"
            
            if char_file.exists():
                self.char_encoding = self._parse_encoding_file(char_file)
                logger.info(f"Loaded {len(self.char_encoding)} character encodings")
            
            if vg_file.exists():
                self.vg_encoding = self._parse_encoding_file(vg_file)
                logger.info(f"Loaded {len(self.vg_encoding)} vatulu/guninthalu encodings")
                
        except Exception as e:
            logger.warning(f"Failed to load encoding files: {e}")
    
    def _parse_encoding_file(self, file_path: Path) -> Dict[int, str]:
        """Parse encoding file format (index, character pairs)"""
        encoding = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i in range(0, len(lines), 2):
                    if i + 1 < len(lines):
                        index = int(lines[i].strip())
                        char = lines[i + 1].strip()
                        encoding[index] = char
        except Exception as e:
            logger.error(f"Error parsing encoding file {file_path}: {e}")
        
        return encoding
    
    def is_telugu_char(self, char: str) -> bool:
        """Check if a character is Telugu"""
        if not char:
            return False
        code = ord(char)
        return self.TELUGU_RANGE[0] <= code <= self.TELUGU_RANGE[1]
    
    def is_vattu(self, char: str) -> bool:
        """Check if character is a Vattu (virama/halant)"""
        return char in self.VATULU_CHARS
    
    def is_gunintham(self, char: str) -> bool:
        """Check if character is a Gunintham (vowel modifier)"""
        return char in self.GUNINTHALU_CHARS
    
    def is_consonant(self, char: str) -> bool:
        """Check if character is a Telugu consonant"""
        return char in self.CONSONANTS
    
    def is_vowel(self, char: str) -> bool:
        """Check if character is a Telugu vowel"""
        return char in self.VOWELS
    
    def analyze_character(self, char: str) -> Dict[str, any]:
        """
        Analyze a Telugu character and return detailed information
        
        Returns:
            Dictionary with character type, transliteration, etc.
        """
        if not self.is_telugu_char(char):
            return {
                'char': char,
                'is_telugu': False,
                'type': 'non-telugu'
            }
        
        analysis = {
            'char': char,
            'unicode': f'U+{ord(char):04X}',
            'is_telugu': True,
            'is_vattu': self.is_vattu(char),
            'is_gunintham': self.is_gunintham(char),
            'is_consonant': self.is_consonant(char),
            'is_vowel': self.is_vowel(char),
        }
        
        # Add transliteration if available
        if char in self.VATULU_CHARS:
            analysis['transliteration'] = self.VATULU_CHARS[char]
            analysis['type'] = 'vattu'
        elif char in self.GUNINTHALU_CHARS:
            analysis['transliteration'] = self.GUNINTHALU_CHARS[char]
            analysis['type'] = 'gunintham'
        elif char in self.CONSONANTS:
            analysis['transliteration'] = self.CONSONANTS[char]
            analysis['type'] = 'consonant'
        elif char in self.VOWELS:
            analysis['transliteration'] = self.VOWELS[char]
            analysis['type'] = 'vowel'
        else:
            analysis['type'] = 'other'
        
        return analysis
    
    def analyze_text(self, text: str) -> Dict[str, any]:
        """
        Analyze Telugu text and identify all Vatulu and Guninthalu
        
        Args:
            text: Telugu text to analyze
            
        Returns:
            Dictionary with analysis results
        """
        if not text:
            return {
                'total_chars': 0,
                'telugu_chars': 0,
                'vatulu_count': 0,
                'guninthalu_count': 0,
                'characters': []
            }
        
        characters = []
        vatulu_count = 0
        guninthalu_count = 0
        telugu_count = 0
        
        for char in text:
            analysis = self.analyze_character(char)
            characters.append(analysis)
            
            if analysis['is_telugu']:
                telugu_count += 1
                if analysis['is_vattu']:
                    vatulu_count += 1
                if analysis['is_gunintham']:
                    guninthalu_count += 1
        
        return {
            'total_chars': len(text),
            'telugu_chars': telugu_count,
            'vatulu_count': vatulu_count,
            'guninthalu_count': guninthalu_count,
            'vatulu_percentage': (vatulu_count / telugu_count * 100) if telugu_count > 0 else 0,
            'guninthalu_percentage': (guninthalu_count / telugu_count * 100) if telugu_count > 0 else 0,
            'characters': characters
        }
    
    def extract_vatulu(self, text: str) -> List[Tuple[int, str, str]]:
        """
        Extract all Vatulu from text with their positions
        
        Returns:
            List of tuples: (position, character, context)
        """
        vatulu = []
        for i, char in enumerate(text):
            if self.is_vattu(char):
                # Get context (previous and next characters)
                prev_char = text[i-1] if i > 0 else ''
                next_char = text[i+1] if i < len(text) - 1 else ''
                context = f"{prev_char}{char}{next_char}"
                vatulu.append((i, char, context))
        
        return vatulu
    
    def extract_guninthalu(self, text: str) -> List[Tuple[int, str, str]]:
        """
        Extract all Guninthalu from text with their positions
        
        Returns:
            List of tuples: (position, character, transliteration)
        """
        guninthalu = []
        for i, char in enumerate(text):
            if self.is_gunintham(char):
                transliteration = self.GUNINTHALU_CHARS.get(char, '')
                guninthalu.append((i, char, transliteration))
        
        return guninthalu
    
    def identify_complex_characters(self, text: str) -> List[Dict[str, any]]:
        """
        Identify complex Telugu characters (consonant + vattu + gunintham combinations)
        
        Returns:
            List of complex character structures
        """
        complex_chars = []
        i = 0
        
        while i < len(text):
            char = text[i]
            
            # Check if it's a consonant
            if self.is_consonant(char):
                complex_char = {
                    'position': i,
                    'base': char,
                    'base_transliteration': self.CONSONANTS.get(char, ''),
                    'has_vattu': False,
                    'has_gunintham': False,
                    'full_char': char
                }
                
                # Check for following vattu
                if i + 1 < len(text) and self.is_vattu(text[i + 1]):
                    complex_char['has_vattu'] = True
                    complex_char['vattu'] = text[i + 1]
                    complex_char['full_char'] += text[i + 1]
                    
                    # Check for consonant after vattu
                    if i + 2 < len(text) and self.is_consonant(text[i + 2]):
                        complex_char['vattu_consonant'] = text[i + 2]
                        complex_char['vattu_consonant_transliteration'] = self.CONSONANTS.get(text[i + 2], '')
                        complex_char['full_char'] += text[i + 2]
                
                # Check for gunintham (can be before or after vattu)
                next_pos = i + 1
                while next_pos < len(text):
                    if self.is_gunintham(text[next_pos]):
                        complex_char['has_gunintham'] = True
                        if 'guninthalu' not in complex_char:
                            complex_char['guninthalu'] = []
                        complex_char['guninthalu'].append({
                            'char': text[next_pos],
                            'transliteration': self.GUNINTHALU_CHARS.get(text[next_pos], '')
                        })
                        complex_char['full_char'] += text[next_pos]
                        next_pos += 1
                    else:
                        break
                
                # Only add if it has vattu or gunintham
                if complex_char['has_vattu'] or complex_char['has_gunintham']:
                    complex_chars.append(complex_char)
            
            i += 1
        
        return complex_chars
    
    # Characters after which a word-final virama is normal Telugu (loanword/
    # transliteration endings like "సర్డార్"/Sardar, "జరమన్"/German, or a
    # plain word/line break) rather than corruption, and characters after
    # which a matra genuinely has no base at all — both ends of a virama or
    # gunintham that sit at one of these are NOT counted as invalid.
    _WORD_BOUNDARY_CHARS = set(' \n\t‌.,;:!?()[]{}"\'-–—')

    @staticmethod
    def _is_latin(char: str) -> bool:
        return bool(char) and char.isascii() and char.isalpha()

    def find_invalid_grapheme_sequences(self, text: str) -> List[Dict[str, any]]:
        """
        Detect Telugu character sequences that are structurally impossible in
        well-formed Telugu — a strong signal of OCR corruption (floating
        vowel signs / dangling viramas) that is invisible to statistical or
        Unicode-block-membership checks, since every character involved is
        still a valid Telugu codepoint on its own.

        Two grammar rules, both absolute (not heuristic thresholds) *inside a
        word*:
          - A Gunintham (vowel sign / matra, e.g. ా ి ు) can only ever attach
            to a preceding consonant. If the character immediately before it
            is another vowel sign, or whitespace with no base at all, the
            matra is "orphaned".
          - A Vattu (virama, ్) exists solely to suppress a consonant's
            inherent vowel so it can form a conjunct with the NEXT consonant.
            If the character immediately after it is a vowel sign (no
            consonant in between), the virama is "dangling".

        Word/line boundaries, ZWNJ, punctuation, and adjacency to Latin script
        are deliberately NOT flagged: a virama at the end of a word (loanword/
        transliteration endings such as "సర్డార్"/Sardar, "జరమన్"/German, or a
        line wrap) or before ZWNJ (explicit conjunct display) is standard
        Telugu orthography, not corruption. Empirically, on real book pages,
        counting those cases as "invalid" pushed almost every page over
        threshold regardless of actual OCR quality (~13% of pages in one test
        book flagged, 0 of which held up as genuine corruption) — this check
        only has signal when restricted to mid-word violations.

        Returns:
            List of {position, char, type, context} for each violation found.
        """
        issues: List[Dict[str, any]] = []

        for i, char in enumerate(text):
            if self.is_gunintham(char):
                prev_char = text[i - 1] if i > 0 else ''
                if prev_char in self._WORD_BOUNDARY_CHARS or self._is_latin(prev_char):
                    continue  # word/line boundary or mixed-script — not corruption
                if not self.is_consonant(prev_char):
                    issues.append({
                        'position': i,
                        'char': char,
                        'type': 'orphaned_gunintham',
                        'context': text[max(0, i - 2):i + 2],
                    })
            elif self.is_vattu(char):
                next_char = text[i + 1] if i < len(text) - 1 else ''
                if next_char in self._WORD_BOUNDARY_CHARS or self._is_latin(next_char) or next_char == '':
                    continue  # word/line boundary, ZWNJ, or mixed-script — not corruption
                if not self.is_consonant(next_char):
                    issues.append({
                        'position': i,
                        'char': char,
                        'type': 'dangling_vattu',
                        'context': text[max(0, i - 1):i + 3],
                    })

        return issues

    def grapheme_validity_score(self, text: str) -> Dict[str, any]:
        """
        Score how structurally valid the Telugu graphemes in `text` are.

        Unlike statistical junk checks (word length, symbol ratio, Unicode-
        block membership), this looks at grammar: a floating vowel sign or a
        dangling virama is grammatically impossible in real Telugu, yet each
        one IS a valid Telugu Unicode codepoint — so symbol-ratio/word-length
        checks never see it as junk. This targets exactly that blind spot.

        Returns:
            {
              'telugu_chars': int,
              'invalid_count': int,     # orphaned matras + dangling viramas
              'invalid_ratio': float,   # invalid_count / telugu_chars
              'issues': [...],          # from find_invalid_grapheme_sequences
            }
        """
        telugu_chars = sum(1 for c in text if self.is_telugu_char(c))
        issues = self.find_invalid_grapheme_sequences(text)
        invalid_count = len(issues)
        invalid_ratio = (invalid_count / telugu_chars) if telugu_chars > 0 else 0.0

        return {
            'telugu_chars': telugu_chars,
            'invalid_count': invalid_count,
            'invalid_ratio': invalid_ratio,
            'issues': issues,
        }

    def segment_graphemes(self, text: str) -> List[str]:
        """
        Segment text into Telugu akshara (orthographic syllable) clusters.

        Generic Unicode grapheme clustering (UAX #29, e.g. regex `\\X`) only pulls a
        combining mark backward onto its preceding base character — it does not merge
        a virama forward onto the next consonant. So a stacked conjunct like క్ష్మ
        (క + ్ + ష + ్ + మ) would still be split into multiple "default" clusters,
        not the single perceptual unit Telugu spelling/edit-distance logic needs.

        Each cluster is: a consonant, extended through zero-or-more (vattu + consonant)
        pairs (stacked conjuncts), extended through at most one trailing gunintham
        matra (a consonant can only take a single dependent vowel sign in valid
        Telugu — a second matra immediately after the first is an orphaned matra,
        the same defect TeluguTextProcessor.find_invalid_grapheme_sequences() flags,
        and is deliberately left to start its own cluster rather than being silently
        absorbed, so it doesn't corrupt this cluster into an unmatchable blob).
        Independent vowels, digits, ASCII, punctuation, and whitespace are each their
        own single-codepoint cluster.

        A trailing virama attaches to the preceding consonant as part of the same
        cluster only when it is NOT followed by a consonant (end of string, or
        followed by punctuation/whitespace/another non-consonant) — this is normal
        Telugu/Sanskrit word-final orthography (loanword endings like సర్డార్/Sardar),
        the same exception find_invalid_grapheme_sequences() already grants at word
        boundaries. If a consonant *does* follow, the virama is left standalone here
        so the next loop iteration can start a fresh cluster with it — attaching it
        to this cluster regardless (an earlier version of this method did) could glue
        an OCR-corrupted virama onto the wrong cluster, producing an unmatchable blob
        instead of two smaller, individually fuzzy-matchable clusters.

        Returns:
            List of grapheme cluster strings, concatenation of which equals `text`.
        """
        clusters: List[str] = []
        i = 0
        n = len(text)
        while i < n:
            char = text[i]
            if self.is_consonant(char):
                cluster = char
                i += 1
                # Stacked conjuncts: (vattu + consonant)*
                while i + 1 < n and self.is_vattu(text[i]) and self.is_consonant(text[i + 1]):
                    cluster += text[i] + text[i + 1]
                    i += 2
                # At most one trailing matra (a second is an orphaned matra, not
                # part of this akshara).
                if i < n and self.is_gunintham(text[i]):
                    cluster += text[i]
                    i += 1
                # Word-final virama (no consonant follows) attaches to this cluster.
                if i < n and self.is_vattu(text[i]) and not (i + 1 < n and self.is_consonant(text[i + 1])):
                    cluster += text[i]
                    i += 1
                clusters.append(cluster)
            else:
                clusters.append(char)
                i += 1
        return clusters

    def classify_single_stroke_edit(self, original: str, corrected: str) -> Optional[str]:
        """
        Classify whether `corrected` differs from `original` by exactly one
        missing/extra matra or vattu-conjunct stroke on a single akshara — the
        signature of an OCR engine dropping (or hallucinating) a subscript
        stroke, e.g. వాడు misread as వడు (the ా matra silently missing).

        This is deliberately narrower than "any tight edit distance": a dropped
        matra/vattu does NOT show up as a cluster *insertion* in grapheme-cluster
        space (see segment_graphemes) — వాడు (వా+డు) vs వడు (వ+డు) has the SAME
        cluster count, just one cluster shortened. So the real signature is "same
        cluster count, exactly one cluster differs, and the two differing
        clusters are related by one being the other plus exactly one trailing
        matra or one trailing (vattu+consonant) pair." Any other single-cluster
        difference is a genuine different-word substitution, not a dropped
        stroke, and is intentionally left unclassified (returns None) — that's
        a different, riskier correction problem this method does not attempt.

        Returns one of 'missing_matra', 'extra_matra', 'missing_vattu',
        'extra_vattu', or None if the edit doesn't match one of those patterns.
        """
        orig_clusters = self.segment_graphemes(original)
        corr_clusters = self.segment_graphemes(corrected)
        if len(orig_clusters) != len(corr_clusters):
            return None  # whole missing/extra akshara — a bigger, different defect

        diffs = [(o, c) for o, c in zip(orig_clusters, corr_clusters) if o != c]
        if len(diffs) != 1:
            return None

        o, c = diffs[0]
        if len(c) == len(o) + 1 and c.startswith(o) and self.is_gunintham(c[-1]):
            return 'missing_matra'
        if len(o) == len(c) + 1 and o.startswith(c) and self.is_gunintham(o[-1]):
            return 'extra_matra'
        if len(c) == len(o) + 2 and c.startswith(o) and self.is_vattu(c[-2]) and self.is_consonant(c[-1]):
            return 'missing_vattu'
        if len(o) == len(c) + 2 and o.startswith(c) and self.is_vattu(o[-2]) and self.is_consonant(o[-1]):
            return 'extra_vattu'
        return None

    def normalize_text(self, text: str) -> str:
        """
        Normalize Telugu text (remove extra spaces, normalize Unicode)
        
        Args:
            text: Telugu text to normalize
            
        Returns:
            Normalized text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Normalize Unicode (NFC normalization)
        import unicodedata
        text = unicodedata.normalize('NFC', text)
        
        return text
    
    def get_statistics(self, text: str) -> Dict[str, any]:
        """
        Get comprehensive statistics about Telugu text
        
        Returns:
            Dictionary with various statistics
        """
        analysis = self.analyze_text(text)
        complex_chars = self.identify_complex_characters(text)
        
        return {
            'total_characters': analysis['total_chars'],
            'telugu_characters': analysis['telugu_chars'],
            'vatulu_count': analysis['vatulu_count'],
            'guninthalu_count': analysis['guninthalu_count'],
            'complex_characters_count': len(complex_chars),
            'vatulu_percentage': analysis['vatulu_percentage'],
            'guninthalu_percentage': analysis['guninthalu_percentage'],
            'has_vatulu': analysis['vatulu_count'] > 0,
            'has_guninthalu': analysis['guninthalu_count'] > 0,
        }
    
    def enhance_ocr_output(self, ocr_text: str, confidence_threshold: float = 0.5) -> Dict[str, any]:
        """
        Enhance OCR output by identifying and validating Telugu characters
        
        Args:
            ocr_text: Text from OCR engine
            confidence_threshold: Minimum confidence for character validation
            
        Returns:
            Enhanced text with validation information
        """
        normalized = self.normalize_text(ocr_text)
        stats = self.get_statistics(normalized)
        complex_chars = self.identify_complex_characters(normalized)
        
        return {
            'original_text': ocr_text,
            'normalized_text': normalized,
            'statistics': stats,
            'complex_characters': complex_chars,
            'vatulu': self.extract_vatulu(normalized),
            'guninthalu': self.extract_guninthalu(normalized),
        }


# Singleton instance for use across the converter (mirrors get_telugu_post_processor
# in telugu_post_processor.py) — avoids re-instantiating (and re-logging init) per page.
_default_text_processor = None

def get_telugu_text_processor() -> TeluguTextProcessor:
    """Get or create the default TeluguTextProcessor singleton."""
    global _default_text_processor
    if _default_text_processor is None:
        _default_text_processor = TeluguTextProcessor()
    return _default_text_processor


# Proper nouns / loanwords the Telugu dictionary is likely to miss (deities, place
# names, transliterations). Shared by any module gating tokens for dictionary lookup
# (spelling correction, OOV-ratio junk detection) via dictionary_lookup_candidate().
TELUGU_PROPER_NOUN_ALLOWLIST = {
    'రాముడు', 'సీత', 'కృష్ణుడు', 'శివుడు', 'విష్ణువు', 'బ్రహ్మ', 'గణేశుడు',
    'హనుమాన్', 'లక్ష్మి', 'సరస్వతి', 'పార్వతి', 'దుర్గ', 'వేంకటేశ్వరుడు',
    'తిరుపతి', 'హైదరాబాద్', 'విజయవాడ', 'తెలంగాణ', 'ఆంధ్రప్రదేశ్',
}


def dictionary_lookup_candidate(token: str, text_processor: TeluguTextProcessor) -> Optional[str]:
    """
    Conservative eligibility gate for whether `token` should be looked up against
    the Telugu dictionary at all — shared by TeluguPostProcessor's correction path
    and PageComplexityAnalyzer's OOV junk signal, so "a word worth checking" stays
    defined in exactly one place.

    Returns the punctuation-stripped token (ready for TeluguSpellChecker.is_known_word
    / .suggest) if eligible, else None. Ineligible: empty after stripping, contains
    ASCII letters/digits (mixed-script — a disjoint failure mode), a known proper
    noun/loanword not in the dictionary, or fewer than 3 grapheme clusters.
    """
    stripped = token.strip('।॥,.;:!?()[]{}"\'-–—')
    if not stripped:
        return None
    if any(c.isascii() and (c.isalpha() or c.isdigit()) for c in stripped):
        return None
    if stripped in TELUGU_PROPER_NOUN_ALLOWLIST:
        return None
    if len(text_processor.segment_graphemes(stripped)) < 3:
        return None
    return stripped


def test_telugu_processor():
    """Test Telugu text processor functionality"""
    import sys
    
    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    
    print("Testing Telugu Text Processor...")
    print("=" * 60)
    
    processor = TeluguTextProcessor()
    
    # Test text with Vatulu and Guninthalu
    test_text = "తెలుగు భాష"  # Telugu language
    
    try:
        print(f"\nTest Text: {test_text}")
    except UnicodeEncodeError:
        print(f"\nTest Text: [Telugu text - Unicode display not supported in this console]")
    
    print("-" * 60)
    
    # Analyze text
    analysis = processor.analyze_text(test_text)
    print(f"\nText Analysis:")
    print(f"  Total characters: {analysis['total_chars']}")
    print(f"  Telugu characters: {analysis['telugu_chars']}")
    print(f"  Vatulu count: {analysis['vatulu_count']}")
    print(f"  Guninthalu count: {analysis['guninthalu_count']}")
    
    # Get statistics
    stats = processor.get_statistics(test_text)
    print(f"\nStatistics:")
    print(f"  Has Vatulu: {stats['has_vatulu']}")
    print(f"  Has Guninthalu: {stats['has_guninthalu']}")
    print(f"  Complex characters: {stats['complex_characters_count']}")
    
    # Extract Guninthalu
    guninthalu = processor.extract_guninthalu(test_text)
    if guninthalu:
        print(f"\nGuninthalu found:")
        for pos, char, trans in guninthalu:
            try:
                print(f"  Position {pos}: {char} ({trans})")
            except UnicodeEncodeError:
                print(f"  Position {pos}: [Unicode char] ({trans})")
    
    # Identify complex characters
    complex_chars = processor.identify_complex_characters(test_text)
    if complex_chars:
        print(f"\nComplex characters:")
        for cc in complex_chars:
            try:
                print(f"  {cc['full_char']} at position {cc['position']}")
            except UnicodeEncodeError:
                print(f"  [Complex char] at position {cc['position']}")
            print(f"    Base: ({cc['base_transliteration']})")
            if cc['has_vattu']:
                print(f"    Has Vattu: Yes")
            if cc['has_gunintham']:
                print(f"    Guninthalu: {[g['transliteration'] for g in cc.get('guninthalu', [])]}")
    
    print("\n" + "=" * 60)
    print("✅ Telugu Text Processor test complete!")


if __name__ == "__main__":
    test_telugu_processor()
