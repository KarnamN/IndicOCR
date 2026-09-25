"""Periodic report: which engine fits which kind of page, and what it costs.

Reads ocr_comparison/engine_performance_log.jsonl (src/engine_performance_log.py,
written automatically by FusionOCRProcessor in production and by
fuse_ocr_engines.py in diagnostics) and buckets pages by quality (brightness,
sharpness/contrast — same metric PaddleV5Processor._assess_clarity and
engine_router.py use) to show, per bucket: how often each engine wins a line,
how often the page gets flagged, and average per-engine time.

This is meant to be re-run periodically as real usage accumulates (that's the
point of logging every page rather than only ad-hoc samples), to check whether
engine_router.py's thresholds still make sense and whether a real
quality-bucketed routing table (rather than router.py's current single
confidence/coverage/structural threshold) would help. It only reports; nothing
here changes automatically.

Usage:
    python tests/diagnostics/report_engine_performance.py
    python tests/diagnostics/report_engine_performance.py --source production
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from engine_performance_log import DEFAULT_LOG_PATH, ENGINES, load_records  # noqa: E402

# Fixed bands rather than quantiles: quantiles shift as more data arrives, which
# would make "the dark bucket" mean something different every time you re-run
# this, right when the point is to compare against earlier runs. Sharpness
# thresholds match TESSERACT_MIN_SHARPNESS/TESSERACT_MIN_CONTRAST (config_v5.py)
# so "clear" here means the same thing it means to the existing clarity gate.
BRIGHTNESS_BANDS = [("dark", 0, 100), ("normal", 100, 200), ("bright", 200, 256)]
SHARPNESS_BANDS = [("blurry", 0, 800), ("normal", 800, 3000), ("sharp", 3000, float("inf"))]


def _band(value: float, bands: list[tuple[str, float, float]]) -> str:
    for name, lo, hi in bands:
        if lo <= value < hi:
            return name
    return bands[-1][0]


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _fmt(value: float | None, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}" if pct else f"{value:.2f}"


def summarize(records: list[dict], band_by: str, bands) -> None:
    buckets: dict[str, list[dict]] = {}
    for r in records:
        value = r["quality"].get(band_by)
        if value is None:
            continue
        buckets.setdefault(_band(value, bands), []).append(r)

    order = [name for name, *_ in bands]
    print(f"\n{'bucket':10}{'pages':>7}{'avg conf':>10}{'flag rate':>11}{'indic skip':>12}"
         f"{'paddle t':>10}{'tess t':>9}{'indic t':>9}")
    for name in order:
        rows = buckets.get(name, [])
        if not rows:
            print(f"{name:10}{'(no pages)':>7}")
            continue
        confs = [r["router"]["avg_paddle_confidence"] for r in rows if r.get("router")]
        flagged = _mean([r["flagged"] / r["lines"] for r in rows if r["lines"]])
        skipped = _mean([1.0 if r.get("router") and not r["timings"].get("indicphoto") else 0.0 for r in rows])
        t_paddle = _mean([r["timings"].get("paddle", 0) for r in rows])
        t_tess = _mean([r["timings"].get("tesseract", 0) for r in rows])
        t_indic = _mean([r["timings"].get("indicphoto", 0) for r in rows if r["timings"].get("indicphoto")])
        print(f"{name:10}{len(rows):7}{_fmt(_mean(confs)):>10}{_fmt(flagged, pct=True):>11}"
             f"{_fmt(skipped, pct=True):>12}{_fmt(t_paddle):>10}{_fmt(t_tess):>9}{_fmt(t_indic):>9}")


def engine_win_rates(records: list[dict]) -> None:
    print(f"\n{'engine':12}{'lines seen':>12}{'won':>10}{'win rate':>10}")
    totals = {e: {"present": 0, "won": 0} for e in ENGINES}
    for r in records:
        for e in ENGINES:
            stats = r.get("engine_stats", {}).get(e, {})
            totals[e]["present"] += stats.get("present", 0)
            totals[e]["won"] += stats.get("won", 0)
    for e in ENGINES:
        t = totals[e]
        rate = t["won"] / t["present"] if t["present"] else None
        print(f"{e:12}{t['present']:12}{t['won']:10}{_fmt(rate, pct=True):>10}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--source", choices=["production", "diagnostic", "all"], default="all")
    args = parser.parse_args()

    records = load_records(args.log_path)
    if args.source != "all":
        records = [r for r in records if r.get("source") == args.source]

    if not records:
        print(f"No records in {args.log_path} (source={args.source}). "
             f"Run fuse_ocr_engines.py, a real conversion, or backfill_performance_log.py first.")
        return 1

    print(f"{len(records)} page records ({args.log_path})")
    print("\n=== By brightness ===")
    summarize(records, "brightness", BRIGHTNESS_BANDS)
    print("\n=== By sharpness ===")
    summarize(records, "sharpness", SHARPNESS_BANDS)
    print("\n=== Overall engine win rates (share of lines each engine supplied the chosen text for) ===")
    engine_win_rates(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
