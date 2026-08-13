"""
Scanner module for ebdx.

Walks directories to find EPUB files and extracts their metadata
for indexing into the database.
"""

import sqlite3
from pathlib import Path

from rich.console import Console


def scan_and_index(
    root: Path,
    db: sqlite3.Connection,
    console: Console | None = None,
) -> dict:
    """Scan a directory for EPUBs, extract metadata, and index into the database.

    Args:
        root: The root directory to scan for .epub files.
        db: The database connection.
        console: Optional Rich console for progress/status output.

    Returns:
        A dictionary with counts: total, indexed, failed.
    """
    from ebdx.db import save_book
    from ebdx.extractor import extract_metadata

    if console is None:
        console = Console()

    # Find all epub files
    epub_files = sorted(root.rglob("*.epub"))
    console.print(f"[cyan]Found {len(epub_files)} EPUB file(s)[/cyan]")

    stats = {"total": len(epub_files), "indexed": 0, "failed": 0}

    if not epub_files:
        return stats

    for epub_path in epub_files:
        try:
            metadata = extract_metadata(epub_path)
            if metadata:
                save_book(db, metadata)
                stats["indexed"] += 1
            else:
                console.print(
                    f"[yellow]No metadata found for {epub_path.name}[/yellow]"
                )
                stats["failed"] += 1
        except Exception as e:
            console.print(f"[red]Error processing {epub_path.name}: {e}[/red]")
            stats["failed"] += 1

    return stats
