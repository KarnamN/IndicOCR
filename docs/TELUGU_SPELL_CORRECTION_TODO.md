# Telugu Spell-Correction — Open TODOs

Follow-ups from the 2026-07-08 implementation and real-book validation (see
[TELUGU_SPELL_CORRECTION.md](TELUGU_SPELL_CORRECTION.md) for full background). Feature is
currently off by default (`ENABLE_TELUGU_DICTIONARY_CORRECTION = False`). Ordered roughly by
what unblocks enabling this in production first.

## DONE (2026-07-08): manual-review gate + correction dashboard

Every correction currently routes to manual review (see item 2 for why) via a review gate
built this session:

- `TeluguPostProcessor.correct_spelling()` / `process_with_corrections()` /
  `post_process_telugu_with_corrections()` (`src/telugu_post_processor.py`) return a
  change-log (`[{'line', 'from', 'to', 'distance'}, ...]`) alongside the corrected text —
  returned as a plain value, not stored on the shared singleton, so it's safe under the
  pipeline's concurrent page processing.
- `DICTIONARY_CORRECTION_GEMINI_THRESHOLD = 10` (`config.py`) — pages with fewer corrections
  than this are flagged `needs_manual_review`; pages at/above it are *also* currently flagged
  the same way, with `needs_gemini_validation = True` additionally set as a stub, since item 2
  isn't implemented yet. No real book has ever hit close to 10 corrections on one page (max
  observed: 3), so in practice everything currently routes to manual review.
- `OptimizedPDFToEPUBConverter.convert_streaming()` (`src/pdf_to_epub_converter_optimized_v2.py`)
  now defers the automatic EPUB/MOBI build when any page has `needs_manual_review` — exposed
  via `self.pages_pending_review` (getattr-after-return convention, same as
  `self.paddle_pages` etc.) rather than changing the method's bool return type.
- `app.py`: emits a new `pending_review` SocketIO event instead of `complete` when the build
  was deferred; the `finally` block that normally deletes the job's converter reference is
  guarded to skip deletion in this state, since `/api/correction/rebuild/<job_id>` needs that
  same converter instance to build once review is done.
- Fixed a pre-existing bug found while wiring this up: `get_correction_pages()`,
  `get_page_for_correction()`, and `save_corrected_page()` all constructed `.jbl`/`_text.json`
  filenames without the `_{sub_idx}` suffix that `_save_page_result()` always includes (even
  for `sub_idx=0`) — meaning the correction dashboard silently returned zero pages for every
  real conversion before this fix.
- `correction.html`: shows a pending-review banner + per-page ⚠️ badge with correction count,
  a before/after panel for the current page's corrections, and clears the review flag when
  the reviewer clicks SAVE CHANGES (whether or not they edited the text — an explicit look
  counts as approval).
- Added a self-contained on-screen Telugu keyboard (vowels/consonants/matras/punctuation grid,
  inserts at cursor) to `correction.html` — no external API/transliteration dependency.
- `main.js`: added a `pending_review` handler that redirects straight to the correction
  dashboard, since no EPUB/MOBI exists yet at that point.

Verified via Flask test-client requests against both real completed job data (confirms the
sub_idx filename fix) and synthetic fixture data simulating a flagged correction (confirms
the full flag → surface → review → clear cycle), all run in WSL.

## 1. Real CER/WER benchmark before enabling by default

Everything validated so far is against real books with **no ground-truth reference
transcript** — the ~83% good / ~12% borderline / ~4% wrong quality split (see
TELUGU_SPELL_CORRECTION.md) is my own read of individual corrected words, not a rigorous
accuracy measurement. `scripts/benchmark_quality.py --dict-correction` already supports
before/after CER/WER comparison but needs a reference `.txt` for at least one real page to
produce an actual number.

**Blocker**: need a ground-truth transcript for one or more real pages. Once available, run
the benchmark and confirm CER/WER doesn't regress before flipping the default flag.

## 2. Gemini-based contextual validation for accepted corrections

