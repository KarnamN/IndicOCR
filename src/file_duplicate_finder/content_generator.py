"""
Content HTML Generator - Generates a standalone content.html
showing the full folder tree with file sizes.

Saved to: <chosen_folder>/content/content.html
"""

import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

try:
    from filename_utils import contains_telugu, transliterate_telugu_to_english, transliterate_english_to_telugu
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from filename_utils import contains_telugu, transliterate_telugu_to_english, transliterate_english_to_telugu


def _nfc(s: str) -> str:
    return unicodedata.normalize('NFC', s)


def _sz(b: int) -> str:
    v = float(b)
    for u in ['B', 'KB', 'MB', 'GB']:
        if v < 1024:
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


def _render_tree_html(node: dict, depth: int = 0) -> str:
    """Recursively render a tree node as HTML list items with dual English/Telugu names."""
    indent = depth * 20
    html = ""
    original_name = node['name']

    if node['type'] == 'dir':
        child_count = len(node.get('children', []))
        icon = "📁"
        
        trans_html = ""
            
        html += f"""
        <li class="tree-dir" style="padding-left:{indent}px;">
            <div class="dir-row" onclick="this.parentElement.classList.toggle('collapsed')">
                <span class="toggle-arrow">▾</span>
                <span class="dir-icon">{icon}</span>
                <span class="dir-name">{_nfc(original_name)}</span>
                {trans_html}
                <span class="dir-size">{node['size_str']}</span>
                <span class="dir-count">{child_count} item{'s' if child_count != 1 else ''}</span>
            </div>
            <ul class="tree-children">"""
        for child in node.get('children', []):
            html += _render_tree_html(child, depth + 1)
        html += """
            </ul>
        </li>"""
    else:
        # File node
        is_dup = node.get('is_duplicate', False)
        is_orig = node.get('is_original', False)

        if is_dup:
            icon = "❌"
            name_class = "file-name dup"
            badge = '<span class="badge dup-badge">DUPLICATE</span>'
        elif is_orig:
            icon = "⭐"
            name_class = "file-name orig"
            badge = '<span class="badge orig-badge">ORIGINAL</span>'
        else:
            icon = "📄"
            name_class = "file-name"
            badge = ""

        # For files, transliterate only the stem to preserve the original extension
        p = Path(original_name)
        stem = p.stem
        ext = p.suffix
        
        has_tel = contains_telugu(stem)
        if has_tel:
            trans_stem = transliterate_telugu_to_english(stem)
        else:
            trans_stem = transliterate_english_to_telugu(stem)
            
        trans_html = ""
        if trans_stem and trans_stem != stem:
            trans_name = trans_stem + ext
            trans_html = f'<span class="trans-name">({_nfc(trans_name)})</span>'

        html += f"""
        <li class="tree-file" style="padding-left:{indent + 20}px;">
            <span class="file-icon">{icon}</span>
            <span class="{name_class}">{_nfc(original_name)}</span>
            {trans_html}
            {badge}
            <span class="file-size">{node['size_str']}</span>
        </li>"""

    return html


