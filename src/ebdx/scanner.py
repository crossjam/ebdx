"""
Scanner module for ebdx.

Walks directories to find EPUB files and extracts their metadata
for indexing into the database.
"""

from collections.abc import Iterator
from pathlib import Path

import sqlite_utils
from loguru import logger
from rich.console import Console


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


def scan_and_index(
    root: Path,
    db: sqlite_utils.Database,
    console: Console | None = None,
) -> dict:
    """Scan a directory for EPUBs, extract metadata, and index into the database.

    Args:
        root: The root directory to scan for .epub files.
        db: The database connection.
        console: Optional Rich console for progress/status output.

    Returns:
        A dictionary with per-run counts: ``total`` files found, ``indexed``
        newly added, ``updated`` already present and refreshed, and
        ``failed`` skipped because they could not be read.
    """
    from ebdx.db import save_book
    from ebdx.extractor import extract_metadata

    if console is None:
        console = Console()

    # Find all epub files
    epub_files = sorted(iter_epub_files(root))
    console.print(f"[cyan]Found {len(epub_files)} EPUB file(s)[/cyan]")

    stats = {"total": len(epub_files), "indexed": 0, "updated": 0, "failed": 0}

    if not epub_files:
        return stats

    for epub_path in epub_files:
        try:
            metadata = extract_metadata(epub_path)
            if metadata is None:
                # A file this run could not read is a warning, not a result:
                # it goes through the logger so --quiet suppresses it while
                # the failure still shows up in the returned counts.
                logger.warning(f"No metadata found for {epub_path}")
                stats["failed"] += 1
                continue

            # save_book keys a book by its absolute path; the resolved path
            # is also what search results report.
            metadata["path"] = str(epub_path.resolve())
            saved = save_book(db, metadata)
            stats["indexed" if saved.created else "updated"] += 1
        except Exception as e:
            logger.warning(f"Error processing {epub_path}: {e}")
            stats["failed"] += 1

    return stats


def plan_index(
    root: Path,
    db: sqlite_utils.Database | None,
    console: Console | None = None,
) -> dict:
    """Report what :func:`scan_and_index` would do, without writing anything.

    Returns the same counts, so a dry run and the real run it predicts are
    directly comparable. ``db`` is ``None`` when no database exists yet, in
    which case every readable EPUB is a would-be insert.

    Metadata is still extracted, because extraction is a read and it is the
    only way to know which files would fail; those counts are therefore
    accurate rather than guessed.
    """
    from ebdx.extractor import extract_metadata

    if console is None:
        console = Console()

    epub_files = sorted(iter_epub_files(root))
    console.print(f"[cyan]Found {len(epub_files)} EPUB file(s)[/cyan]")

    stats = {"total": len(epub_files), "indexed": 0, "updated": 0, "failed": 0}

    if not epub_files:
        return stats

    from ebdx.db import plan_mode

    mode = "insert-all" if db is None else plan_mode(db).mode

    known_paths: set[str] = set()
    if mode == "compare":
        known_paths = {row[0] for row in db.execute("SELECT path FROM books")}

    for epub_path in epub_files:
        try:
            metadata = extract_metadata(epub_path)
            if metadata is None:
                logger.warning(f"No metadata found for {epub_path}")
                stats["failed"] += 1
                continue
            if mode == "fail-all":
                # The open would succeed but every write would fail, so
                # promising an insert here would promise a run that cannot
                # happen.
                stats["failed"] += 1
                continue
            # save_book resolves before keying, so classify against the same form.
            resolved = str(epub_path.resolve())
            stats["updated" if resolved in known_paths else "indexed"] += 1
        except Exception as e:
            logger.warning(f"Error processing {epub_path}: {e}")
            stats["failed"] += 1

    return stats
