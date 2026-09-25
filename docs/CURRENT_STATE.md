# IndicOCR Current State

Updated: 2026-09-26 (IndicPhotoOCR latency/quality fixes and the deskew-corruption bug from 2026-09-25, plus a 2026-09-26 fix for a sharpness/contrast metric that was wrong by orders of magnitude at real production resolution — see "Fixed (2026-09-26)" below. Server has been restarted (by the user, after `Toli Prema` finished cleanly); all of 2026-09-25's and 2026-09-26's fixes are live as of 00:19.)

## Project

This repository is a Flask-based Telugu and mixed-language PDF OCR application that converts scanned PDFs to EPUB/MOBI. The current production OCR path on WSL is PP-OCRv5 with Tesseract fallback.

## OCR Engines

### Tesseract

- Native WSL Tesseract is available.
- Telugu language data is installed, including `tel_best`.
- The project uses Telugu and English combinations such as `tel_best+eng`.
- Tesseract is fast, but it returned no text on the first benchmark image because that image was difficult for the selected invocation.

### PP-OCRv5

- Telugu recognition model: `te_PP-OCRv5_mobile_rec`.
- Detection model: `PP-OCRv5_server_det`.
- CPU inference works in WSL.
- The application has Telugu-specific detection settings, quality gates, batching, and automatic Tesseract fallback.
- PaddleX's OpenVINO/HPI backend needs the optional `ultra-infer` package, which is not on PyPI, so it does not load. Instead `src/openvino_runner.py` swaps the PaddleX predictor's runner for OpenVINO running the exported `inference.onnx` of each model (see "Speed work"). This is active whenever `PADDLE_USE_OPENVINO = True`.

### IndicPhotoOCR

- Installed locally from `Bhashini-IITJ/IndicPhotoOCR`.
- Runs on CPU with PyTorch.
- The shared environment uses `torch 2.6.0+cpu` and reports `cuda_available=False`.
- Supports detection, script identification, and recognition for multiple Indian languages.
- Telugu (or any Indic) books also contain English, so the engine must always handle native script plus English.
- Upstream `OCR.ocr()` always identifies scripts with the 12-class `auto` model and ignores `identifier_lang`. That is why the first run leaked Malayalam, Marathi, and other scripts.
- `src/indicphoto_ocr_processor.py` therefore runs its own pipeline: detect words, classify each crop with the 3-class `<language>/english/hindi` identifier (`hindienglishtelugu` for Telugu), then recognise each crop with the native PARSeq checkpoint or English PARSeq. The `hindi` class is routed to the native language.
- The Telugu checkpoint emits the digit zero (U+0C66) for the anusvara (U+0C02), for example `వు౦ది`. The adapter converts a zero that follows a Telugu letter or vowel sign back to the anusvara.

## Shared WSL Environment

The shared environment is intended to avoid duplicating large Python environments:

```text
/home/naveen/venvs/ocr-common
```

Use it with:

```bash
source ~/venvs/ocr-common/bin/activate
```

The setup script is:

```text
scripts/setup_shared_ocr_venv.sh
```

It:

1. Reads package inventories from the existing MyOCR and IndicPhotoOCR environments.
2. Installs inventories sequentially so conflicting exact pins do not fail resolution.
3. Skips the optional, non-PyPI `ultra-infer-python` wheel.
4. Installs PaddleOCR.
5. Installs IndicPhotoOCR without duplicating its dependencies.
6. Removes any CUDA Torch packages pulled by merged requirements.
7. Installs CPU-only Torch and torchvision last.
8. Writes a lock file to `~/venvs/ocr-common/requirements.lock.txt`.
9. Verifies Torch, PaddleOCR, IndicPhotoOCR, and Tesseract.

The shared environment is for WSL/Linux. It should not be used as a Windows Python environment.

## Language Models

IndicPhotoOCR recognition checkpoints were requested for:

- Assamese
- Bengali
- Gujarati
- Hindi
- Kannada
- Malayalam
- Marathi
- Odia
- Punjabi
- Tamil
- Telugu
- English through the PARSeq Torch Hub model

Telugu documents contain English words, so IndicPhotoOCR runs the native+English identifier (`--indicphoto-language telugu`) and Tesseract `tel_best+eng` stays as a cleanup or fallback path. Do not use the 12-class `auto` identification unless three or more scripts are really present.

## Benchmark (Telugu + English pipeline)

Run on 2026-09-21 with `--indicphoto-language telugu` on four Telugu book pages. IndicPhotoOCR used the native+English identifier and routed each word crop to Telugu or English recognition.

Runtime environment: WSL Ubuntu, CPU-only PyTorch, native Tesseract, PP-OCRv5 CPU inference (warm model cache).

