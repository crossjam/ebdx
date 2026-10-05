"""
Scanner module for ebdx.

Walks directories to find EPUB files and extracts their metadata
for indexing into the database.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import sqlite_utils
from loguru import logger
from rich.console import Console

from ebdx.progress import file_progress, short_name, walk_progress
from ebdx.utils.file_stats import FileStats, get_file_stats


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every regular file at or below ``root``, in sorted order.

    Walks with :meth:`Path.walk` rather than a glob so callers filter on
    explicit filename checks. ``Path.walk`` does not descend into directory
    symlinks, so it cannot loop; a non-directory ``root`` yields nothing.
    """
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in root.walk():
        dirnames.sort()
        for name in sorted(filenames):
            candidate = dirpath / name
            if candidate.is_file():
                yield candidate


def iter_epub_files(root: Path) -> Iterator[Path]:
    """Yield EPUB files at or below ``root``, matching the suffix case-insensitively."""
    return (p for p in iter_files(root) if p.suffix.lower() == ".epub")


def _find_epub_files(root: Path, *, show_progress: bool) -> list[Path]:
    """Walk ``root`` for EPUBs, pulsing a display while the walk runs.

    Sorted after the walk rather than during it: the display reports files as
    they are found, which is only possible while the walk is still producing
    them.
    """
    with walk_progress(
        iter_epub_files(root),
        f"Scanning {short_name(root)}",
        enabled=show_progress,
    ) as walked:
        return sorted(walked)


def _saved_file_facts(db: sqlite_utils.Database) -> dict[str, FileStats]:
    """Return the stored file facts keyed by the canonical book path."""
    return {
        row[0]: FileStats(size=row[1], mtime=row[2], content_hash=row[3])
        for row in db.execute("SELECT path, file_size, file_mtime, content_hash FROM books")
    }


def _facts_match(saved: FileStats | None, current: FileStats) -> bool:
    """Whether two complete file-fact sets prove a file is unchanged.

    A partial read is deliberately never trusted as a change detector. It is
    still stored after a successful extraction so a later scan can retry it,
    but only size, mtime, and content hash together may avoid extraction.
    """
    return (
        saved is not None
        and all(value is not None for value in (*saved, *current))
        and saved == current
    )


