"""Turn a fuse_ocr_engines.py report into a flat, page-ordered review queue.

Unlike fusion.html (every line of every page, so a human has to scan whole
pages to find the handful worth checking), this lists only the lines flagged by
either signal: engine disagreement (ocr_fusion) or implausible Telugu
(review_queue's structural-grammar check). Measured on the 2026-09-21 sample
book: 183 total lines, 14 flagged (8%) -- see docs/CURRENT_STATE.md.

Run from the repository root (no OCR engines needed, scores an existing
fusion.json):
    python tests/diagnostics/build_review_queue.py ocr_comparison/fusion/fusion.json
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from review_queue import build_review_queue  # noqa: E402

REASON_LABELS = {
    "engine_disagreement": "engines disagree",
    "missing_from_paddle": "possibly missing (PP-OCRv5 skipped it)",
    "structurally_invalid_telugu": "structurally invalid Telugu",
    "out_of_dictionary": "not in dictionary",
    "uncorroborated_ascii": "stray Latin text (likely misread)",
}


def render(result: dict) -> str:
    rows = []
    for item in result["queue"]:
        reasons = ", ".join(REASON_LABELS.get(r, r) for r in item["reasons"])
        cand_lines = "".join(
            f"<div><b>{html.escape(engine)}:</b> {html.escape(text)}</div>"
            for engine, text in item["candidates"].items()
        )
        suggested = item["suggested_text"]
        note = (f'<div class="suggested">suggested (most structurally valid candidate) — '
                f'confirm or edit:</div>' if suggested != item["text"] else "")
        rows.append(f"""<tr>
          <td>{html.escape(item['page'])}<br><small>line {item['line'] + 1}</small></td>
          <td>{html.escape(reasons)}</td>
          <td>{cand_lines}</td>
          <td>{note}<span contenteditable="true" class="final"
              data-page="{html.escape(item['page'])}" data-line="{item['line']}">
              {html.escape(suggested)}</span></td>
        </tr>""")

    s = result["summary"]
    page_rows = "".join(
        f"<tr><td>{html.escape(page)}</td><td>{stats['flagged']}/{stats['lines']}</td>"
        f"<td>{stats['flagged_rate']:.0%}</td></tr>"
        for page, stats in result["per_page"].items()
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OCR review queue</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;color:#202124}}
table{{border-collapse:collapse;width:100%;margin-bottom:1.5rem;font-size:.95rem}}
td,th{{border:1px solid #dfe3e8;padding:.4rem .6rem;vertical-align:top;text-align:left}}
th{{background:#eef2f6}} .final{{background:#fffbe6;display:inline-block;width:100%}}
.suggested{{font-size:.8rem;color:#188038;margin-bottom:.2rem}}
.summary{{background:#eef2f6;padding:1rem;border-radius:6px;margin-bottom:1.5rem}}
button{{padding:.5rem 1rem}}
</style></head><body>
<h1>OCR review queue</h1>
<div class="summary">
  <b>{s['total_flagged']} of {s['total_lines']} lines flagged ({s['line_flag_rate']:.0%})</b>
  across {s['pages']} page(s), {s['pages_with_any_flag']} touched.
  <table><tr><th>page</th><th>flagged</th><th>rate</th></tr>{page_rows}</table>
</div>
<p>Edit the yellow cells to the correct text, then download.</p>
<button onclick="dl()">Download corrections</button>
<table><tr><th>where</th><th>why flagged</th><th>candidates</th><th>final (editable)</th></tr>
{''.join(rows)}</table>
<script>
function dl(){{const out={{}};
document.querySelectorAll('.final').forEach(td=>{{const p=td.dataset.page;(out[p]=out[p]||{{}})[+td.dataset.line]=td.innerText.trim();}});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}));
a.download='review_queue_corrections.json';a.click();}}
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fusion_json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "ocr_comparison" / "fusion")
    parser.add_argument("--oov-threshold", type=float, default=None,
                        help="Off by default -- see review_queue.OOV_THRESHOLD docstring.")
    args = parser.parse_args()

    report = json.loads(args.fusion_json.read_text(encoding="utf-8"))
    kwargs = {} if args.oov_threshold is None else {"oov_threshold": args.oov_threshold}
    result = build_review_queue(report, **kwargs)

    s = result["summary"]
    print(f"{s['total_flagged']}/{s['total_lines']} lines flagged ({s['line_flag_rate']:.0%}), "
          f"{s['pages_with_any_flag']}/{s['pages']} pages touched")
    for page, stats in result["per_page"].items():
        print(f"  {page:28} {stats['flagged']:3}/{stats['lines']:3}  ({stats['flagged_rate']:.0%})")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "review_queue.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "review_queue.html").write_text(render(result), encoding="utf-8")
    print(f"Saved {args.output_dir / 'review_queue.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
