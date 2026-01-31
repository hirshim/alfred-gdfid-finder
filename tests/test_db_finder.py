"""Tests for db_finder module."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from gdfid_finder.db_finder import (
    _get_drivefs_db_paths,
    _query_path_segments,
    _resolve_path,
    find_file_by_id_via_db,
)


def _create_test_db(db_path: Path) -> None:
    """Create a minimal DriveFS-like SQLite database for testing."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE stable_ids (
            stable_id INTEGER PRIMARY KEY,
            cloud_id TEXT
        );
        CREATE INDEX stable_ids_cloud_id_idx ON stable_ids(cloud_id);

        CREATE TABLE items (
            stable_id INTEGER PRIMARY KEY,
            local_title TEXT,
            is_folder BOOLEAN
        );

        CREATE TABLE stable_parents (
            item_stable_id INTEGER PRIMARY KEY,
            parent_stable_id INTEGER
        );

        -- Root: マイドライブ (no parent)
        INSERT INTO stable_ids VALUES (101, '0AROOT');
        INSERT INTO items VALUES (101, 'マイドライブ', 1);

        -- Folder: Colab Notebooks (parent: マイドライブ)
        INSERT INTO stable_ids VALUES (201, '1AFOLDER');
        INSERT INTO items VALUES (201, 'Colab Notebooks', 1);
        INSERT INTO stable_parents VALUES (201, 101);

        -- File: sample.py (parent: Colab Notebooks)
        INSERT INTO stable_ids VALUES (301, '1BFILE');
        INSERT INTO items VALUES (301, 'sample.py', 0);
        INSERT INTO stable_parents VALUES (301, 201);

        -- Computer backup root: マイ iMac (no parent, under その他のパソコン)
        INSERT INTO stable_ids VALUES (102, '0BCOMPUTER');
        INSERT INTO items VALUES (102, 'マイ iMac', 1);

        -- File under computer backup
        INSERT INTO stable_ids VALUES (302, '1CBACKUP');
        INSERT INTO items VALUES (302, 'backup.txt', 0);
        INSERT INTO stable_parents VALUES (302, 102);

        -- Shared drive root: TeamDrive (no parent, under 共有ドライブ)
        INSERT INTO stable_ids VALUES (103, '0CTEAM');
        INSERT INTO items VALUES (103, 'TeamDrive', 1);

        -- File under shared drive
        INSERT INTO stable_ids VALUES (303, '1DSHARED');
        INSERT INTO items VALUES (303, 'shared.doc', 0);
        INSERT INTO stable_parents VALUES (303, 103);

        -- Item with NULL local_title
        INSERT INTO stable_ids VALUES (999, '0DNULL');
        INSERT INTO items VALUES (999, NULL, 0);
        """
    )
    conn.close()


class TestGetDrivefsDbPaths:
    """Tests for _get_drivefs_db_paths function."""

    def test_returns_empty_when_drivefs_dir_missing(self) -> None:
        """Should return empty list when DriveFS directory doesn't exist."""
        with patch(
            "gdfid_finder.db_finder._DRIVEFS_BASE",
            Path("/nonexistent/path"),
        ):
            result = _get_drivefs_db_paths()
            assert result == []

    def test_finds_db_files(self, tmp_path: Path) -> None:
        """Should find metadata_sqlite_db files in account directories."""
        account_dir = tmp_path / "12345"
        account_dir.mkdir()
        db_file = account_dir / "metadata_sqlite_db"
        db_file.write_text("")

        # Non-account file (should be skipped)
        (tmp_path / "some_file.txt").write_text("")

        # Account dir without DB (should be skipped)
        (tmp_path / "67890").mkdir()

        with patch("gdfid_finder.db_finder._DRIVEFS_BASE", tmp_path):
            result = _get_drivefs_db_paths()
            assert result == [db_file]

    def test_handles_permission_error(self, tmp_path: Path) -> None:
        """Should return empty list on PermissionError."""
        with (
            patch("gdfid_finder.db_finder._DRIVEFS_BASE", tmp_path),
            patch("gdfid_finder.db_finder.os.scandir", side_effect=PermissionError),
        ):
            result = _get_drivefs_db_paths()
            assert result == []


