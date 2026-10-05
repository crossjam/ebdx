"""Tests for file statistics utilities."""

import hashlib
from datetime import UTC, datetime

from ebdx.utils.file_stats import FileStats, get_file_stats


def test_get_file_stats_for_regular_file(tmp_path):
    """Report the size, UTC modification time, and digest of a regular file."""
    contents = b"Hello, World!"
    file_path = tmp_path / "book.epub"
    file_path.write_bytes(contents)

    stats = get_file_stats(file_path)

    assert stats == FileStats(
        size=len(contents),
        mtime=datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        content_hash=hashlib.sha256(contents).hexdigest(),
    )


def test_get_file_stats_for_empty_file(tmp_path):
    """An empty file has zero size and the SHA-256 digest of empty bytes."""
    file_path = tmp_path / "empty.epub"
    file_path.touch()

    stats = get_file_stats(file_path)

    assert stats.size == 0
    assert stats.mtime is not None
    assert stats.content_hash == hashlib.sha256(b"").hexdigest()


def test_get_file_stats_for_missing_file(tmp_path):
    """A missing file degrades gracefully when neither operation can run."""
    stats = get_file_stats(tmp_path / "missing.epub")

    assert stats == FileStats(size=None, mtime=None, content_hash=None)


def test_get_file_stats_hashes_when_stat_fails(tmp_path, monkeypatch):
    """A stat failure does not prevent hashing the file contents."""
    contents = b"still hashable"
    file_path = tmp_path / "book.epub"
    file_path.write_bytes(contents)

    def fail_stat(_path):
        raise OSError("stat failed")

    monkeypatch.setattr(type(file_path), "stat", fail_stat)

    stats = get_file_stats(file_path)

    assert stats == FileStats(
        size=None,
        mtime=None,
        content_hash=hashlib.sha256(contents).hexdigest(),
    )


def test_get_file_stats_preserves_stat_fields_when_file_is_unreadable(tmp_path, monkeypatch):
    """A read error does not discard independently available stat fields."""
    contents = b"readable metadata"
    file_path = tmp_path / "book.epub"
    file_path.write_bytes(contents)
    expected_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
    expected_mtime = expected_mtime.isoformat().replace("+00:00", "Z")

    def fail_open(_path, *_args, **_kwargs):
        raise PermissionError("file is unreadable")

    monkeypatch.setattr(type(file_path), "open", fail_open)

    stats = get_file_stats(file_path)

    assert stats == FileStats(
        size=len(contents),
        mtime=expected_mtime,
        content_hash=None,
    )
