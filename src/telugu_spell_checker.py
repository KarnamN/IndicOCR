"""
Telugu Dictionary-Based Spell Checker
Grapheme-cluster-aware fuzzy word lookup against a Telugu vocabulary, used to
correct structurally-defective OCR output (see telugu_post_processor.py).
"""
import logging
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from symspellpy import SymSpell, Verbosity

from telugu_text_processor import get_telugu_text_processor

logger = logging.getLogger(__name__)

# Default asset locations, relative to the repo root (src/ is one level down).
_DEFAULT_WORDLIST_PATH = Path(__file__).resolve().parent.parent / "resources" / "telugu_dictionary" / "te_wordlist.txt"
_DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / "resources" / "telugu_dictionary" / "te_wordlist.symspell_cache.pkl"

# Supplementary Private Use Area-A (U+F0000-U+FFFFD): 65534 codepoints, far more
# than the realistic number of distinct Telugu grapheme clusters in any real
# dictionary/corpus. Kept out of the BMP PUA (U+E000-U+F8FF) so it can never
# collide with any font's private-use glyphs that might appear in OCR input.
_PUA_START = 0xF0000
_PUA_END = 0xFFFFD

MAX_EDIT_DISTANCE = 2

# Minimum grapheme-cluster length for a dictionary word to be usable as a fuzzy
# correction *target*. The LibreOffice te_IN Hunspell wordlist includes short
# morpheme-fragment entries (bare consonant+virama stubs like క్, స్, బ్, and
# other 1-2 codepoint entries — 621 of them) meant to combine with Hunspell affix
# rules we don't apply here. Used as a flat vocabulary, these aren't real
# standalone Telugu words, and short garbled OCR tokens were being "corrected"
# to them (e.g. దోేషాలు -> మషాలు instead of దోషాలు, పూర్ి -> పూర్ instead of
# పూర్తి) — found via real-book verification 2026-07-08. Matches the minimum
# already enforced on *input* tokens in telugu_post_processor.py.
MIN_TARGET_CLUSTERS = 3


