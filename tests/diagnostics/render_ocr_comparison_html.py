"""Render compare_image_ocr.py JSON output as a readable HTML report."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def _cell(engine: str, result: dict) -> str:
    text = html.escape(result.get("text", "")) or "<em>No text returned</em>"
    error = result.get("error")
    status = f"<p class=\"error\">{html.escape(error)}</p>" if error else ""
    counts = result.get("script_counts")
    script_counts = f"· crops by script: {html.escape(json.dumps(counts))}" if counts else ""
    return f"""
    <section class="engine">
      <h3>{html.escape(engine)}</h3>
      <p class="stats">{result.get('characters', 0)} characters ·
        {result.get('lines', 0)} lines · {result.get('seconds', 0)} seconds ·
        {result.get('telugu_characters', 0)} Telugu ·
        {result.get('latin_characters', 0)} English ·
        {result.get('other_script_characters', 0)} other-script characters
        {script_counts}</p>
      {status}
      <pre>{text}</pre>
    </section>"""


def render(report: dict) -> str:
    image_sections = []
    for image_name, engines in report.get("images", {}).items():
        cells = "\n".join(_cell(name, result) for name, result in engines.items())
        image_sections.append(f"<article><h2>{html.escape(image_name)}</h2><div class=\"grid\">{cells}</div></article>")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>IndicOCR Engine Comparison</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #202124; background: #f5f7fa; }}
h1 {{ margin-bottom: .25rem; }}
.meta {{ color: #5f6368; margin-bottom: 2rem; }}
article {{ background: white; border: 1px solid #dfe3e8; border-radius: 8px; padding: 1rem; margin: 1rem 0 1.5rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
.engine {{ border: 1px solid #e1e5ea; border-radius: 6px; overflow: hidden; }}
.engine h3 {{ margin: 0; padding: .7rem .9rem; background: #eef2f6; }}
.stats {{ font-size: .85rem; color: #5f6368; padding: 0 .9rem; }}
pre {{ white-space: pre-wrap; word-break: break-word; padding: .9rem; margin: 0; min-height: 8rem; background: #fbfcfd; font-family: ui-monospace, monospace; }}
.error {{ color: #b3261e; padding: 0 .9rem; }}
</style></head><body>
<h1>IndicOCR Engine Comparison</h1>
<p class="meta">Images: {html.escape(report.get('image_dir', 'unknown'))}<br>
Engines: {html.escape(', '.join(report.get('engines', [])))}</p>
{''.join(image_sections)}
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.report.with_suffix(".html")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    output.write_text(render(report), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())