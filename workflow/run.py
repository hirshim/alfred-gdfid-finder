#!/usr/bin/env python3
"""Alfred Workflow entry point for gdfid_finder.

Reads file ID from clipboard and reveals the file in Finder.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

# Google Drive base path pattern
CLOUD_STORAGE_BASE = Path.home() / "Library" / "CloudStorage"

# Extended attribute name for Google Drive file ID
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


def get_clipboard() -> str:
    """Get text from clipboard using pbpaste."""
    result = subprocess.run(
        ["pbpaste"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def get_google_drive_base_paths() -> List[Path]:
    """Get all Google Drive for Desktop mount points."""
    if not CLOUD_STORAGE_BASE.exists():
        return []

    paths: List[Path] = []
    try:
        for child in CLOUD_STORAGE_BASE.iterdir():
            if child.name.startswith("GoogleDrive-") and child.is_dir():
                paths.append(child)
    except PermissionError:
        pass

    return sorted(paths)


def has_file_id(path_bytes: bytes, target_bytes: bytes) -> bool:
    """Check if a path's xattr file ID matches the target.

    Bytes-only comparison avoids decode overhead in the search loop.
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


def get_file_id(path: Path) -> Optional[str]:
    """Get the Google Drive file ID from a path's extended attributes.

    Uses ctypes to call macOS getxattr() directly with a fixed-size buffer,
    reducing syscalls from 2 to 1 per file.
    """
    if _libc is None:
        return None
    try:
        path_bytes = str(path).encode("utf-8")
        size = _libc.getxattr(
            path_bytes, _XATTR_BYTES, _xattr_buf, _XATTR_BUF_SIZE, 0, 0
        )
        if size <= 0:
            return None
        return _xattr_buf.raw[:size].decode("utf-8").strip()
    except Exception:
        return None


def search_iterative(
    root: Path, file_id: str, visited: Set[str]
) -> Optional[Path]:
    """Iteratively search for a file ID using a stack.

    Tracks resolved paths to detect symlink loops.
    Uses DirEntry cache, bytes comparison, and string paths for performance.
    """
    target_bytes = file_id.encode("utf-8")
    root_str = str(root)

    if has_file_id(root_str.encode("utf-8"), target_bytes):
        return root

    if not root.is_dir():
        return None

    try:
        real_path = os.path.realpath(root_str) if root.is_symlink() else root_str
    except Exception:
        return None

    if real_path in visited:
        return None
    visited.add(real_path)

    stack: List[_StackEntry] = []
    try:
        for entry in os.scandir(root_str):
            if entry.name.startswith("."):
                continue
            stack.append(
                (entry.path, entry.is_dir(follow_symlinks=False), entry.is_symlink())
            )
    except PermissionError:
        return None

    while stack:
        path_str, is_dir, is_symlink = stack.pop()

        if has_file_id(path_str.encode("utf-8"), target_bytes):
            return Path(path_str)

        if not is_dir and not is_symlink:
            continue

        if is_symlink and not is_dir:
            if not os.path.isdir(path_str):
                continue

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


def search_in_path(base_path: Path, file_id: str) -> Optional[Path]:
    """Search for a file ID within a given path."""
    target_bytes = file_id.encode("utf-8")

    if has_file_id(str(base_path).encode("utf-8"), target_bytes):
        return base_path

    visited: Set[str] = set()

    for dir_name in _PRIORITY_DIRS:
        priority_path = base_path / dir_name
        if priority_path.exists():
            found = search_iterative(priority_path, file_id, visited)
            if found:
                return found

    try:
        for entry in os.scandir(base_path):
            if entry.name.startswith(".") or entry.name in _PRIORITY_DIRS_SET:
                continue
            if entry.is_dir(follow_symlinks=False):
                found = search_iterative(Path(entry.path), file_id, visited)
                if found:
                    return found
    except PermissionError:
        pass

    return None


def find_file_by_id(file_id: str) -> Optional[Path]:
    """Find a Google Drive file by its file ID."""
    base_paths = get_google_drive_base_paths()
    if not base_paths:
        return None

    for base_path in base_paths:
        found = search_in_path(base_path, file_id)
        if found:
            return found

    return None


# Google Drive file IDs: alphanumeric, hyphens, underscores
_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_file_id(file_id: str) -> bool:
    """Validate that a string looks like a Google Drive file ID."""
    if not file_id:
        return False
    return _FILE_ID_PATTERN.match(file_id) is not None


def reveal_in_finder(path: Path) -> bool:
    """Reveal a file in Finder using open -R."""
    if not path.exists():
        return False

    result = subprocess.run(
        ["open", "-R", str(path)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    """Main entry point.

    Reads file ID from: argv (Alfred selection) > clipboard (fallback).
    """
    # Alfred passes selected text via argv; fall back to clipboard
    if len(sys.argv) > 1 and sys.argv[1].strip():
        file_id = sys.argv[1].strip()
    else:
        file_id = get_clipboard()
    if not file_id or not is_valid_file_id(file_id):
        print("ファイルIDが取得できません", file=sys.stderr)
        return 1

    path = find_file_by_id(file_id)
    if not path:
        print(f"ファイルが見つかりません: {file_id}", file=sys.stderr)
        return 1

    if not reveal_in_finder(path):
        print(f"Finderで表示できませんでした: {path}", file=sys.stderr)
        return 1

    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
