# PDF Manipulation Tools

Standalone PDF utilities (split/remove/extract/reorder/rotate pages, plus wide-spread
splitting) exposed via the "PDF Tools" tab in the web UI and a Python API. Independent of
the OCR/EPUB pipeline — these operate on PDFs directly, no OCR involved.

## Operations

| Operation | Form field(s) | Effect |
|---|---|---|
| `split` | `ranges` (e.g. `1-10,15-20,25-30`) | Splits into multiple PDFs, one per range |
| `remove` | `pages` (e.g. `1,5,10-15`) | Removes the given pages, keeps the rest |
| `extract` | `pages` (e.g. `1-5,10,20`) | Creates a new PDF with only the given pages |
| `reorder` | `order` (e.g. `10,9,8,...,1`) | Rearranges pages into the specified order |
| `rotate` | `pages` (empty = all), `rotation` (90/180/270) | Rotates the given pages |
| `split_wide` | — | Splits double/triple/quad-page spreads into individual portrait pages (via `split_pdf_pages_cli.split_pdf_pages`, 300 DPI) |

Page-range/list syntax matches the OCR pipeline's [skip-pages feature](SKIP_PAGES.md):
comma-separated, hyphen ranges inclusive, 1-indexed, whitespace-tolerant.

## Implementation

- **Core logic**: `src/pdf_manipulator.py` — `PDFManipulator` class (`split_pdf`,
  `remove_pages`, `extract_pages`, `reorder_pages`, `rotate_pages`, `get_pdf_info`) plus
  the parsing helpers `parse_page_ranges()` and `parse_page_list()`.
- **Routes**: `src/app.py`
  - `POST /pdf_tools` (`src/app.py:562`) — dispatches on the `operation` form field to
    one of the six operations above.
  - `POST /pdf_info` (`src/app.py:740`) — returns PDF metadata (page count, title, author,
    file size).
- **UI**: "PDF Tools" tab in `src/templates/index.html`.

## API examples

```bash
curl -X POST http://localhost:5001/pdf_tools \
  -F "file=@input.pdf" -F "operation=split" -F "ranges=1-10,15-20"

curl -X POST http://localhost:5001/pdf_tools \
  -F "file=@input.pdf" -F "operation=remove" -F "pages=1,5,10-15"

curl -X POST http://localhost:5001/pdf_tools \
  -F "file=@input.pdf" -F "operation=rotate" -F "pages=1,2,3" -F "rotation=90"

curl -X POST http://localhost:5001/pdf_info -F "file=@input.pdf"
```

Response shape:
```json
{
  "success": true,
  "operation": "split",
  "files": [{"name": "input_part1.pdf", "url": "/download/input_part1.pdf"}],
  "message": "PDF split completed successfully"
}
```

## Python API

```python
from pdf_manipulator import PDFManipulator
from pathlib import Path

manipulator = PDFManipulator()
manipulator.split_pdf(Path("input.pdf"), Path("output/"), [(1, 10), (11, 20)])
manipulator.remove_pages(Path("input.pdf"), Path("output.pdf"), pages_to_remove=[1, 5, 10])
manipulator.extract_pages(Path("input.pdf"), Path("output.pdf"), pages=[1, 2, 3])
manipulator.reorder_pages(Path("input.pdf"), Path("output.pdf"), new_order=[3, 2, 1])
manipulator.rotate_pages(Path("input.pdf"), Path("output.pdf"), pages=[1, 2], rotation=90)
info = manipulator.get_pdf_info(Path("input.pdf"))
```