**The threshold/gate scaffolding for this now exists** (see DONE section above) —
`needs_gemini_validation` is already set on pages with 10+ corrections, currently treated
identically to `needs_manual_review` as a stub. What's missing is the actual Gemini call:
pages flagged `needs_gemini_validation` should be auto-validated instead of routed to manual
review, only falling through to manual review if Gemini itself is uncertain or fails.

Addresses the remaining ~4% "clearly wrong word" class (e.g. `దోేషాలు`→`మషాలు` instead of
`దోషాలు`) — cases where edit distance lands on a real dictionary word that doesn't fit the
sentence. Pure edit distance has no way to judge meaning; Gemini is already integrated in
this pipeline for OCR escalation (`gemini_ocr_processor.py`), so it's the most readily
available resource for a meaning-aware check.

**Named sub-case: verb tense/aspect/person agreement.** The dictionary is a flat wordlist —
every inflected verb form (`కూర్చున్నాడు`, `కూర్చుంటాడు`, `కూర్చోక`, `కూర్చోవడం`...) is its
own independent entry with no tracked relationship to its root or to other forms of the same
verb. The corrector picks whichever entry is edit-distance-closest with no check on whether
its tense/aspect/person/number actually agrees with the surrounding sentence. Confirmed
examples from the real-book data: `కూర్చోే`→`కూర్చోక` (landed on a negative gerund, "without
sitting" — may not match the tense the sentence needed), `వీలుంే`→`వీలుండు` (bare/imperative
form vs. a more likely habitual/future `వీలుంటుంది`), `అివృద్ధియై,`→`అభివృద్ధియైన` (past
participle "having become" vs. adjectival participle "that became" — a subtler aspect
shift). Nouns mostly avoid this specific failure mode (their equivalent is case-marker loss,
already documented separately) — verbs are the sharp edge because Telugu inflects so heavily
for tense/aspect/person/number and each inflected form looks unrelated to an edit-distance
algorithm. A contextual check needs to verify grammatical agreement, not just "is this a real
word," to close this gap.

Since corrections are rare (~0.18% of all words per the real-book numbers), this only needs
to run on the small slice of *already-accepted* corrections, not full-page OCR — cheap
relative to existing Gemini usage.

**Needs deciding before implementing**:
- Where it plugs in: synchronous per-correction call inside `correct_spelling()`, or a
  batched pass (collect corrections + surrounding sentence, one Gemini call per page)?
- Accept/reject prompt and threshold — same spirit as the existing quality gates in
  `paddle_v5_processor._quality_gate()`.
- What happens on Gemini failure/timeout — fall back to accepting the dictionary
  correction as-is, or reject it? (Given the low base rate, rejecting on failure is probably
  safer — matches the "conservative by default" design.)
- Logging/auditability requirements, matching the existing debug-log pattern for corrections.

## 3. Word-frequency weighting — lower priority

Would only help when multiple candidates are genuinely tied on edit distance — doesn't help
the "single unambiguous but wrong" cases that dominate the remaining error class (those need
context, not frequency). The AI4Bharat IndicNLP frequency list was already ruled out earlier
for its NonCommercial license; an alternative source would need sourcing. Worth revisiting
only if post-Gemini-validation data shows tie-breaking is still a meaningful share of errors.

## 4. Telugu morphological analyzer — exploratory, no resource identified yet

The more principled fix for the verb tense/aspect/person mismatch problem named in item 2 —
a morphological analyzer that decomposes a verb into root + tense/aspect/person markers
could constrain corrections to forms that share the *same* inflection category as the
degraded input, instead of accepting any edit-distance-close form regardless of tense.
Would also let the corrector reject a match like `ఆమిక` as morphologically implausible (not a
real derivational form) even before checking edit distance, and would also help recover
correct inflected/case-marked forms currently missed by the flat dictionary (see the
"dropped grammatical suffix" category, e.g. `కాలంలిో`→`కాలం` instead of `కాలంలో`). No such
resource is currently available to this project — this is a bigger lift (sourcing or
building) than the other items here, revisit only if the above don't close the gap enough.

## 5. Revisit the v1-strict clean-but-OOV policy

