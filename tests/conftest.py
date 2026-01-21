"""Pytest configuration and fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_google_drive(tmp_path: Path) -> Path:
    """Create a temporary Google Drive-like directory structure.

    Args:
        tmp_path: Pytest temporary path fixture.

    Returns:
        Path to the temporary Google Drive directory.
    """
    drive_path = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-test@example.com"
    drive_path.mkdir(parents=True)
    return drive_path