| Image | Engine | Chars | Lines | Telugu | English (Latin) | Other script | Time (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| A night_in_karachi | Tesseract | 0 | 0 | 0 | 0 | 0 | 0.5 |
| | PP-OCRv5 | 704 | 27 | 528 | 30 | 0 | 13.0 |
| | IndicPhotoOCR | 745 | 19 | 586 | 52 | 0 | 24.9 |
| ApprovaSuodham | Tesseract | 1063 | 37 | 839 | 25 | 0 | 3.4 |
| | PP-OCRv5 | 1130 | 35 | 850 | 77 | 0 | 16.4 |
| | IndicPhotoOCR | 987 | 19 | 840 | 23 | 0 | 26.6 |
| Rudhranethrudu | Tesseract | 1244 | 25 | 911 | 11 | 0 | 3.4 |
| | PP-OCRv5 | 1329 | 32 | 1071 | 0 | 0 | 11.2 |
| | IndicPhotoOCR | 1276 | 27 | 1103 | 11 | 0 | 29.7 |
| మరణ మృదంగం | Tesseract | 2956 | 57 | 2346 | 27 | 0 | 6.5 |
| | PP-OCRv5 | 3064 | 60 | 2534 | 0 | 0 | 25.7 |
| | IndicPhotoOCR | 2957 | 43 | 2560 | 30 | 0 | 71.5 |

IndicPhotoOCR crops routed by the identifier (Telugu / English): 92/11, 116/8, 156/6, 354/13.

Files:

- Raw result: `ocr_comparison/image_engine_comparison.json`
- Human-readable report: `ocr_comparison/image_engine_comparison.html`
- Benchmark runner: `tests/diagnostics/compare_image_ocr.py` (`--only <file names>` selects images)
- HTML renderer: `tests/diagnostics/render_ocr_comparison_html.py`

## Interpretation

Still a smoke comparison, not an accuracy benchmark: there is no ground truth, so character counts cannot say which engine is right.

- The native+English identifier fixed the script contamination. All four pages show zero other-script characters, and English words (for example the printer and city names on the copyright page) come out as Latin text.
- IndicPhotoOCR is the slowest engine on every page, about 2 to 3 times PP-OCRv5.
- IndicPhotoOCR recognises words independently, so it drops punctuation (quotes, full stops, commas), which is a real problem for book text. PP-OCRv5 and Tesseract keep it.
- Its word-to-line grouping is weaker on multi-column or irregular layouts: it produced 43 lines on a page where PP-OCRv5 found 60 and Tesseract 57, and some words from neighbouring lines run together.
- It sometimes forces non-English crops (ornaments, decorations) into English, producing junk such as `on` or `armoer`.
- PP-OCRv5 remained the more complete page-level engine in these samples; Tesseract `tel_best+eng` is fast and decent on clean pages but returned nothing on the karachi cover page.

Working hypothesis: keep PP-OCRv5 as the primary engine and Tesseract as fallback. IndicPhotoOCR is a candidate second opinion for words or regions where PP-OCRv5 confidence is low, not a page-level replacement. This needs the ground-truth run below to confirm.

## Speed Work (2026-09-21)

Per-page timings on the dev machine (i5-13420H, 12 threads, CPU only, WSL). PP-OCRv5 time is the full `extract_text` path; IndicPhotoOCR is the standalone adapter.

| Page | PP-OCRv5 before | PP-OCRv5 now | IndicPhotoOCR `vit` | IndicPhotoOCR `hinted` |
|---|---:|---:|---:|---:|
| A night_in_karachi | 13.0 s | 1.7 s | 23 s | 6.3 s |
| ApprovaSuodham | 16.4 s | 2.3 s | 25 s | 9.5 s |
| Rudhranethrudu | 11.2 s | 1.8 s | 29 s | 7.5 s |
| మరణ మృదంగం | 25.7 s | 3.6 s | 66 s | 15.6 s |
| blurry | 14.7 s | 2.4 s | 28 s | 7.1 s |

### PP-OCRv5: OpenVINO runner (done, in the app)

- Profile of the old path on the busiest page: detection 10.9 s of 19.3 s; the full `extract_text` added another 8.6 s of gating and merging.
- The 84 MB server detector on Paddle's CPU runner takes about 10 s per page. The same detector as ONNX on OpenVINO takes 1.4 s (onnxruntime 2.3 s). Recognition also moved to OpenVINO.
- `src/openvino_runner.py` replaces `predictor.runner`, so PaddleX's own pre- and post-processing and the model weights are unchanged. `paddle_v5_processor.py` calls it after loading each engine when `PADDLE_USE_OPENVINO` is true. If the ONNX file or OpenVINO is missing, the engine stays on Paddle.
- The ONNX exports (`~/.paddlex/official_models/<model>/inference.onnx`) already exist from an earlier `paddle2onnx` run. They are not created automatically yet.
- Verification: the final text from the full pipeline is byte-identical before and after on all five pages, at 6 to 8 times the speed.
- Unexplained: in ad-hoc scripts that called `_paddle_extract` directly, the native Paddle runner scored a mean confidence of 0.64–0.77 against 0.88–0.96 on OpenVINO. The app path did not show this difference. Do not cite the confidence gain until it is understood.

### PP-OCRv5: options rejected or not yet tried

- `PP-OCRv5_mobile_det` is 17 times faster (0.6 s against 10 s) and gives similar box counts, but agreement with the other engines dropped on 3 of 5 pages (about 59% against 64% on average). Rejected while the server detector is only 1.4 s on OpenVINO.
- MKL-DNN (`enable_mkldnn=True`) still crashes with the PIR error described in `config_v5.py`.
- Recognition batch size: on the old Paddle runner batch size 1 was fastest (5.5 s) and larger batches were slower (14.5 s at 32), probably from padding to the widest crop. Not re-measured on OpenVINO. Sorting crops by width before batching is untested.

### IndicPhotoOCR: where the time goes and what helps

Profile on `blurry.png` (144 crops): detection 2.0 s, script identification 21.3 s, recognition 6.1 s.

- The ViT identifier is compute-bound at about 0.12 s per crop. OpenVINO conversion agreed on 144 of 144 labels but was not faster (17.7 s PyTorch, 18 to 26 s OpenVINO). Batch size 32 did not help.
- Dynamic int8 quantisation of its Linear layers: 21.9 s down to 15.5 s (about 30%), 142 of 144 labels unchanged. Available as `quantize_identifier=True`, not yet checked against page text.
- Gating the ViT on Telugu-recogniser confidence does not work: the Telugu model is at least 0.99 confident on many crops the ViT calls English, so a threshold catches only about 32% of them.
- What works: `identifier_mode="hinted"`. The ViT runs only on crops that overlap PP-OCRv5 lines containing Latin letters, and everything else is read as Telugu. This needs PP-OCRv5 to run first, which the fusion pipeline does anyway.
- Modes: `vit` identifies every crop, `hinted` identifies crops overlapping `english_boxes`, `none` never identifies (Telugu only).
- Risk of `hinted`: an English word that PP-OCRv5 misreads as Telugu will not be re-checked. Not measured yet.

## Fusion Pipeline (built 2026-09-21, unverified)

Code:

- `src/ocr_fusion.py`: line-level fusion.
- `src/indicphoto_ocr_processor.py`: now also has `extract_words()` (word text, box, confidence, script).
- `tests/diagnostics/fuse_ocr_engines.py`: runs all three engines and writes `ocr_comparison/fusion/fusion.json` and `fusion.html`.

Run:

```bash
source ~/venvs/ocr-common/bin/activate
python tests/diagnostics/fuse_ocr_engines.py --only "blurry.png" "మరణ మృదంగం.png"
# options: --identifier-mode vit|hinted|none   --quantize-identifier
```

How it works:

1. PP-OCRv5 gives the skeleton: line boxes, reading order, punctuation, and a confidence per line.
2. Each IndicPhotoOCR and Tesseract word is assigned to exactly one PP-OCRv5 line, by the nearest vertical centre among boxes that horizontally contain it. An earlier version matched every box containing the word centre, which mixed neighbouring lines because PP-OCRv5 boxes overlap (`unclip_ratio=2.0`). That bug is fixed.
3. Agreement is measured on Telugu character clusters (`regex` `\X`), ignoring spaces, punctuation and digits.
4. Rules: keep PP-OCRv5 when it is confident (0.85 or more) and confirmed by another engine at 0.80 or more; with three candidates keep the medoid (ties go to PP-OCRv5); with two candidates keep PP-OCRv5 unless it is unconfident and the other engine disagrees; if the best pairwise agreement is under 0.60, keep PP-OCRv5 and flag the line for review.
5. When a word-level engine wins, PP-OCRv5's trailing punctuation is re-attached.

First results (identifier mode `hinted`; total time per page includes all three engines):

| Page | Lines | PP-OCRv5 kept | IndicPhotoOCR won | Tesseract won | Flagged | Total time |
|---|---:|---:|---:|---:|---:|---:|
| A night_in_karachi | 27 | 24 | 3 | 0 | 3 | 9.4 s |
| ApprovaSuodham | 35 | 35 | 0 | 0 | 2 | 14.8 s |
| Rudhranethrudu | 32 | 30 | 2 | 0 | 0 | 11.3 s |
| మరణ మృదంగం | 60 | 59 | 1 | 0 | 0 | 25.9 s |
| blurry | 29 | 25 | 2 | 2 | 4 | 11.3 s |

These numbers count decisions, not accuracy. Whether the chosen lines are actually better is unknown until there is ground truth.

Review page: open `ocr_comparison/fusion/fusion.html`. It shows the three candidates per line, the chosen one in green, and disagreeing lines in red. The yellow cells are editable, and "Download corrections" saves `ground_truth_corrections.json`.

## CER/WER Scorer (built 2026-09-22; first real-ish numbers same day, still provisional)

`tests/diagnostics/score_ocr_accuracy.py` scores `paddle`, `indicphoto`, `tesseract`, and `fused` text per line against a ground-truth JSON in the exact shape `fusion.html`'s "Download corrections" produces (`{page: [line0, line1, ...]}`, one entry per `fusion.json` line). Reports, per engine: CER and WER (Levenshtein, over the same grapheme-cluster tokenizer `ocr_fusion.py` uses), Telugu character precision (CER restricted to Telugu-block clusters), English word accuracy (multiset match on ASCII words), and missing-line rate (hypothesis blank or CER ≥ 0.9).

```bash
python tests/diagnostics/score_ocr_accuracy.py ocr_comparison/fusion/fusion.json ground_truth_corrections.json
```

Verified against a small hand-built fixture first (not real Telugu ground truth, just a correctness check of the arithmetic): CER, WER, Telugu precision, English accuracy, and missing-line all came out matching a hand calculation.

**First run against something closer to real text**, same day: `ocr_comparison/poratam/draft_ground_truth.json`, a transcription of `poratam.png` (22 lines) done by reading the scan directly rather than typed by a human — explicitly a draft, not verified ground truth (see `draft_ground_truth_NOTES.md` in that folder for the specific words that are genuine guesses, not confident reads). Treat these numbers as a preview of what real ground truth will look like, not a result to cite:

| Engine | CER | WER | Telugu char precision |
|---|---:|---:|---:|
| PP-OCRv5 | 12% | 48% | 88% |
| IndicPhotoOCR | 13% | 57% | 87% |
| Tesseract | 22% | 57% | 79% |
| **Fused** | **9%** | 48% | **91%** |

Fused beat every individual engine on both CER and Telugu precision — the first quantitative (if provisional) evidence that fusion helps rather than just reshuffling errors. WER is high across the board and not very informative here: it's whitespace-tokenized, and word boundaries vary between engines for reasons unrelated to correctness (conjunct/compound spacing). Still waiting on a human-corrected version of this same file, and on step 1 below for the rest of the sampled pages.

## Review-Queue Signal (built 2026-09-22)

Motivation: fusion's own `needs_review` flag only fires when the three engines disagree. When they all misread a crop the same way, agreement is perfect and nothing gets flagged — a real, observed failure mode (see the `మ` structural examples below). `src/review_queue.py` adds a second, independent signal that does not depend on agreement: whether the *chosen* text is plausible Telugu, reusing the project's existing dictionary/grammar tools (`telugu_spell_checker.py`, `telugu_text_processor.py` — not reimplemented).

Two candidate signals were tried:

- **Structural grammar validity** (`grapheme_validity_score` — orphaned vowel sign, dangling virama: grammatically impossible in real Telugu regardless of dictionary coverage). Fixed threshold, no calibration needed. On the 5-page sample it caught 6 real corruptions that agreement had missed and produced zero false positives on manual read-through, e.g. `వందీ` for `వుంది`, `ఇంా` for `ఇంకా`, `ఇణంలోనైనా` for (likely) `ఏ దేశంలోనైనా`. **Kept, on by default.**
- **Dictionary out-of-vocabulary rate.** At an uncalibrated 0.40 threshold this flagged 77% of all lines — useless. Calibrating the threshold against the book's own `confident_and_confirmed` (agreement-passed) lines pushed it to 1.00, i.e. never fires, because those lines are only *agreed*, not verified — the same undetected-shared-error problem the signal exists to catch also pollutes its own calibration set. **Off by default** (`OOV_THRESHOLD = 1.01`) until real human-corrected ground truth exists to calibrate against non-circularly; the mechanism (`review_queue.distortion_score`) is in place for that.

`tests/diagnostics/build_review_queue.py` turns a `fuse_ocr_engines.py` report into a flat, page-ordered list of only the flagged lines (`ocr_comparison/fusion/review_queue.html`), instead of the full per-page grid in `fusion.html`. For structurally-flagged lines it also pre-fills the editable cell with whichever candidate is most grammatically valid (`review_queue.best_candidate`), so review is usually confirm-or-edit instead of retype-from-scratch. Spot-checked on the 7 lines it fired on: 5 clearly better, 1 modestly better, **1 worse** — a candidate with fluent-looking wrong words scored a lower structural-invalid ratio than the correct-but-garbled original, since the check only looks at grapheme grammar, not whether the words are the right ones. It is a suggestion shown next to every candidate, never auto-applied.

```bash
python tests/diagnostics/build_review_queue.py ocr_comparison/fusion/fusion.json
```

**Review-rate result on the 5-page sample (agreement + structural, no OOV):**

| Page | Lines | Flagged | Rate |
|---|---:|---:|---:|
| A night_in_karachi | 27 | 5 | 19% |
| ApprovaSuodham | 35 | 3 | 9% |
| Rudhranethrudu | 32 | 0 | 0% |
| మరణ మృదంగం | 60 | 1 | 2% |
| blurry | 29 | 5 | 17% |
| **Total** | **183** | **14** | **8%** |

Against agreement alone (9/183 = 5%, but 3/5 pages = 60% touched), adding the structural signal moved 6 more lines into the queue while keeping the reviewer's actual workload to specific lines, not whole pages — this is the concrete answer to "review 70-80% of a book" → **8% of lines, on this sample**. Caveat: this counts flagged lines, not verified errors; it is unknown how many *actual* errors on these pages were missed by both signals, since there is still no ground truth. Also unverified: whether 8% generalizes past this one book/5-page sample.

## Missing-Line Detection (built 2026-09-22, unproven)

`ocr_fusion.missing_lines` looks for words IndicPhotoOCR and Tesseract *both* saw (at the same vertical position) that landed in no PP-OCRv5 box at all — i.e. PP-OCRv5's detector may have skipped an entire line. Requires double corroboration on purpose, to avoid manufacturing a phantom line from one engine's stray noise. On the 5-page sample it never fired (0 missing lines across all pages) — either PP-OCRv5 genuinely didn't miss any full line on these particular pages, or the double-corroboration bar is stricter than needed. Not validated either way yet.

## `identifier_mode="hinted"` — real bug found and characterized (2026-09-22)

Measured hinted mode's recall against full `vit` mode (which checks every crop) on the same 5 pages: **hinted caught 0 of 42 crops that vit labelled English.** Root cause, not a coordinate bug (checked: both engines' detections are in the same pixel space): `latin_regions()` only hints a region when *PP-OCRv5's own text already contains ASCII letters* — so it can never recover a region PP-OCRv5 already misread as Telugu-shaped garbage, which is precisely the case where the hint is needed. PP-OCRv5's per-box confidence doesn't help either — it stayed 0.86–0.99 on the misread lines, no lower than on correct ones (same problem as yesterday's rejected Telugu-recognizer-confidence gate).

