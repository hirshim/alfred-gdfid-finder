"""Main entry point for gdfid_finder."""

from __future__ import annotations

import sys
from typing import Optional

from gdfid_finder.finder import find_file_by_id
from gdfid_finder.utils import reveal_in_finder


def main() -> int:
    """Main entry point.

    Reads file ID from command line argument or stdin,
    finds the corresponding file, and reveals it in Finder.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    file_id = _get_file_id()
    if not file_id:
        print("Error: No file ID provided", file=sys.stderr)
        return 1

    path = find_file_by_id(file_id)
    if not path:
        print(f"Error: File not found for ID: {file_id}", file=sys.stderr)
        return 1

    result = reveal_in_finder(path)
    if not result.success:
        error_detail = f": {result.error_message}" if result.error_message else ""
        print(f"Error: Could not reveal file{error_detail}", file=sys.stderr)
        return 1

    print(str(path))
    return 0


def _get_file_id() -> Optional[str]:
    """Get file ID from command line argument or stdin.

    Returns:
        File ID string or None if not provided.
    """
    if len(sys.argv) > 1:
        return sys.argv[1].strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    return None


if __name__ == "__main__":
    sys.exit(main())
