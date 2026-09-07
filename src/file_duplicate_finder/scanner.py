"""
Scanner - Recursively collects file metadata from a directory.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Callable

from file_duplicate_finder.name_normalizer import normalize_key, get_extension

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules',
    'venv', 'wenv', 'myenv', '.venv', 'env',
    '$RECYCLE.BIN', 'System Volume Information',
    '_DUPLICATES',  # skip our own output folder prefix
}

SKIP_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


@dataclass
class FileInfo:
    path: str
    name: str
    stem: str
    extension: str
    size: int
    norm_key: str       # normalized_stem + extension (lowercase)
    parent_dir: str

    def size_human(self) -> str:
        b = float(self.size)
        for u in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB"


def scan_directory(
    root_path: str,
    extra_skip_dirs: Optional[set] = None,
    extensions_filter: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> List[FileInfo]:
    """
    Recursively scan root_path and return list of FileInfo objects.
    Skips venv/system dirs, hidden files, and optionally filters by extension.
    """
    root = Path(root_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root_path}")
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root_path}")

    skip = SKIP_DIRS.copy()
    if extra_skip_dirs:
        skip.update(extra_skip_dirs)

    results: List[FileInfo] = []
    count = 0

    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Prune dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in skip
            and not d.startswith('.')
            and not d.startswith('_DUPLICATES')
        ]

        for filename in filenames:
            if filename in SKIP_FILES or filename.startswith('.'):
                continue

            ext = get_extension(filename)
            if extensions_filter and ext not in extensions_filter:
                continue

            filepath = Path(dirpath) / filename
            try:
                size = filepath.stat().st_size
            except (OSError, PermissionError) as e:
                logger.warning(f"Skip {filepath}: {e}")
                continue

            results.append(FileInfo(
                path=str(filepath),
                name=filename,
                stem=Path(filename).stem,
                extension=ext,
                size=size,
                norm_key=normalize_key(filename),
                parent_dir=str(dirpath),
            ))
            count += 1
            if progress_callback:
                progress_callback(str(filepath), count)

    logger.info(f"Scanned {count} files in {root_path}")
    return results
