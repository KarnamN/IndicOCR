# Fine-tuning `te_PP-OCRv5_mobile_rec` on our own corpus — scoping

Written 2026-08-31, following a letter-mistake investigation (see the mining-script output referenced
below). Not implemented — this is a plan to review/schedule separately, not a finished feature.

## Why this is the biggest remaining lever

Every cheap, rule-based fix for letter-level mistakes in this pipeline is now either already shipped
or ruled out:

- Missing matra/vattu stroke drops → `ENABLE_TELUGU_STROKE_CORRECTION` (already on).
- The "్ర misread as literal (" conjunct confusion → `CONJUNCT_RA_MISREAD_FIXES` (already on, fixes
  91.5% of its own pattern; the residual 8.5% is edge-case triple-conjuncts/loanwords not safely
  regex-fixable — see the 2026-08-31 session notes).
- Cross-script (Telugu+Latin) word contamination → already gated by `PADDLE_MAX_MIXED_WORDS`/`_RATIO`.
- Ambiguous-confidence single-letter misreads → `ENABLE_PADDLE_CONFIDENCE_REVOTE` (built 2026-08-31,
  off by default, needs a real calibration pass — see that flag's docstring in `config_v5.py`).

What's left is errors baked into `te_PP-OCRv5_mobile_rec` itself: it's a small (7.5MB) general-purpose
public model that never saw this project's specific book fonts, scan degradation, or paper texture.
No post-processing layer can fully compensate for that — the model needs to actually learn our data.
PP-OCRv5 also doesn't ship a larger Telugu recognition tier to swap in instead (confirmed by checking
both the downloaded model cache and PaddleX's bundled `paddlex/configs/modules/text_recognition/`
directory on the WSL box — `te_PP-OCRv5_mobile_rec` is the only Telugu recognition model in the zoo).

## The data problem (the actual hard part)

Fine-tuning a `TextRecognition` model needs **(single-line crop image, ground-truth line text)** pairs
— PaddleOCR's standard rec-training format is an image folder plus a label file of
`relative/image/path\tground_truth_text` lines. We don't have this directly. What we have:

1. **Original PDFs**: retained in `data/uploads/`.
2. **Per-page final text**: retained per page in `page_{n}_{sub_idx}_text.json` / `.jbl` — this is the
   text *after* whatever correction happened (dictionary correction, stroke repair, and — for pages
   that went through the correction dashboard — actual human edits saved via
   `/api/correction/rebuild/<job_id>`). Human-reviewed pages are the real ground truth; auto-corrected
   pages are not.
3. **What's missing**: per-box coordinates. `PaddleV5Processor._paddle_extract()` returns
   `boxes_data` (text + confidence + `left/top/width/height` per line) at OCR time, but the converter
   never persists it — confirmed by grepping `pdf_to_epub_converter_optimized_v2.py` for any
   `boxes`-saving call; there is none. Page images themselves also aren't kept as files (rendered
   on-the-fly from the PDF via `_convert_single_page()`, discarded after use, per the `del page_image`
   cleanup calls throughout that module) — memory-usage reasons, see
   [[project_ocr_perf_omp_thread_starvation]].

So building a training set means, per page you want to use:

1. Re-render the source page image from its original PDF (same DPI settings as the original run —
   check `converter_events.jsonl`/job metadata for what was used).
2. Re-run detection (`TextDetection.predict()`) on that re-rendered image to get boxes back (detection
   is deterministic given the same model/config, so this reproduces the same crop regions the
   original OCR pass used — no need to persist boxes going forward *unless* the DPI/preprocessing
   pipeline has changed since the original run).
3. Align the *original per-box OCR text* (before correction) against the *final corrected page text*
   to figure out which correction (if any) applies to which box. This project already has the tooling
   for this kind of alignment — `ocr_text_diff.compute_word_diff_spans()` and the
   `difflib.SequenceMatcher`-based merge logic in `paddle_v5_processor._merge_ocr_texts()` are both
   reusable starting points, though line-level (not word-level) alignment is what's needed here.
4. Crop the box region from the re-rendered image, save as a training image, pair with the
   corrected line text in the label file.

None of this is currently automated. It's a real tooling task (a new script, roughly comparable in
scope to `scripts/calibrate_stroke_correction.py`), not a data export that already exists.

## Volume — likely the actual blocker

Per [[project_telugu_dictionary_spell_correction]] and the TODO doc, real human-*reviewed* pages (not
just auto-corrected ones) have been rare so far — the correction dashboard's manual-review gate exists,
but no volume count of actually-completed reviews is tracked yet. **Before scoping this further,
check how many pages have actually been through `/api/correction/rebuild/<job_id>` with a human
SAVE**, not just how many got dictionary/stroke auto-corrections. If that number is small (plausible,
given `docs/TELUGU_SPELL_CORRECTION_TODO.md` item 1 was already blocked on "need a ground-truth
transcript for even one page" as of 2026-07-08), a fine-tuning corpus large enough to move the needle
may not exist yet, and step 0 becomes "review more pages," not "build the export tooling."

## Training mechanics (once data exists)

- PaddleX ships a config for this exact model:
  `venv/lib/python3.12/site-packages/paddlex/configs/modules/text_recognition/te_PP-OCRv5_mobile_rec.yaml`
  — low-code fine-tuning via `paddlex --train` should work from this, starting from the pretrained
  checkpoint (not from scratch) with a low learning rate and few epochs to avoid catastrophic
  forgetting on the much larger public pretraining data the base model already knows.
- **Do a tiny pilot first** (even 50-100 synthetic or hand-picked pairs) purely to confirm the
  training command runs end-to-end on this WSL box before investing in the full export-tooling build
  — untested territory (fine-tuning has never been run in this project).
- Evaluate with `scripts/benchmark_quality.py` (already supports before/after CER/WER comparison per
  the TODO doc) against a held-out slice of human-reviewed pages, not a subjective read-through.

## Recommended order of operations

1. Count actual human-reviewed (dashboard-approved) pages to date — cheap, answers whether this is
   viable now or needs "collect more reviewed pages" as a prerequisite first.
2. If volume looks workable: tiny pilot (hand-build ~50-100 pairs manually) to de-risk the training
   pipeline itself before building automated export tooling.
3. If the pilot moves CER/WER in the right direction: build the automated export script (re-render →
   re-detect → align → crop) to scale up the corpus from ongoing correction-dashboard usage.
4. Re-run `scripts/mine_ocr_failure_patterns.py`-style analysis after fine-tuning to confirm the
   specific failure categories it was meant to target actually improved, not just aggregate CER/WER.
