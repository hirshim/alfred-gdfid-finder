"""Tests for main module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gdfid_finder.main import _get_file_id, _is_valid_file_id, main
from gdfid_finder.utils import RevealResult


class TestGetFileId:
    """Tests for _get_file_id function."""

    def test_returns_arg_when_provided(self) -> None:
        """Should return file ID from command line argument."""
        with patch("gdfid_finder.main.sys.argv", ["script", "test_file_id"]):
            result = _get_file_id()
            assert result == "test_file_id"

    def test_strips_whitespace_from_arg(self) -> None:
        """Should strip whitespace from argument."""
        with patch("gdfid_finder.main.sys.argv", ["script", "  file_id  \n"]):
            result = _get_file_id()
            assert result == "file_id"

    def test_returns_none_when_no_arg_and_tty(self) -> None:
        """Should return None when no argument and stdin is a tty."""
        with (
            patch("gdfid_finder.main.sys.argv", ["script"]),
            patch("gdfid_finder.main.sys.stdin.isatty", return_value=True),
        ):
            result = _get_file_id()
            assert result is None

    def test_reads_from_stdin_when_not_tty(self) -> None:
        """Should read from stdin when not a tty."""
        with (
            patch("gdfid_finder.main.sys.argv", ["script"]),
            patch("gdfid_finder.main.sys.stdin.isatty", return_value=False),
            patch("gdfid_finder.main.sys.stdin.read", return_value="stdin_file_id\n"),
        ):
            result = _get_file_id()
            assert result == "stdin_file_id"

    def test_returns_none_for_invalid_file_id(self) -> None:
        """Should return None when argument contains invalid characters."""
        with patch("gdfid_finder.main.sys.argv", ["script", "has spaces"]):
            result = _get_file_id()
            assert result is None

    def test_returns_none_for_empty_arg(self) -> None:
        """Should return None when argument is empty after strip."""
        with patch("gdfid_finder.main.sys.argv", ["script", "   "]):
            result = _get_file_id()
            assert result is None


class TestIsValidFileId:
    """Tests for _is_valid_file_id function."""

    def test_valid_alphanumeric_id(self) -> None:
        """Should accept alphanumeric IDs."""
        assert _is_valid_file_id("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

    def test_valid_id_with_hyphens_and_underscores(self) -> None:
        """Should accept IDs with hyphens and underscores."""
        assert _is_valid_file_id("1C-n4F2DCbJ_SlzE9i830rlzHDtZFbX39q")

    def test_rejects_empty_string(self) -> None:
        """Should reject empty string."""
        assert not _is_valid_file_id("")

    def test_rejects_string_with_spaces(self) -> None:
        """Should reject strings with spaces."""
        assert not _is_valid_file_id("hello world")

    def test_rejects_string_with_special_chars(self) -> None:
        """Should reject strings with special characters."""
        assert not _is_valid_file_id("file@id#123")

    def test_rejects_string_with_path_chars(self) -> None:
        """Should reject strings with path separators."""
        assert not _is_valid_file_id("../etc/passwd")


class TestMain:
    """Tests for main function."""

    def test_returns_1_when_no_file_id(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should return 1 and print error when no file ID provided."""
        with patch("gdfid_finder.main._get_file_id", return_value=None):
            result = main()

            assert result == 1
            captured = capsys.readouterr()
            assert "No file ID provided" in captured.err

    def test_returns_1_when_file_not_found(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should return 1 when file is not found."""
        with (
            patch("gdfid_finder.main._get_file_id", return_value="test_id"),
            patch("gdfid_finder.main.find_file_by_id", return_value=None),
        ):
            result = main()

            assert result == 1
            captured = capsys.readouterr()
            assert "File not found" in captured.err

    def test_returns_1_when_reveal_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should return 1 with error message when reveal_in_finder fails."""
        test_path = tmp_path / "test.txt"
        fail_result = RevealResult(success=False, error_message="Permission denied")

        with (
            patch("gdfid_finder.main._get_file_id", return_value="test_id"),
            patch("gdfid_finder.main.find_file_by_id", return_value=test_path),
            patch("gdfid_finder.main.reveal_in_finder", return_value=fail_result),
        ):
            result = main()

            assert result == 1
            captured = capsys.readouterr()
            assert "Could not reveal file" in captured.err
            assert "Permission denied" in captured.err

    def test_returns_1_when_reveal_fails_without_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should return 1 without detail when error_message is None."""
        test_path = tmp_path / "test.txt"
        fail_result = RevealResult(success=False, error_message=None)

        with (
            patch("gdfid_finder.main._get_file_id", return_value="test_id"),
            patch("gdfid_finder.main.find_file_by_id", return_value=test_path),
            patch("gdfid_finder.main.reveal_in_finder", return_value=fail_result),
        ):
            result = main()

            assert result == 1
            captured = capsys.readouterr()
            assert "Could not reveal file" in captured.err

    def test_returns_0_on_success(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should return 0 and print path on success."""
        test_path = tmp_path / "test.txt"
        success_result = RevealResult(success=True)

        with (
            patch("gdfid_finder.main._get_file_id", return_value="test_id"),
            patch("gdfid_finder.main.find_file_by_id", return_value=test_path),
            patch("gdfid_finder.main.reveal_in_finder", return_value=success_result),
        ):
            result = main()

            assert result == 0
            captured = capsys.readouterr()
            assert str(test_path) in captured.out
