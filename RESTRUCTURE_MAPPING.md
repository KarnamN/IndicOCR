# Restructuring File Mapping

This document details the restructuring of test, diagnostic, and legacy files in this repository. All moved files were backed up to `backup_pre_restructure_20260703/` before relocation.

## Summary

* **Diagnostics and Testing Scripts**: Moved from root and `scratch/` into [tests/diagnostics/](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/tests/diagnostics/).
* **Legacy Code**: Moved from `src/` into [src/legacy/](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/src/legacy/).

---

## File Mappings

| Original Path | Target Path | Role / Purpose |
| :--- | :--- | :--- |
| `analyze_page19.py` | `tests/diagnostics/analyze_page19.py` | Diagnostic script for checking page line ratios |
| `check_usage.py` | `tests/diagnostics/check_usage.py` | Utility to query Gemini API usage quota |
| `compare_ocr.py` | `tests/diagnostics/compare_ocr.py` | Script to benchmark OCR engine output and word merge algorithms |
| `count_audits.py` | `tests/diagnostics/count_audits.py` | Utility to count page audits in system logs |
| `inspect_jbl.py` | `tests/diagnostics/inspect_jbl.py` | Diagnostic tool to inspect disk-serialized joblib objects |
| `search_log.py` | `tests/diagnostics/search_log.py` | Search utility inside system log file |
| `slice_pdf.py` | `tests/diagnostics/slice_pdf.py` | Slices single page from PDF |
| `test_conversion_run.py` | `tests/diagnostics/test_conversion_run.py` | CLI test converter harness |
| `test_gemini_isolated.py` | `tests/diagnostics/test_gemini_isolated.py` | Testing script for isolated Gemini requests |
| `test_google_vision.py` | `tests/diagnostics/test_google_vision.py` | Testing script for Google Cloud Vision API |
| `test_layout_html.py` | `tests/diagnostics/test_layout_html.py` | Generates layout blocks HTML visuals for pages |
| `test_oom_handling.py` | `tests/diagnostics/test_oom_handling.py` | Tests out of memory handlers in parallel page execution |
| `test_paddle_rec.py` | `tests/diagnostics/test_paddle_rec.py` | Tests PaddleOCR text recognition in isolation |
| `test_paddle_v5.py` | `tests/diagnostics/test_paddle_v5.py` | Tests PP-OCRv5 model initialization in isolation |
| `test_telugu_paddle.py` | `tests/diagnostics/test_telugu_paddle.py` | Benchmark test for Telugu characters in PP-OCRv5 |
| `verify_escalation_junk.py` | `tests/diagnostics/verify_escalation_junk.py` | Verification harness for Tesseract-to-Gemini escalation triggers |
| `scratch/analyze_approva.py` | `tests/diagnostics/analyze_approva.py` | Analysis of ApprovaSuodham.png layout |
| `scratch/simulate_gutter.py` | `tests/diagnostics/simulate_gutter.py` | Vertical projection and gutter band simulation |
| `scratch/print_gutter_details.py` | `tests/diagnostics/print_gutter_details.py` | Detailed projection density around true column gutter |
| `scratch/analyze_binary.py` | `tests/diagnostics/analyze_binary.py` | Global Otsu binarization projection density statistics |
| `scratch/check_colors.py` | `tests/diagnostics/check_colors.py` | Check original grayscale pixel values to diagnose Otsu failure |
| `scratch/test_adaptive_thresh.py` | `tests/diagnostics/test_adaptive_thresh.py` | Adaptive binarization comparison test |
| `scratch/test_adaptive_analyze.py` | `tests/diagnostics/test_adaptive_analyze.py` | Comparison between global Otsu and local adaptive thresholding PageComplexityAnalyzer |
| `scratch/test_adaptive_gutter.py` | `tests/diagnostics/test_adaptive_gutter.py` | Adaptive thresholding column gutter candidate runs test |
| `scratch/test_adaptive_gutter_v2.py` | `tests/diagnostics/test_adaptive_gutter_v2.py` | Scoring and margin-rejection balance logic for gutters test |
| `scratch/analyze_approva_1.py` | `tests/diagnostics/analyze_approva_1.py` | Complexity analysis of ApprovaSuodham_1.png layout |
| `scratch/check_approva_1_components.py` | `tests/diagnostics/check_approva_1_components.py` | Coordinates check of layout blocks in ApprovaSuodham_1.png |
| `scratch/test_single_column.py` | `tests/diagnostics/test_single_column.py` | Column count check on single column images (pdf_page, chakra, book name) |
| `src/pdf_to_epub_converter.py` | `src/legacy/pdf_to_epub_converter.py` | [Legacy] Original unoptimized PDF to EPUB converter |
| `src/pdf_to_epub_converter_optimized.py` | `src/legacy/pdf_to_epub_converter_optimized.py` | [Legacy] First-generation optimized converter (replaced by v2) |
| `src/pdf_to_epub_converter_optimized.py.backup` | `src/legacy/pdf_to_epub_converter_optimized.py.backup` | [Legacy] Backup of first-generation optimized converter |
| `src/pdf_to_epub_converter_optimized_temp.py` | `src/legacy/pdf_to_epub_converter_optimized_temp.py` | [Legacy] Temp copy of optimized converter |
| `src/paddle_ocr_processor.OLD.py` | `src/legacy/paddle_ocr_processor.OLD.py` | [Legacy] Legacy PaddleOCR processor |
| `src/hybrid_ocr_processor.py` | `src/legacy/hybrid_ocr_processor.py` | [Legacy] Unused hybrid processor wrapper |
| `src/qwen_ocr_processor.py` | `src/legacy/qwen_ocr_processor.py` | [Legacy] Unused Qwen API processor |

---

## July 2026 Archive Cleanup

To keep the repository root and `scratch/` directory clean and simple, the following reference files and scratch scripts have been archived:

### Root Reference Files Archived to [archive_reference/root_files/](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/archive_reference/root_files/)

* `3-column.png` (Reference 3-column book page scan)
* `benchmark_results.txt` (Historical layout binarization benchmarks)
* `shvasanusamdhanam.epub` (Reference output EPUB)
* `telugu_folder_report.json` / `telugu_folder_report.txt` (Historical batch run reports)
* `test_output.log` (Historical run logs)
* `test_scratch.epub` / `test_scratch.mobi` (Test generated output files)
* `test_wsl.log` (WSL environment verification logs)
* `repair_book.py` (One-off script for cleaning up broken book elements)

### Root Validation Images Moved to [images/](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/images/)

* `chakra.png` $\rightarrow$ `images/chakra.png`
* `pdf_page.png` $\rightarrow$ `images/pdf_page.png`
* `reversepage.png` $\rightarrow$ `images/reversepage.png`

### Scratch Scripts Archived to [archive_reference/scratch/](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/archive_reference/scratch/)

* All temporary diagnostic scripts generated during parameter optimization, binarization checking, and line safety testing (such as `test_narrow_parameters.py`, `inspect_book_name.py`, `test_new_preprocess.py`, `check_crop.py`, etc.) were relocated to the archive folder for future reference.
* Only [scratch/ocr_approva_1.py](file:///c:/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/scratch/ocr_approva_1.py) is kept in the active `scratch/` directory for developer column-splitting verification.
