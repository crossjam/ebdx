"""Tests for file statistics utilities."""

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ebdx.utils.file_stats import FileStats, get_file_stats


def test_get_file_stats_with_valid_file():
    """Test get_file_stats with a valid file."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"Hello, World!")
        tmp_path = Path(tmp.name)

    try:
        stats = get_file_stats(tmp_path)
        
        # Check that we got a FileStats object
        assert isinstance(stats, FileStats)
        
        # Check size
        assert stats.size == 13
        
        # Check mtime is a valid ISO-8601 UTC timestamp
        assert stats.mtime is not None
        assert stats.mtime.endswith('Z')
        # Parse to verify it's a valid timestamp
        datetime.fromisoformat(stats.mtime.replace('Z', '+00:00'))
        
        # Check content hash
        assert stats.content_hash == hashlib.sha256(b"Hello, World!").hexdigest()
        
    finally:
        tmp_path.unlink()


def test_get_file_stats_with_empty_file():
    """Test get_file_stats with an empty file."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        stats = get_file_stats(tmp_path)
        
        # Check that we got a FileStats object
        assert isinstance(stats, FileStats)
        
        # Check size
        assert stats.size == 0
        
        # Check mtime is a valid ISO-8601 UTC timestamp
        assert stats.mtime is not None
        assert stats.mtime.endswith('Z')
        
        # Check content hash for empty file
        assert stats.content_hash == hashlib.sha256(b"").hexdigest()
        
    finally:
        tmp_path.unlink()


def test_get_file_stats_with_nonexistent_file():
    """Test get_file_stats with a nonexistent file."""
    nonexistent_path = Path("/nonexistent/file")
    stats = get_file_stats(nonexistent_path)
    
    # Should return FileStats with all None values
    assert isinstance(stats, FileStats)
    assert stats.size is None
    assert stats.mtime is None
    assert stats.content_hash is None


def test_get_file_stats_with_unreadable_file(monkeypatch):
    """Test get_file_stats with a file that can't be read."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test content")
        tmp_path = Path(tmp.name)

    try:
        # Make file unreadable
        tmp_path.chmod(0o000)
        
        stats = get_file_stats(tmp_path)
        
        # Should still get size and mtime, but not content hash
        assert isinstance(stats, FileStats)
        assert stats.size == 12
        assert stats.mtime is not None
        assert stats.content_hash is None
        
    finally:
        # Restore permissions so we can delete
        tmp_path.chmod(0o644)
        tmp_path.unlink()


def test_compute_sha256_large_file():
    """Test SHA-256 computation with a larger file."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        # Write a larger amount of data
        data = b"A" * 100000  # 100KB of A's
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        stats = get_file_stats(tmp_path)
        
        # Check content hash
        assert stats.content_hash == hashlib.sha256(data).hexdigest()
        
    finally:
        tmp_path.unlink()
