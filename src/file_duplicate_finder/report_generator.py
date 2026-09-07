"""
Report Generator - Produces HTML and CSV reports of duplicate scan results.
"""

import os
import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from file_duplicate_finder.duplicate_detector import ScanResult

logger = logging.getLogger(__name__)

try:
    from filename_utils import contains_telugu, transliterate_telugu_to_english, transliterate_english_to_telugu
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from filename_utils import contains_telugu, transliterate_telugu_to_english, transliterate_english_to_telugu


def _get_dual_name(name: str) -> str:
    """Format file or folder name in both English and Telugu if possible."""
    p = Path(name)
    stem = p.stem
    ext = p.suffix
    has_tel = contains_telugu(stem)
    if has_tel:
        trans_stem = transliterate_telugu_to_english(stem)
    else:
        trans_stem = transliterate_english_to_telugu(stem)
    if trans_stem and trans_stem != stem:
        return f'{name} <span class="rpt-trans-name">({trans_stem}{ext})</span>'
    return name


def _sz(b: int) -> str:
    v = float(b)
    for u in ['B', 'KB', 'MB', 'GB']:
        if v < 1024:
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


def generate_html_report(
    scan_result: ScanResult,
    moved_files: Optional[List[dict]] = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    moved_paths = {m['source'] for m in (moved_files or [])}

    group_html = ""
    for i, g in enumerate(scan_result.groups, 1):
        dup_rows = ""
        for d in g.duplicates:
            badge = '<span class="rpt-badge rpt-moved">MOVED</span>' if d.path in moved_paths else ''
            dup_rows += f"""<tr class="rpt-dup">
                <td>📄</td><td>{_get_dual_name(d.name)}</td>
                <td class="rpt-path">{d.parent_dir}</td>
                <td>{_sz(d.size)}</td>
                <td>Duplicate {badge}</td></tr>"""

        group_html += f"""
        <div class="rpt-group">
          <div class="rpt-group-hdr">
            <span class="rpt-num">#{i}</span>
            <span class="rpt-gname">{_get_dual_name(g.normalized_name + g.extension)}</span>
            <span class="rpt-gcnt">{g.total_files} files</span>
            <span class="rpt-stat">📦 {g.size_str} each</span>
            <span class="rpt-stat rpt-waste">🗑 {g.wasted_str} wasted</span>
          </div>
          <table class="rpt-table">
            <thead><tr><th></th><th>Filename</th><th>Location</th><th>Size</th><th>Status</th></tr></thead>
            <tbody>
              <tr class="rpt-orig"><td>⭐</td><td>{_get_dual_name(g.original.name)}</td>
                <td class="rpt-path">{g.original.parent_dir}</td>
                <td>{_sz(g.original.size)}</td>
                <td><span class="rpt-badge rpt-original">ORIGINAL</span></td></tr>
              {dup_rows}
            </tbody>
          </table>
        </div>"""

    moved_section = ""
    if moved_files:
        rows = "".join(
            f"<tr><td>{m['name']}</td><td class='rpt-path'>{m['source']}</td>"
            f"<td class='rpt-path'>{m['dest']}</td><td>{_sz(m['size'])}</td>"
            f"<td>{m['group_name']}</td></tr>"
            for m in moved_files
        )
        moved_section = f"""
        <h2 style="margin-top:32px">📦 Moved Files Log</h2>
        <table class="rpt-table" style="border:1px solid #2e3147;border-radius:8px">
          <thead><tr><th>Filename</th><th>Original Path</th><th>Moved To</th><th>Size</th><th>Group</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><title>Duplicate File Report</title>
<style>
:root{{--bg:#0f1117;--s:#1a1d27;--s2:#232635;--bd:#2e3147;--ac:#6366f1;--ac2:#8b5cf6;
--ok:#10b981;--warn:#f59e0b;--err:#ef4444;--tx:#e2e8f0;--txm:#94a3b8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);padding:24px;line-height:1.5}}
.rpt-hdr{{text-align:center;padding:32px;background:linear-gradient(135deg,var(--s),var(--s2));
  border-radius:16px;border:1px solid var(--bd);margin-bottom:28px}}
.rpt-hdr h1{{font-size:1.8rem;background:linear-gradient(135deg,var(--ac),var(--ac2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}}
.rpt-hdr p{{color:var(--txm);font-size:.85rem}}
.rpt-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:28px}}
.rpt-stat-card{{background:var(--s);border:1px solid var(--bd);border-radius:10px;padding:16px;text-align:center}}
.rpt-stat-card .n{{font-size:1.8rem;font-weight:700;color:var(--ac)}}
.rpt-stat-card .l{{font-size:.75rem;color:var(--txm);margin-top:4px}}
.rpt-stat-card.d .n{{color:var(--err)}}.rpt-stat-card.w .n{{color:var(--warn)}}.rpt-stat-card.ok .n{{color:var(--ok)}}
h2{{font-size:1.1rem;margin-bottom:14px}}
.rpt-group{{background:var(--s);border:1px solid var(--bd);border-radius:10px;margin-bottom:16px;overflow:hidden}}
.rpt-group-hdr{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 16px;
  background:var(--s2);border-bottom:1px solid var(--bd)}}
.rpt-num{{background:var(--ac);color:#fff;font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:99px}}
.rpt-gname{{font-weight:600}}
.rpt-gcnt{{font-size:.72rem;color:var(--txm);background:var(--bd);padding:2px 8px;border-radius:99px}}
.rpt-stat{{font-size:.78rem;color:var(--txm)}}
.rpt-waste{{color:var(--warn)}}
.rpt-table{{width:100%;border-collapse:collapse;font-size:.82rem}}
.rpt-table th{{padding:9px 12px;text-align:left;color:var(--txm);font-weight:500;border-bottom:1px solid var(--bd);
  font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}}
.rpt-table td{{padding:9px 12px;border-bottom:1px solid var(--bd);vertical-align:middle}}
.rpt-table tr:last-child td{{border-bottom:none}}
.rpt-orig{{background:rgba(5,150,105,.05)}}
.rpt-dup{{background:rgba(220,38,38,.03)}}
.rpt-path{{color:var(--txm);font-family:monospace;font-size:.75rem;word-break:break-all}}
.rpt-badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.68rem;font-weight:700;text-transform:uppercase}}
.rpt-original{{background:rgba(5,150,105,.2);color:#10b981;border:1px solid rgba(16,185,129,.3)}}
.rpt-moved{{background:rgba(99,102,241,.2);color:#818cf8;border:1px solid rgba(129,140,248,.3)}}
.rpt-trans-name{{font-size:.78rem;color:#fbbf24;font-weight:500;margin-left:6px}}
.rpt-footer{{text-align:center;margin-top:36px;color:var(--txm);font-size:.78rem}}
@media print{{body{{background:#fff;color:#000}}.rpt-group{{page-break-inside:avoid}}}}
</style></head><body>
<div class="rpt-hdr">
  <h1>🔍 Duplicate File Report</h1>
  <p>Generated: {now} &nbsp;|&nbsp; Scanned: <code>{scan_result.root_path}</code></p>
</div>
<div class="rpt-stats">
  <div class="rpt-stat-card"><div class="n">{scan_result.total_files}</div><div class="l">Files Scanned</div></div>
  <div class="rpt-stat-card d"><div class="n">{scan_result.total_groups}</div><div class="l">Duplicate Groups</div></div>
  <div class="rpt-stat-card d"><div class="n">{scan_result.total_duplicate_files}</div><div class="l">Duplicate Files</div></div>
  <div class="rpt-stat-card w"><div class="n">{scan_result.wasted_str}</div><div class="l">Wasted Space</div></div>
  {'<div class="rpt-stat-card ok"><div class="n">' + str(len(moved_files)) + '</div><div class="l">Files Moved</div></div>' if moved_files else ''}
</div>
<h2>🗂 Duplicate Groups ({scan_result.total_groups} found)</h2>
{group_html or '<p style="color:var(--txm);text-align:center;padding:40px">No duplicates found.</p>'}
{moved_section}
<div class="rpt-footer">File Duplicate Finder &nbsp;•&nbsp; {now}</div>
</body></html>"""


def generate_csv_report(scan_result: ScanResult, moved_files: Optional[List[dict]] = None) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Group#", "Normalized Name", "Extension", "File Size (bytes)",
                "Role", "Filename", "Full Path", "Directory", "Moved To"])
    moved_map = {m['source']: m['dest'] for m in (moved_files or [])}
    for i, g in enumerate(scan_result.groups, 1):
        w.writerow([i, g.normalized_name, g.extension, g.size,
                    "ORIGINAL", g.original.name, g.original.path, g.original.parent_dir, ""])
        for d in g.duplicates:
            w.writerow([i, g.normalized_name, g.extension, g.size,
                        "DUPLICATE", d.name, d.path, d.parent_dir, moved_map.get(d.path, "")])
    return out.getvalue()


def save_report(
    scan_result: ScanResult,
    output_dir: str,
    moved_files: Optional[List[dict]] = None,
) -> dict:
    """Save HTML + CSV reports. Returns {'html': path, 'csv': path}."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"duplicate_report_{ts}"
    html_path = os.path.join(output_dir, f"{base}.html")
    csv_path = os.path.join(output_dir, f"{base}.csv")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_html_report(scan_result, moved_files))
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        f.write(generate_csv_report(scan_result, moved_files))
    logger.info(f"Reports saved → {html_path}, {csv_path}")
    return {'html': html_path, 'csv': csv_path}