However: most of what full `vit` mode calls "English" on Telugu-only pages (e.g. `ApprovaSuodham.png`, which has no real English text) turned out to be **vit's own false positives** — noisy/blurry Telugu crops misclassified as English, then read with the wrong (English) recognizer, producing garbage like `111111111111111111111` and `artifica`. So `vit` mode is not a clean recall reference either; a chunk of the "42 missed" crops were noise, not real missed English.

Net effect on the pipeline: probably small, since IndicPhotoOCR is a secondary vote in fusion, not the primary reader — but unverified. `hinted` stays the default for speed. Do not read the earlier "OpenVINO speed-up" section's IndicPhotoOCR timings as implying full English coverage.

## Third Sample: poratam.png (2026-09-22, non-blurry)

Every page tried so far had some degradation (mixed quality, blurry, low-light). `images/poratam.png` is clean, well-lit, single column, not blurry — a control case to check the pipeline isn't tuned specifically to hard pages.

```bash
python tests/diagnostics/fuse_ocr_engines.py --only poratam.png --adaptive --output-dir ocr_comparison/poratam
python tests/diagnostics/build_review_queue.py ocr_comparison/poratam/fusion.json --output-dir ocr_comparison/poratam
```

**Router still triggered** (didn't skip IndicPhotoOCR) even though the page looks clean by eye: avg PP-OCRv5 confidence 0.924 (just under the 0.93 bar) and 9.1% structurally-invalid lines. A useful sign the router is reading real signal, not just "does this look blurry."

**Result: 2/22 lines flagged (9%)** — inside the range seen on every sample so far (2-19%).

**Found and fixed live:** `review_queue.best_candidate`'s suggestion for the structurally-flagged line picked Tesseract's candidate purely because it scored the lowest grapheme-invalid ratio -- but that candidate itself contained a stray Latin fragment ("od", from `స్ట్రగుల్‌` misread) the structural check has no opinion on. `best_candidate` now excludes any candidate with its own `uncorroborated_ascii` hit whenever a clean alternative exists. Verified: the suggestion switched to IndicPhotoOCR's candidate, which has no such fragment (it still has its own, different recognition error, but not this specific double-uncaught-defect problem).

**Eye-checked against the source scan, not just the flagged lines**, same caveat as every prior pilot: line 2's chosen text has `బలవంతులు` (correct) misread as `బలపంతులు` (వ→ప) and `దుర్బల` misread as `దురృల` -- both individually valid Telugu graphemes, so neither the structural check nor the agreement check (0.89, well above the 0.60 flag threshold) catches a plausible-looking single-letter substitution. Still no signal in this project catches that failure shape. This is the same gap noted in the book pilot, now confirmed on a clean page too -- it is not specific to hard pages.

## Book Pilot (2026-09-22): 12 real pages from a 258-page book

Not another standalone test image — `data/uploads/20260910_205937_10acb64a_..._split.pdf` is a real book already run through the production Tesseract+Gemini pipeline (`data/temp/Ardha_Ratri_Pilupu_10acb64a/`, 258 pages). That folder kept only the extracted text, not the page images (except the cover), so pages were re-rendered from the source PDF at 400 DPI instead. 12 pages spread across the whole book (every 20th, pages 10-230) were run through the full fusion + review-queue pipeline.

```bash
python tests/diagnostics/fuse_ocr_engines.py --image-dir ocr_comparison/book_sample --only page_010.png ... --output-dir ocr_comparison/book_sample_fusion
python tests/diagnostics/build_review_queue.py ocr_comparison/book_sample_fusion/fusion.json --output-dir ocr_comparison/book_sample_fusion
```

**Result: 9 of 363 lines flagged — 2%.** Lower than the 5-page sample's 8%, consistent with this book being cleaner single-column dialogue-heavy prose (the 5-page sample mixed a cover page and a known-blurry page). Per page, 0-10%, all pages well inside the 10-20% target.

**New signal added from a real miss found by eye-checking `page_210.png` against the source scan:** `review_queue.uncorroborated_ascii` flags a short ASCII run (≤6 letters) in the chosen text that appears in *none* of the other candidates. Found live: Tesseract's candidate for one line read `... అనుమతి CET. ఆ కవరు ...` — "CET." is not in PP-OCRv5's or IndicPhotoOCR's candidate for the same line at all, clearly a misread fragment, not real content — and neither agreement (0.88, above the review threshold) nor the structural-grammar check caught it, since "CET" is valid ASCII, not invalid Telugu grammar. This is a single found-and-fixed example, not a tuned threshold — treat `UNCORROBORATED_ASCII_MAX_LEN = 6` as provisional.

**A second gap found the same way, not yet fixed:** the same eye-check found PP-OCRv5's line `నిర్ణయిం చుకున్న` for the source's `నిర్ణయించుకున్న` — a stray space splitting one word into two fluent-looking fragments. Neither fragment is structurally invalid or contains ASCII, so no current signal catches it. This is real evidence that **the flagged-line rate (2-8%) understates the true error rate** — these are two errors found by spot-checking a small sample of unflagged lines, not by the review queue itself.

**Reading on "are we ready to run a whole book automatically":** ready to *pilot* with review kept in the loop — the flagged-line count is small enough to actually review (9 lines across 12 pages), and the extra checks earn their keep by widening what the flagged set covers. Not ready to run *unattended* — every mechanism here (agreement, structural validity, ASCII contamination) is a plausibility check, not a correctness check, and the two real errors found today by simply looking at one page were both invisible to all of them. The one thing that would change this assessment: actual corrections from a human against `review_queue.html`, which is still the missing piece — `score_ocr_accuracy.py` has nothing to score against yet.

## Engine Failure/Strength Tabulation (2026-09-22)

Computed from every candidate slot across the 17-page sample above (546 line-slots: 5 standalone pages + 12 real book pages), not just the chosen text — this counts what each engine actually produced, win or lose.

| Engine | Present | Empty | Won the line | Structurally invalid | Stray uncorroborated Latin | Punctuation kept |
|---|---:|---:|---:|---:|---:|---:|
| PP-OCRv5 | 546/546 (100%) | 1 | 459 (84%) | 5.3% | 2.0%¹ | 4.7 per 100 chars |
| IndicPhotoOCR | 532/546 (97%) | 0 | 54 (10%) | 0.8% | 0.2% | **0.0%** |
| Tesseract | 496/546 (91%) | 0 | 33 (6%) | 0.0% | **11.1%** | 4.0 per 100 chars |

¹ One of PP-OCRv5's flagged "stray ASCII" cases was a false positive on the tabulator's part, not an engine failure: `ApprovaSuodham.png`'s source image is a screenshot that accidentally captured a browser AI-assistant banner ("This appears to be a long document... Generative AI User Guidelines") at the very top. PP-OCRv5 read it correctly — that's real, if unwanted, content in the test image, not a misread. A reminder that "uncorroborated Latin" is a heuristic, not ground truth.

**Three distinct, well-separated failure signatures**, not just "some are better than others":

- **PP-OCRv5**: most complete (won 84% of lines, present on all but one), keeps punctuation, but is the only engine with a meaningful structurally-invalid-Telugu rate (5.3%) — its dominant failure mode is producing garbled-but-present Telugu (orphaned vowel signs, dangling viramas), not dropping content.
- **IndicPhotoOCR**: cleanest Telugu when it has an answer (lowest structural-invalid rate, lowest stray-Latin rate) but **never preserves punctuation** — 0.0%, a complete, universal gap, not an occasional one — and is absent on 3% of lines (word-to-box assignment gaps, not recognition failures).
- **Tesseract**: highest missing rate (9% of lines produced nothing) and by far the highest stray-Latin-contamination rate (11.1%, vs ~2% and ~0.2% for the other two) — its dominant, distinctive failure mode is inserting spurious English/Latin fragments into Telugu text, not garbling Telugu grammar (0.0% structural-invalid) or dropping content when it does produce something.

## Page-Quality Router (built and live-tested 2026-09-22)

Motivation: IndicPhotoOCR is 3-10x slower than PP-OCRv5 (Speed Work, above) and its value is concentrated on harder pages — running it on every page of a book is the safe default but not the cheapest one. `src/engine_router.py` decides, per page, whether to run it at all, from PP-OCRv5 + Tesseract output alone (both cheap/fast, already run first).

Trigger (any one): PP-OCRv5's own average line confidence on the page < 0.93; Tesseract produced text for less than 95% of PP-OCRv5's lines (a strong independent "this page is hard" signal, cheaper than running IndicPhotoOCR to find out); more than 5% of PP-OCRv5's own chosen lines are structurally invalid Telugu.

Thresholds were read by eye off the correlation in the 17-page data (lower PP-OCRv5 confidence tracked strongly with how often IndicPhotoOCR ended up winning a line) — not a tuned model, and unverified on a different book.

```bash
python tests/diagnostics/fuse_ocr_engines.py --adaptive --only ... --output-dir <dir>
```

**Live-run result (not just retrospective simulation — actually re-ran with IndicPhotoOCR conditionally skipped):**

| Sample | Pages | IndicPhotoOCR skipped | Flagged lines, baseline | Flagged lines, adaptive |
|---|---:|---:|---:|---:|
| 12-page real book | 12 | 4 (33%) | 9/363 (2%) | **9/363 (2%) — identical** |
| 5-page mixed sample | 5 | 1 (20%) | 15/183 (8%) | **22/183 (12%) — worse** |

**The book-sample result is a genuine win**: skipping a third of the slow passes cost nothing in review burden, because `review_queue.LOW_CONFIDENCE_SOLO_THRESHOLD` (added the same day — see below) caught the one case that would otherwise have gone through silently.

**The 5-page result is a real, mechanistically-understood cost, not noise.** Traced it: on `మరణ మృదంగం.png` (the one page skipped in that sample), 3 lines newly flagged as `engine_disagreement` that were clean in the baseline. In each case Tesseract's candidate for that specific line was outright garbage (`"ది."`, `"గాగ"`, `"="`) while PP-OCRv5's own text was fine — and in the baseline, IndicPhotoOCR's candidate *agreed with PP-OCRv5*, which raised `ocr_fusion`'s `max()`-based agreement score enough to pass. Remove IndicPhotoOCR and the only remaining pair is PP-OCRv5 vs garbage-Tesseract, which fails the agreement threshold and gets flagged — a false alarm on an already-correct line. **IndicPhotoOCR's value here wasn't supplying a better candidate; it was corroborating PP-OCRv5 against a bad Tesseract read.** The router's cheap signals (PP-OCRv5 confidence, Tesseract coverage) don't see this, because they don't look at *per-line* Tesseract quality, only page averages.

Implication: `ocr_fusion.fuse_page`'s use of `max()` over pairwise agreement (any one corroborating candidate is enough to suppress a flag) is doing real, useful work that a 2-engine fallback loses. Fixing this properly (e.g. weighting agreement by how many engines agree, not just the best pair) is unstarted — noted as a follow-up, not attempted this session.

## Low-Confidence-Solo Safety Net (built 2026-09-22)

`ocr_fusion`'s `needs_review` flag requires ≥2 candidates to disagree — a line with only one candidate (IndicPhotoOCR skipped by the router, or Tesseract found nothing there) gets reason `only_engine` and was never flagged by agreement, no matter how unconfident PP-OCRv5 itself was. Found live during the book pilot: `page_130.png` line 29, PP-OCRv5 read `జాూరగత్ల!` (confidence 0.744, structurally valid so the grammar check missed it too, correct is likely `జాగ్రత్తగ`) — would have gone through with zero review signal at all had IndicPhotoOCR been skipped there (which the router does). `review_queue.flag_line` now also flags any `only_engine` line with confidence below 0.80 (`LOW_CONFIDENCE_SOLO_THRESHOLD`, deliberately stricter than `ocr_fusion`'s own 0.85 `CONFIDENT` bar — an uncorroborated reading should need to look *more* certain than a corroborated one). Confirmed live: this is exactly what closed the gap on the 12-page book's identical before/after flag rate.

