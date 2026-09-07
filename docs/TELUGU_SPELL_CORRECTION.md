# Telugu Dictionary-Based Spell-Correction

Added 2026-07-08. Supersedes `docs/archive/OCR_CORRECTION_ANALYSIS.md`, which was an
unimplemented proposal for this exact feature — this doc describes what was actually built.

**Status: implemented, off by default** (`ENABLE_TELUGU_DICTIONARY_CORRECTION = False`).
Needs a CER/WER benchmark pass on real books before flipping on in production. Open
follow-ups tracked in [TELUGU_SPELL_CORRECTION_TODO.md](TELUGU_SPELL_CORRECTION_TODO.md).

## What it does

Corrects Telugu OCR output that's **structurally broken** — an orphaned vowel sign (matra)
with no consonant to attach to, or a dangling virama with no consonant following it — against
a real Telugu dictionary. These defects are already detected elsewhere
(`TeluguTextProcessor.grapheme_validity_score()`, used to flag junk pages) but were never
*corrected*, only used as a signal to reject the page.

**v1 is deliberately strict**: only words that already show a structural defect are
considered for correction. Structurally-clean but out-of-dictionary words (rare words,
proper nouns not in the dictionary) are left untouched — the lowest false-positive-risk
choice for a first version, at the cost of lower recall. A looser policy (correcting
clean-but-unknown words too) was considered and explicitly deferred, not rejected.

## Why a custom grapheme segmenter, not generic Unicode clustering

