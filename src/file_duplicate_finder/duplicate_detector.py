"""
Duplicate Detector - Groups files by (normalized_key, size) to find duplicates.

The 'original' in each group is the file whose stem is already clean
(no copy suffix), or the shortest/alphabetically-first name.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple

from file_duplicate_finder.scanner import FileInfo
from file_duplicate_finder.name_normalizer import normalize_stem

logger = logging.getLogger(__name__)


def _size_str(b: int) -> str:
    v = float(b)
    for u in ['B', 'KB', 'MB', 'GB']:
        if v < 1024:
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


@dataclass
class DuplicateGroup:
    group_key: str
    normalized_name: str
    extension: str
    size: int
    original: FileInfo
    duplicates: List[FileInfo]

    @property
    def total_files(self) -> int:
        return 1 + len(self.duplicates)

    @property
    def wasted_bytes(self) -> int:
        return self.size * len(self.duplicates)

    @property
    def size_str(self) -> str:
        return _size_str(self.size)

    @property
    def wasted_str(self) -> str:
        return _size_str(self.wasted_bytes)

    def to_dict(self) -> dict:
        return {
            'group_key': self.group_key,
            'normalized_name': self.normalized_name,
            'extension': self.extension,
            'size': self.size,
            'size_str': self.size_str,
            'wasted_bytes': self.wasted_bytes,
            'wasted_str': self.wasted_str,
            'total_files': self.total_files,
            'original': {
                'path': self.original.path,
                'name': self.original.name,
                'parent_dir': self.original.parent_dir,
                'size_str': self.original.size_human(),
            },
            'duplicates': [
                {
                    'path': d.path,
                    'name': d.name,
                    'parent_dir': d.parent_dir,
                    'size_str': d.size_human(),
                }
                for d in self.duplicates
            ],
        }


@dataclass
class ScanResult:
    root_path: str
    total_files: int
    total_groups: int
    total_duplicate_files: int
    total_wasted_bytes: int
    groups: List[DuplicateGroup]

    @property
    def wasted_str(self) -> str:
        return _size_str(self.total_wasted_bytes)

    def to_dict(self) -> dict:
        return {
            'root_path': self.root_path,
            'total_files': self.total_files,
            'total_groups': self.total_groups,
            'total_duplicate_files': self.total_duplicate_files,
            'total_wasted_bytes': self.total_wasted_bytes,
            'wasted_str': self.wasted_str,
            'groups': [g.to_dict() for g in self.groups],
        }


def _pick_original(files: List[FileInfo]) -> Tuple[FileInfo, List[FileInfo]]:
    """Pick the cleanest-named file as original; rest are duplicates."""
    def score(f: FileInfo):
        normalized = normalize_stem(f.stem)
        is_clean = normalized.lower() == f.stem.lower().strip()
        return (0 if is_clean else 1, len(f.stem), f.path)

    sorted_files = sorted(files, key=score)
    return sorted_files[0], sorted_files[1:]


def detect_duplicates(files: List[FileInfo], root_path: str) -> ScanResult:
    """
    Group files by (norm_key, size). Groups with 2+ files are duplicates.
    """
    groups: Dict[Tuple[str, int], List[FileInfo]] = defaultdict(list)
    for f in files:
        groups[(f.norm_key, f.size)].append(f)

    dup_groups: List[DuplicateGroup] = []
    total_dups = 0
    total_wasted = 0

    for (norm_key, size), group_files in groups.items():
        if len(group_files) < 2:
            continue

        original, duplicates = _pick_original(group_files)
        p = Path(norm_key)

        g = DuplicateGroup(
            group_key=f"{norm_key}||{size}",
            normalized_name=p.stem,
            extension=p.suffix,
            size=size,
            original=original,
            duplicates=duplicates,
        )
        dup_groups.append(g)
        total_dups += len(duplicates)
        total_wasted += g.wasted_bytes

    dup_groups.sort(key=lambda g: g.wasted_bytes, reverse=True)

    return ScanResult(
        root_path=root_path,
        total_files=len(files),
        total_groups=len(dup_groups),
        total_duplicate_files=total_dups,
        total_wasted_bytes=total_wasted,
        groups=dup_groups,
    )
