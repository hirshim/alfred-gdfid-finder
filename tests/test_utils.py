"""Tests for utility functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from gdfid_finder.utils import (
    RevealResult,
    get_google_drive_base_paths,
    reveal_in_finder,
)


class TestGetGoogleDriveBasePaths:
    """Tests for get_google_drive_base_paths function."""

    def test_returns_empty_when_cloud_storage_not_exists(self, tmp_path: Path) -> None:
        """Should return empty list when CloudStorage directory doesn't exist."""
        with patch("gdfid_finder.utils.Path.home", return_value=tmp_path):
            result = get_google_drive_base_paths()
            assert result == []

    def test_returns_google_drive_paths(self, tmp_path: Path) -> None:
        """Should return Google Drive paths when they exist."""
        cloud_storage = tmp_path / "Library" / "CloudStorage"
        cloud_storage.mkdir(parents=True)

        drive1 = cloud_storage / "GoogleDrive-user1@example.com"
        drive2 = cloud_storage / "GoogleDrive-user2@example.com"
        other = cloud_storage / "OneDrive-Personal"

        drive1.mkdir()
        drive2.mkdir()
        other.mkdir()

        with patch("gdfid_finder.utils.Path.home", return_value=tmp_path):
            result = get_google_drive_base_paths()

            assert len(result) == 2
            assert drive1 in result
            assert drive2 in result
            assert other not in result

    def test_returns_sorted_paths(self, tmp_path: Path) -> None:
        """Should return paths sorted alphabetically."""
        cloud_storage = tmp_path / "Library" / "CloudStorage"
        cloud_storage.mkdir(parents=True)

        (cloud_storage / "GoogleDrive-zebra@example.com").mkdir()
        (cloud_storage / "GoogleDrive-alpha@example.com").mkdir()

        with patch("gdfid_finder.utils.Path.home", return_value=tmp_path):
            result = get_google_drive_base_paths()

            assert result[0].name == "GoogleDrive-alpha@example.com"
            assert result[1].name == "GoogleDrive-zebra@example.com"


class TestRevealResult:
    """Tests for RevealResult dataclass."""

    def test_success_result(self) -> None:
        """Should create successful result."""
        result = RevealResult(success=True)
        assert result.success is True
        assert result.error_message is None

    def test_failure_result_with_message(self) -> None:
        """Should create failure result with error message."""
        result = RevealResult(success=False, error_message="Test error")
        assert result.success is False
        assert result.error_message == "Test error"


class TestRevealInFinder:
    """Tests for reveal_in_finder function."""

    def test_returns_failure_when_path_not_exists(self, tmp_path: Path) -> None:
        """Should return failure result when path doesn't exist."""
        non_existent = tmp_path / "non_existent_file.txt"
        result = reveal_in_finder(non_existent)

        assert result.success is False
        assert "does not exist" in (result.error_message or "")

    def test_returns_success_on_successful_reveal(self, tmp_path: Path) -> None:
        """Should return success when open -R succeeds."""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "gdfid_finder.utils.subprocess.run", return_value=mock_result
        ) as mock_run:
            result = reveal_in_finder(test_file)

            assert result.success is True
            assert result.error_message is None
            mock_run.assert_called_once_with(
                ["open", "-R", str(test_file)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_returns_failure_on_failed_reveal(self, tmp_path: Path) -> None:
        """Should return failure with error message when open -R fails."""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"

        with patch("gdfid_finder.utils.subprocess.run", return_value=mock_result):
            result = reveal_in_finder(test_file)

            assert result.success is False
            assert result.error_message == "Permission denied"

    def test_returns_unknown_error_when_no_stderr(self, tmp_path: Path) -> None:
        """Should return 'Unknown error' when stderr is empty."""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""

        with patch("gdfid_finder.utils.subprocess.run", return_value=mock_result):
            result = reveal_in_finder(test_file)

            assert result.success is False
            assert result.error_message == "Unknown error"

    def test_handles_special_characters_in_path(self, tmp_path: Path) -> None:
        """Should handle paths with special characters safely."""
        # Create file with special characters in name
        special_file = tmp_path / 'file with "quotes" and spaces.txt'
        special_file.write_text("test")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "gdfid_finder.utils.subprocess.run", return_value=mock_result
        ) as mock_run:
            result = reveal_in_finder(special_file)

            assert result.success is True
            # Verify the path is passed as-is, not embedded in a script
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "open"
            assert call_args[1] == "-R"
            assert call_args[2] == str(special_file)
