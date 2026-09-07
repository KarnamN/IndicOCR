# Architecture

Current as of 2026-07-08. Supersedes the archived `docs/archive/ARCHITECTURE.md` and
`docs/archive/project_architecture.md.resolved`, both of which describe a pre-Paddle
Tesseract+EasyOCR design that no longer matches the code.

## Overview

MyOCR converts Telugu (and mixed Telugu/English) PDF scans into EPUB/MOBI. The pipeline is
PaddleOCR-primary: **PP-OCRv5** (via a custom low-level PaddleX wrapper) does the bulk of the
recognition work, with **Tesseract** as the automatic in-engine fallback and **Gemini** /
**Google Vision** as an escalation ladder for pages that fail quality gates.

## Entry points

- **Web app**: `python src/app.py` — Flask + Flask-SocketIO on port 5001. Routes cover
  upload/convert/audit/correction/duplicate-finder/file-search-copier, plus the standalone
  [PDF manipulation tools](PDF_TOOLS.md) and the
  [correction/repair/resume workflow](CORRECTION_AND_REPAIR.md) for fixing already-processed
  books.
- **CLI/batch**: `scripts/convert_large_pdf.py`, `src/split_pdf_pages_cli.py`,
  `scripts/test_quality.py`. `pdf_to_epub_converter_optimized_v2.py` also has its own `main()`.
- **Config**: `src/config.py` is the Tesseract-primary base config; `src/config_v5.py`
  (`from config import *`, then overrides) makes PaddleOCR primary and is what production
  actually runs. `src/config_tesseract.py` is a third, Tesseract-only variant. Config files are
  declarative only — plain constants, no computed logic; logic that consumes a flag lives in
  the module that uses it (e.g. `telugu_post_processor.py`, not `config.py`).
- **Environments**: `venv/` is the real WSL Ubuntu environment the app actually runs in.
  `wenv/` (Windows) is a dev-sandbox for editing/testing only — **not** a deployment target.

## Pipeline

Orchestrated by `OptimizedPDFToEPUBConverter.convert_streaming()`
(`src/pdf_to_epub_converter_optimized_v2.py`), driving `process_page_optimized()` per page:

1. **PDF → image** — PyMuPDF (`fitz`) at configured DPI (400 default).
2. **Skip-list check** — pages the user marked to [skip OCR](SKIP_PAGES.md) are converted to
   an image and returned immediately, before any splitting.
3. **Double-page split** — `page_splitter.py` confirms a genuine central spine gutter
   (`_has_central_spine`) before splitting a wide scan into two pages, to avoid mis-splitting
   genuinely wide multi-column pages. Recursive for 3+/N-up scans.
4. **Stage 1 — page analysis** (memory-preflight gated):
   - Auto-rotate (Tesseract OSD), optional table detection.
   - Layout-first figure extraction (`layout_analyzer.py`) crops illustrations and builds a
     text mask so complexity scoring isn't skewed by images.
   - Decorative-border filtering keeps text-in-a-box pages from being saved as bloated
     full-page images — see [Border fix](BORDER_FIX.md).
   - `page_complexity_analyzer.py` computes a complexity score, column count/gutter position,
     estimated line count, and a recommended engine/PSM.
