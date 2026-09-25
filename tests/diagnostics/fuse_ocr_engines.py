"""Fuse PP-OCRv5, IndicPhotoOCR and Tesseract per line and write a review page.

Run from the repository root inside the WSL shared environment:
    python tests/diagnostics/fuse_ocr_engines.py --only "blurry.png"

Outputs (in --output-dir):
    fusion.json   per-line candidates, decision, agreement, timings
    fusion.html   side-by-side review page; edit the "final" cells and use
                  "Download corrections" to save ground-truth lines as JSON
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def _load(device: str, language: str, identifier_mode: str, quantize: bool, min_confidence: float):
    import config_v5 as active_config

    sys.modules["config"] = active_config
    from indicphoto_ocr_processor import IndicPhotoOCRProcessor
    from ocr_processor import OCRProcessor
    from paddle_v5_processor import PaddleV5Processor

    return (
        PaddleV5Processor(language="tel+eng", config=active_config),
        IndicPhotoOCRProcessor(device=device, identifier_lang=language, identifier_mode=identifier_mode,
                               quantize_identifier=quantize, min_confidence=min_confidence),
        OCRProcessor(language="tel+eng"),
    )


def _fuse_image(paddle, indic, tesseract, image: Image.Image, adaptive: bool = False,
                page_label: str = "") -> dict:
    import unicodedata

    from ocr_fusion import fuse_page, latin_regions, paddle_line, unresolved_lines

    image = paddle._resize_if_needed(paddle._ensure_rgb(image))   # one coordinate system for all engines
    timings = {}

    started = time.perf_counter()
    _, boxes = paddle._paddle_extract(image)
    timings["paddle"] = time.perf_counter() - started
    lines = [paddle_line(box) for box in boxes]

    started = time.perf_counter()
    tess_words = [
        {"text": unicodedata.normalize("NFC", w["text"]),
         "bbox": [w["left"], w["top"], w["left"] + w["width"], w["top"] + w["height"]]}
        for w in tesseract.extract_text_with_boxes(image, preprocess=False) if w["text"].strip()
    ]
    timings["tesseract"] = time.perf_counter() - started

    router_decision = None
    run_indic = True
    if adaptive:
        from engine_router import should_run_indicphoto
        run_indic, router_decision = should_run_indicphoto(lines, tess_words)

    started = time.perf_counter()
    target_lines = unresolved_lines(lines, tess_words)
    words = indic.extract_words(image, english_boxes=latin_regions(lines),
                                paddle_boxes=[line["bbox"] for line in target_lines]) if run_indic else []
    timings["indicphoto"] = time.perf_counter() - started

    started = time.perf_counter()
    fused = fuse_page(lines, words, tess_words)
    timings["fusion"] = time.perf_counter() - started
    timings["total"] = sum(timings.values())

    from engine_performance_log import page_quality_metrics, record_page
    record_page(page_label=page_label, quality=page_quality_metrics(image),
               timings={k: v for k, v in timings.items() if k in ("paddle", "indicphoto", "tesseract")},
               fused_lines=fused, router_meta=router_decision, source="diagnostic")
    return {
        "size": image.size,
        "timings": {k: round(v, 2) for k, v in timings.items()},
        "indicphoto_scripts": indic.last_script_counts if run_indic else {},
        "router": router_decision,
        "indicphoto_ran": run_indic,
        "lines": fused,
        "text": "\n".join(line["text"] for line in fused),
    }


def _render(report: dict) -> str:
    sections = []
    for name, page in report["images"].items():
        rows = []
        for i, line in enumerate(page["lines"]):
            cand = line["candidates"]
            flag = ' class="review"' if line["needs_review"] else ""
            cells = "".join(
                f'<td class="{"win" if line["chosen"] == e else ""}">{html.escape(cand.get(e, ""))}</td>'
                for e in ("paddle", "indicphoto", "tesseract")
            )
            rows.append(
                f"<tr{flag}><td>{i + 1}</td>{cells}"
                f'<td contenteditable="true" class="final" data-page="{html.escape(name)}" data-line="{i}">'
                f'{html.escape(line["text"])}</td>'
                f'<td>{html.escape(line["chosen"])}<br><small>{line["agreement"]}</small></td></tr>'
            )
        sections.append(
            f'<h2>{html.escape(name)}</h2><p class="meta">timings (s): {html.escape(json.dumps(page["timings"]))}'
            f' &middot; IndicPhotoOCR crops: {html.escape(json.dumps(page["indicphoto_scripts"]))}</p>'
            '<table><tr><th>#</th><th>PP-OCRv5</th><th>IndicPhotoOCR</th><th>Tesseract</th>'
            f'<th>final (editable)</th><th>chosen / agreement</th></tr>{"".join(rows)}</table>'
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OCR fusion review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;color:#202124}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem;font-size:.95rem}}
td,th{{border:1px solid #dfe3e8;padding:.35rem .5rem;vertical-align:top}}
th{{background:#eef2f6;text-align:left}} .win{{background:#e6f4ea}}
tr.review td{{border-color:#d93025}} tr.review td:first-child{{background:#fce8e6}}
.final{{background:#fffbe6}} .meta{{color:#5f6368}} button{{padding:.5rem 1rem}}
</style></head><body><h1>OCR fusion review</h1>
<p>Green = the engine whose text was chosen. Red row = engines disagree; check it first.
Edit the yellow cells to the correct text, then download.</p>
<button onclick="dl()">Download corrections</button>{''.join(sections)}
<script>
function dl(){{const out={{}};
document.querySelectorAll('.final').forEach(td=>{{const p=td.dataset.page;(out[p]=out[p]||[])[+td.dataset.line]=td.innerText.trim();}});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}));
a.download='ground_truth_corrections.json';a.click();}}
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", type=Path, default=ROOT / "images")
    parser.add_argument("--only", nargs="+", required=True, help="Image file names to fuse.")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--language", default="telugu")
    parser.add_argument("--identifier-mode", default="hinted", choices=["vit", "hinted", "none"])
    parser.add_argument("--quantize-identifier", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.35,
                        help="Drop IndicPhotoOCR words below this confidence (see config_v5.FUSION_INDIC_MIN_CONFIDENCE).")
    parser.add_argument("--adaptive", action="store_true",
                        help="Skip IndicPhotoOCR on pages engine_router.py judges easy enough. See its docstring.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "ocr_comparison" / "fusion")
    args = parser.parse_args()

    paddle, indic, tesseract = _load(args.device, args.language, args.identifier_mode,
                                     args.quantize_identifier, args.min_confidence)
    report = {"identifier_mode": args.identifier_mode, "adaptive": args.adaptive, "images": {}}
    skipped = 0
    for name in args.only:
        image = Image.open(args.image_dir / name).convert("RGB")
        page = _fuse_image(paddle, indic, tesseract, image, adaptive=args.adaptive, page_label=name)
        report["images"][name] = page
        skipped += not page["indicphoto_ran"]
        chosen = {}
        for line in page["lines"]:
            chosen[line["chosen"]] = chosen.get(line["chosen"], 0) + 1
        flagged = sum(line["needs_review"] for line in page["lines"])
        router_note = f" router={page['router']}" if page["router"] else ""
        print(f"{name}: {len(page['lines'])} lines, chosen {chosen}, {flagged} flagged, timings {page['timings']}{router_note}")

    if args.adaptive:
        print(f"\nIndicPhotoOCR skipped on {skipped}/{len(args.only)} pages")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fusion.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "fusion.html").write_text(_render(report), encoding="utf-8")
    print(f"Saved {args.output_dir / 'fusion.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
