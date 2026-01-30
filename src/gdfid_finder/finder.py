"""File finder logic for Google Drive files."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

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

# Priority search directories (common Google Drive locations)
_PRIORITY_DIRS = ["マイドライブ", "My Drive", "共有ドライブ", "Shared drives"]
_PRIORITY_DIRS_SET = frozenset(_PRIORITY_DIRS)

# Type alias for stack entries: (path_str, is_dir_no_follow, is_symlink)
_StackEntry = Tuple[str, bool, bool]


def find_file_by_id(file_id: str) -> Optional[Path]:
    """Find a Google Drive file by its file ID.

    First attempts a fast lookup via the DriveFS SQLite database (~1ms).
    Falls back to xattr directory scan (~365ms) if the DB lookup fails.

    Args:
        file_id: Google Drive file ID to search for.

    Returns:
        Path to the file if found, None otherwise.
    """
    # Fast path: SQLite DB lookup
    from gdfid_finder.db_finder import find_file_by_id_via_db

    path = find_file_by_id_via_db(file_id)
    if path:
        return path

    # Fallback: xattr scan
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
    target_bytes = file_id.encode("utf-8")

    # Check the base path itself
    if _has_file_id(str(base_path).encode("utf-8"), target_bytes):
        return base_path

    visited: Set[str] = set()

    # Search in common locations first (マイドライブ, My Drive)
    for dir_name in _PRIORITY_DIRS:
        priority_path = base_path / dir_name
        if priority_path.exists():
            found = _search_iterative(priority_path, file_id, visited)
            if found:
                return found

    # Search other directories
    try:
        for entry in os.scandir(base_path):
            if entry.name.startswith(".") or entry.name in _PRIORITY_DIRS_SET:
                continue
            if entry.is_dir(follow_symlinks=False):
                found = _search_iterative(Path(entry.path), file_id, visited)
                if found:
                    return found
    except PermissionError:
        pass

    return None


def _search_iterative(root: Path, file_id: str, visited: Set[str]) -> Optional[Path]:
    """Iteratively search for a file ID using a stack.

    Uses an explicit stack instead of recursion to avoid stack overflow
    on deep directory trees. Tracks resolved paths to detect symlink loops.

    Performance optimizations over naive Path-based traversal:
    - Stack stores (path_str, is_dir, is_symlink) tuples from DirEntry,
      avoiding redundant stat()/lstat() syscalls per file.
    - Bytes-only file ID comparison skips decode() overhead.
    - String paths avoid Path object construction in the hot loop.

    Args:
        root: Root path to start searching from.
        file_id: File ID to search for.
        visited: Set of resolved directory paths already visited.

    Returns:
        Path if found, None otherwise.
    """
    target_bytes = file_id.encode("utf-8")
    root_str = str(root)

    # Check root's file ID
    if _has_file_id(root_str.encode("utf-8"), target_bytes):
        return root

    if not root.is_dir():
        return None

    # Symlink loop detection for root
    try:
        real_path = os.path.realpath(root_str) if root.is_symlink() else root_str
    except Exception:
        return None

    if real_path in visited:
        return None
    visited.add(real_path)

    # Build initial stack from root's children using DirEntry cache
    stack: List[_StackEntry] = []
    try:
        for entry in os.scandir(root_str):
            if entry.name.startswith("."):
                continue
            # DirEntry caches is_dir/is_symlink from readdir d_type (no syscall)
            stack.append(
                (entry.path, entry.is_dir(follow_symlinks=False), entry.is_symlink())
            )
    except PermissionError:
        return None

    while stack:
        path_str, is_dir, is_symlink = stack.pop()

        # Bytes-only file ID check (no decode overhead)
        if _has_file_id(path_str.encode("utf-8"), target_bytes):
            return Path(path_str)

        # Skip non-directories (DirEntry cached, no stat syscall)
        if not is_dir and not is_symlink:
            continue

        # Symlinks that aren't directories: check if target is a directory
        # Using os.path.isdir (not Path.is_dir) to avoid Path construction
        if is_symlink and not is_dir and not os.path.isdir(path_str):  # noqa: PTH112
            continue

        # Symlink loop detection (string-based, no Path construction)
        try:
            real_path = os.path.realpath(path_str) if is_symlink else path_str
        except Exception:
            continue

        if real_path in visited:
            continue
        visited.add(real_path)

        try:
            for entry in os.scandir(path_str):
                if entry.name.startswith("."):
                    continue
                stack.append(
                    (
                        entry.path,
                        entry.is_dir(follow_symlinks=False),
                        entry.is_symlink(),
                    )
                )
        except PermissionError:
            pass

    return None


def _has_file_id(path_bytes: bytes, target_bytes: bytes) -> bool:
    """Check if a path's xattr file ID matches the target.

    Bytes-only comparison avoids decode overhead in the search loop.
    Uses the shared fixed-size ctypes buffer.

    Args:
        path_bytes: UTF-8 encoded file path.
        target_bytes: UTF-8 encoded target file ID.

    Returns:
        True if the file ID matches, False otherwise.
    """
    if _libc is None:
        return False
    try:
        size = _libc.getxattr(
            path_bytes, _XATTR_BYTES, _xattr_buf, _XATTR_BUF_SIZE, 0, 0
        )
        if size <= 0:
            return False
        return _xattr_buf.raw[:size].strip() == target_bytes
    except Exception:
        return False


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
