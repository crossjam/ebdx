"""
Scanner module for ebdx.

Walks directories to find EPUB files and extracts their metadata
for indexing into the database.
"""

from collections.abc import Iterator
from pathlib import Path

import sqlite_utils
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
                console.print(
                    f"[yellow]No metadata found for {epub_path.name}[/yellow]"
                )
                stats["failed"] += 1
                continue

            # save_book keys a book by its absolute path; the resolved path
            # is also what search results report.
            metadata["path"] = str(epub_path.resolve())
            saved = save_book(db, metadata)
            stats["indexed" if saved.created else "updated"] += 1
        except Exception as e:
            console.print(f"[red]Error processing {epub_path.name}: {e}[/red]")
            stats["failed"] += 1

    return stats
