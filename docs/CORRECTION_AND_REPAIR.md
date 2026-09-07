# Correction Dashboard, Book Repair & Resume

Covers the manual-correction workflow: `/correction/<job_id>` (review/edit/rebuild),
`/repair` (re-OCR specific pages of an already-finished book), and
`/api/correction/resume` (reopen a previous conversion's saved results). Written 2026-07-13
after fixing several real bugs across all three and adding the resume feature — see
[TELUGU_SPELL_CORRECTION.md](TELUGU_SPELL_CORRECTION.md) for the dictionary-correction
feature that first motivated building out this review workflow.

## Three ways to fix an already-processed book

| Situation | Use | Why |
|---|---|---|
| Same server session still running, book mid-review | Correction dashboard directly | No PDF/EPUB re-upload needed. REBUILD EBOOK works immediately even with pages still unreviewed — nothing blocks it, "review everything first" is not enforced |
| Server restarted since, results folder still exists | **Resume** (`/api/correction/resume`) | No re-OCR, no re-upload — reuses saved `.jbl` results directly, correct page numbers guaranteed (each `.jbl` already carries its real page_num) |
| Only the PDF + an EPUB survive, no results folder | **Repair** (`/repair`) | Re-OCRs specific pages from the PDF from scratch — the only option left, but see the page-numbering caveat below |

## Resume (`POST /api/correction/resume`)

Paste a `data/temp/<title>_<session_id>` folder name or full path; reopens
`/correction/<job_id>` directly. Job ID is derived from the folder's trailing 8-character
session ID, reusing the same `d.name.endswith(job_id[:8])` lookup convention the rest of the
correction routes already use — no other route needed changes to support it.

- Path-traversal safe: only ever resolves a bare folder **name** under `config.TEMP_FOLDER`,
  regardless of what full path is pasted in.
- View/edit/save/rebuild all work from the saved data alone, no PDF needed.
- An **optional PDF upload** enables REWORK (re-OCR with a different engine) — saved as
  `source.pdf` inside the results folder itself, so it's only needed once per folder, not
  once per resume.
- Refuses to resume a job whose `status == 'processing'` (409).

## Bugs fixed in `/repair` (2026-07-13)

1. **The repair download link never worked, at all.** `repair_book()` wrote its output using
   the *temp-saved copy's* filename (`repair_<uuid>_<name>.epub`, prefixed by `app.py` to
   avoid collisions between concurrent requests), but the route independently guessed the
   download filename without that prefix (`epub_file.filename.split('.')[0] + "_repaired.epub"`
   — also wrong for any filename with multiple dots). The two never matched, so every repair
   silently returned `{success: true, files: []}`. Fixed: `repair_book()` now returns the
   actual `output_path`/`mobi_path` it wrote; the route uses those directly.
2. UI accepted `.epub,.mobi`, but the backend parses via `ebooklib.epub.read_epub()`, which
   can't read MOBI. Fixed: UI restricted to `.epub`, plus a server-side guard.
3. Temp-saved PDF/EPUB copies leaked on any exception (cleanup wasn't in a `finally`). Fixed.
4. Dictionary corrections during repair now surface via a `pages_needing_review` response
   field — repair is a one-shot flow with no interactive review step, so this is a heads-up
   rather than a gate.

## Known limitation: page-numbering risk in `/repair`

`repair_book()` assumes EPUB chapter index N == PDF page N. That's false whenever the
original conversion split double-page spreads (default on) or skipped pages — either changes
the chapter:PDF-page ratio. Detected (chapter count vs. actual PDF page count via `fitz`) and
surfaced as a `warning` in the response, not blocked — a correct fix needs the original
per-chapter PDF page number, which isn't stored in the EPUB today. **Prefer Resume over
Repair whenever the results folder still exists** — resume doesn't have this problem, since
each `.jbl` file already carries its correct original `page_num`.

## `rework_page()` — implemented 2026-07-13, was previously missing entirely

`app.py`'s REWORK button called `converter.rework_page(...)`, but no such method existed
anywhere in the codebase — clicking REWORK on *any* job (not just resumed ones) threw
`AttributeError`, caught by the generic error handler. Implemented as a direct per-engine
dispatch (`GeminiOCRProcessor.extract_text()` / `GoogleVisionProcessor.extract_text()` /
`OCRProcessor.extract_text()`), bypassing the normal complexity-based adaptive routing
entirely — an explicit engine choice from the correction UI should be honored exactly, not
reinterpreted.

**Split-page correctness**: re-runs the same `page_splitter.process_image()` split
`process_page_optimized()` used originally and targets the requested `sub_idx`, rather than
OCRing the whole raw (unsplit) page — getting this wrong would silently merge both columns'
text into one result instead of reworking just the flagged half.

## Known gap: split pages are only half-reachable in the correction dashboard

Not fixed this session — flagged as a follow-up. For a page that was split into two halves
(`sub_idx` 0 and 1 both exist as separate `.jbl` files), the entire correction dashboard
today only ever operates on `page_num` — no `sub_idx` in the sidebar list, URLs, or
JavaScript. `get_page_for_correction()`/`save_corrected_page()` fall back to "try
`sub_idx=0`, else first match," meaning **the second half of any split page is currently
unreachable through the UI** — not just for rework, for viewing and saving too. `rework_page()`
itself is implemented correctly and accepts `sub_idx`, but nothing in the dashboard UI can
select a non-zero `sub_idx` to send it yet.

Fixing this properly needs: `get_correction_pages()` to return distinct sidebar entries per
`(page_num, sub_idx)` pair instead of colliding on `page_num` alone; the correction.html page
list, URL scheme (`?page=N`), and `loadPage()`/`saveCurrentPage()`/`reworkCurrentPage()` JS to
carry `sub_idx` alongside `page_num` throughout. A real but scoped follow-up, not started.

## Correction dashboard UX additions (2026-07-13)

- **Flagged-pages filter**: sidebar defaults to showing only pages with `status === 'flagged'`
  (covers both the pre-existing short-text heuristic and dictionary-correction review flags)
  when any exist, with a toggle to see all pages. PREV/NEXT navigate within the active filter.
  Saving a flagged page auto-advances to the next one (review-queue flow) rather than leaving
  the reviewer to hunt for the next flagged page manually.
- **On-screen Telugu keyboard**: self-contained vowel/consonant/matra/punctuation grid,
  inserts at cursor — no external transliteration API dependency.
- **Corrections panel**: shows the specific before/after word pairs for the current page's
  dictionary corrections, not just a flat text diff.
