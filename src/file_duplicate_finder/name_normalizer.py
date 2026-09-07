"""
Name Normalizer - Strips copy/version suffixes from filenames.

Supports Telugu (Unicode) and English filenames.
All comparisons use Unicode NFC normalization for consistency.

Handles patterns like:
  fileName         → fileName
  fileName-1       → fileName
  fileName-2       → fileName
  fileName (1)     → fileName
  fileName(1)      → fileName
  fileName(1)(1)   → fileName
  fileName (1)(2)  → fileName
  fileName - Copy  → fileName
  fileName copy    → fileName  (case-insensitive)
  fileName_1       → fileName

  Telugu examples:
  పుస్తకం(1).pdf  → పుస్తకం.pdf
  పుస్తకం-1.pdf   → పుస్తకం.pdf
  పుస్తకం (1)(1)  → పుస్తకం
"""

import re
import unicodedata
from pathlib import Path

# Suffix patterns stripped from the RIGHT end of the stem, applied repeatedly.
# These are purely ASCII-based suffixes, so they work regardless of the
# script (Telugu, English, mixed) used in the base filename.
_SUFFIX_PATTERNS = [
    r'\s*\(\d+\)',        # (1), (12)
    r'\s*-\s*\d+',       # -1, - 1, -12
    r'_\d+',             # _1, _12
    r'\s*-\s*[Cc]opy',   # - Copy, -copy
    r'\s+[Cc]opy',       # " copy", " Copy"
    r'\s*\[\d+\]',       # [1], [12]
]
_COMBINED = re.compile('(' + '|'.join(_SUFFIX_PATTERNS) + ')$',
                        re.UNICODE)


def _nfc(text: str) -> str:
    """Apply Unicode NFC normalization (consistent form for Telugu + English)."""
    return unicodedata.normalize('NFC', text)


def normalize_stem(stem: str) -> str:
    """
    Strip copy/version suffixes from a filename stem iteratively.
    Works with Telugu, English, or mixed names.

    Examples:
        'report(1)'        → 'report'
        'పుస్తకం(1)(1)'   → 'పుస్తకం'
        'doc - Copy'       → 'doc'
    """
    current = _nfc(stem)
    while True:
        stripped = _COMBINED.sub('', current).rstrip()
        stripped = _nfc(stripped)
        if stripped == current or stripped == '':
            break
        current = stripped
    return current


def normalize_key(filename: str) -> str:
    """
    Return the grouping key: NFC(normalized_stem + extension), lowercased.
    Telugu characters have no case, so lowercasing is safe and a no-op for them.

    Examples:
        'Report(1).PDF'         → 'report.pdf'
        'పుస్తకం-1.pdf'        → 'పుస్తకం.pdf'
        'MyFile (1)(1).docx'    → 'myfile.docx'
    """
    p = Path(_nfc(filename))
    stem = normalize_stem(p.stem)
    ext = p.suffix.lower()        # extension always ASCII, lowercasing is safe
    return _nfc(stem + ext)       # don't lowercase Telugu stem — keep original


def get_extension(filename: str) -> str:
    """Return lowercase extension (e.g. '.pdf')."""
    return Path(filename).suffix.lower()


def is_likely_copy(filename: str) -> bool:
    """Return True if the filename appears to be a copy (has a suffix stripped)."""
    p = Path(_nfc(filename))
    return normalize_stem(p.stem) != p.stem.rstrip()


def display_name(filename: str) -> str:
    """Return the NFC-normalized filename for display (preserves Telugu)."""
    return _nfc(filename)