def _index_timestamp() -> str:
    """Return an explicit UTC timestamp for a successful indexing write."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def scan_and_index(
    root: Path,
    db: sqlite_utils.Database,
    console: Console | None = None,
    *,
    show_progress: bool = False,
) -> dict:
    """Scan a directory for EPUBs, extract metadata, and index into the database.

    Args:
        root: The root directory to scan for .epub files.
        db: The database connection.
        console: Optional Rich console for result output.
        show_progress: Whether to show a live display. Off by default, and
            opt-in rather than opt-out on purpose: the display shares a console
            with log records so a warning cannot tear through the bar, but that
            sharing only holds once something has installed
            :func:`ebdx.progress.log_sink` as loguru's sink. The CLI does that
            at startup and then passes its own choice here explicitly; a caller
            embedding the scanner has loguru writing to its own stderr handler
            until it does the same, and a display enabled by default would be
            corrupted by the first warning. It renders only when the diagnostic
            stream is a terminal, so turning it on costs a redirected run
            nothing.

    Returns:
        A dictionary with per-run counts: ``total`` files found, ``indexed``
        newly added, ``updated`` already present and refreshed, and
        ``failed`` skipped because they could not be read. Unchanged files do
        not need metadata extraction or a database write, so they are not
        counted as updates.
    """
    from ebdx.db import save_book
    from ebdx.extractor import extract_metadata

    if console is None:
        console = Console()

    # Find all epub files
    epub_files = _find_epub_files(root, show_progress=show_progress)
    console.print(f"[cyan]Found {len(epub_files)} EPUB file(s)[/cyan]")

    stats = {"total": len(epub_files), "indexed": 0, "updated": 0, "failed": 0}

    if not epub_files:
        return stats

    saved_facts: dict[str, FileStats] = {}
    if {"file_size", "file_mtime", "content_hash"} <= set(db["books"].columns_dict):
        saved_facts = _saved_file_facts(db)

    with file_progress(
        epub_files,
        "Extracting metadata",
        enabled=show_progress,
    ) as tracked:
        for epub_path in tracked:
            resolved = str(epub_path.resolve())
            file_stats = get_file_stats(epub_path)
            if _facts_match(saved_facts.get(resolved), file_stats):
                continue

            # Reading a file and storing it fail for different reasons and
            # deserve different levels, so they are caught separately. A file
            # this run could not read is a warning -- expected in a messy
            # library, and --quiet is meant to hide it. A write that fails is
            # an error: the database or the disk is the problem, not the book,
            # and --quiet promises to show errors.
            try:
                metadata = extract_metadata(epub_path)
            except Exception as e:
                logger.warning(f"Error reading {epub_path}: {e}")
                stats["failed"] += 1
                continue

            if metadata is None:
                logger.warning(f"No metadata found for {epub_path}")
                stats["failed"] += 1
                continue

            try:
                # save_book keys a book by its absolute path; the resolved path
                # is also what search results report.
                metadata.update(
                    {
                        "path": resolved,
                        "file_size": file_stats.size,
                        "file_mtime": file_stats.mtime,
                        "content_hash": file_stats.content_hash,
                        "indexed_at": _index_timestamp(),
                    }
                )
                saved = save_book(db, metadata)
            except Exception as e:
                logger.error(f"Failed to store {epub_path}: {e}")
                stats["failed"] += 1
                continue

            stats["indexed" if saved.created else "updated"] += 1
            # A second path resolving to this file (for example, a symlink)
            # sees the facts just written and can skip extraction too.
            saved_facts[resolved] = file_stats

    return stats


def plan_index(
    root: Path,
    db: sqlite_utils.Database | None,
    console: Console | None = None,
    *,
    show_progress: bool = False,
) -> dict:
    """Report what :func:`scan_and_index` would do, without writing anything.

    Returns the same counts, so a dry run and the real run it predicts are
    directly comparable. ``db`` is ``None`` when no database exists yet, in
    which case every readable EPUB is a would-be insert.

    Metadata is extracted only for files whose complete stored facts do not
    match the current file. That keeps the predicted counts aligned with the
    real incremental run while still reporting files that would fail during
    extraction. It gets the same progress display -- see
    :func:`scan_and_index` for what ``show_progress`` means.
    """
    from ebdx.db import UnindexableDatabaseError, plan_mode
    from ebdx.extractor import extract_metadata

    if console is None:
        console = Console()

    # Settled before the library is scanned. Whether this database can be
    # indexed has nothing to do with how many files are in the library, and an
    # empty library must not turn an impossible run into a clean zero report.
    if db is None:
        mode = "insert-all"
    else:
        predicted = plan_mode(db)
        if predicted.mode == "unusable":
            # Not a layout this build writes, so no counts are predicted for
            # it -- see plan_mode. The CLI checks the mode first so it can
            # render this nicely; the raise is what protects every other
            # caller from a number that was never meant to be trusted.
            raise UnindexableDatabaseError(predicted.reason)
        mode = predicted.mode

    epub_files = _find_epub_files(root, show_progress=show_progress)
    console.print(f"[cyan]Found {len(epub_files)} EPUB file(s)[/cyan]")

    stats = {"total": len(epub_files), "indexed": 0, "updated": 0, "failed": 0}

    if not epub_files:
        return stats

    known_paths: set[str] = set()
    saved_facts: dict[str, FileStats] = {}
    if mode == "compare" and db is not None:
        known_paths = {row[0] for row in db.execute("SELECT path FROM books")}
        # A version-1 database is readable during a dry run but has not yet
        # received the file-stat migration a real run applies before scanning.
        # Treat all of its facts as absent rather than issuing a query for
        # columns that do not exist yet.
        if {"file_size", "file_mtime", "content_hash"} <= set(db["books"].columns_dict):
            saved_facts = _saved_file_facts(db)

    with file_progress(
        epub_files,
        "Extracting metadata",
        enabled=show_progress,
    ) as tracked:
        for epub_path in tracked:
            try:
                resolved = str(epub_path.resolve())
                file_stats = get_file_stats(epub_path)
                if _facts_match(saved_facts.get(resolved), file_stats):
                    continue

                metadata = extract_metadata(epub_path)
                if metadata is None:
                    logger.warning(f"No metadata found for {epub_path}")
                    stats["failed"] += 1
                    continue
                # save_book resolves before keying, so classify against the same form.
                stats["updated" if resolved in known_paths else "indexed"] += 1
                # Counted as known from here on: a real run has written this
                # path by now, so a later file resolving to it -- a symlink
                # beside its target, say -- is an update rather than a second
                # insert.
                known_paths.add(resolved)
                saved_facts[resolved] = file_stats
            except Exception as e:
                logger.warning(f"Error processing {epub_path}: {e}")
                stats["failed"] += 1

    return stats