def generate_content_html(
    tree: dict,
    root_path: str,
    duplicate_count: int = 0,
    original_count: int = 0,
    total_files: int = 0,
    wasted_str: str = "0 B",
    scan_done: bool = False,
) -> str:
    """
    Generate a self-contained HTML page showing the full folder tree.

    Args:
        tree: Folder tree dict from build_folder_tree()
        root_path: The scanned root path
        duplicate_count: Number of duplicate files (0 if scan not done)
        original_count: Number of original files in duplicate groups
        total_files: Total files scanned
        wasted_str: Human-readable wasted space
        scan_done: Whether a duplicate scan was performed

    Returns:
        HTML string
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tree_items = _render_tree_html(tree, 0)

    scan_summary_html = ""
    if scan_done:
        scan_summary_html = f"""
        <div class="scan-banner">
            <div class="scan-stat"><span class="scan-num">{total_files}</span><span class="scan-lbl">Files Scanned</span></div>
            <div class="scan-stat dup"><span class="scan-num">{duplicate_count}</span><span class="scan-lbl">Duplicates Found</span></div>
            <div class="scan-stat orig"><span class="scan-num">{original_count}</span><span class="scan-lbl">Originals</span></div>
            <div class="scan-stat waste"><span class="scan-num">{wasted_str}</span><span class="scan-lbl">Wasted Space</span></div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Folder Contents – {_nfc(Path(root_path).name)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+Telugu:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0f1117; --s: #1a1d27; --s2: #232635; --bd: #2e3147;
            --ac: #6366f1; --ac2: #8b5cf6; --ok: #10b981; --warn: #f59e0b;
            --err: #ef4444; --tx: #e2e8f0; --txm: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', 'Noto Sans Telugu', system-ui, sans-serif;
            background: var(--bg); color: var(--tx);
            padding: 0; min-height: 100vh;
        }}

        /* ── Header ── */
        .hdr {{
            background: linear-gradient(135deg, #0d1b2a 0%, #1a1042 100%);
            border-bottom: 1px solid var(--bd);
            padding: 24px 32px;
        }}
        .hdr h1 {{
            font-size: 1.5rem; font-weight: 700;
            background: linear-gradient(135deg, var(--ac), var(--ac2));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .hdr .meta {{
            font-size: .8rem; color: var(--txm);
            display: flex; gap: 20px; flex-wrap: wrap; margin-top: 6px;
        }}
        .hdr .meta code {{
            color: #818cf8; font-family: monospace;
            background: rgba(99,102,241,0.1); padding: 2px 6px; border-radius: 4px;
        }}

        /* ── Scan Summary Banner ── */
        .scan-banner {{
            display: flex; gap: 12px; flex-wrap: wrap;
            padding: 16px 32px; background: rgba(99,102,241,0.07);
            border-bottom: 1px solid var(--bd);
        }}
        .scan-stat {{
            display: flex; flex-direction: column; align-items: center;
            background: var(--s); border: 1px solid var(--bd);
            border-radius: 10px; padding: 12px 20px; min-width: 100px;
        }}
        .scan-num {{ font-size: 1.6rem; font-weight: 700; color: var(--ac); }}
        .scan-lbl {{ font-size: .72rem; color: var(--txm); margin-top: 3px; }}
        .scan-stat.dup .scan-num {{ color: var(--err); }}
        .scan-stat.orig .scan-num {{ color: var(--ok); }}
        .scan-stat.waste .scan-num {{ color: var(--warn); font-size: 1.2rem; }}

        /* ── Controls ── */
        .controls {{
            padding: 12px 32px; background: var(--s2);
            border-bottom: 1px solid var(--bd);
            display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
        }}
        .ctrl-btn {{
            background: var(--ac); color: #fff; border: none; cursor: pointer;
            padding: 6px 14px; border-radius: 6px; font-size: .8rem; font-weight: 500;
        }}
        .ctrl-btn:hover {{ background: var(--ac2); }}
        .ctrl-btn.outline {{
            background: transparent; border: 1px solid var(--bd); color: var(--txm);
        }}
        .legend {{
            display: flex; gap: 14px; margin-left: auto; font-size: .78rem; color: var(--txm);
        }}
        .legend span {{ display: flex; align-items: center; gap: 4px; }}

        /* ── Tree ── */
        .tree-wrap {{
            padding: 20px 32px; overflow-x: auto;
        }}
        ul.tree-root, ul.tree-children {{
            list-style: none; padding: 0; margin: 0;
        }}
        .tree-dir {{ margin: 2px 0; }}
        .dir-row {{
            display: flex; align-items: center; gap: 8px;
            padding: 5px 10px; border-radius: 7px; cursor: pointer;
            user-select: none; transition: background .12s;
        }}
        .dir-row:hover {{ background: rgba(99,102,241,0.1); }}
        .toggle-arrow {{ color: #60a5fa; font-size: .72rem; width: 12px; flex-shrink: 0; transition: transform .15s; }}
        .dir-icon {{ font-size: 1rem; }}
        .dir-name {{
            font-weight: 600; color: #93c5fd;
            font-family: 'Noto Sans Telugu', 'Inter', sans-serif;
        }}
        .trans-name {{
            font-size: 0.82rem;
            color: #fbbf24;
            font-weight: 500;
            margin-left: 8px;
            font-family: 'Noto Sans Telugu', 'Inter', sans-serif;
        }}
        .dir-size {{ font-size: .75rem; color: var(--txm); margin-left: 6px; }}
        .dir-count {{ font-size: .7rem; color: var(--tx); background: var(--bd); padding: 1px 6px; border-radius: 99px; }}
        .tree-dir.collapsed > .tree-children {{ display: none; }}
        .tree-dir.collapsed .toggle-arrow {{ transform: rotate(-90deg); }}

        .tree-file {{
            display: flex; align-items: center; gap: 8px;
            padding: 3px 10px; border-radius: 6px; margin: 1px 0;
            transition: background .1s;
        }}
        .tree-file:hover {{ background: rgba(255,255,255,0.03); }}
        .file-icon {{ font-size: .9rem; flex-shrink: 0; }}
        .file-name {{
            color: var(--tx); font-size: .84rem;
            font-family: 'Noto Sans Telugu', 'Inter', monospace;
        }}
        .file-name.dup {{ color: #f87171; }}
        .file-name.orig {{ color: #34d399; }}
        .file-size {{ font-size: .72rem; color: var(--txm); margin-left: 4px; white-space: nowrap; }}

        .badge {{
            font-size: .62rem; font-weight: 700; padding: 1px 7px;
            border-radius: 99px; text-transform: uppercase; letter-spacing: .04em;
            flex-shrink: 0;
        }}
        .dup-badge {{
            background: rgba(220,38,38,0.2); color: #f87171;
            border: 1px solid rgba(248,113,113,0.3);
        }}
        .orig-badge {{
            background: rgba(5,150,105,0.2); color: #34d399;
            border: 1px solid rgba(52,211,153,0.3);
        }}

        /* ── Footer ── */
        .footer {{
            text-align: center; padding: 20px; color: var(--txm);
            font-size: .75rem; border-top: 1px solid var(--bd); margin-top: 20px;
        }}

        /* ── Search highlight ── */
        .hl {{ background: rgba(245,158,11,0.3); border-radius: 2px; }}
    </style>
</head>
<body>

<div class="hdr">
    <h1>📂 Folder Contents</h1>
    <div class="meta">
        <span>Path: <code>{_nfc(root_path)}</code></span>
        <span>Generated: {now}</span>
        {'<span style="color:#10b981;font-weight:600;">✓ Duplicate scan applied</span>' if scan_done else ''}
    </div>
</div>

{scan_summary_html}

<div class="controls">
    <button class="ctrl-btn" onclick="expandAll()">Expand All</button>
    <button class="ctrl-btn outline" onclick="collapseAll()">Collapse All</button>
    <input id="searchBox" type="text" placeholder="Search files &amp; folders…"
        oninput="doSearch(this.value)"
        style="background:rgba(255,255,255,0.07);border:1px solid var(--bd);
               color:var(--tx);border-radius:6px;padding:5px 12px;font-size:.82rem;
               outline:none;width:220px;">
    <div class="legend">
        <span>⭐ <span style="color:#34d399">Original</span></span>
        <span>❌ <span style="color:#f87171">Duplicate</span></span>
        <span>📄 <span>File</span></span>
        <span>📁 <span style="color:#60a5fa">Folder</span></span>
    </div>
</div>

<div class="tree-wrap">
    <ul class="tree-root">
        {tree_items}
    </ul>
</div>

<div class="footer">
    File Duplicate Finder &nbsp;•&nbsp; Folder Contents Report &nbsp;•&nbsp; {now}
</div>

<script>
    function expandAll() {{
        document.querySelectorAll('.tree-dir.collapsed').forEach(el => el.classList.remove('collapsed'));
    }}
    function collapseAll() {{
        document.querySelectorAll('.tree-dir:not(.collapsed)').forEach(el => el.classList.add('collapsed'));
    }}
    function doSearch(q) {{
        // Clear existing highlights
        document.querySelectorAll('.hl').forEach(el => {{
            el.outerHTML = el.textContent;
        }});
        if (!q.trim()) return;
        const re = new RegExp(q.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&'), 'gi');
        document.querySelectorAll('.file-name, .dir-name, .trans-name').forEach(el => {{
            if (re.test(el.textContent)) {{
                el.innerHTML = el.textContent.replace(re, m => `<span class="hl">${{m}}</span>`);
                // Expand parent dirs
                let p = el.closest('.tree-dir')?.parentElement?.closest('.tree-dir');
                while (p) {{ p.classList.remove('collapsed'); p = p.parentElement?.closest('.tree-dir'); }}
            }}
        }});
    }}
</script>
</body>
</html>"""


def save_content_html(
    tree: dict,
    root_path: str,
    duplicate_count: int = 0,
    original_count: int = 0,
    total_files: int = 0,
    wasted_str: str = "0 B",
    scan_done: bool = False,
) -> str:
    """
    Save content.html to <root_path>/content/content.html.

    Returns:
        Absolute path to the saved file.
    """
    content_dir = os.path.join(root_path, "content")
    os.makedirs(content_dir, exist_ok=True)
    out_path = os.path.join(content_dir, "content.html")

    html = generate_content_html(
        tree=tree,
        root_path=root_path,
        duplicate_count=duplicate_count,
        original_count=original_count,
        total_files=total_files,
        wasted_str=wasted_str,
        scan_done=scan_done,
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return out_path