Original design decision (see plan history) was to only correct tokens already flagged
structurally defective, leaving clean-but-out-of-dictionary words untouched entirely. A
looser policy (also attempting very-tight-edit-distance corrections on clean-but-unknown
words) was explicitly deferred, not rejected. Revisit once the false-positive rate on the
current strict policy is well understood (items 1-2 above should inform this).

## 6. Dictionary OOV-ratio junk-detection signal — built, calibrated, NOT viable as designed

2026-07-19: Added `PageComplexityAnalyzer._compute_oov_ratio()` (`src/page_complexity_analyzer.py`),
wired into `is_junk_text()` behind `ENABLE_TELUGU_OOV_JUNK_SIGNAL` (`src/config.py`, default `False`)
— the idea being that structurally-valid-but-wrong-word hallucinations (real graphemes, correct
grammar shape, just the wrong word — common on faint/low-contrast scans) slip past every existing
signal, all of which check shape/grammar, not word identity. Reuses the same `te_IN` dictionary as
spell-correction via the shared `dictionary_lookup_candidate()` gate (also promoted to
`telugu_text_processor.py` in this change, replacing the copy that used to live on
`TeluguPostProcessor`).

Ran `scripts/calibrate_oov_ratio.py` against all 5,964 real page samples in `data/temp/`. Result:
**no viable global threshold exists** — the OOV-ratio distributions for "already junk per existing
signals" and "currently clean" overlap too heavily to separate:

| | median | p90 | p99 |
|---|---|---|---|
| Already junk (existing signals) | 84.7% | 92.1% | 98.8% |
| Currently clean (existing signals) | 61.4% | 78.4% | 95.3% |

Root cause, confirmed by hand-inspecting individual words: `TeluguSpellChecker.is_known_word()` is an
**exact match** against a flat wordlist. Telugu is agglutinative — case-marked/inflected forms
(`కంఠంలో`, `సంవత్సరాలు`, `గుర్తించాడు`) aren't in the list even though they're completely correct,
which alone pushes clean-page OOV into the 40-60%+ range (same underlying gap as item 4's
"dropped grammatical suffix" note). On top of that, this corpus has a lot of devotional/Sanskrit-
hybrid content (stotrams, ashtakams) that reads as ~100% OOV even when perfectly transcribed —
several of the highest-OOV "currently clean" pages the calibration script flagged were legitimate
hymns (e.g. అన్నపూర్ణాష్టకమ్), not hallucinations.

**Conclusion: leave `ENABLE_TELUGU_OOV_JUNK_SIGNAL` off** — this isn't a "needs a better threshold"
gap, the exact-match approach itself doesn't separate the two populations. The instrumentation
(always-computed ratio logged to `converter_events.jsonl` per page, `_compute_oov_ratio()`, the
calibration script) is left in place since it's harmless when off and useful raw material for
whichever fix is pursued. Two paths forward, neither started:
- **Stem/fuzzy-aware lookup** instead of exact match, so inflected-but-correct forms don't count as
  unknown — would need the same kind of morphological handling named in item 4, or a looser
  edit-distance-based "is this close to a known word" check (distinct from `.suggest()`'s correction
  role) that tolerates suffix-length differences.
- **Exclude devotional/shloka content before scoring** — this codebase already treats that content
  as a distinct category (`ENABLE_SHLOKA_FIXES`), so extending that classification to gate the OOV
  signal (rather than applying it uniformly) is a smaller lift than a full morphological analyzer.

## 7. Missing/extra matra-vattu stroke repair — built, validated, missing-direction enabled-ready