## Configuration-Driven OCR Engine Selection (built 2026-09-22)

The fusion pipeline existed only as standalone diagnostics until now. Wired it into the real app the same way every other engine is — the project already had exactly the right seam for this (`ocr_factory.py` dispatches by an `engine` string, `adaptive_ocr_factory.py` gates each one on a config flag, `config.OCR_ENGINE` force-overrides the router) — so this is a few small, additive changes, not a new system:

- `src/fusion_ocr_processor.py`: new `FusionOCRProcessor`, implementing the exact same `extract_with_fallback(image, preprocess, psm, page_label) -> {'text','engine','reason','confidence','boxes'}` contract as `PaddleV5Processor`, wrapping `ocr_fusion` + `engine_router` + `indicphoto_ocr_processor` internally.
- `ocr_factory.py`: `_create_fusion()`, gated on `config.ENABLE_FUSION_OCR` (default `False`), falling back to plain `PaddleV5Processor` when off or on any failure — same pattern as `_create_paddle`.
- `adaptive_ocr_factory.py`: deliberately has **no** enable/disable gate for `'fusion'` (unlike paddle/gemini/google_vision) — the generic fallback there drops to Tesseract, which would be a much bigger regression than just using plain PP-OCRv5; `OCRFactory._create_fusion` already does the right fallback internally.
- `pdf_to_epub_converter_optimized_v2.py`: one-line change, `_ocr_single_image` now routes `'fusion'` through the same branch as `'paddle'`.
- `config_v5.py`: `ENABLE_FUSION_OCR = False`, `FUSION_ADAPTIVE_ROUTER = True`, `FUSION_IDENTIFIER_MODE = 'hinted'`. To activate: set `ENABLE_FUSION_OCR = True` **and** `OCR_ENGINE = 'fusion'` (the latter forces every page to this path — there's no per-page routing tier for it yet, unlike the complexity-based tiers that pick between paddle/gemini/vision).

**Smoke-tested through the real factory chain** (`OCRFactory.create_processor('fusion', ...)`, and `AdaptiveOCRFactory.get_processor_for_page()` with `OCR_ENGINE='fusion'`), not just imported: confirmed the off-by-default fallback returns a plain `PaddleV5Processor`, and the on path returns a working `FusionOCRProcessor` that produces fused text end-to-end on `poratam.png`.

**Enabled in the running app 2026-09-22** (`ENABLE_FUSION_OCR = True`, `OCR_ENGINE = 'fusion'` in `config_v5.py`) and the Flask app restarted to pick it up — every page now routes through fusion. Still **not yet run through an actual PDF→EPUB conversion**, only the direct factory smoke test above. The `preprocess=True` discrepancy right below is still unresolved and applies to this live app.

Cosmetic trap, not a bug: the startup log prints `"OCR Engine: TESSERACT (primary)"` regardless of any config — `config.py` line 426 is a literal hardcoded string (`print(f"  OCR Engine: TESSERACT (primary)")`, no variable involved), executed as an import-time side effect. It has never reflected the real engine, in any run today. Don't use it to check what's active — check `AdaptiveOCRFactory`'s own log line or, better, what engine a converted page actually reports.

**`scripts/start.sh` (what `start4WWsl.bat` runs) fixed the same day, for a real gap found by tracing it**: it created its own separate `./venv` and installed only `requirements.txt`, which has `paddleocr`/`paddlepaddle`/`openvino`/`symspellpy` but not `torch`/`transformers`/IndicPhotoOCR itself (those are only in `requirements-indicphoto.txt`). Launched that way, `FusionOCRProcessor` would have silently degraded to paddle+tesseract only — `IndicPhotoOCRProcessor.__init__`'s `ImportError` is caught, so nothing crashes, it just quietly loses the one thing fusion mode exists for. Fixed: `start.sh` now prefers the already-populated shared venv (`~/venvs/ocr-common`, from `scripts/setup_shared_ocr_venv.sh`) when it exists, and skips the `pip install -r requirements.txt` step entirely in that case (that shared venv is managed by its own setup script, which deliberately installs CPU-only torch *last* to override anything CUDA pulled in transitively — a generic `pip install -r requirements.txt` on top could silently break that pin). Falls back to the old separate-`./venv` behavior — PP-OCRv5+Tesseract, no IndicPhotoOCR — when the shared venv isn't set up. Syntax-checked (`bash -n`) and the detection branch confirmed to trigger; **not yet run end-to-end** (the dev Flask instance already had port 5001, so running the full script would have conflicted with it).

**Found by the smoke test, worth flagging clearly:** the real call site always passes `preprocess=True` (`_ocr_single_image`: `processor.extract_with_fallback(image, preprocess=True, ...)`), which runs `PaddleV5Processor._preprocess` (contrast/sharpness enhancement) before OCR. Every diagnostic run today (`fuse_ocr_engines.py`, all 18 sampled pages, everything in the "Engine Failure/Strength Tabulation" and "Book Pilot" sections above) used `preprocess=False`. On `poratam.png` the preprocessed read was visibly different from — not obviously better or worse than, just different from — the unpreprocessed one tested all day (e.g. `బలవంతులు` misread as `దలవంతలు` with preprocessing vs `బలపంతులు` without). **None of today's flag-rate or CER numbers are guaranteed to transfer to how this behaves in the real, preprocessed call path.** This needs its own pass before the fusion engine is trusted in production, independent of the ground-truth work already queued.

### Real-conversion latency bug found and fixed (2026-09-22, unverified after the fix)

Ran a real 76-page book through the live app with fusion enabled. Per-page time went from the 10-25s/page seen in every single-process diagnostic today to **67-208s/page**, roughly stabilizing there rather than climbing further (pages 7-12: 67, 111, 130, 150, 192, 209, 174, 150, 165, 170s) — 12 of 76 pages completed in ~5.3 minutes wall-clock before the run was stopped.

Root cause, traced from the log rather than guessed: `config_v5.STAGE2_WORKERS = 2` lets 2 pages run their OCR concurrently (an existing, documented throttle — see its comment in `config_v5.py`). `paddle_v5_processor.py` already serializes all PaddleX calls behind a module-level `_engine_lock` for exactly this reason ("PaddleX models are not thread-safe for concurrent inference"). `indicphoto_ocr_processor.py` had no equivalent — two threads calling its PyTorch models concurrently each spin up their own OMP/MKL thread pool, oversubscribing the 12 physical cores instead of getting 2x throughput. Since `FusionOCRProcessor` is cached as one shared instance per `AdaptiveOCRFactory`, every concurrent page conversion hits the same `IndicPhotoOCRProcessor` object.

Fix: `indicphoto_ocr_processor.py` now has its own `_INDIC_LOCK`, serializing `extract_words()` (detector, identifier, recogniser — the whole model-touching section) the same way Paddle's is serialized. Trades "no parallelism from IndicPhotoOCR across pages" for "no CPU thrash" — the right trade since it's already the CPU-bound bottleneck engine; two concurrent passes competing for the same cores couldn't have gone faster anyway.

**Status: verified against a real conversion, with a more precise (and more interesting) diagnosis than the fix alone.** A second live 76-page run (job `86c7632a`, this time reading the real `converter.log` file instead of redirected stdout — see below) showed the lock fix genuinely working: actual fusion throughput (`Fusion ✅` log-line cadence) settled at **35-41s/page**, close to the single-process diagnostic baseline. But the *reported* `[Page N] Completed in X.Xs` number kept climbing to a 170-200s plateau anyway.

Root cause of *that* gap, also traced from the code, not guessed: `page_start = time.time()` (line ~1702 of `pdf_to_epub_converter_optimized_v2.py`) starts before Stage 1 (page analysis, running at the full `MAX_WORKERS=6` width) and before the page even queues for `self._stage2_semaphore` (limit 2). Stage 1 produces OCR-ready pages faster than the now-correctly-serialized Paddle+IndicPhotoOCR stage can drain them, so a backlog builds and each page's reported time increasingly reflects **queue wait**, not compute. `converter.log` (via `logging_config.py`'s `RotatingFileHandler`, at `config.LOG_FILE` = project root `converter.log`) is the authoritative source for this — redirected-stdout logs from an ad-hoc launch miss whatever a separately-launched instance (e.g. via `start4WWsl.bat` in a different terminal) is doing.

