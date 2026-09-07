# Telugu Wordlist

`te_wordlist.txt` — flat Telugu vocabulary (125,082 unique words), one word per line, UTF-8.

Source: [LibreOffice/dictionaries `te_IN`](https://github.com/LibreOffice/dictionaries/tree/master/te_IN)
(`te_IN.dic`), extracted from the Hunspell dictionary header/affix-flag lines. No affix
flags are present in the source file, so it is used as-is as a flat surface-form vocabulary.

License: GNU GPL v2 or later (see `README_te_IN.txt` in the source repository). Commercial use
and redistribution are permitted under GPL terms.

Used by `src/telugu_spell_checker.py` for dictionary-based Telugu spell-correction.