2026-07-20: User reported the manual-reprocess correction dashboard frequently shows vatulu
(subscript conjunct consonants) and guninthalu (vowel signs/matras) **missing** from OCR output
(e.g. `వాడు` read as `వడు` — the ా matra silently dropped). Investigated whether any Telugu NLP
library exists for this: none does as of 2026 (academic-only space; AI4Bharat's `indic_nlp_library`
has an MIT-licensed unsupervised Telugu morphological analyzer, but its pretrained model comes from
the same AI4Bharat resource bundle already ruled out in item 3 for NonCommercial licensing, and it
targets suffix segmentation, not stroke defects, so it wouldn't have solved this anyway). Confirmed
this is exactly item 5's deferred "clean-but-OOV" gap: `grapheme_validity_score()` only catches
*orphaned/extra* marks (something present in the wrong place), never a *dropped* stroke (nothing
left behind to inspect) — so a dropped matra/vattu produces a structurally-clean-looking wrong word
that `correct_spelling()`'s `invalid_count == 0` branch has always left untouched, never reaching
`TeluguSpellChecker.suggest()`.

Added `TeluguTextProcessor.classify_single_stroke_edit()` (`src/telugu_text_processor.py`), which
segments both the original and a distance-1 `suggest()` candidate into grapheme clusters
(`segment_graphemes()`) and only classifies the edit as a stroke repair when cluster *count* is
unchanged and the one differing cluster pair is related by "one is the other plus exactly one
trailing matra, or one trailing (vattu+consonant) pair" — i.e. a dropped/added stroke on a single
akshara, not a different word entirely. (Key implementation detail: a dropped matra/vattu is a
cluster *substitution* in grapheme-cluster space, not an insertion — `వాడు`→`వడు` is `వా`+`డు` vs
`వ`+`డు`, same cluster count. This was verified against `segment_graphemes()`'s actual clustering
rules before implementing, not assumed.) Wired into `correct_spelling()`
(`src/telugu_post_processor.py`) behind two new flags, both default `False`:
`ENABLE_TELUGU_STROKE_CORRECTION` (missing-direction: `missing_matra`/`missing_vattu`) and
`ENABLE_TELUGU_STROKE_REMOVAL_CORRECTION` (reverse/extra-direction, nested under the first).
Corrections get a `'category'` key alongside the existing `{'line','from','to','distance'}` shape.

Ran `scripts/calibrate_stroke_correction.py` (new) against all 6,061 real page samples in
`data/temp/`: **4,393 candidate corrections** — `missing_matra`: 2,053, `missing_vattu`: 1,120,
`extra_matra`: 1,114, `extra_vattu`: 106. Hand-reviewed a sample of each category:

- **Missing-direction (matching the user's original complaint) validated clean.** Every example
  checked was a genuine OCR drop, correctly restored — `మహాత్మల`→`మహాత్ముల`, `అప్పటికప్పడు`→
  `అప్పటికప్పుడు`, `గంథములందు`→`గ్రంథములందు` (dropped ్ర), including cases where the OCR also glued
  a stray `(` onto the word (`(బహ్మచర్యం`→`బ్రహ్మచర్యం`) that `dictionary_lookup_candidate`'s
  punctuation-stripping incidentally cleans up too.
- **Extra-direction (removal) surfaced a real false-positive risk**, confirming the residual risk
  named when this was scoped: Telugu has legitimate optional long-vowel/emphatic forms and
  compound-linking forms a flat dictionary doesn't fully cover. `ఎంతోమంది`→`ఎంతమంది` changes meaning
  (ఎంతో = "so much/many" intensifier vs ఎంత = "how much/many" — not the same word); `అహింసా,`→
  `అహింస` may remove a legitimate emphatic/verse form (as in "అహింసా పరమో ధర్మః"). This direction is
  real but not obviously safe to auto-apply the way the missing-direction is.

**Current state**: `ENABLE_TELUGU_STROKE_CORRECTION` (missing-direction only) was flipped to `True`
in `src/config.py` and `src/config_tesseract.py` on 2026-07-20, after the user independently
reported seeing lots of unclear/uncorrected words while reviewing a real conversion
(`Nuvve_naa_pranam`) — re-running the validation script against that specific book's already-shipped
output found **61 more clean missing-stroke corrections** the existing structural-only path had
missed entirely (vs. 38 structural corrections applied), confirming the gap in practice, not just in
calibration data. `ENABLE_TELUGU_STROKE_REMOVAL_CORRECTION` stays off pending further review (e.g.
checking removal candidates against a devotional/verse-content allowlist similar to item 6's
shloka-exclusion idea, or requiring higher confidence before accepting a removal).
