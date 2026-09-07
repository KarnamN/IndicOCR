"""
File Mover - Moves duplicate files to a destination folder,
preserving relative directory structure.
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

from file_duplicate_finder.duplicate_detector import ScanResult

logger = logging.getLogger(__name__)


def _safe_dest(dest_path: str) -> str:
    """If dest already exists, append _conflict<n> to avoid overwriting."""
    if not os.path.exists(dest_path):
        return dest_path
    p = Path(dest_path)
    n = 1
    while True:
        candidate = p.parent / f"{p.stem}_conflict{n}{p.suffix}"
        if not candidate.exists():
            return str(candidate)
        n += 1


def move_duplicates(
    scan_result: ScanResult,
    dest_folder: Optional[str] = None,
    dry_run: bool = False,
    selected_keys: Optional[List[str]] = None,
) -> Tuple[List[dict], List[dict]]:
    """
    Move duplicate files (not originals) to dest_folder.

    Returns:
        (moved_list, error_list)
    """
    if dest_folder is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_folder = os.path.join(scan_result.root_path, f"_DUPLICATES_{ts}")

    moved: List[dict] = []
    errors: List[dict] = []

    groups = scan_result.groups
    if selected_keys:
        key_set = set(selected_keys)
        groups = [g for g in groups if g.group_key in key_set]

    for group in groups:
        for dup in group.duplicates:
            # Mirror directory structure
            rel = os.path.relpath(dup.path, scan_result.root_path)
            dest_path = _safe_dest(os.path.join(dest_folder, rel))

            try:
                if not dry_run:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.move(dup.path, dest_path)

                moved.append({
                    'source': dup.path,
                    'dest': dest_path,
                    'name': dup.name,
                    'size': dup.size,
                    'size_str': dup.size_human(),
                    'group_name': group.normalized_name + group.extension,
                    'original': group.original.path,
                    'dry_run': dry_run,
                })
                logger.info(f"{'[DRY]' if dry_run else 'MOVED'} {dup.path} → {dest_path}")
            except Exception as e:
                logger.error(f"Failed to move {dup.path}: {e}")
                errors.append({'source': dup.path, 'dest': dest_path, 'error': str(e)})

    return moved, errors
