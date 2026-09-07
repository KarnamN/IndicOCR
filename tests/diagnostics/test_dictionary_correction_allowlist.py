"""
Regression check for Telugu dictionary-based spell-correction
(telugu_post_processor.TeluguPostProcessor.correct_spelling).

Feeds a fixed list of loanwords/proper nouns/known-good phrases through the
post-processor with dictionary correction ON and asserts the output is
byte-identical to the input — these must never be "corrected" away.

Run from the repo root: python tests/diagnostics/test_dictionary_correction_allowlist.py
"""
import sys

# Add src to path (run from repo root)
sys.path.append('src')

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from telugu_post_processor import TeluguPostProcessor

# Loanwords / proper nouns / common transliterations that must survive unchanged.
# Some are structurally clean (never touched under the v1 strict policy regardless);
# include known-good sentences too, as a broader smoke check.
KNOWN_GOOD = [
    'శ్రీ వేంకటేశ్వరుడు తిరుపతిలో కొలువై ఉన్నాడు',
    'రాముడు సీత లక్ష్మణుడు అడవికి వెళ్లారు',
    'హైదరాబాద్ తెలంగాణ రాజధాని',
    'విజయవాడ ఆంధ్రప్రదేశ్‌లో ఉంది',
    'ఇది ఒక పరీక్ష వాక్యం',
    'తెలుగు భాష చాలా అందమైనది',
    'కృష్ణుడు గోవర్ధన పర్వతం ఎత్తాడు',
    'బ్రహ్మ విష్ణువు శివుడు త్రిమూర్తులు',
]


def main():
    proc = TeluguPostProcessor(
        enable_shloka_fixes=True,
        enable_char_fixes=False,
        enable_punctuation_fixes=True,
        enable_stray_english_cleanup=True,
        enable_dictionary_correction=True,
    )

    failures = []
    for text in KNOWN_GOOD:
        out = proc.process(text)
        if out != text:
            failures.append((text, out))

    print(f"Checked {len(KNOWN_GOOD)} known-good strings.")
    if failures:
        print(f"❌ {len(failures)} regression(s) found:")
        for original, corrupted in failures:
            print(f"  IN : {original}")
            print(f"  OUT: {corrupted}")
        sys.exit(1)
    else:
        print("✅ All known-good strings survived unchanged.")


if __name__ == '__main__':
    main()