class TestQueryPathSegments:
    """Tests for _query_path_segments function."""

    def test_returns_segments_for_file(self, tmp_path: Path) -> None:
        """Should return path segments for a known file."""
        db_path = tmp_path / "metadata_sqlite_db"
        _create_test_db(db_path)

        result = _query_path_segments(db_path, "1BFILE")
        assert result == ["マイドライブ", "Colab Notebooks", "sample.py"]

    def test_returns_segments_for_root(self, tmp_path: Path) -> None:
        """Should return single segment for a root folder."""
        db_path = tmp_path / "metadata_sqlite_db"
        _create_test_db(db_path)

        result = _query_path_segments(db_path, "0AROOT")
        assert result == ["マイドライブ"]

    def test_returns_none_for_unknown_id(self, tmp_path: Path) -> None:
        """Should return None for an unknown cloud_id."""
        db_path = tmp_path / "metadata_sqlite_db"
        _create_test_db(db_path)

        result = _query_path_segments(db_path, "UNKNOWN_ID")
        assert result is None

    def test_returns_none_on_db_error(self) -> None:
        """Should return None when database is inaccessible."""
        result = _query_path_segments(Path("/nonexistent/db"), "some_id")
        assert result is None

    def test_returns_none_when_title_is_null(self, tmp_path: Path) -> None:
        """Should return None when any segment has NULL local_title."""
        db_path = tmp_path / "metadata_sqlite_db"
        _create_test_db(db_path)

        result = _query_path_segments(db_path, "0DNULL")
        assert result is None

    def test_returns_segments_for_computer_backup(self, tmp_path: Path) -> None:
        """Should return segments for a file under computer backup."""
        db_path = tmp_path / "metadata_sqlite_db"
        _create_test_db(db_path)

        result = _query_path_segments(db_path, "1CBACKUP")
        assert result == ["マイ iMac", "backup.txt"]


class TestResolvePath:
    """Tests for _resolve_path function."""

    def test_resolves_direct_child(self, tmp_path: Path) -> None:
        """Should resolve path when root is a direct child of base."""
        # Create: base_path/マイドライブ/file.txt
        my_drive = tmp_path / "マイドライブ"
        my_drive.mkdir()
        target = my_drive / "file.txt"
        target.write_text("test")

        result = _resolve_path(tmp_path, ["マイドライブ", "file.txt"])
        assert result == target

    def test_resolves_under_computers(self, tmp_path: Path) -> None:
        """Should resolve path under その他のパソコン."""
        # Create: base_path/その他のパソコン/マイ iMac/file.txt
        computers = tmp_path / "その他のパソコン"
        computers.mkdir()
        computer = computers / "マイ iMac"
        computer.mkdir()
        target = computer / "file.txt"
        target.write_text("test")

        result = _resolve_path(tmp_path, ["マイ iMac", "file.txt"])
        assert result == target

    def test_resolves_under_shared_drives(self, tmp_path: Path) -> None:
        """Should resolve path under 共有ドライブ."""
        # Create: base_path/共有ドライブ/TeamDrive/file.doc
        shared = tmp_path / "共有ドライブ"
        shared.mkdir()
        team = shared / "TeamDrive"
        team.mkdir()
        target = team / "file.doc"
        target.write_text("test")

        result = _resolve_path(tmp_path, ["TeamDrive", "file.doc"])
        assert result == target

    def test_resolves_under_shared_drives_english(self, tmp_path: Path) -> None:
        """Should resolve path under Shared drives (English)."""
        shared = tmp_path / "Shared drives"
        shared.mkdir()
        team = shared / "TeamDrive"
        team.mkdir()
        target = team / "file.doc"
        target.write_text("test")

        result = _resolve_path(tmp_path, ["TeamDrive", "file.doc"])
        assert result == target

    def test_returns_none_when_segments_empty(self, tmp_path: Path) -> None:
        """Should return None when segments list is empty."""
        result = _resolve_path(tmp_path, [])
        assert result is None

    def test_returns_none_when_path_not_found(self, tmp_path: Path) -> None:
        """Should return None when no prefix produces a valid path."""
        result = _resolve_path(tmp_path, ["nonexistent", "file.txt"])
        assert result is None


