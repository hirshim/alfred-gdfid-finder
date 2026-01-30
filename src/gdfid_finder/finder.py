"""File finder logic for Google Drive files."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Optional, Set

from gdfid_finder.utils import get_google_drive_base_paths

# Extended attribute name used by Google Drive for Desktop to store file IDs
XATTR_ITEM_ID = "com.google.drivefs.item-id#S"

# Pre-encoded attribute name (avoid per-file encoding overhead)
_XATTR_BYTES = XATTR_ITEM_ID.encode("utf-8")

# Fixed-size buffer for getxattr (Google Drive file IDs are ~40-50 chars)
_XATTR_BUF_SIZE = 256
_xattr_buf = ctypes.create_string_buffer(_XATTR_BUF_SIZE)

# Load C library for direct xattr access (avoids subprocess overhead)
_libc_name = ctypes.util.find_library("c")
_libc = ctypes.CDLL(_libc_name) if _libc_name else None

if _libc is not None:
    # macOS getxattr(path, name, value, size, position, options)
    _libc.getxattr.restype = ctypes.c_ssize_t
    _libc.getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]


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

    Iteratively searches through the directory tree, checking the
    extended attribute 'com.google.drivefs.item-id#S' on each file/folder.
    Detects symlink loops via resolved path tracking.

    Args:
        base_path: Base path to search in.
        file_id: File ID to search for.

    Returns:
        Path if found, None otherwise.
    """
    # Check the base path itself
    if _get_file_id(base_path) == file_id:
        return base_path

    visited: Set[str] = set()

    # Search in common locations first (マイドライブ, My Drive)
    priority_dirs = ["マイドライブ", "My Drive", "共有ドライブ", "Shared drives"]
    for dir_name in priority_dirs:
        priority_path = base_path / dir_name
        if priority_path.exists():
            found = _search_iterative(priority_path, file_id, visited)
            if found:
                return found

    # Search other directories
    try:
        for entry in os.scandir(base_path):
            if entry.name.startswith(".") or entry.name in priority_dirs:
                continue
            if entry.is_dir(follow_symlinks=False):
                found = _search_iterative(Path(entry.path), file_id, visited)
                if found:
                    return found
    except PermissionError:
        pass

    return None


def _search_iterative(
    root: Path, file_id: str, visited: Set[str]
) -> Optional[Path]:
    """Iteratively search for a file ID using a stack.

    Uses an explicit stack instead of recursion to avoid stack overflow
    on deep directory trees. Tracks resolved paths to detect symlink loops.
    Uses os.scandir() for efficient directory enumeration (DirEntry caches
    is_dir/is_symlink from readdir, avoiding extra stat() calls).

    Args:
        root: Root path to start searching from.
        file_id: File ID to search for.
        visited: Set of resolved directory paths already visited.

    Returns:
        Path if found, None otherwise.
    """
    stack = [root]

    while stack:
        path = stack.pop()

        if _get_file_id(path) == file_id:
            return path

        if not path.is_dir():
            continue

        # Only resolve symlinks when actually a symlink
        try:
            real_path = str(path.resolve()) if path.is_symlink() else str(path)
        except OSError:
            continue

        if real_path in visited:
            continue
        visited.add(real_path)

        try:
            for entry in os.scandir(path):
                if entry.name.startswith("."):
                    continue
                stack.append(Path(entry.path))
        except PermissionError:
            pass

    return None


def _get_file_id(path: Path) -> Optional[str]:
    """Get the Google Drive file ID from a path's extended attributes.

    Uses ctypes to call macOS getxattr() directly with a fixed-size buffer,
    reducing syscalls from 2 to 1 per file.

    Args:
        path: Path to check.

    Returns:
        File ID string if found, None otherwise.
    """
    if _libc is None:
        return None
    try:
        path_bytes = str(path).encode("utf-8")
        # Single getxattr call with fixed-size buffer
        size = _libc.getxattr(
            path_bytes, _XATTR_BYTES, _xattr_buf, _XATTR_BUF_SIZE, 0, 0
        )
        if size <= 0:
            return None
        return _xattr_buf.raw[:size].decode("utf-8").strip()
    except Exception:
        return None