5. **Engine routing** (`adaptive_ocr_factory.py`) — complexity-tiered: very high complexity
   routes to Google Vision/Gemini; otherwise PaddleOCR is primary for essentially all pages
   under `config_v5.py` (Tesseract is PaddleOCR's own internal fallback, not a separate tier).
6. **Stage 2 — OCR** (own semaphore, independent of the Stage-1 worker pool — see
   [Concurrency](#concurrency--paddleocr-integration)):
   - Deskew + sharpen preprocessing.
   - Column-aware OCR: 2+-column pages are cropped at the detected gutter and each column
     OCR'd concurrently, then joined in reading order. **Only 2-column layouts are supported**
     — 3+-column pages and pages with a faint/worn gutter are explicitly out of scope (see
     `page_complexity_analyzer.find_column_gutter()` and `page_splitter._has_central_spine()`).
   - Dispatches to Paddle / Gemini / Tesseract via `_ocr_single_image()`.
7. **Quality gate + escalation ladder** — a dynamic accuracy threshold (stricter for
   TOC/illustration/multicolumn pages) combined with `is_junk_text()` decides whether to
   escalate a page through Tesseract PSM-flip, then Gemini rescue. If everything fails, the
   text is discarded and the original page image is preserved instead.
8. **Telugu post-processing** — `telugu_post_processor.post_process_telugu()`: regex fixes
   for known misreads (shloka markers, punctuation), stray-English-token stripping on
   Telugu-dominant lines, and (opt-in) [dictionary-based spell-correction](TELUGU_SPELL_CORRECTION.md).
9. **Output** — `epub_builder.py` assembles chapters (text + images) into an EPUB via
   `ebooklib`; `mobi_converter.py` optionally converts to MOBI via Calibre. Per-page results
   are persisted incrementally as `.jbl` files for crash resilience, then assembled by
   `rebuild_book_from_results()`; `repair_book()` allows re-OCRing specific failed pages later.

## Concurrency & PaddleOCR integration

`src/paddle_v5_processor.py` does **not** use the high-level `PaddleOCR` class — it drives
PaddleX's low-level `TextRecognition`/`TextDetection` API directly, with several
version-specific workarounds baked in:

- MKL-DNN is forcibly disabled (`FLAGS_use_mkldnn=0`) to avoid a PIR-executor crash; detection
  is instead forced onto the OpenVINO backend via an explicit `engine_config` override, since
  PaddleX's own auto-selection would otherwise pick the now-neutered `paddle_mkldnn` path.
- A single global `threading.Lock` (`_engine_lock`) serializes **every** `.predict()` call,
  because PaddleX models are not thread-safe. This is a hard throughput ceiling: extra
  Stage-1 concurrency doesn't help Stage-2 OCR throughput, it just queues behind the lock —
  hence Stage 2 has its own, smaller semaphore (`config.STAGE2_WORKERS`) sized independently
  of the Stage-1 worker pool.
- `OMP_THREAD_LIMIT` is raised in-process (`max(2, cpu_count//2)`) when Paddle is enabled,
  since the Tesseract-tuned default of 1 thread would otherwise throttle Paddle inference on
  top of the lock serialization. Tesseract subprocesses are kept independently pinned to 1
  thread via a per-call env override (never mutating shared `os.environ`), so this change is
  safe under concurrent worker threads.
- Detection/recognition thresholds are tuned for Telugu glyphs specifically — e.g.
  `unclip_ratio=2.0` (vs. the 1.5 default) to avoid clipping vatulu/guninthalu.
- A custom quality gate (`_quality_gate`) rejects Paddle output on too-few-lines, low
  confidence, no-Telugu-chars, or mixed Telugu/English word contamination, triggering
  automatic Tesseract fallback. A comparative merge (`_merge_ocr_texts`) does word-level
  alignment between Tesseract and Paddle output when both run.
- Confidence scores are used only as internal gating signals (box-level filter, page-level
  quality gate) — they are not currently surfaced per-line to the output/EPUB.

## Telugu-specific text handling

- `src/telugu_text_processor.py` — Unicode-table-based grapheme analysis: consonants,
  matras (guninthalu), virama (vattu), akshara segmentation (`segment_graphemes()`).
  `grapheme_validity_score()` detects structurally-impossible sequences (orphaned matras,
  dangling viramas) that Unicode-block/symbol-ratio junk checks can't see, since every
  character involved is still individually a valid Telugu codepoint.
- `src/telugu_post_processor.py` — regex-based misread fixes, stray-English-token stripping,
  and (opt-in, default off) dictionary-based spell-correction — see
  [TELUGU_SPELL_CORRECTION.md](TELUGU_SPELL_CORRECTION.md).
- `src/telugu_spell_checker.py` — grapheme-cluster-aware fuzzy dictionary lookup backing the
  spell-correction step.

## Logging

- `src/logging_config.py` — rotating file handler (`converter.log`, 20MB × 5 backups) +
  console handler; `werkzeug` access logs demoted to `WARNING`.
- Structured event log — `converter_events.jsonl` (one JSON object per line) inside each
  book's temp results dir, written in real time so partial data survives a crash even before
  the end-of-run `quality_report.json` exists.

## Testing & benchmarking

There is no pytest/CI suite — verification is via targeted scripts:

- `scripts/benchmark_quality.py` — CER/WER benchmark (via `jiwer`) comparing Tesseract-only,
  Paddle-only, and the merged pipeline against a ground-truth reference text. Supports
  `--dict-correction` to also measure the isolated CER/WER impact of Telugu dictionary
  spell-correction.
- `tests/diagnostics/` — ad-hoc diagnostic/analysis scripts (gutter detection, OCR
  comparisons, layout dumps, allowlist regression checks). Not CI-integrated; run manually.

## Known limitations (intentionally out of scope)

- **3+ column layouts** — column-aware OCR only ever detects a single gutter; pages with
  3 or more text columns are not automatically split into columns for OCR.
- **Faint/worn gutters** — double-page-spread splitting requires a confirmed spine
  (`require_spine_confirmation=True` by default); book photocopies with a faint or worn
  gutter that a pixel-projection check can't confirm fall back to being treated as a single
  unsplit page.
- **Per-line OCR confidence** is not exposed to the output/EPUB or the audit workflow, only
  used internally for engine-selection/quality-gating decisions.
