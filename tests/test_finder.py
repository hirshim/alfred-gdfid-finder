"""Tests for finder module."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from gdfid_finder.finder import (
    _has_file_id,
    _search_in_path,
    _search_iterative,
    find_file_by_id,
)


class TestFindFileById:
    """Tests for find_file_by_id function."""

    def test_returns_none_when_no_drive_paths(self) -> None:
        """Should return None when no Google Drive paths exist."""
        with (
            patch(
                "gdfid_finder.db_finder.find_file_by_id_via_db",
                return_value=None,
            ),
            patch(
                "gdfid_finder.finder.get_google_drive_base_paths",
                return_value=[],
            ),
        ):
            result = find_file_by_id("some_file_id")
            assert result is None

    def test_returns_none_when_file_not_found(self, tmp_path: Path) -> None:
        """Should return None when file ID is not found in any drive."""
        drive_path = tmp_path / "GoogleDrive-test"
        drive_path.mkdir()

        with (
            patch(
                "gdfid_finder.db_finder.find_file_by_id_via_db",
                return_value=None,
            ),
            patch(
                "gdfid_finder.finder.get_google_drive_base_paths",
                return_value=[drive_path],
            ),
            patch("gdfid_finder.finder._has_file_id", return_value=False),
        ):
            result = find_file_by_id("nonexistent_id")
            assert result is None

    def test_searches_all_drive_paths(self, tmp_path: Path) -> None:
        """Should search through all available Google Drive paths."""
        drive1 = tmp_path / "GoogleDrive-user1"
        drive2 = tmp_path / "GoogleDrive-user2"
        drive1.mkdir()
        drive2.mkdir()

        with (
            patch(
                "gdfid_finder.db_finder.find_file_by_id_via_db",
                return_value=None,
            ),
            patch(
                "gdfid_finder.finder.get_google_drive_base_paths",
                return_value=[drive1, drive2],
            ),
            patch(
                "gdfid_finder.finder._search_in_path", return_value=None
            ) as mock_search,
        ):
            find_file_by_id("test_id")

            assert mock_search.call_count == 2
            mock_search.assert_any_call(drive1, "test_id")
            mock_search.assert_any_call(drive2, "test_id")

    def test_returns_first_found_path(self, tmp_path: Path) -> None:
        """Should return the first matching path found."""
        drive1 = tmp_path / "GoogleDrive-user1"
        drive2 = tmp_path / "GoogleDrive-user2"
        drive1.mkdir()
        drive2.mkdir()

        expected_path = drive1 / "found_file.txt"

        with (
            patch(
                "gdfid_finder.db_finder.find_file_by_id_via_db",
                return_value=None,
            ),
            patch(
                "gdfid_finder.finder.get_google_drive_base_paths",
                return_value=[drive1, drive2],
            ),
            patch(
                "gdfid_finder.finder._search_in_path",
                side_effect=[expected_path, None],
            ),
        ):
            result = find_file_by_id("test_id")
            assert result == expected_path

    def test_returns_db_result_when_available(self, tmp_path: Path) -> None:
        """Should return DB lookup result without falling back to xattr."""
        expected_path = tmp_path / "db_result.txt"

        with patch(
            "gdfid_finder.db_finder.find_file_by_id_via_db",
            return_value=expected_path,
        ):
            result = find_file_by_id("test_id")
            assert result == expected_path


class TestSearchInPath:
    """Tests for _search_in_path function."""

    def test_returns_base_path_if_id_matches(self, tmp_path: Path) -> None:
        """Should return base path if its file ID matches."""
        with patch("gdfid_finder.finder._has_file_id", return_value=True):
            result = _search_in_path(tmp_path, "target_id")
            assert result == tmp_path

    def test_searches_priority_directories_first(self, tmp_path: Path) -> None:
        """Should search マイドライブ/My Drive before other directories."""
        my_drive = tmp_path / "マイドライブ"
        my_drive.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        target_file = my_drive / "target.txt"
        target_file.write_text("test")

        target_bytes = str(target_file).encode("utf-8")

        def mock_has_id(path_bytes: bytes, _target_bytes: bytes) -> bool:
            return path_bytes == target_bytes

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            result = _search_in_path(tmp_path, "target_id")
            assert result == target_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Should return None when file ID is not found."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with patch("gdfid_finder.finder._has_file_id", return_value=False):
            result = _search_in_path(tmp_path, "nonexistent_id")
            assert result is None

    def test_finds_in_non_priority_directory(self, tmp_path: Path) -> None:
        """Should find file in non-priority directory after priority search."""
        my_drive = tmp_path / "マイドライブ"
        my_drive.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        target_file = other_dir / "target.txt"
        target_file.write_text("test")

        target_bytes = str(target_file).encode("utf-8")

        def mock_has_id(path_bytes: bytes, _target_bytes: bytes) -> bool:
            return path_bytes == target_bytes

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            result = _search_in_path(tmp_path, "target_id")
            assert result == target_file

    def test_handles_permission_error(self, tmp_path: Path) -> None:
        """Should handle PermissionError gracefully."""
        with (
            patch("gdfid_finder.finder._has_file_id", return_value=False),
            patch("gdfid_finder.finder.os.scandir", side_effect=PermissionError),
        ):
            result = _search_in_path(tmp_path, "test_id")
            assert result is None


class TestSearchIterative:
    """Tests for _search_iterative function."""

    def test_returns_path_if_id_matches(self, tmp_path: Path) -> None:
        """Should return path if its file ID matches."""
        with patch("gdfid_finder.finder._has_file_id", return_value=True):
            result = _search_iterative(tmp_path, "target_id", set())
            assert result == tmp_path

    def test_searches_children(self, tmp_path: Path) -> None:
        """Should search child directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        target_file = subdir / "target.txt"
        target_file.write_text("test")

        target_bytes = str(target_file).encode("utf-8")

        def mock_has_id(path_bytes: bytes, _target_bytes: bytes) -> bool:
            return path_bytes == target_bytes

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            result = _search_iterative(tmp_path, "target_id", set())
            assert result == target_file

    def test_skips_hidden_files(self, tmp_path: Path) -> None:
        """Should skip hidden files/directories."""
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        hidden_file = hidden_dir / "file.txt"
        hidden_file.write_text("test")

        call_count = 0

        def mock_has_id(_path_bytes: bytes, _target_bytes: bytes) -> bool:
            nonlocal call_count
            call_count += 1
            return False

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            _search_iterative(tmp_path, "test_id", set())
            # Should only check tmp_path, not .hidden or its contents
            assert call_count == 1

    def test_handles_permission_error(self, tmp_path: Path) -> None:
        """Should handle PermissionError gracefully."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        original_scandir = os.scandir

        def mock_scandir(path: object) -> object:
            if Path(str(path)) == subdir:
                raise PermissionError
            return original_scandir(path)

        with (
            patch("gdfid_finder.finder._has_file_id", return_value=False),
            patch("gdfid_finder.finder.os.scandir", side_effect=mock_scandir),
        ):
            result = _search_iterative(tmp_path, "test_id", set())
            assert result is None

    def test_skips_non_directory_entries(self, tmp_path: Path) -> None:
        """Should skip non-directory entries after checking file ID."""
        regular_file = tmp_path / "file.txt"
        regular_file.write_text("test")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        target_file = subdir / "target.txt"
        target_file.write_text("test")

        target_bytes = str(target_file).encode("utf-8")

        def mock_has_id(path_bytes: bytes, _target_bytes: bytes) -> bool:
            return path_bytes == target_bytes

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            result = _search_iterative(tmp_path, "target_id", set())
            assert result == target_file

    def test_handles_error_on_realpath(self, tmp_path: Path) -> None:
        """Should handle errors when resolving symlink path."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target_dir)

        with (
            patch("gdfid_finder.finder._has_file_id", return_value=False),
            patch("os.path.realpath", side_effect=Exception("error")),
        ):
            result = _search_iterative(tmp_path, "test_id", set())
            assert result is None

    def test_detects_symlink_loop(self, tmp_path: Path) -> None:
        """Should detect and skip symlink loops."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        # Create symlink pointing back to parent
        loop_link = subdir / "loop"
        loop_link.symlink_to(tmp_path)

        call_paths: List[str] = []

        def mock_has_id(path_bytes: bytes, _target_bytes: bytes) -> bool:
            call_paths.append(path_bytes.decode("utf-8"))
            return False

        with patch("gdfid_finder.finder._has_file_id", side_effect=mock_has_id):
            result = _search_iterative(tmp_path, "nonexistent", set())
            assert result is None
            # Should NOT infinitely recurse; visited set prevents re-entering tmp_path
            assert len(call_paths) < 20


class TestHasFileId:
    """Tests for _has_file_id function."""

    def test_returns_true_on_match(self, tmp_path: Path) -> None:
        """Should return True when file ID matches target."""
        test_data = b"target_file_id"

        def mock_getxattr(
            _path: bytes,
            _name: bytes,
            value: object,
            _size: int,
            _position: int,
            _options: int,
        ) -> int:
            ctypes.memmove(value, test_data, len(test_data))
            return len(test_data)

        mock_libc = MagicMock()
        mock_libc.getxattr.side_effect = mock_getxattr

        with patch("gdfid_finder.finder._libc", mock_libc):
            result = _has_file_id(str(tmp_path).encode("utf-8"), b"target_file_id")
            assert result is True

    def test_returns_false_on_mismatch(self, tmp_path: Path) -> None:
        """Should return False when file ID does not match target."""
        test_data = b"other_file_id"

        def mock_getxattr(
            _path: bytes,
            _name: bytes,
            value: object,
            _size: int,
            _position: int,
            _options: int,
        ) -> int:
            ctypes.memmove(value, test_data, len(test_data))
            return len(test_data)

        mock_libc = MagicMock()
        mock_libc.getxattr.side_effect = mock_getxattr

        with patch("gdfid_finder.finder._libc", mock_libc):
            result = _has_file_id(str(tmp_path).encode("utf-8"), b"target_file_id")
            assert result is False

    def test_returns_false_on_failure(self, tmp_path: Path) -> None:
        """Should return False when getxattr fails."""
        mock_libc = MagicMock()
        mock_libc.getxattr.return_value = -1

        with patch("gdfid_finder.finder._libc", mock_libc):
            result = _has_file_id(str(tmp_path).encode("utf-8"), b"target")
            assert result is False

    def test_returns_false_when_libc_unavailable(self) -> None:
        """Should return False when libc is not available."""
        with patch("gdfid_finder.finder._libc", None):
            result = _has_file_id(b"/some/path", b"target")
            assert result is False

    def test_short_id_after_long_id_no_corruption(self, tmp_path: Path) -> None:
        """Should match correct ID even after buffer contains longer data.

        Regression test: the shared ctypes buffer retains old data.
        raw[:size].strip() must be used for exact byte comparison.
        """
        long_data = b"1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        short_data = b"1akwdmoOKcbdPMAm2HcuclRARu53ypHSt"

        call_count = 0

        def mock_getxattr(
            _path: bytes,
            _name: bytes,
            value: object,
            _size: int,
            _position: int,
            _options: int,
        ) -> int:
            nonlocal call_count
            call_count += 1
            data = long_data if call_count == 1 else short_data
            ctypes.memmove(value, data, len(data))
            return len(data)

        mock_libc = MagicMock()
        mock_libc.getxattr.side_effect = mock_getxattr

        path_bytes = str(tmp_path).encode("utf-8")

        with patch("gdfid_finder.finder._libc", mock_libc):
            # First call: long ID matches long target
            assert _has_file_id(path_bytes, long_data) is True
            # Second call: short ID must match short target, not corrupted
            assert _has_file_id(path_bytes, short_data) is True
            # Verify short ID does NOT match long target
            call_count = 1  # Reset to make next call return short_data
            assert _has_file_id(path_bytes, long_data) is False