class TestFindFileByIdViaDb:
    """Tests for find_file_by_id_via_db function."""

    def test_returns_path_on_success(self, tmp_path: Path) -> None:
        """Should return Path when DB lookup and path resolution succeed."""
        # Create DB
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        # Create filesystem structure
        mount = tmp_path / "CloudStorage" / "GoogleDrive-test@gmail.com"
        mount.mkdir(parents=True)
        my_drive = mount / "マイドライブ"
        my_drive.mkdir()
        colab = my_drive / "Colab Notebooks"
        colab.mkdir()
        target = colab / "sample.py"
        target.write_text("test")

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[mount],
            ),
        ):
            result = find_file_by_id_via_db("1BFILE")
            assert result == target

    def test_returns_none_when_no_dbs(self) -> None:
        """Should return None when no DriveFS databases exist."""
        with patch(
            "gdfid_finder.db_finder._DRIVEFS_BASE",
            Path("/nonexistent"),
        ):
            result = find_file_by_id_via_db("some_id")
            assert result is None

    def test_returns_none_when_no_mount_points(self, tmp_path: Path) -> None:
        """Should return None when no Google Drive mount points exist."""
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[],
            ),
        ):
            result = find_file_by_id_via_db("1BFILE")
            assert result is None

    def test_returns_none_when_file_not_in_db(self, tmp_path: Path) -> None:
        """Should return None when file ID is not in the database."""
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        mount = tmp_path / "CloudStorage" / "GoogleDrive-test@gmail.com"
        mount.mkdir(parents=True)

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[mount],
            ),
        ):
            result = find_file_by_id_via_db("UNKNOWN_ID")
            assert result is None

    def test_returns_none_when_path_not_on_disk(self, tmp_path: Path) -> None:
        """Should return None when DB path doesn't exist on filesystem."""
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        # Mount point exists but file structure doesn't
        mount = tmp_path / "CloudStorage" / "GoogleDrive-test@gmail.com"
        mount.mkdir(parents=True)

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[mount],
            ),
        ):
            result = find_file_by_id_via_db("1BFILE")
            assert result is None

    def test_resolves_computer_backup_file(self, tmp_path: Path) -> None:
        """Should resolve file under その他のパソコン via DB lookup."""
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        mount = tmp_path / "CloudStorage" / "GoogleDrive-test@gmail.com"
        mount.mkdir(parents=True)
        computers = mount / "その他のパソコン"
        computers.mkdir()
        computer = computers / "マイ iMac"
        computer.mkdir()
        target = computer / "backup.txt"
        target.write_text("test")

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[mount],
            ),
        ):
            result = find_file_by_id_via_db("1CBACKUP")
            assert result == target

    def test_resolves_shared_drive_file(self, tmp_path: Path) -> None:
        """Should resolve file under 共有ドライブ via DB lookup."""
        account_dir = tmp_path / "drivefs" / "12345"
        account_dir.mkdir(parents=True)
        db_path = account_dir / "metadata_sqlite_db"
        _create_test_db(db_path)

        mount = tmp_path / "CloudStorage" / "GoogleDrive-test@gmail.com"
        mount.mkdir(parents=True)
        shared = mount / "共有ドライブ"
        shared.mkdir()
        team = shared / "TeamDrive"
        team.mkdir()
        target = team / "shared.doc"
        target.write_text("test")

        with (
            patch(
                "gdfid_finder.db_finder._DRIVEFS_BASE",
                tmp_path / "drivefs",
            ),
            patch(
                "gdfid_finder.db_finder.get_google_drive_base_paths",
                return_value=[mount],
            ),
        ):
            result = find_file_by_id_via_db("1DSHARED")
            assert result == target