class TeluguSpellChecker:
    """
    Dictionary-backed fuzzy lookup for Telugu words, operating in grapheme-cluster
    space (one akshara = one edit unit) rather than raw Unicode codepoint space.

    SymSpell's fast lookup is built on precomputed deletion variants over Python
    string *codepoints*. To get grapheme-level edit distance out of it, each
    unique grapheme cluster (from TeluguTextProcessor.segment_graphemes) is
    remapped to a single synthetic Private-Use-Area codepoint before being fed
    to SymSpell, and mapped back on the way out.
    """

    def __init__(self, wordlist_path: Optional[Path] = None, cache_path: Optional[Path] = None):
        self.wordlist_path = Path(wordlist_path) if wordlist_path else _DEFAULT_WORDLIST_PATH
        self.cache_path = Path(cache_path) if cache_path else _DEFAULT_CACHE_PATH
        self._text_processor = get_telugu_text_processor()

        self.sym_spell: SymSpell
        self.cluster_to_pua: Dict[str, str]
        self.pua_to_cluster: Dict[str, str]
        self.known_words: set

        self._load_or_build()

    def _load_or_build(self):
        if (
            self.cache_path.exists()
            and self.wordlist_path.exists()
            and self.cache_path.stat().st_mtime >= self.wordlist_path.stat().st_mtime
        ):
            try:
                with open(self.cache_path, "rb") as f:
                    data = pickle.load(f)
                self.sym_spell = data["sym_spell"]
                self.cluster_to_pua = data["cluster_to_pua"]
                self.pua_to_cluster = data["pua_to_cluster"]
                self.known_words = data["known_words"]
                logger.info(
                    f"Telugu spell checker loaded from cache: {len(self.known_words)} words, "
                    f"{len(self.cluster_to_pua)} grapheme clusters"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load spell-checker cache, rebuilding: {e}")

        self._build_index()
        self._save_cache()

    def _next_pua_codepoint(self, counter: List[int]) -> str:
        cp = _PUA_START + counter[0]
        if cp > _PUA_END:
            raise RuntimeError("Exhausted Private Use Area codepoint space for grapheme clusters")
        counter[0] += 1
        return chr(cp)

    def _to_pua_string(self, clusters: List[str], counter: List[int]) -> str:
        pua_chars = []
        for cluster in clusters:
            pua_char = self.cluster_to_pua.get(cluster)
            if pua_char is None:
                pua_char = self._next_pua_codepoint(counter)
                self.cluster_to_pua[cluster] = pua_char
                self.pua_to_cluster[pua_char] = cluster
            pua_chars.append(pua_char)
        return "".join(pua_chars)

    def _build_index(self):
        if not self.wordlist_path.exists():
            raise FileNotFoundError(f"Telugu wordlist not found: {self.wordlist_path}")

        logger.info(f"Building Telugu spell-checker index from {self.wordlist_path}")
        self.cluster_to_pua = {}
        self.pua_to_cluster = {}
        self.known_words = set()
        self.sym_spell = SymSpell(max_dictionary_edit_distance=MAX_EDIT_DISTANCE, prefix_length=10)

        counter = [0]
        skipped_short = 0
        with open(self.wordlist_path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if not word:
                    continue
                self.known_words.add(word)
                clusters = self._text_processor.segment_graphemes(word)
                if len(clusters) < MIN_TARGET_CLUSTERS:
                    # Not added to the fuzzy-match index — see MIN_TARGET_CLUSTERS.
                    skipped_short += 1
                    continue
                pua_string = self._to_pua_string(clusters, counter)
                self.sym_spell.create_dictionary_entry(pua_string, 1)

        logger.info(
            f"Telugu spell-checker index built: {len(self.known_words)} words "
            f"({skipped_short} short fragments excluded from fuzzy-match targets), "
            f"{len(self.cluster_to_pua)} distinct grapheme clusters"
        )

    def _save_cache(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "wb") as f:
                pickle.dump(
                    {
                        "sym_spell": self.sym_spell,
                        "cluster_to_pua": self.cluster_to_pua,
                        "pua_to_cluster": self.pua_to_cluster,
                        "known_words": self.known_words,
                    },
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
            logger.info(f"Telugu spell-checker cache written to {self.cache_path}")
        except Exception as e:
            logger.warning(f"Failed to write spell-checker cache: {e}")

    def is_known_word(self, word: str) -> bool:
        return word in self.known_words

    def _encode_to_pua(self, word: str) -> Optional[str]:
        """
        Encode `word` as a string of PUA characters, one per grapheme cluster,
        so SymSpell's edit distance operates on whole aksharas instead of raw
        codepoints. Shared by suggest() and suggest_candidates(). Returns None
        if the word has more unseen clusters than remaining PUA slots.
        """
        clusters = self._text_processor.segment_graphemes(word)
        # Unseen clusters get a throwaway PUA slot for this lookup only (not
        # persisted into the shared mapping) so they still act as one edit
        # unit instead of exploding into per-codepoint edits.
        local_counter = [len(self.cluster_to_pua)]
        pua_chars = []
        for cluster in clusters:
            pua_char = self.cluster_to_pua.get(cluster)
            if pua_char is None:
                cp = _PUA_START + local_counter[0]
                if cp > _PUA_END:
                    return None
                pua_char = chr(cp)
                local_counter[0] += 1
            pua_chars.append(pua_char)
        return "".join(pua_chars)

    def suggest(self, word: str, max_edit_distance: int = MAX_EDIT_DISTANCE) -> Optional[Tuple[str, int]]:
        """
        Look up the best correction for `word` in grapheme-cluster space.

        Returns (corrected_word, edit_distance) only when there is a single,
        unambiguous best candidate (no tie with another candidate at the same
        distance) and word is not already known. Returns None otherwise —
        callers should treat None as "do not correct this word".
        """
        if self.is_known_word(word):
            return None

        pua_string = self._encode_to_pua(word)
        if pua_string is None:
            return None

        suggestions = self.sym_spell.lookup(
            pua_string, Verbosity.ALL, max_edit_distance=max_edit_distance
        )
        if not suggestions:
            return None

        best = suggestions[0]
        if len(suggestions) > 1 and suggestions[1].distance == best.distance:
            return None  # ambiguous — no unambiguous single best candidate

        corrected_clusters = [
            self.pua_to_cluster.get(c, c) for c in best.term
        ]
        corrected_word = "".join(corrected_clusters)
        return corrected_word, best.distance

    def suggest_candidates(self, word: str, max_edit_distance: int = MAX_EDIT_DISTANCE) -> List[Tuple[str, int]]:
        """
        Like suggest(), but returns every candidate found (at any distance up
        to max_edit_distance), not just a single unambiguous winner.

        suggest()'s tie-avoidance is the right default for blind dictionary
        correction — but it makes suggest() useless for short/common words,
        which are exactly the words most likely to have many equally-distant
        real-word neighbors (e.g. తండి has 55 candidates within edit distance
        1, so suggest() always returns None for it, tie or not). A caller that
        has independent structural evidence about which *kind* of edit it's
        looking for (see TeluguTextProcessor.classify_single_stroke_edit) can
        filter this raw candidate list itself instead of being blocked by
        suggest()'s generic ambiguity check. Returns [] under the same
        conditions suggest() would return None (already known, or no
        candidate).
        """
        if self.is_known_word(word):
            return []

        pua_string = self._encode_to_pua(word)
        if pua_string is None:
            return []

        suggestions = self.sym_spell.lookup(
            pua_string, Verbosity.ALL, max_edit_distance=max_edit_distance
        )
        results = []
        for s in suggestions:
            corrected = "".join(self.pua_to_cluster.get(c, c) for c in s.term)
            results.append((corrected, s.distance))
        return results


# Singleton instance, mirroring get_telugu_post_processor() / get_telugu_text_processor().
_default_spell_checker = None
_spell_checker_lock = threading.Lock()


def get_telugu_spell_checker() -> TeluguSpellChecker:
    """
    Get or create the default TeluguSpellChecker singleton.

    Double-checked locking: without the lock, concurrent page-processing threads
    racing on first access could each build the 125k-word index and race on the
    non-atomic pickle cache write in _save_cache(), risking a corrupted cache file.
    """
    global _default_spell_checker
    if _default_spell_checker is None:
        with _spell_checker_lock:
            if _default_spell_checker is None:
                _default_spell_checker = TeluguSpellChecker()
    return _default_spell_checker
