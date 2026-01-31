"""SQLite-based file finder using Google Drive for Desktop's internal database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from gdfid_finder.utils import get_google_drive_base_paths

# DriveFS application support directory
_DRIVEFS_BASE = Path.home() / "Library" / "Application Support" / "Google" / "DriveFS"

# Metadata database filename
_METADATA_DB = "metadata_sqlite_db"

# Possible parent directories for root segments that aren't direct children
# of the CloudStorage mount point.
# Empty string MUST be first: マイドライブ/My Drive are direct children of the
# mount point, while other roots are nested under prefix directories.
_ROOT_PREFIXES = [
    "",  # Direct child (e.g. マイドライブ, My Drive)
    "その他のパソコン",
    "Computers",
    "共有ドライブ",
    "Shared drives",
]

# Recursive CTE to build the full path from a cloud_id.
# Traverses stable_ids -> items -> stable_parents upward to the root.
_PATH_QUERY = """\
WITH RECURSIVE path_cte(stable_id, local_title, parent_id, depth) AS (
    SELECT i.stable_id, i.local_title, sp.parent_stable_id, 0
    FROM stable_ids s
    JOIN items i ON s.stable_id = i.stable_id
    LEFT JOIN stable_parents sp ON sp.item_stable_id = i.stable_id
    WHERE s.cloud_id = ?
    UNION ALL
    SELECT i.stable_id, i.local_title, sp.parent_stable_id, p.depth + 1
    FROM path_cte p
    JOIN items i ON i.stable_id = p.parent_id
    LEFT JOIN stable_parents sp ON sp.item_stable_id = i.stable_id
    WHERE p.parent_id IS NOT NULL AND p.depth < 50  -- safety limit; Google Drive nesting rarely exceeds ~10
)
SELECT local_title FROM path_cte ORDER BY depth DESC
"""


def find_file_by_id_via_db(file_id: str) -> Optional[Path]:
    """Find a Google Drive file by its file ID using the DriveFS SQLite database.

    Queries the internal metadata database that Google Drive for Desktop
    maintains, reconstructs the file path via parent traversal, and
    verifies the path exists on disk.

    Args:
        file_id: Google Drive file ID to search for.

    Returns:
        Path to the file if found, None otherwise.
    """
    db_paths = _get_drivefs_db_paths()
    if not db_paths:
        return None

    base_paths = get_google_drive_base_paths()
    if not base_paths:
        return None

    for db_path in db_paths:
        segments = _query_path_segments(db_path, file_id)
        if not segments:
            continue

        for base_path in base_paths:
            path = _resolve_path(base_path, segments)
            if path is not None:
                return path

    return None


def _get_drivefs_db_paths() -> List[Path]:
    """Find all DriveFS metadata SQLite database paths.

    Scans the DriveFS application support directory for account-specific
    metadata databases.

    Returns:
        List of paths to metadata_sqlite_db files.
    """
    if not _DRIVEFS_BASE.exists():
        return []

    db_paths: List[Path] = []
    try:
        for entry in os.scandir(_DRIVEFS_BASE):
            if not entry.is_dir():
                continue
            db_file = Path(entry.path) / _METADATA_DB
            if db_file.exists():
                db_paths.append(db_file)
    except PermissionError:
        pass

    return db_paths


def _query_path_segments(db_path: Path, cloud_id: str) -> Optional[List[str]]:
    """Query path segments from the DriveFS metadata database.

    Uses a recursive CTE to traverse the parent chain from the target
    file up to the root, producing an ordered list of path segments.

    Args:
        db_path: Path to the metadata_sqlite_db file.
        cloud_id: Google Drive file/folder ID.

    Returns:
        List of path segments from root to target, or None if not found.
    """
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            timeout=1,
        )
        try:
            cursor = conn.execute(_PATH_QUERY, (cloud_id,))
            segments = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

        if not segments or None in segments:
            return None
        return segments
    except (sqlite3.Error, OSError):
        return None


def _resolve_path(base_path: Path, segments: List[str]) -> Optional[Path]:
    """Resolve path segments to a full filesystem path.

    The first segment from the DB is the drive root name (e.g. マイドライブ).
    Depending on the drive type, this may be a direct child of the
    CloudStorage mount point, or nested under a prefix directory
    (e.g. その他のパソコン, 共有ドライブ).

    Args:
        base_path: Google Drive CloudStorage mount point.
        segments: Path segments from DB (root to target).

    Returns:
        Full Path if it exists on disk, None otherwise.
    """
    relative = Path(*segments)

    for prefix in _ROOT_PREFIXES:
        candidate = base_path / prefix / relative if prefix else base_path / relative

        if candidate.exists():
            return candidate

    return None