**Decision, given the latency is still real even with the lock fix working correctly:** IndicPhotoOCR's own script identifier is ~70% of its runtime, and it's 10-20x slower than plain PP-OCRv5 for an accuracy benefit that is still unverified beyond one draft, unconfirmed-by-a-human ground-truth page (`poratam.png`, 12%→9% CER, fused vs. plain PP-OCRv5). Not worth that cost in the live conversion path yet. **Reverted `config_v5.OCR_ENGINE` back to `'hybrid'`** (plain PP-OCRv5 + Tesseract, no fusion, the pre-session-start baseline) — `ENABLE_FUSION_OCR` stays `True` so the machinery remains available, just not invoked by the router. IndicPhotoOCR remains available for the offline `build_review_queue.py` workflow, where its cost is naturally limited to the small set of already-flagged lines. Requires an app restart to take effect (config is read once at process start); not yet restarted as of this note.

Two real paths back to using it live, neither built yet: (a) real ground truth showing it's worth the cost, or (b) restructure `FusionOCRProcessor`/`IndicPhotoOCRProcessor` to run only on the crops corresponding to PP-OCRv5's already-flagged lines, not the whole page on every invocation — plausibly a 5-10x cut to its per-page cost since typically only 2-19% of a page's lines get flagged.

## Engine Performance Log (built 2026-09-22)

For periodic review of which engine fits which kind of page, and to catch drift over time rather than re-deriving conclusions from scratch each session — this is a persistent, growing log, not another one-off analysis.

- `src/engine_performance_log.py`: `record_page()` appends one JSON line per page — brightness/sharpness/contrast (same sharpness/contrast numbers as `PaddleV5Processor._assess_clarity` and `engine_router.py`, so this stays comparable to the existing clarity gate and router thresholds instead of inventing a fourth metric), per-engine timing, per-engine win/presence counts, flagged-line count, and the router's decision — to `ocr_comparison/engine_performance_log.jsonl`. Wired into both `FusionOCRProcessor` (`source: "production"`, gated on `config.FUSION_LOG_PERFORMANCE`, default on) and `fuse_ocr_engines.py` (`source: "diagnostic"`), so it grows automatically from both real conversions and future diagnostic runs without extra effort.
- `tests/diagnostics/backfill_performance_log.py`: one-off, imports already-computed `fusion.json` results into the log without re-running OCR (reuses the candidates/timings already on disk, only recomputes quality metrics from the source image). Used once, to backfill everything sampled before this logging existed.
- `tests/diagnostics/report_engine_performance.py`: the actual periodic report — buckets logged pages by brightness and sharpness (fixed bands, not quantiles, so "the dark bucket" means the same thing across re-runs as the log grows) and shows, per bucket, average PP-OCRv5 confidence, flag rate, how often the router skipped IndicPhotoOCR, and average per-engine time; plus overall win rates.

**First run, backfilled from all 18 pages sampled today:**

```
=== By sharpness ===
bucket      pages  avg conf  flag rate  indic skip  paddle t   tess t  indic t
blurry          1      0.88        11%          0%      1.92     0.63     9.62
normal          5      0.94         1%         40%      2.18     2.36     6.39
sharp          12      0.89         2%         25%      2.27     2.57     9.96

engine        lines seen       won  win rate
paddle               568       482       85%
indicphoto           374        52       14%
tesseract            518        34        7%
```

