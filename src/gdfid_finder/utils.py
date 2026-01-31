"""Utility functions for gdfid_finder."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class RevealResult:
    """Result of reveal_in_finder operation."""

    success: bool
    error_message: Optional[str] = None


def get_google_drive_base_paths() -> List[Path]:
    """Get Google Drive for Desktop base paths.

    Returns:
        List of Google Drive mount paths found in CloudStorage.
    """
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if not cloud_storage.exists():
        return []

    try:
        return sorted(
            p
            for p in cloud_storage.iterdir()
            if p.name.startswith("GoogleDrive-") and p.is_dir()
        )
    except PermissionError:
        return []


def reveal_in_finder(path: Path) -> RevealResult:
    """Reveal a file or folder in Finder.

    Uses `open -R` command which is safe from injection attacks
    as it passes the path as an argument, not embedded in a script.

    Args:
        path: Path to reveal in Finder.

    Returns:
        RevealResult with success status and optional error message.
    """
    if not path.exists():
        return RevealResult(success=False, error_message=f"Path does not exist: {path}")

    # Use `open -R` instead of AppleScript to avoid injection vulnerabilities.
    # `open -R` reveals the file in Finder and is safe with any path characters.
    result = subprocess.run(
        ["open", "-R", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        return RevealResult(success=False, error_message=error_msg)

    return RevealResult(success=True)
