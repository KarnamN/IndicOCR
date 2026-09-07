"""
Folder Tree Builder - Builds a nested tree of a directory's contents
with file sizes, for display in the UI.

Supports Telugu, English, or mixed filenames (Unicode NFC).
"""

import os
import unicodedata
from pathlib import Path
from typing import Optional, Set

from file_duplicate_finder.scanner import SKIP_DIRS, SKIP_FILES


def _nfc(s: str) -> str:
    return unicodedata.normalize('NFC', s)


def _size_str(b: int) -> str:
    v = float(b)
    for u in ['B', 'KB', 'MB', 'GB']:
        if v < 1024:
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


def build_folder_tree(
    root_path: str,
    duplicate_paths: Optional[Set[str]] = None,
    original_paths: Optional[Set[str]] = None,
    max_depth: int = 12,
) -> dict:
    """
    Recursively build a folder tree dict for the given root_path.

    Args:
        root_path:       The folder to build the tree for.
        duplicate_paths: Set of absolute paths that are duplicates (marked red).
        original_paths:  Set of absolute paths that are originals (marked green).
        max_depth:       Maximum recursion depth.

    Returns:
        Nested dict tree:
        {
            "name": "FolderName",
            "path": "/abs/path",
            "type": "dir" | "file",
            "size": <bytes>,
            "size_str": "1.2 MB",
            "is_duplicate": bool,
            "is_original": bool,
            "children": [...]   # only for dirs
        }
    """
    dup_paths = duplicate_paths or set()
    orig_paths = original_paths or set()
    root = Path(root_path).resolve()

    def _build(p: Path, depth: int) -> Optional[dict]:
        if depth > max_depth:
            return None

        name = _nfc(p.name)
        abs_path = str(p)

        if p.is_file():
            if p.name in SKIP_FILES or p.name.startswith('.'):
                return None
            try:
                size = p.stat().st_size
            except (OSError, PermissionError):
                size = 0
            return {
                'name': name,
                'path': abs_path,
                'type': 'file',
                'size': size,
                'size_str': _size_str(size),
                'is_duplicate': abs_path in dup_paths,
                'is_original': abs_path in orig_paths,
            }

        if p.is_dir():
            if p.name in SKIP_DIRS or p.name.startswith('.') or p.name.startswith('_DUPLICATES'):
                return None
            children = []
            total_size = 0
            try:
                entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), _nfc(x.name)))
                for child in entries:
                    child_node = _build(child, depth + 1)
                    if child_node:
                        children.append(child_node)
                        total_size += child_node.get('size', 0)
            except PermissionError:
                pass

            return {
                'name': name,
                'path': abs_path,
                'type': 'dir',
                'size': total_size,
                'size_str': _size_str(total_size),
                'children': children,
                'is_duplicate': False,
                'is_original': False,
            }

        return None

    return _build(root, 0) or {
        'name': _nfc(root.name),
        'path': str(root),
        'type': 'dir',
        'size': 0,
        'size_str': '0 B',
        'children': [],
        'is_duplicate': False,
        'is_original': False,
    }
