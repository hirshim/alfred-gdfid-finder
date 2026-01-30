#!/usr/bin/env python3
"""Alfred Workflow entry point for gdfid_finder.

Reads file ID from clipboard and reveals the file in Finder.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Google Drive base path pattern
CLOUD_STORAGE_BASE = Path.home() / "Library" / "CloudStorage"

# Extended attribute name for Google Drive file ID
XATTR_ITEM_ID = "com.google.drivefs.item-id#S"

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


def get_file_id(path: Path) -> Optional[str]:
    """Get the Google Drive file ID from a path's extended attributes.

    Uses ctypes to call macOS getxattr() directly, avoiding the overhead
    of spawning a subprocess for each file.
    """
    if _libc is None:
        return None
    try:
        path_bytes = str(path).encode("utf-8")
        attr_bytes = XATTR_ITEM_ID.encode("utf-8")
        size = _libc.getxattr(path_bytes, attr_bytes, None, 0, 0, 0)
        if size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        result = _libc.getxattr(path_bytes, attr_bytes, buf, size, 0, 0)
        if result <= 0:
            return None
        return buf.value.decode("utf-8").strip()
    except Exception:
        return None


def search_recursive(path: Path, file_id: str) -> Optional[Path]:
    """Recursively search for a file ID."""
    if get_file_id(path) == file_id:
        return path

    if path.is_dir():
        try:
            for child in path.iterdir():
                if child.name.startswith("."):
                    continue
                found = search_recursive(child, file_id)
                if found:
                    return found
        except PermissionError:
            pass

    return None


def search_in_path(base_path: Path, file_id: str) -> Optional[Path]:
    """Search for a file ID within a given path."""
    if get_file_id(base_path) == file_id:
        return base_path

    priority_dirs = ["マイドライブ", "My Drive", "共有ドライブ", "Shared drives"]
    for dir_name in priority_dirs:
        priority_path = base_path / dir_name
        if priority_path.exists():
            found = search_recursive(priority_path, file_id)
            if found:
                return found

    try:
        for child in base_path.iterdir():
            if child.name.startswith(".") or child.name in priority_dirs:
                continue
            if child.is_dir():
                found = search_recursive(child, file_id)
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
    """Main entry point."""
    file_id = get_clipboard()
    if not file_id:
        print("クリップボードにファイルIDがありません", file=sys.stderr)
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
