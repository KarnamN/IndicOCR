"""
Telugu OCR Post-Processor
Fixes known OCR misreads in Telugu/Sanskrit text.
Applied after OCR extraction to clean up systematic errors.
"""
import re
import logging
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TeluguPostProcessor:
    """Post-processes OCR output to fix common Telugu/Sanskrit misreads."""
    
    # Known misreads: OCR produces English chars for Telugu glyphs
    # These patterns appear when Tesseract confuses Telugu characters with English
    SHLOKA_MARKER_FIXES = [
        # శ్లో॥ (shloka marker) commonly misread as English abbreviations
        (r'\bSn\b', 'శ్లో॥'),
        (r'\bFn\b', 'శ్లో॥'),
        (r'\bFu\b', 'శ్లో॥'),
        (r'\bEn\b', 'శ్లో॥'),
        (r'\bSu\b', 'శ్లో॥'),
        (r'\bGn\b', 'శ్లో॥'),
        (r'\bGp\b', 'శ్లో॥'),
        (r'\bEi\b', 'శ్లో॥'),
        (r'\b\$i\b', 'శ్లో॥'),
        (r'\bgh\b', 'శ్లో॥'),
        (r'\bgu\b', 'శ్లో॥'),
        (r'\boh\b', 'శ్లో॥'),
        (r'\bgn\b', 'శ్లో॥'),
        # శ్లో! variant (when ॥ reads as !)
        (r'శ్లో!', 'శ్లో॥'),
    ]
    
    # Common Telugu character substitution errors
    CHAR_FIXES = [
        # English fragments that appear mid-Telugu text
        (r'\bDo:', ''),           # Random "Do:" in Telugu text
        (r'\bSOE\b', 'పూర్వోక్త'),  # Common misread
        (r'\bFHI\b', 'చతురస్రే'),   # Common misread  
        (r'\bFTE\b', 'హరేత్'),      # Common misread
        (r'\bPETE\b', 'షోడశార్ఘో'), # Common misread
        (r'\bDPE\b', 'లిఖిత్వా'),   # Common misread
        (r'\bIED\b', 'వేశ్మని'),    # Common misread
        (r'\bIQ\b', 'వేష్టయే'),     # Common misread
        (r'\bSy\b', 'తైలమద్ధ్వ'),   # Common misread
        (r'\bSHE\b', 'చతురస్రే'),   # Common misread
    ]
    
    # PaddleOCR/Tesseract sometimes misread the subjoined-ra conjunct sign
    # ("్ర", e.g. in క్ర/గ్ర/ద్ర/ప్ర/త్ర...) as a literal "(" attached to the
    # following base consonant — e.g. "వీరేంద్రనాథ్" (Yandamuri Veerendranath,
    # a running page-header in one real book) came back as "వీరేం(దనాథ్".
    # Distinguish this from a genuine opening parenthesis by requiring the "("
    # to be fused directly onto the previous Telugu character with no space —
    # real parenthetical text is always preceded by whitespace/line-start, so
    # this signature is unambiguous. Fix: drop the "(" and move its "్ర" onto
    # the consonant that follows (క-హ covers the Telugu consonant block).
    #
    # Excludes the case where that consonant is itself immediately followed by
    # its own virama (్) — that means a conjunct is already correctly formed
    # right after the "(" (e.g. "అతడు(ప్రధాన" — "ప్ర" is already intact), so
    # the "(" is a separate/ambiguous artifact rather than a moved "్ర", and
    # blindly inserting another "్ర" would corrupt already-correct text (was
    # empirically checked against ~264 real matches in one book: ~8 fell into
    # this excluded case and would have been corrupted without it).
    CONJUNCT_RA_MISREAD_FIXES = [
        (r'(?<=[ఀ-౿])\(([క-హ])(?!్)', r'\1్ర'),
    ]

    # Same "్ర misread as (" defect, but for a proper noun where it lands at the
    # START of a word (preceded by whitespace, not fused onto a prior character)
    # — the general word-initial case is dictionary-gated and off by default (see
    # fix_word_initial_conjunct_ra()) because "(" is ambiguous with a real
    # parenthesis there, but ద్రుపదుడు (Drupada, a recurring Mahabharata
    # character name) isn't in the flat dictionary at all so that gate can never
    # recover it, and its root "దుపద" collides with no real Telugu word (0 hits
    # in resources/telugu_dictionary/te_wordlist.txt) — unambiguous regardless of
    # dictionary coverage. A regex on the stem catches all case-inflected forms
    # (దుపదుడు/దుపదుని/దుపదునికి/దుపదరాజు/దుపదపుత్రి/...) in one entry. Confirmed
    # against data/temp/Sri_Krishna_Charitra_3-6_e06e0cad/ (2026-09-07): 85+
    # real occurrences across 15 inflected forms, 0 false-positive risk.
    #
    # ద్రోణాచార్యులు (Dronacharya, Drupada's rival and the Pandavas'/Kauravas'
    # teacher — appears constantly alongside Drupada in this same epic) has the
    # identical defect and the identical reason the general dictionary-gated
    # fix can't reach it: its root "దోణ" collides with no real Telugu word (0
    # hits in te_wordlist.txt) and none of its inflected forms
    # (దోణాచార్యులు/దోణాచార్యుల/దోణాచార్యులను/దోణాచార్యులవారు/దోణాచార్యలవారు/
    # దోణాచార్యని/దోణాచార్యులవారిని/దోణాచార్యులవార్ని/దోణాచార్యలనెదిరించాడు/...)
    # are in the flat dictionary either. Found 2026-09-07 in
    # data/temp/Sri_Krishna_Charitra_6-9_405ccae2/ (post-fix run, so this
    # confirms the Drupada-only fix left a sibling name uncaught): 21+ raw
    # occurrences across 10 inflected forms in that one book alone.
    CONJUNCT_RA_PROPER_NOUN_FIXES = [
        (r'(?<![ఀ-౿])\(దుపద', 'ద్రుపద'),
        (r'(?<![ఀ-౿])\(దోణ', 'ద్రోణ'),
    ]

    # Punctuation normalization for Sanskrit/Telugu
    PUNCTUATION_FIXES = [
        # Normalize danda marks
        (r'\bII\b', '॥'),          # Double I → double danda
        (r'(?<!\w)I(?!\w)', '।'),  # Standalone I → single danda
        (r'\|\s*\|', '॥'),         # || → ॥
        # Fix spacing around dandas
        (r'\s+।', ' ।'),
        (r'\s+॥', ' ॥'),
    ]
    
    # Clean up stray English fragments in otherwise Telugu text
    STRAY_ENGLISH = [
        # Single or double English chars surrounded by Telugu text
        # Only match when clearly out of place (between Telugu chars)
        (r'(?<=[\u0C00-\u0C7F])\s+[A-Z]{1,3}\s+(?=[\u0C00-\u0C7F])', ' '),
    ]

    # Real English words commonly found in Telugu religious/devotional/cultural books.
    # Any ASCII token matching this list is preserved even on Telugu-dominant lines.
    # Extend this set as you encounter false positives.
    REAL_ENGLISH_WORDS = {
        # Numbers / ordinals
        'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
        'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx',
        # Common English words in Telugu texts
        'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'is', 'are',
        'for', 'on', 'at', 'by', 'as', 'be', 'it', 'he', 'she', 'we',
        'his', 'her', 'its', 'our', 'that', 'this', 'with', 'from',
        'was', 'not', 'but', 'they', 'all', 'can', 'had', 'has', 'have',
        'will', 'one', 'two', 'three', 'four', 'five', 'six', 'era', 'no',
        # Common proper nouns / abbreviations in Telugu books
        'sri', 'shri', 'dr', 'mr', 'rs', 'ad', 'bc', 'am', 'pm', 'p', 'pp',
        'vol', 'pg', 'op', 'ed', 'etc', 'isbn', 'cf', 'ibid', 'vs',
        # Telugu transliterations that look like English
        'om', 'ram', 'sai', 'siva', 'devi', 'deva', 'rao', 'das', 'lal',
        'swami', 'giri', 'nath', 'anand', 'das', 'amma', 'yogi',
    }

    def __init__(self, enable_shloka_fixes=True, enable_char_fixes=True,
                 enable_punctuation_fixes=True, enable_stray_english_cleanup=False,
                 enable_dictionary_correction=False, enable_conjunct_ra_fixes=True,
                 enable_conjunct_ra_word_initial_fix=False,
                 enable_stroke_correction=False, enable_stroke_removal_correction=False):
        """
        Initialize post-processor with configurable fix categories.

        Args:
            enable_shloka_fixes: Fix శ్లో॥ misreads (safe for Sanskrit texts)
            enable_char_fixes: Fix known character substitutions (use with caution)
            enable_punctuation_fixes: Normalize danda marks
            enable_stray_english_cleanup: Remove stray English chars (aggressive)
            enable_dictionary_correction: Fix structurally-defective Telugu words
                (orphaned matras / dangling viramas) against a real Telugu
                vocabulary. Default off until validated (see docs/OCR_CORRECTION_ANALYSIS.md).
            enable_conjunct_ra_fixes: Fix "్ర" (subjoined-ra conjunct) misread as
                a literal "(" fused onto the next consonant. Narrow, high-confidence
                pattern (see CONJUNCT_RA_MISREAD_FIXES) — safe to leave on.
            enable_conjunct_ra_word_initial_fix: Fix the same "్ర"-as-"(" misread
                when it lands at the START of a word instead of fused onto a
                preceding character (e.g. "(దుపదుడు" -> "ద్రుపదుడు", Drupada) —
                see fix_word_initial_conjunct_ra(). Unlike the fused case, this
                position is genuinely ambiguous with a real opening parenthesis
                (this corpus uses "(" heavily for annotations like "నవల (novel)"
                — "నవల" needs no ్ర), so it's dictionary-gated rather than a plain
                regex, and defaults off until validated at scale — found via a
                2026-09-07 real-corpus scan (~19,000 raw matches across data/temp/,
                including many false-positive-shaped ones), see
                [[project_paddle_letter_mistake_investigation]].
            enable_stroke_correction: Within correct_spelling(), also repair a single
                MISSING matra or vattu-conjunct stroke on an otherwise-clean,
                dictionary-unknown word (e.g. వాడు OCR'd as వడు — classify_single_stroke_edit
                categories 'missing_matra'/'missing_vattu' only). Only takes effect when
                enable_dictionary_correction is also on. Default off until validated —
                see docs/TELUGU_SPELL_CORRECTION_TODO.md item 7. Real-data validation found
                this direction reliably safe (a dropped stroke is a pure OCR failure mode).
            enable_stroke_removal_correction: Additionally allow the REVERSE direction —
                removing an apparently-extra matra/vattu stroke ('extra_matra'/'extra_vattu').
                Only takes effect when enable_stroke_correction is also on. Kept as a
                separate, more cautious flag: real-data validation found this direction
                riskier, since Telugu has legitimate optional long-vowel/emphatic forms
                (e.g. అహింసా vs అహింస) and compound-linking forms a flat dictionary doesn't
                fully cover, so "removing" a stroke can silently change a word's meaning
                rather than fix an OCR error. Default off — see
                docs/TELUGU_SPELL_CORRECTION_TODO.md item 7.
        """
        self.fixes = []

        if enable_shloka_fixes:
            self.fixes.extend(self.SHLOKA_MARKER_FIXES)
        if enable_char_fixes:
            self.fixes.extend(self.CHAR_FIXES)
        if enable_punctuation_fixes:
            self.fixes.extend(self.PUNCTUATION_FIXES)
        if enable_stray_english_cleanup:
            self.fixes.extend(self.STRAY_ENGLISH)
        if enable_conjunct_ra_fixes:
            self.fixes.extend(self.CONJUNCT_RA_MISREAD_FIXES)
            self.fixes.extend(self.CONJUNCT_RA_PROPER_NOUN_FIXES)

        self.enable_junk_english_filter = enable_stray_english_cleanup
        self.enable_conjunct_ra_word_initial_fix = enable_conjunct_ra_word_initial_fix
        self.enable_dictionary_correction = enable_dictionary_correction
        self.enable_stroke_correction = enable_stroke_correction
        self.enable_stroke_removal_correction = enable_stroke_removal_correction

        logger.info(f"Telugu post-processor initialized with {len(self.fixes)} fix patterns")
    
    def _is_telugu_dominant(self, line: str, threshold: float = 0.45) -> bool:
        """
        Returns True if the line is predominantly Telugu characters.
        threshold: fraction of visible chars that must be Telugu (default 45%).
        """
        chars = [c for c in line if not c.isspace()]
        if not chars:
            return False
        tel_count = sum(1 for c in chars if 0x0C00 <= ord(c) <= 0x0C7F)
        return (tel_count / len(chars)) >= threshold

    def _strip_junk_english_tokens(self, line: str) -> str:
        """
        On a Telugu-dominant line, remove ASCII tokens that look like
        Tesseract misreads of Telugu glyphs.

        A token is considered JUNK if ALL of these hold:
          1. The token is pure ASCII letters (no digits, no punctuation)
          2. Length <= 4 characters
          3. It is NOT in REAL_ENGLISH_WORDS (case-insensitive)
          4. It has no Telugu neighbours that were already identified as shloka markers

        Real English words (longer strings or dict matches) are kept.
        """
        real_words = self.REAL_ENGLISH_WORDS

        def should_drop(token: str) -> bool:
            # Must be pure alpha ASCII
            if not token.isascii() or not token.isalpha():
                return False
            # Keep if long enough to be a real word (>4 chars)
            if len(token) > 4:
                return False
            # Keep if in known-real-English dictionary
            if token.lower() in real_words:
                return False
            # Drop: short junk token on a Telugu-dominant line
            return True

        tokens = line.split(' ')
        cleaned = [t for t in tokens if not should_drop(t)]
        return ' '.join(cleaned)

    def strip_junk_english(self, text: str) -> str:
        """
        Apply line-level junk English removal.
        Only processes lines that are Telugu-dominant (>= 45% Telugu chars).
        Real English-only lines are left completely untouched.
        """
        lines = text.split('\n')
        result = []
        removed_count = 0
        for line in lines:
            if self._is_telugu_dominant(line):
                cleaned = self._strip_junk_english_tokens(line)
                if cleaned != line:
                    removed_count += 1
                result.append(cleaned)
            else:
                result.append(line)  # Pure English / mixed lines: untouched
        if removed_count:
            logger.debug(f"Junk-English filter cleaned {removed_count} line(s)")
        return '\n'.join(result)

    def _is_dictionary_correction_candidate(self, token: str, text_processor) -> bool:
        """
        Conservative gates for whether `token` should even be considered for
        dictionary correction. See correct_spelling() for the v1-strict policy.
        Delegates to the shared gate also used by PageComplexityAnalyzer's
        OOV junk signal — see telugu_text_processor.dictionary_lookup_candidate.
        """
        from telugu_text_processor import dictionary_lookup_candidate
        return dictionary_lookup_candidate(token, text_processor) is not None

    def correct_spelling(
        self, text: str, token_frequency: Optional[Counter] = None
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        Correct structurally-defective Telugu words (orphaned matras / dangling
        viramas, per TeluguTextProcessor.grapheme_validity_score) against a real
        Telugu dictionary. Conservative v1 policy: only tokens already flagged as
        structurally broken are attempted — structurally clean but out-of-dictionary
        words (rare words, proper nouns not in TELUGU_PROPER_NOUN_ALLOWLIST) are
        left untouched, to keep the false-positive rate low.

        There is no per-word OCR confidence signal available at this stage, so
        this relies purely on structural + dictionary-membership evidence.

        Args:
            token_frequency: Optional pre-computed word-frequency count (see
                telugu_text_processor.compute_book_token_frequency) covering a
                wider scope than just this call's `text` — typically every page
                of the same book. When given, this is used instead of counting
                repeats only within `text` for the repeat-guard below. Matters
                because a name/word that appears once on THIS page but repeats
                elsewhere in the same book is otherwise invisible to a
                page-local count — found live (2026-09-26): సరోజ (a character's
                name appearing 11 times across a real book, never more than
                twice on any single page) still got wrongly "corrected" to
                సరోజి on every page where it appeared only once, because a
                page-local counter alone can't see the other pages. When None
                (the default — e.g. a caller correcting one page in isolation,
                with no access to the rest of the book), falls back to counting
                repeats only within this call's own `text`, the original,
                narrower protection.

        Returns:
            (corrected_text, corrections) where corrections is a list of
            {'line': int, 'from': str, 'to': str, 'distance': int} — one entry per
            accepted correction. Returned as a plain value (not stored on self) so
            this is safe to call concurrently from multiple page-processing threads
            against the shared TeluguPostProcessor singleton.
        """
        from telugu_text_processor import get_telugu_text_processor, dictionary_lookup_candidate
        from telugu_spell_checker import get_telugu_spell_checker

        text_processor = get_telugu_text_processor()
        spell_checker = get_telugu_spell_checker()

        if token_frequency is not None:
            candidate_counts = token_frequency
        else:
            # How many times each dictionary-eligible token form appears in
            # this text (one page, when no book-wide count was supplied).
            # Used below to protect a repeated word/name from the widened
            # stroke-correction match — see that branch for why. Computed
            # once up front rather than per-token to avoid re-deriving it
            # inside the loop.
            candidate_counts = Counter()
            for _line in text.split('\n'):
                for _tok in _line.split(' '):
                    _cand = dictionary_lookup_candidate(_tok, text_processor)
                    if _cand is not None:
                        candidate_counts[_cand] += 1

        corrections: List[Dict[str, object]] = []
        lines = text.split('\n')
        out_lines = []
        for line_num, line in enumerate(lines):
            tokens = line.split(' ')
            new_tokens = []
            for token in tokens:
                candidate = dictionary_lookup_candidate(token, text_processor)
                if candidate is None:
                    new_tokens.append(token)
                    continue

                validity = text_processor.grapheme_validity_score(token)
                if validity['invalid_count'] == 0:
                    # Structurally clean. v1 leaves this alone entirely. When
                    # enable_stroke_correction is on, additionally attempt a
                    # narrowly-scoped repair for exactly one missing/extra matra
                    # or vattu-conjunct stroke (see classify_single_stroke_edit)
                    # — NOT a general "is this a real word" check, which risks
                    # false positives on rare/dialectal words the flat
                    # dictionary just doesn't have.
                    #
                    # Uses suggest_candidates() (every candidate at distance 1),
                    # not suggest() (a single unambiguous winner or nothing) —
                    # suggest()'s generic tie-avoidance blocks short/common
                    # words outright (e.g. తండి has 55 same-distance
                    # candidates, so suggest() always returns None for it
                    # regardless of whether one of them is a genuine stroke
                    # fix). Filtering the full candidate list through
                    # classify_single_stroke_edit first, and only accepting
                    # when exactly one candidate survives that structural
                    # filter, recovers real cases suggest() could never reach
                    # (e.g. మాతమే -> మాత్రమే, తలుప -> తలుపు — confirmed
                    # 2026-09-26 against the real dictionary) while staying
                    # just as conservative: a short word with several
                    # equally-plausible one-stroke real words (తండి is one
                    # stroke from తిండి/తొండి/తండ్రి all at once) still yields
                    # more than one survivor and is correctly left untouched
                    # rather than guessing which one was intended.
                    #
                    # Guarded by candidate_counts[candidate] < 2: found live
                    # (2026-09-26, real book) that this widened match narrows
                    # to exactly one "survivor" just as confidently for a
                    # structurally-unrelated false positive as for a real
                    # fix — సరోజ (a character's name, appearing 5+ times
                    # across two pages, not in the flat dictionary at all)
                    # structurally narrows to exactly one candidate,
                    # సరోజి (a real but different, unrelated word), and would
                    # otherwise get silently "corrected" into the wrong word
                    # every single time it appears. A name/word repeated
                    # identically across a page is strong evidence it's
                    # intentional, not a one-off OCR stroke drop (real OCR
                    # noise doesn't reliably collide with the same unrelated
                    # dictionary word multiple independent times) — so a
                    # repeated token is left alone even when it structurally
                    # narrows to one match. Deliberately errs conservative:
                    # this also skips a genuinely repeated OCR defect (e.g. a
                    # systematic misread that recurs identically), but a
                    # silent wrong correction to a real name is worse than a
                    # missed one, consistent with this corrector's existing
                    # conservative-by-default design elsewhere.
                    if self.enable_stroke_correction and candidate_counts[candidate] < 2:
                        stroke_matches = []
                        for cand_word, cand_distance in spell_checker.suggest_candidates(candidate, max_edit_distance=1):
                            edit_type = text_processor.classify_single_stroke_edit(candidate, cand_word)
                            if edit_type is not None:
                                stroke_matches.append((cand_word, cand_distance, edit_type))
                        if len(stroke_matches) == 1:
                            stroke_corrected, stroke_distance, edit_type = stroke_matches[0]
                            # 'missing_matra'/'missing_vattu' (a stroke the OCR dropped) are
                            # always eligible. 'extra_matra'/'extra_vattu' (removing a
                            # stroke) additionally require enable_stroke_removal_correction
                            # — real-data validation found that direction riskier
                            # (legitimate long-vowel/emphatic forms can look like a false
                            # "extra" stroke). See __init__ docstring.
                            is_removal_edit = edit_type in ('extra_matra', 'extra_vattu')
                            if not is_removal_edit or self.enable_stroke_removal_correction:
                                logger.debug(
                                    f"Stroke-repair correction: '{token}' -> '{stroke_corrected}' ({edit_type})"
                                )
                                corrections.append({
                                    'line': line_num, 'from': token, 'to': stroke_corrected,
                                    'distance': stroke_distance, 'category': edit_type,
                                })
                                new_tokens.append(stroke_corrected)
                                continue
                    new_tokens.append(token)
                    continue

                suggestion = spell_checker.suggest(token)
                if suggestion is None:
                    new_tokens.append(token)
                    continue

                corrected_word, distance = suggestion
                max_allowed = min(2, max(1, len(text_processor.segment_graphemes(token)) // 3))
                if distance > max_allowed:
                    new_tokens.append(token)
                    continue

                logger.debug(f"Dictionary correction: '{token}' -> '{corrected_word}' (distance={distance})")
                corrections.append({
                    'line': line_num, 'from': token, 'to': corrected_word, 'distance': distance,
                })
                new_tokens.append(corrected_word)
            out_lines.append(' '.join(new_tokens))

        if corrections:
            logger.debug(f"Dictionary correction applied {len(corrections)} fix(es)")

        return '\n'.join(out_lines), corrections

    def fix_word_initial_conjunct_ra(self, text: str) -> str:
        """
        Fix the "్ర" (subjoined-ra conjunct) misread as a literal "(" when it
        lands at the START of a word — e.g. "(దుపదుడు" -> "ద్రుపదుడు" (Drupada) —
        rather than fused onto a preceding character (that case is handled
        unconditionally above by CONJUNCT_RA_MISREAD_FIXES; this method only
        looks at "(" NOT immediately preceded by a Telugu character, so the two
        never double-handle the same match).

        A word-initial "(" is genuinely ambiguous with a real opening
        parenthesis in a way the fused case isn't: this corpus uses "(" heavily
        for legitimate annotations — "గోన గన్నారెడ్డి (నవల)" ("... (novel)"),
        "టైగర్ (హాస్య నవల)" ("... (comedy novel)") — where the word right after
        "(" is already valid and needs no ్ర inserted. A positional/regex-only
        fix is therefore not safe here (see 2026-09-07 real-corpus scan,
        [[project_paddle_letter_mistake_investigation]]: ~19,000 raw matches of
        this shape across data/temp/, a meaningful fraction genuinely
        parenthetical). Dictionary-gated instead: only consider rewriting when
        the word right after "(" is NOT already a known dictionary word (that
        check alone is what protects genuine parentheticals like "(నవల)" above
        — it never reaches the fuzzy step below).

        Between the two candidates (plain vs. "్ర"-inserted), prefer an exact
        dictionary hit if either gets one; otherwise fall back to comparing
        which one is closer to *some* known word via the same fuzzy
        grapheme-cluster lookup correct_spelling() already uses elsewhere
        (TeluguSpellChecker.suggest()). This fallback exists because the
        dictionary is a flat, non-inflected wordlist (see
        docs/TELUGU_SPELL_CORRECTION_TODO.md item 6) — an exact-match-only gate
        never accepts a correctly-conjugated verb like ప్రయత్నించింది ("tried")
        or ప్రారంభించాడు ("began") just because the citation/root form is the
        one actually in the list, not this inflected form. Confirmed against
        the real dictionary (2026-09-26): "పయత్నించింది"/"పారంభించాడు" (broken)
        get no suggestion at all, while "ప్రయత్నించింది"/"ప్రారంభించాడు" (్ర
        restored) each get one within edit distance 2 — the fixed reading is
        measurably closer to real Telugu even though it's not a literal entry.
        Still conservative: if neither reading gets a strictly better match,
        nothing is changed.
        """
        from telugu_spell_checker import get_telugu_spell_checker
        spell_checker = get_telugu_spell_checker()

        def _try_fix(m) -> str:
            consonant, rest = m.group(1), m.group(2)
            plain = consonant + rest
            if spell_checker.is_known_word(plain):
                return m.group(0)  # already a real word — genuine parenthetical
            fixed = consonant + '్ర' + rest
            if spell_checker.is_known_word(fixed):
                return fixed

            # Neither is an exact dictionary hit. Compare how close each
            # reading is to *some* real word instead of giving up — see
            # docstring above. suggest() returns None for a word that's
            # already known (not the case for either candidate here, both
            # failed is_known_word above) or that has no candidate within its
            # max edit distance.
            plain_suggestion = spell_checker.suggest(plain)
            fixed_suggestion = spell_checker.suggest(fixed)
            if fixed_suggestion is not None and (
                plain_suggestion is None or fixed_suggestion[1] < plain_suggestion[1]
            ):
                return fixed
            return m.group(0)  # no reading is clearly closer to real Telugu — don't guess

        return re.sub(
            r'(?<![ఀ-౿])\(([క-హ])(?!్)([ఀ-౿]*)',
            _try_fix,
            text,
        )

    def process(self, text: str) -> str:
        """
        Apply all post-processing fixes to OCR text.

        Args:
            text: Raw OCR text

        Returns:
            Cleaned text with known misreads corrected
        """
        processed_text, _corrections = self._process_impl(text)
        return processed_text

    def process_with_corrections(
        self, text: str, token_frequency: Optional[Counter] = None
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        Same as process(), but also returns the dictionary-correction change-log
        (empty list if enable_dictionary_correction is off, or nothing was
        corrected). Use this when the caller needs to know exactly which words
        were auto-corrected — e.g. to flag pages for manual review.

        token_frequency: see correct_spelling() — pass a book-wide count when
        available (e.g. re-processing every page of a book together) so the
        repeated-word/name guard isn't limited to what repeats on this one
        page.
        """
        return self._process_impl(text, token_frequency)

    def _process_impl(
        self, text: str, token_frequency: Optional[Counter] = None
    ) -> Tuple[str, List[Dict[str, object]]]:
        if not text or not text.strip():
            return text, []

        original_len = len(text)
        fix_count = 0
        corrections: List[Dict[str, object]] = []

        # NFC-normalize first so downstream regex/dictionary matching operates on
        # a single canonical Unicode form (OCR engines are not guaranteed to emit
        # NFC-composed output).
        text = unicodedata.normalize('NFC', text)

        for pattern, replacement in self.fixes:
            new_text = re.sub(pattern, replacement, text)
            if new_text != text:
                fix_count += 1
                text = new_text

        # Dictionary-gated word-initial "్ర as (" fix — see
        # fix_word_initial_conjunct_ra() docstring. Runs after the regex fixes
        # above (so PUNCTUATION_FIXES etc. have already normalized the text)
        # and before dictionary correction below.
        if self.enable_conjunct_ra_word_initial_fix:
            new_text = self.fix_word_initial_conjunct_ra(text)
            if new_text != text:
                fix_count += 1
                text = new_text

        # Line-level junk English filter (always on for tel+eng output)
        text = self.strip_junk_english(text)

        # Dictionary-based spell-correction runs after ASCII-junk/shloka-marker
        # cleanup so it never sees tokens that are actually mis-scripted markers
        # or stray English, only genuine Telugu-script words.
        if self.enable_dictionary_correction:
            text, corrections = self.correct_spelling(text, token_frequency=token_frequency)

        # Clean up whitespace
        text = re.sub(r' +', ' ', text)   # Multiple spaces -> single
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Max 1 blank line

        # NFC normalization: ensure all Telugu glyphs are in composed Unicode form.
        # Kept here too as an idempotent safety net even though it now also runs
        # at the start of this function.
        text = unicodedata.normalize('NFC', text)

        if fix_count > 0:
            logger.debug(f"Post-processing applied {fix_count} fixes ({original_len} -> {len(text)} chars)")

        return text.strip(), corrections

    def process_with_stats(self, text: str) -> tuple:
        """
        Process text and return stats about what was fixed.
        
        Returns:
            Tuple of (processed_text, dict of stats)
        """
        if not text:
            return text, {'fixes_applied': 0}
        
        stats = {'fixes_applied': 0, 'patterns_matched': []}
        
        for pattern, replacement in self.fixes:
            matches = re.findall(pattern, text)
            if matches:
                stats['fixes_applied'] += len(matches)
                stats['patterns_matched'].append({
                    'pattern': pattern,
                    'replacement': replacement,
                    'count': len(matches)
                })
                text = re.sub(pattern, replacement, text)
        
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        return text.strip(), stats


# Singleton instance for use across the converter
_default_processor = None

def get_telugu_post_processor(**kwargs) -> TeluguPostProcessor:
    """Get or create the default Telugu post-processor."""
    global _default_processor
    if _default_processor is None:
        # Fix categories are driven by config (config.py / config_v5.py /
        # config_tesseract.py, whichever is the active `config` module) so they
        # are actually toggleable in production, with the previous hardcoded
        # values kept as defaults if a flag isn't declared.
        try:
            import config
        except ImportError:
            config = None

        # Stray English cleanup is safe: it only removes short ASCII tokens
        # (<= 4 chars, not in a known-words dict) from Telugu-dominant lines.
        # Real English lines and recognised words are always preserved. Not
        # config-driven (no corresponding flag exists) — always on.
        _default_processor = TeluguPostProcessor(
            enable_shloka_fixes=getattr(config, 'ENABLE_SHLOKA_FIXES', True),
            enable_char_fixes=getattr(config, 'ENABLE_CHAR_FIXES', False),  # Keep off — too aggressive
            enable_punctuation_fixes=getattr(config, 'ENABLE_PUNCTUATION_FIXES', True),
            enable_stray_english_cleanup=True,
            enable_dictionary_correction=getattr(config, 'ENABLE_TELUGU_DICTIONARY_CORRECTION', False),
            enable_conjunct_ra_fixes=getattr(config, 'ENABLE_CONJUNCT_RA_FIXES', True),
            enable_conjunct_ra_word_initial_fix=getattr(config, 'ENABLE_CONJUNCT_RA_WORD_INITIAL_FIX', False),
            enable_stroke_correction=getattr(config, 'ENABLE_TELUGU_STROKE_CORRECTION', False),
            enable_stroke_removal_correction=getattr(config, 'ENABLE_TELUGU_STROKE_REMOVAL_CORRECTION', False),
            **kwargs
        )
    return _default_processor


def post_process_telugu(text: str) -> str:
    """Convenience function to post-process Telugu OCR text."""
    processor = get_telugu_post_processor()
    return processor.process(text)


def post_process_telugu_with_corrections(
    text: str, token_frequency: Optional[Counter] = None
) -> Tuple[str, List[Dict[str, object]]]:
    """
    Same as post_process_telugu(), but also returns the dictionary-correction
    change-log (empty list if the feature is off or nothing was corrected).
    Safe to call concurrently — see TeluguPostProcessor.correct_spelling().

    token_frequency: optional book-wide word count — see
    TeluguPostProcessor.correct_spelling() and
    telugu_text_processor.compute_book_token_frequency().
    """
    processor = get_telugu_post_processor()
    return processor.process_with_corrections(text, token_frequency=token_frequency)
