"""File statistics utilities for ebdx."""

import hashlib
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple


class FileStats(NamedTuple):
    """File statistics for a single file."""

    size: int | None
    mtime: str | None
    content_hash: str | None


def get_file_stats(file_path: Path) -> FileStats:
    """Get file statistics including size, modification time, and content hash.

    Args:
        file_path: Path to the file to stat.

    Returns:
        FileStats with size, mtime (ISO-8601 UTC), and content hash (SHA-256).
        Any field may be None if the operation fails.
    """
    size = None
    mtime = None
    content_hash = None

    try:
        # Get file size and modification time
        stat_result = file_path.stat()
        size = stat_result.st_size
        mtime = (
            datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")
        )
    except OSError:
        # File access failed, leave size and mtime as None
        pass

    # Compute SHA-256 hash of file contents when possible.
    with suppress(OSError):
        content_hash = _compute_sha256(file_path)

    return FileStats(size=size, mtime=mtime, content_hash=content_hash)


def _compute_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Size of chunks to read at a time.

    Returns:
        SHA-256 hash as hexadecimal string.
    """
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()
