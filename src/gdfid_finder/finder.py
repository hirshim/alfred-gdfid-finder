"""File finder logic for Google Drive files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from gdfid_finder.utils import get_google_drive_base_paths

# Extended attribute name used by Google Drive for Desktop to store file IDs
XATTR_ITEM_ID = "com.google.drivefs.item-id#S"


def find_file_by_id(file_id: str) -> Optional[Path]:
    """Find a Google Drive file by its file ID.

    Searches through Google Drive for Desktop mount points to find
    a file or folder matching the given ID.

    Args:
        file_id: Google Drive file ID to search for.

    Returns:
        Path to the file if found, None otherwise.
    """
    base_paths = get_google_drive_base_paths()
    if not base_paths:
        return None

    for base_path in base_paths:
        found = _search_in_path(base_path, file_id)
        if found:
            return found

    return None


def _search_in_path(base_path: Path, file_id: str) -> Optional[Path]:
    """Search for a file ID within a given path.

    Recursively searches through the directory tree, checking the
    extended attribute 'com.google.drivefs.item-id#S' on each file/folder.

    Args:
        base_path: Base path to search in.
        file_id: File ID to search for.

    Returns:
        Path if found, None otherwise.
    """
    # Check the base path itself
    if _get_file_id(base_path) == file_id:
        return base_path

    # Search in common locations first (マイドライブ, My Drive)
    priority_dirs = ["マイドライブ", "My Drive", "共有ドライブ", "Shared drives"]
    for dir_name in priority_dirs:
        priority_path = base_path / dir_name
        if priority_path.exists():
            found = _search_recursive(priority_path, file_id)
            if found:
                return found

    # Search other directories
    try:
        for child in base_path.iterdir():
            if child.name.startswith(".") or child.name in priority_dirs:
                continue
            if child.is_dir():
                found = _search_recursive(child, file_id)
                if found:
                    return found
    except PermissionError:
        pass

    return None


def _search_recursive(path: Path, file_id: str) -> Optional[Path]:
    """Recursively search for a file ID.

    Args:
        path: Path to search in.
        file_id: File ID to search for.

    Returns:
        Path if found, None otherwise.
    """
    # Check current path
    if _get_file_id(path) == file_id:
        return path

    # If it's a directory, search children
    if path.is_dir():
        try:
            for child in path.iterdir():
                # Skip hidden files/directories for performance
                if child.name.startswith("."):
                    continue
                found = _search_recursive(child, file_id)
                if found:
                    return found
        except PermissionError:
            pass

    return None


def _get_file_id(path: Path) -> Optional[str]:
    """Get the Google Drive file ID from a path's extended attributes.

    Args:
        path: Path to check.

    Returns:
        File ID string if found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["xattr", "-p", XATTR_ITEM_ID, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
