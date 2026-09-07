"""
file_search_copier.py - Recursively searches files by name pattern and copies them to a destination folder.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules',
    'venv', 'wenv', 'myenv', '.venv', 'env',
    '$RECYCLE.BIN', 'System Volume Information',
}

SKIP_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


def size_human(size_in_bytes: int) -> str:
    """Helper to convert bytes to human readable format."""
    b = float(size_in_bytes)
    for u in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


def search_files_by_name(
    source_dir: str,
    query_word: str,
    case_sensitive: bool = False
) -> List[Dict[str, Any]]:
    """
    Recursively scans source_dir for files matching query_word in their names.
    Skips common venv/system/hidden directories.
    
    Returns a list of dicts with file metadata.
    """
    root = Path(source_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not root.is_dir():
        raise ValueError(f"Source path is not a directory: {source_dir}")

    results: List[Dict[str, Any]] = []
    
    import unicodedata
    
    # Pre-process query
    q = query_word if case_sensitive else query_word.lower()
    q_norm = unicodedata.normalize('NFC', q)

    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Prune dirs in-place to avoid scanning heavy/system dirs
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith('.')
        ]

        for filename in filenames:
            if filename in SKIP_FILES or filename.startswith('.'):
                continue

            match_name = filename if case_sensitive else filename.lower()
            match_name_norm = unicodedata.normalize('NFC', match_name)
            if q_norm in match_name_norm:
                filepath = Path(dirpath) / filename
                try:
                    size = filepath.stat().st_size
                except (OSError, PermissionError) as e:
                    logger.warning(f"Skip {filepath}: {e}")
                    continue

                results.append({
                    'path': str(filepath),
                    'name': filename,
                    'size': size,
                    'size_str': size_human(size),
                    'parent_dir': str(dirpath),
                    'relative_path': os.path.relpath(str(filepath), str(root))
                })

    logger.info(f"Search found {len(results)} matches for '{query_word}' in {source_dir}")
    return results


def copy_files_to_dest(
    files_list: List[Dict[str, Any]],
    dest_dir: str,
    dry_run: bool = False,
    rename_collisions: bool = True
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Copies matched files to dest_dir.
    
    Returns:
        (copied_list, error_list)
    """
    dest = Path(dest_dir).resolve()
    copied: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    for file_info in files_list:
        src_path = Path(file_info['path'])
        if not src_path.exists():
            errors.append({
                'source': file_info['path'],
                'dest': '',
                'error': 'Source file does not exist'
            })
            continue

        filename = file_info['name']
        target_path = dest / filename

        # Handle collisions
        if target_path.exists() and rename_collisions:
            stem = src_path.stem
            suffix = src_path.suffix
            counter = 1
            while True:
                candidate = dest / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    target_path = candidate
                    break
                counter += 1

        try:
            if not dry_run:
                shutil.copy2(src_path, target_path)
            
            copied.append({
                'source': file_info['path'],
                'dest': str(target_path),
                'name': target_path.name,
                'size': file_info['size'],
                'size_str': file_info['size_str'],
                'collision_renamed': target_path.name != filename,
                'dry_run': dry_run
            })
            logger.info(f"{'[DRY]' if dry_run else 'COPIED'} {src_path} → {target_path}")
        except Exception as e:
            logger.error(f"Failed to copy {src_path} to {target_path}: {e}")
            errors.append({
                'source': file_info['path'],
                'dest': str(target_path),
                'error': str(e)
            })

    return copied, errors