Generic Unicode grapheme clustering (UAX #29, e.g. the `regex` module's `\X`) only pulls a
*combining mark backward* onto its preceding base character — it does not merge a virama
*forward* onto the next consonant. So a stacked conjunct like క్ష (క + ్ + ష) would still be
split into multiple "default" clusters, not the single perceptual unit ("akshara") that
Telugu spelling and edit-distance logic actually needs to reason about.

`TeluguTextProcessor.segment_graphemes()` (`src/telugu_text_processor.py`) does this
correctly: consonant → zero-or-more (vattu + consonant) pairs (handles stacked conjuncts) →
zero-or-more trailing matras = one cluster.

## How correction works

`src/telugu_spell_checker.py` — `TeluguSpellChecker`:

1. Each unique grapheme cluster is remapped to a synthetic Unicode Private-Use-Area (PUA)
   codepoint (Supplementary PUA-A, `U+F0000`–`U+FFFFD`).
2. The PUA-remapped dictionary is loaded into `symspellpy.SymSpell`.
3. Lookups run in PUA/grapheme space, so edit distance is counted **per akshara**, not per
   raw Unicode codepoint — one misread conjunct costs exactly one edit, regardless of how
   many codepoints it spans.
4. The result is mapped back to real Telugu text via the inverse PUA→cluster map.

`TeluguPostProcessor.correct_spelling()` (`src/telugu_post_processor.py`) applies this per
whitespace-delimited token, gated by:

1. **Telugu-purity** — tokens containing ASCII letters/digits are skipped (that's
   `strip_junk_english()` / `CHAR_FIXES` territory — a disjoint failure mode).
2. **Minimum length** — fewer than 3 grapheme clusters is skipped (too ambiguous).
3. **Already known** — exact dictionary matches are never touched.
4. **Structural-defect gate (v1 strict)** — only tokens `grapheme_validity_score()` flags as
   defective are attempted; clean-but-unknown words are left alone.
5. **Unambiguous-best-candidate gate** — a correction is only accepted if it's the single
   best edit-distance match with no tie, and the distance is within
   `min(2, max(1, grapheme_length // 3))`. Ties are common with this dictionary (see
   [Limitations](#limitations)) and are intentionally rejected rather than guessed at.
6. Every accepted correction is logged at debug level.
7. A small curated `TELUGU_PROPER_NOUN_ALLOWLIST` (deities, place names, common
   transliterations) is checked first, independent of the above gates.

## Remaining failure class: structurally valid, semantically wrong

Even after both segmenter fixes above, edit distance alone can still land on a real
dictionary word that's the wrong word for the context — e.g. `దోేషాలు`→`మషాలు` instead of
`దోషాలు`. This is a hard limit of the approach, not a bug: nothing in the pipeline currently
judges whether a correction *makes sense next to the words around it*, only whether it's
structurally the closest dictionary entry. Options considered for closing this gap, none
implemented:

- **Word-frequency weighting** — rank candidates by corpus frequency, not just edit
  distance, so a common word beats an obscure one on a tie. Only helps when candidates are
  actually competing; doesn't help when the wrong word is the single unambiguous closest
  match (as in the traced `ఆధ్యాో్మిక` case before the segmenter fix — that was a
  segmentation bug, not a frequency problem).
- **Contextual validation via the already-integrated Gemini** — the pipeline already calls
  Gemini for OCR escalation (`gemini_ocr_processor.py`), so it's the most readily available
  resource for judging *meaning*, which pure edit distance structurally cannot do. Since
  corrections are rare (~0.15-0.18% of all words, per the real-book numbers above), a
  contextual sanity check ("does this word fit the surrounding sentence?") would only need
  to run on that tiny slice of already-accepted corrections — cheap relative to full-page
  OCR calls. Not implemented; would need its own accept/reject threshold and logging, same
  spirit as the existing quality gates.
- **Telugu morphological analyzer** — a resource that understands real derivational patterns
  (e.g. ఆధ్యాత్మిక = ఆధ్యాత్మ + -ika) could reject a match like `ఆమిక` as morphologically
  implausible even before checking edit distance. No such resource is currently available to
  this project; would be a significant new dependency to source or build.

## Dictionary asset

- `resources/telugu_dictionary/te_wordlist.txt` — 125,082 words, extracted from the
  [LibreOffice `te_IN` Hunspell dictionary](https://github.com/LibreOffice/dictionaries/tree/master/te_IN)
  (GPL v2+, commercial use and redistribution permitted). No affix flags in the source file,
  used as a flat surface-form vocabulary.
- `resources/telugu_dictionary/te_wordlist.symspell_cache.pkl` — generated build cache (SymSpell
  index + PUA cluster mapping, ~49MB), rebuilt automatically if the `.txt` source is newer.
  Not meant to be hand-edited or committed if this repo starts using version control with
  size limits — it's fully reproducible from the `.txt` file.
- No word-frequency data — every dictionary entry has equal weight, which is why ambiguous
  (tied) corrections are common; see Limitations.

## Configuration

`ENABLE_TELUGU_DICTIONARY_CORRECTION` in `config.py` / `config_v5.py` / `config_tesseract.py`
(default `False`). Wiring this flag also fixed three pre-existing dead flags —
`get_telugu_post_processor()` previously hardcoded its fix-category flags and ignored
`config` entirely; it now reads all four via `getattr(config, ..., default)`.

## Limitations

- **No per-word OCR confidence signal** is available at this stage (confidence exists inside
  `PaddleV5Processor._quality_gate` but isn't threaded through to post-processing), so this
  relies purely on structural + dictionary-membership evidence — it cannot distinguish "OCR
  was unsure" from "OCR was confident but wrong."
- **Low recall by design** — with a frequency-less 125k-word dictionary, many single-edit
  corrections tie with multiple equally-plausible candidates, and ties are rejected rather
  than guessed. Verified directly: 5/5 hand-corrupted real dictionary words (longer,
  lower-ambiguity words) were corrected exactly; a short/common corrupted word produced a tie
  and was correctly left uncorrected.
- **Clean-but-out-of-dictionary words are never touched in v1** — a genuine misread that
  happens to still be grammatically well-formed (a valid-looking but wrong word) will not be
  caught by this mechanism at all.

## Verification done so far

- `tests/diagnostics/test_dictionary_correction_allowlist.py` — 8 known-good strings
  (proper nouns, common phrases) survive unchanged with the flag on.
- Manual correction tests — 5 hand-corrupted real dictionary words corrected exactly.
- Confirmed working end-to-end in both the Windows dev-sandbox (`wenv`) and the real WSL
  deployment environment (`venv`) — the SymSpell cache built on Windows loaded correctly in
  WSL without a rebuild.
- **Real-book validation (2026-07-08)**: ran `correct_spelling()` against already-extracted
  raw OCR text from two in-progress/completed live conversions (a 70+ page Telugu novel and
  a 202-page heavily-degraded mantra/sloka book), read-only, not affecting either run (the
  flag was off in both). Findings:
  - Low recall by design is confirmed in practice: on the mantra book, only 3.3% of flagged
    structural defects were resolved (28/842) — most garbled tokens in a badly-degraded scan
    have no unambiguous single-edit dictionary match and are correctly left alone.
  - Found and fixed a real bug via this analysis: the LibreOffice dictionary contains 621
    short morpheme-fragment entries (bare consonant+virama stubs like క్, స్, బ్, meant to
    combine with Hunspell affix rules we don't apply) that were being offered as fuzzy
    correction targets, collapsing short garbled tokens into meaningless stubs (e.g.
    `స్ూ`→`స్`, `పూర్ి`→`పూర్` instead of `పూర్తి`). Fixed by excluding dictionary entries
    with fewer than 3 grapheme clusters from the fuzzy-match index (`MIN_TARGET_CLUSTERS` in
    `telugu_spell_checker.py`), plus a related segmenter fix so a word-final virama with
    nothing following it (e.g. the `్` in `పూర్`) attaches to the preceding consonant as one
    cluster instead of counting as a spurious extra cluster (`segment_graphemes()` in
    `telugu_text_processor.py`). Re-verified after the fix: both previously-buggy patterns no
    longer fire, word-change count on the mantra book dropped from 59 to 41 with no allowlist
    regressions.
  - The remaining failure mode is the documented no-language-model limitation: a correction
    can be structurally sound and dictionary-valid but semantically wrong (e.g.
    `దోేషాలు`→`మషాలు` instead of `దోషాలు`) because edit distance alone can't judge meaning.
    This is inherent to the v1 design, not a bug — see Limitations above.
  - Found and fixed a second, related bug via a traced example (`ఆధ్యాో్మిక`→`ఆమిక` instead
    of the correct `ఆధ్యాత్మిక`): the original `segment_graphemes()` let a consonant absorb
    *multiple* stacked matras and an unconditional trailing virama into one cluster. On
    corrupted input this produced an oversized "blob" cluster with no real dictionary
    counterpart, which SymSpell then treated as a single opaque symbol — cheap to delete
    outright (distance 1, landing on an unrelated word) rather than correctly substitute
    (distance 2+, the actually-intended word). Fixed by (a) capping trailing matras at one
    per cluster — a second matra is itself an orphaned-matra defect and now starts its own
    cluster instead of being absorbed, and (b) only attaching a trailing virama when NOT
    followed by a consonant (true word-final case only). Re-traced after the fix: the
    corrupted token now segments into 6 granular clusters instead of one blob, its true
    edit distance to the correct word is 3 (over the max-2 threshold), and the algorithm
    now correctly declines to correct it at all rather than confidently picking the wrong
    word. Net effect on the 270-page test book: corrections dropped from 62 to 53 — this
    traded away a few previously-good corrections along with the wrong ones, which is the
    expected precision-over-recall direction for a feature designed to be conservative.

## Before enabling in production

Run `scripts/benchmark_quality.py --dict-correction --image <page> --reference <ref.txt>`
against real book pages with ground-truth text (ideally in WSL) to compare CER/WER with the
flag on vs. off, across enough pages to get a representative false-positive rate — a single
page isn't representative. See [ARCHITECTURE.md](ARCHITECTURE.md#testing--benchmarking).