Honest reading of this first run, not a conclusion: 18 pages from 2 sources (one book's spread + a handful of standalone images) is not enough to trust the bucket boundaries yet — the brightness bucketing came back almost useless (17 of 18 pages landed in "bright", since old book-paper scans cluster there; the bands need real variety, probably from scans across several different books/scanners, before brightness says anything). Sharpness fared better (a real 1/5/12 spread) but still thin. The point of building this now is that it starts accumulating from today's first production and diagnostic runs onward — it should mean something after a few dozen more pages, not yet.

## Output Quality on a Real, Harder Book (2026-09-22, session-ending finding)

While the 76-page `రాయల నీతి కథలు` ("Rayala Neeti Kathalu") conversion ran (fusion engine, before the revert below), read the actual extracted text directly from `data/temp/RayalaNeethiKathalu_912e8354/page_*_text.json` — not just the front-matter/title page (genuinely hard content, expected to be rough) but several mid-book body-text pages too. Page 20 body text, verbatim:

```
'తా న్నసేను' నేరగా బృందావనమునకు వచ్చినాఁడు.
పలికోంజమునం విక
సించిన [పతి కుస మమునందును రాధా దేవిదర్ననము నా కాం
సం చెను. ఇంతలో 'బృంద'లో వసంతము వచ్చినది. అన్ని
క డలను వసంత ము వచ్చును...
```

Readable, coherent classical Telugu prose, not gibberish — but visibly degraded throughout: `[పతి` for `ప్రతి` (the `్ర` conjunct misread as a bracket, the same failure class already documented elsewhere in `config_v5.py`'s comments), `వికసించిన` split across a line break with a stray space, `వసంత ము` for `వసంతము`. This is consistent with, not new evidence beyond, the ~9-12% CER already measured on `poratam.png` (paddle 12%, fused 9%) — this book is just older/more archaic (heavy conjuncts, classical prose register) and likely nearer the harder end of what's been tested, so the same error rate is more visually obvious and more damaging to readability. The per-page log entries seen earlier (`oov_ratio` 0.61-0.93 on several pages) are consistent with this but not independently confirmed as error rate specifically — archaic/classical vocabulary genuinely not being in a modern dictionary is a real confound, not purely an OCR-error signal.

**Important clarification for whoever resumes this:** the engine revert below (fusion → hybrid) fixes latency, not quality. On the one page actually scored today, fusion had a small quality edge over plain PP-OCRv5 (9% vs 12% CER) — reverting trades that small, unconfirmed edge for 10-20x speed. Quality and latency are two separate open problems with two different fixes; do not assume solving one solved the other.

## Known Limitations

- The fusion decisions, review-queue flags, and `hinted` mode have not been scored against real ground truth; only five pages of one book have been run.
- The dictionary/OOV review signal is disabled (see above) until it can be calibrated against verified corrections instead of the book's own agreed-but-unverified lines.
- On multi-column pages the fusion keeps PP-OCRv5 for almost every line, which is expected if PP-OCRv5 is right but could also hide errors PP-OCRv5 and Tesseract share.
- Missing-line detection has not fired on real data yet, so its double-corroboration threshold is unvalidated in either direction.
- `identifier_mode="hinted"` cannot recover English that PP-OCRv5 already misread as Telugu; `vit` mode has its own false-positive problem on Telugu-only pages. Neither is a clean signal for "is this region English."
- The ONNX exports needed by the OpenVINO runner are not created automatically.
- PP-OCRv5 currently runs standard CPU inference when HPI/`ultra-infer` is unavailable (mitigated by the OpenVINO runner above, but the runner itself needs the ONNX files to already exist).
- IndicPhotoOCR is primarily a scene-text pipeline and does no punctuation recovery or column-aware line ordering on its own (fusion recovers punctuation from PP-OCRv5).
- The anusvara fix is a heuristic for the Telugu checkpoint only; other Indic checkpoints may have their own systematic confusions that have not been checked.
- The identifier has only `native`, `english`, and `hindi` classes, so a third script on the same page (for example Sanskrit in Devanagari) would be routed to the native language or English.

## Session Pause (2026-09-22, end of day)

**Where things actually stand right now:**

- **Production config: `OCR_ENGINE = 'hybrid'`** (plain PP-OCRv5 + Tesseract, no fusion, no IndicPhotoOCR) — reverted from `'fusion'` this session because real-conversion latency (35-40s/page real throughput, inflated to 150-250s/page reported due to a separate Stage-1/Stage-2 queueing issue — see above) wasn't justified by the still-unverified accuracy gain. `ENABLE_FUSION_OCR` stays `True` so the machinery isn't deleted, just not invoked by default.
- **A conversion may still be running** as of this note — a 76-page book (`రాయల నీతి కథలు`), job `a7bf2e5e`, was at page ~50/76 (65%) in a process that started *before* the revert above, so it's still running on `fusion`. Left alone at the user's implicit direction (todays's stop/restart cycles caused enough confusion already — see the "two independently-managed server instances" mess a few sections up). If it's still going when you resume, `converter.log` (project root, `RotatingFileHandler`, not any redirected-stdout file) is the authoritative place to check progress, not terminal scrollback.
- **Quality is a second, separate open problem from latency** — see "Output Quality on a Real, Harder Book" above. Not solved by the engine revert.

**Resume here, roughly in priority order:**

1. **Ground truth is still the single biggest lever, more than ever now that a harder, real book has surfaced real quality concerns.** Correct the small flagged-line sets in `ocr_comparison/fusion/review_queue.html` and `ocr_comparison/book_sample_fusion/review_queue.html`, and ideally also transcribe a page or two of `RayalaNeethiKathalu` (harder/more archaic than anything scored so far) once its output is available, ground truth format is sparse (`{page: {line_index: text}}`) vs `fusion.html`'s dense array — `score_ocr_accuracy.py` doesn't read the sparse format yet.
2. Once real corrections exist, run `score_ocr_accuracy.py` and get real per-engine and fused CER/WER, specifically checking whether fusion's quality edge (9% vs 12% CER, one page) holds up on more/harder data — that's the number that would justify bringing IndicPhotoOCR back into the live path despite its cost.
3. Fix `ocr_fusion.fuse_page`'s `max()`-over-pairwise-agreement flagging (lets one corroborating candidate mask a real disagreement between the other two — see "Page-Quality Router").
4. If quality on `RayalaNeethiKathalu` specifically turns out to be a genre/difficulty problem (archaic conjunct-heavy classical prose) rather than a pipeline bug, that's a different fix (better models, or dictionary/post-processing tuned to that register) than anything built this session.
5. Decide on IndicPhotoOCR's future shape: real ground truth justifying its cost as-is, or restructure it to run only on already-flagged crops instead of the whole page (plausibly 5-10x cheaper) — neither started.
6. Retune `MAX_WORKERS`/`STAGE2_WORKERS` now that IndicPhotoOCR is properly locked, to reduce the Stage-1/Stage-2 backlog even in hybrid mode if similar symptoms show up there.
7. Explain why the native Paddle runner scored lower confidence than OpenVINO in the 2026-09-21 ad-hoc scripts (the app path showed no difference), and auto-export the ONNX files when missing.
8. Decide whether to fix `hinted` mode's English-recall gap or accept it as a known, small gap.

**Not committed.** Everything from this session and prior ones — `src/openvino_runner.py`, `src/ocr_fusion.py`, `src/review_queue.py`, `src/engine_router.py`, `src/indicphoto_ocr_processor.py`, `src/fusion_ocr_processor.py`, `src/engine_performance_log.py`, the `ocr_factory.py`/`adaptive_ocr_factory.py`/`pdf_to_epub_converter_optimized_v2.py`/`config_v5.py`/`paddle_v5_processor.py` edits, `scripts/start.sh`, the diagnostics scripts, the benchmark outputs, and this file — is uncommitted in the working tree. Given how much of that now touches the real production path (not just diagnostics), committing before further changes is worth doing early next session.

## Session 2026-09-25: latency fixes, a real quality bug found, one dead end

Focus going in: why is IndicPhotoOCR slow in the live app (user saw 150-250s/page), and separately, why does fused output still look wrong sometimes. Both got real answers. `OCR_ENGINE` was flipped back to `'fusion'` this session to test live (was `'hybrid'` at the end of 2026-09-22) — **still `'fusion'` as of this note**, machinery is active in production again.

### Fixed: IndicPhotoOCR quality (hallucination on low-confidence crops)

Sampled `IndicPhotoOCRProcessor.extract_words()`'s raw output on a real book page: of 482 recognized "words," one single string (`'అడుగ'`) was recognized **68 separate times** (14% of the whole page), every occurrence at confidence 0.22-0.36 — a recognizer collapse pattern on ambiguous/junk crops, not real text. Several other strings showed the identical pattern (dozens of repeats, same low confidence band). Plausible real recurring words sat higher (0.42-0.59) — confidence cleanly separates the two.

Fix: `min_confidence` (already existed as a constructor param, always defaulted to `0.0`, so it never filtered anything) is now wired to `config_v5.FUSION_INDIC_MIN_CONFIDENCE = 0.35`. Validated on the same page: 482 words → 207, every collapse-pattern string gone, plausible real recurring words kept. **Quality fix only — does not touch timing**, since filtering happens after recognition already ran.

### Fixed: IndicPhotoOCR latency (recognizing lines nobody was going to use)

Root cause, traced precisely: `ocr_fusion.fuse_page`'s first rule already picks PP-OCRv5 whenever it's confident AND any other candidate agrees — so on the ~84% of lines that rule resolves (see 2026-09-22's "Engine Failure/Strength Tabulation"), IndicPhotoOCR's answer was computed and then discarded unread. It was running on entire pages when only a minority of lines could ever change the outcome.

Fix: new `ocr_fusion.unresolved_lines(paddle_lines, tesseract_words)` — replicates fuse_page's own "already resolved" check using only PP-OCRv5+Tesseract (both already run before IndicPhotoOCR, cheap) — returns just the lines that check doesn't resolve. `IndicPhotoOCRProcessor.extract_words()` gained a `paddle_boxes` param (crops outside the given boxes are dropped before identification/recognition, using the existing `_center_in_any` helper). `fusion_ocr_processor.py` now calls `indic.extract_words(..., paddle_boxes=[l['bbox'] for l in unresolved_lines(lines, tess_words)])` instead of passing every line.

Validated on a real page: 31 lines total, only 3 needed a third opinion. Crops recognized dropped 207 → 32, IndicPhotoOCR time 46.5s → **16.4s**, and — checked explicitly — **fused output text was byte-identical** before and after. Trade-off, deliberately accepted: this also starves `ocr_fusion.missing_lines` (which needs IndicPhotoOCR to see lines PP-OCRv5 missed entirely) of data on resolved lines — acceptable since that feature has never fired on any sample to date (still true).

An earlier attempt at this same idea — filtering IndicPhotoOCR's crops to only those inside *any* PP-OCRv5 line (not specifically *unresolved* ones) — was tried first and barely worked (482→482 and 473→466 crops on two test pages): almost all of IndicPhotoOCR's crops already fall inside real PP-OCRv5 line boxes, so "is it in a line" doesn't discriminate. "Is it in a line PP-OCRv5+Tesseract already agree on" does. Worth remembering if this class of fix comes up again elsewhere.

### Investigated and rejected: accelerating IndicPhotoOCR's detector with ONNX/OpenVINO

The obvious next lever, by direct analogy to PaddleOCR's detector (10s → 1.4s via ONNX export + OpenVINO, done before this session) — tried the same on IndicPhotoOCR's TextBPN detector. Real difference found before attempting anything: PaddleOCR's detector is a clean CNN with all pre/post-processing outside the model; TextBPN's `forward()` bakes a global config value (`cfg.test_size`, set fresh per image size) into a fixed-size canvas, and its boundary-proposal step (`Evolution.get_boundary_proposal_eval`) does real NumPy/Python logic *inside* the forward pass — not a single cleanly-traceable graph.

Scoped the attempt down to just the exportable part (`self.fpn` + `self.seg_head`, the CNN backbone) and prototyped it standalone (`tests/diagnostics/prototype_textbpn_onnx.py`, not wired into production):
- Export succeeded, correctness verified (max diff ~0.00002 vs native PyTorch), including at a different input size than the export size (dynamic axes work).
- **Speedup: only 1.2x** (4.46s → 3.69s) — nowhere near PaddleOCR's 6-7x.
- **The backbone itself is only 4.46s of PyTorch time, but full `detect()` was measured at 11-43s elsewhere this session** — meaning the exportable part is a minority of the real cost. The majority lives in the boundary-proposal step, which is exactly the part that can't be cleanly exported.

**Dead end for latency.** Would need to rewrite the boundary-proposal/GCN refinement logic itself into pure tensor ops to matter — deep change to vendored model internals, not attempted.

Also ruled out (cheap check, took two minutes): thread oversubscription. `torch.get_num_threads()` already returns 6, correctly inheriting the same `OMP_THREAD_LIMIT=6` ocr_processor.py sets for PaddleOCR — not the cause of detect()'s 11-43s variance. That variance (same image, same code, repeated runs) remains unexplained.

### Fixed: Stage-2 queueing backlog reintroduced by fusion's cost profile

Live evidence: pages where the page-level router **skipped IndicPhotoOCR entirely** (`indic_ran=False`, pure PaddleOCR+Tesseract, a few seconds of real work) still reported 44-65s "Completed in" in the live app. Cause: `STAGE2_WORKERS=2` lets only 2 of `MAX_WORKERS=6` concurrently-dispatched pages actually enter the OCR call at once; the other 4 block on a semaphore, and the page timer (`page_start`, used for the reported time) starts before that wait. Both PaddleOCR (`_engine_lock`) and IndicPhotoOCR (`_INDIC_LOCK`, added 2026-09-22) already serialize their own model calls independently — `STAGE2_WORKERS=2` was mostly just adding extra queueing on top, not preventing the CPU-thrash it was originally set to prevent.

Fix: `STAGE2_WORKERS` raised 2 → 4 in `config_v5.py`. Not yet re-measured live after the raise (needs a server restart, which was pending other fixes landing first) — flagged as the first thing to verify next session.

### Fixed: a real, reproduced quality bug — auto-deskew was corrupting straight pages

This is the session's most important finding. A page (`No616` book, page 15) looked badly garbled in production despite every existing quality signal saying it was fine: PP-OCRv5 confidence 0.95, router skipped IndicPhotoOCR (nothing to disagree with it), line count passed the safeguard, `oov_ratio` (0.563) was actually *better* than several genuinely clean pages, and the structural-validity check didn't fire (the garbled text is grammatically *valid* Telugu graphemes, just the wrong ones — the exact "plausible substitution" gap already documented on 2026-09-22 as uncaught by anything in the pipeline).

Went to file it as a ground-truth calibration example of that gap. Before doing that: re-ran the identical page image (byte-verified against both uploaded copies, same MD5) through PaddleOCR in isolation — **clean output**, no garbling, PP-OCRv5 winning every line against Tesseract at 0.85-1.0 agreement. Ran it 4x concurrently — byte-identical across all 4 runs, ruling out a concurrency-correctness bug. Neither explained the discrepancy between my re-run and what production had stored.

Root cause, found by replicating the *rest* of the real pipeline one piece at a time: `pdf_to_epub_converter_optimized_v2.py`'s auto-deskew step (Hough-line tilt detection, gated on `config.ENABLE_DESKEW`, on by default) detected a spurious 0.53° "tilt" on this page — from character strokes, not the actual page edge; the page isn't tilted. The old threshold (`abs(median_angle) > 0.3`) rotated it anyway. Applying that exact rotation to the clean image **reproduced the same garbling pattern** seen in production. BICUBIC resampling from even a sub-1-degree "correction" blurs characters enough to cause the single-letter-substitution misreads that no other signal in this project catches.

Fix: threshold raised 0.3° → 1.5° (`DESKEW_MIN_ANGLE` in `pdf_to_epub_converter_optimized_v2.py`). Verified: re-running with the new threshold skips the rotation and restores the clean output. **Not yet live** — needs a server restart, same as the other fixes above.

Important caveat, raised directly by the user and confirmed by re-reading the corrected output: fixing the deskew bug does **not** make this page's OCR correct — it removes one specific, severe, reproducible source of corruption. The corrected text still has real, separate PP-OCRv5 errors at roughly the baseline rate already documented (e.g. `(గహించాము` for `గ్రహించాము` — the `్ర` conjunct misread as an open bracket, a known, separate, already-documented weakness, not caused by or fixed by the deskew change). Do not read this fix as "page 15 is now correct" — only as "page 15 is no longer catastrophically wrong for a reason that had nothing to do with the OCR engines."

`ocr_comparison/No616_page15/` holds the source image, the original (garbled) production output, and `NOTES.md` documents the full chase — including the corrected diagnosis superseding the original "confidently wrong PP-OCRv5" framing the page was first filed under.

### Fixed: two infrastructure bugs found while testing on a new, real book

- **PIL decompression-bomb guard**: hit `Image size (184350800 pixels) exceeds limit...` while splitting a real book (`రూమ్_బోయ్_కొప్పిశెట్టి.pdf`). Root cause: this PDF's page boxes are declared at absurd physical sizes (up to 49×41 "inches") — a PDF-authoring quirk (page box set ~1:1 with source pixel dimensions instead of through a real scan DPI), not an actual attack or a real giant page. Fixed by raising `PIL.Image.MAX_IMAGE_PIXELS = None` process-wide at the top of `src/app.py` (before anything else imports PIL) — appropriate since this app only ever processes the user's own scans, not untrusted third-party images.
- **Render-dimension cap**: raising the PIL guard alone would have let the *actual* OCR page-render step (`zoom = DPI/72` in `pdf_to_epub_converter_optimized_v2.py`, and the equivalent in `split_pdf_pages_cli.py`) blindly render this PDF's pages at 175-327 megapixels each, at 400 DPI, for all 146 pages — probably impractically slow/memory-heavy, not just a one-time split error. Fixed: both render call sites now cap the longer rendered side to `MAX_RENDER_DIM = 7000` (generous enough that real large physical pages, e.g. A3, are unaffected), computed by scaling down the zoom factor rather than trusting `DPI × declared page size` blindly. Verified directly against this PDF's actual pages: 175-327 megapixels → 32-41 megapixels, a 5-9x cut.

### Investigated: three PP-OCRv5 recognition/detection quality levers — none earned enabling

Prompted by wanting to "improve PaddleOCR Telugu extraction" generally. Two levers already existed in code but disabled (`ENABLE_PADDLE_CONFIDENCE_REVOTE`, `PADDLE_USE_CLAHE`); the third was the detector threshold set (`PADDLE_DET_UNCLIP_RATIO`/`PADDLE_DET_THRESH`/`PADDLE_DET_BOX_THRESH`). Tested with two new diagnostics, `tests/diagnostics/tune_paddle_quality.py` (revote/CLAHE, scored against `ocr_comparison/poratam/draft_ground_truth.json`, plus a qualitative word-diff on `ocr_comparison/No616_page15/page15_source.png` which has no ground truth) and `tests/diagnostics/tune_paddle_detector.py` (detector thresholds, poratam.png only — each variant reloads the detector singleton, ~3-5s per reload).

- **Confidence-band re-vote: essentially inert on this sample, one real case is a wash.** Fired on only 1 of ~930+1239 characters across the two test pages (the confidence band 0.45–0.70 rarely gets hit). The one flip, on poratam.png: `హోరాటం` → `పోాటం` (ground truth: `పోరాటం`). It fixed the wrong initial consonant (హ→ప, correct) but dropped the `ర` entirely, leaving a structurally-invalid dangling vowel sign — CER was identical before/after (one substitution either way) but the result traded a plausible-but-wrong word (invisible to every existing signal) for a grammatically-broken one (which `review_queue`'s structural check would actually catch). Not enabled — sample is too small to trust, but nothing here argues for turning it on either.
- **CLAHE: clear, reproducible regression, do not enable.** CER on poratam.png rose 0.127 → 0.175 (Telugu precision 0.873 → 0.825) vs. the current global contrast/sharpness boost, and the word-diff on both test pages shows CLAHE introducing new corruptions the baseline didn't have — dropped consonants (`చేస్తూ` → `ేస్తూ`, `చెప్పాము.` → `చె్పాము`), wrong substitutions (`హైజాకర్స్` → `పైాకర్స్`), a stray hallucinated quote mark. At `clip_limit=2.0`/`8×8` tiles it appears to amplify scan noise rather than help, at least on these two pages (one blurry-book cover, one clean page). Left off; would need a genuinely unevenly-faded/stained source page to be a fair test, not attempted.
- **Detector thresholds: current settings already validated as the better choice, no headroom found.** Reverting `PADDLE_DET_UNCLIP_RATIO` to PaddleOCR's own default (1.5, from the current 2.0) measurably hurt — CER 0.107 → 0.127 on poratam.png — which is direct evidence for the 2026-07 decision to raise it (to avoid clipping Telugu vowel/consonant marks), not just a plausible rationale. `PADDLE_DET_BOX_THRESH` at 0.5 and 0.7 (vs. current 0.6) changed nothing (same 22 boxes, same 0.107 CER) on this page — expected, since box_thresh mainly matters on noisy/low-confidence pages, and this one test page doesn't stress it. No change made; would need a genuinely borderline/noisy page to test box_thresh meaningfully.

**Incidental finding, bigger than any of the three levers above: the real production preprocessing path measurably hurts an already-clean page.** `tune_paddle_quality.py` compares `preprocess=False` against `preprocess=True` (the real call site always uses `True`) as a side effect of setting up the CLAHE test. On poratam.png — clean, well-lit, not blurry — CER went 0.107 (`preprocess=False`, everything every diagnostic this month has used) → 0.127 (`preprocess=True`, what production actually runs). This is the same gap flagged-but-unquantified on 2026-09-22 ("None of today's flag-rate or CER numbers are guaranteed to transfer to how this behaves in the real, preprocessed call path") — now with a real number. Surprising because `PADDLE_MIN_SHARPNESS_BOOST`/`PADDLE_MIN_CONTRAST_BOOST` are both `1.0` for an already-sharp/high-contrast page like this one, i.e. the multiplier should be close to a no-op — evidently even a ~1.0x PIL enhance pass alters pixels enough to cost real accuracy. Not investigated further or fixed this session — flagged for whoever picks up preprocessing next; the fix is likely skipping `_preprocess` entirely above the sharpness/contrast HIGH_LIMIT rather than applying a 1.0 multiplier through it.

### Fixed (2026-09-26): the sharpness/contrast metric was wrong by orders of magnitude at real production resolution

Follow-up to the preprocessing finding above, prompted by checking the live conversion actually running at the time (`Toli Prema`, job `151222c0`, `data/temp/Toli_Prema_151222c0/`, `OCR_ENGINE='fusion'`). Re-rendered a few of its already-completed pages (20, 44, 54) straight from the source PDF at the same 400 DPI / `MAX_RENDER_DIM=7000` the real pipeline uses, and measured `_preprocess`'s sharpness metric on them directly: **raw Laplacian variance measured 8–12 on these real, visually crisp, well-printed pages** (`page_20.png`, `page_44.png` — eyeballed directly, not remotely blurry) — three orders of magnitude below `PADDLE_SHARPNESS_LOW_LIMIT=1500`, let alone `TESSERACT_MIN_SHARPNESS=800`. Every real page in this live job was therefore getting the *maximum* sharpness boost (2.2x) and reading as "not clear" (`_assess_clarity`), regardless of true quality.

Root cause: Laplacian variance is not resolution-invariant. Real production renders are `~4400x7000` (hitting the `MAX_RENDER_DIM` cap); resizing the same page to `PADDLE_MAX_IMAGE_DIM` (1500px, the resolution the OCR model actually receives) before measuring gives values in the hundreds-to-thousands range that are directly comparable to what the thresholds were evidently tuned against (`ocr_comparison/book_sample` pages, ~1800-2843px, measure 2000-4800 raw — already close to the intended scale, which is presumably why this wasn't caught earlier: none of the standalone test images this month happened to be at real 400 DPI/7000px scale except the ones rendered specifically for the deskew and megapixel-cap bugs, and nobody had compared their sharpness numbers against the thresholds directly until now). `poratam.png` (541px wide, the opposite direction) also measured off-scale, just less dramatically.

Fix: new `PaddleV5Processor._clarity_metrics()` resizes a working copy to `PADDLE_MAX_IMAGE_DIM` before computing both metrics (contrast/std-dev barely changes with resize, confirmed directly — only the Laplacian-variance sharpness metric was scale-confounded), and both `_preprocess` and `_assess_clarity` now call it instead of measuring the raw source image. Not the same change as the one already reverted at `_assess_clarity`'s call site (that measured an already-*enhanced*-and-downscaled copy, which is circular — see the updated comment there); this resizes only, no enhancement, purely to normalize the measurement scale. Verified: on the three live-job pages, `_assess_clarity` and the sharpness/contrast factors now land in sane, comparable ranges instead of pinned to the extreme ends.

**Important, honestly-reported limit of this fix:** it corrects a real, confirmed order-of-magnitude measurement bug — it does not prove the resulting enhance-or-not *decision* is now well-tuned. Ran a real word-level diff of `preprocess=False` vs. `preprocess=True` (now metric-corrected) on `page_20.png` against my own direct reading of the source scan: of 18 differing word spans, roughly 7 favored the boosted version (including two exact-match corrections and one case that fixed the earlier-flagged plausible-substitution class, `క్ిన`→`కల్లిన`, still one letter off from correct `కల్గిన` but far closer), 7 favored the unboosted version, and 4 were a wash — including the `్ర`-as-bracket hallucination (see the still-separately-tracked item #3 in the resume list) appearing in *both* variants at different words, not tied to preprocessing either way. Read this as: the metric is no longer lying to the decision, but whether ~1500/3000 sharpness and ~30/50 contrast are the *right* cutoffs at this now-correct scale is still an open, data-starved question — deliberately not tuned further this session without more ground truth, consistent with how every other threshold in this file has been handled.

**Live as of 2026-09-26 00:19.** `Toli Prema` finished cleanly first (129/129 pages, EPUB+MOBI produced, verified — no interruption), then the user manually restarted the server (`Starting Flask server on 0.0.0.0:5001` in `converter.log` at 00:19:32). `Prema Kiranam` (121 pages) is the first real conversion running on the fixed metric. Verified live: `_assess_clarity`'s logged sharpness values for its pages land in the normal hundreds-to-low-thousands range (e.g. page 43: sharpness=1429.6, contrast=51.0) instead of the old raw-scale 8-12.

Cross-checked IndicPhotoOCR's router-skip rate across the last five real production runs (`ocr_comparison/engine_performance_log.jsonl`, production-sourced entries only, matched to `data/temp/*/` by timestamp):

| Book | Pages logged | IndicPhotoOCR ran | Window |
|---|---:|---:|---|
| రాయల నీతి కథలు | 47 | 44 (94%) | 09-22 22:34–23:08 |
| No_333 | 110 | 37 (34%) | 09-25 22:18–22:48 |
| No616 | 123 | 83 (67%) | 09-25 23:04–23:34 |
| Toli Prema | 125/129 | 9 (7%) | 09-25 23:55–00:14 |
| Prema Kiranam (in progress, fixed metric) | 52 so far | 12 (23%) | 00:24– |

Skip rate swings 6-93% book to book — expected, since the router reacts to each page's real PP-OCRv5 confidence/Tesseract-coverage, not a fixed policy. Toli Prema's unusually low 7% matches what direct eyeballing of its pages 20/44 found: PP-OCRv5 was confident but still visibly wrong in places (missing vowel signs, dropped consonants) — the router trusts PP-OCRv5's *own* confidence, not whether it's actually correct, the same gap already documented for the deskew bug. Worth re-checking Prema Kiranam's rate once it finishes, as the first full book on the corrected sharpness metric.

### Current config state (all in `config_v5.py` unless noted)

```
OCR_ENGINE = 'fusion'                    # was 'hybrid' at end of 2026-09-22 -- changed back this session
ENABLE_FUSION_OCR = True
FUSION_ADAPTIVE_ROUTER = True
FUSION_IDENTIFIER_MODE = 'hinted'
FUSION_INDIC_MIN_CONFIDENCE = 0.35       # new this session
MAX_WORKERS = 6
STAGE2_WORKERS = 4                       # raised from 2 this session
```

`src/app.py`: `PIL.Image.MAX_IMAGE_PIXELS = None` (new). `src/pdf_to_epub_converter_optimized_v2.py`: `MAX_RENDER_DIM = 7000` render cap (new), `DESKEW_MIN_ANGLE = 1.5` (raised from 0.3, new). `src/split_pdf_pages_cli.py`: same `MAX_RENDER_DIM = 7000` cap (new).

**All of 2026-09-25's and 2026-09-26's fixes are confirmed live** as of the 00:19 restart (see "Fixed (2026-09-26)" above for the verification). `Prema Kiranam` is the first book converting end-to-end on all of them together.

### Resume here, next session, roughly in priority order

1. **Check `Prema Kiranam` once it finishes** — first full book on the corrected sharpness/contrast metric. Compare its flagged-line rate and IndicPhotoOCR-skip rate (currently 23% partway through, see the table above) against the pre-fix books; also worth a spot eyeball-check of a page or two against the source PDF, same as was done for Toli Prema.
2. **Ground truth is still the single biggest lever, unchanged from prior sessions' #1.** Nothing new was transcribed this session either — `ocr_comparison/No616_page15/` remains a good candidate (deskew understood, shows remaining baseline error rate), and `Toli Prema` page 20 now has a rough manual transcription (in this session's investigation, not saved as a formal ground-truth file yet) that could be turned into one.
3. **The `్ర`-as-bracket conjunct misread** — confirmed present again today (`తండి`→`తం(డి` and the reverse, on real live pages), independent of preprocessing choice. Estimated 45min-1.5hr for a first attempt: find a few more instances, write a conservative post-processing correction, validate it doesn't corrupt genuine parentheses. Not started.
4. **Re-verify `STAGE2_WORKERS=4` doesn't reintroduce a real problem** — not yet stress-tested under real concurrent load with IndicPhotoOCR actually running on multiple pages at once.
5. **The unexplained detect()-time variance (11-43s, same image, same code, repeated runs)** — root cause still unknown, lower priority given `unresolved_lines` already cut how often detect() runs.
6. **Threshold *values* (not just the now-fixed measurement scale) for `PADDLE_SHARPNESS_LOW/HIGH_LIMIT` and `PADDLE_CONTRAST_LOW/HIGH_LIMIT` are still unvalidated** — see "Fixed (2026-09-26)" above. The confidence-band re-vote and CLAHE conclusions from earlier in this session (tested on `poratam.png`, which is 541px wide and so was never affected by the resize-normalization bug either way) still stand as tested; detector threshold tuning found no headroom over current settings.
7. Everything carried over, unchanged, from 2026-09-22's list: fix `fuse_page`'s `max()`-over-pairwise-agreement flagging, decide `hinted` mode's English-recall gap, commit this and prior sessions' work to git (still nothing committed — now a larger diff than ever, worth doing soon).
