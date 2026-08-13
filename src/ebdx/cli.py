"""
CLI module for the ebdx eBook Database tool.

Provides a Click-based command-line interface with discover, index, and search
commands for managing an EPUB metadata index.
"""

from importlib.metadata import metadata as get_metadata
from importlib.metadata import version as get_version
from pathlib import Path

import click
from platformdirs import user_data_dir
from rich.console import Console

APP_NAME = "ebdx"
APP_AUTHOR = "crossjam"
console = Console()


def _get_pkg_version() -> str:
    """Return the installed package version, or 'unknown' if unavailable."""
    try:
        return get_version("ebdx")
    except Exception:
        return "unknown"


def _parse_pkg_metadata():
    """Return (summary, repository_url) from package metadata."""
    try:
        meta = get_metadata("ebdx")
        summary = meta["Summary"] or ""
        repo_url = ""
        for entry in meta.get_all("Project-URL") or []:
            label, _, link = entry.partition(", ")
            if label.strip().lower() == "repository":
                repo_url = link.strip()
                break
    except Exception:
        summary = repo_url = "unknown"
    return summary, repo_url


def get_data_dir() -> Path:
    """Get the XDG compliant data directory for the app."""
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def _ensure_data_dir() -> Path:
    """Create the app data directory if it doesn't exist and return it.

    Call this only from commands that actually write to the data directory.
    """
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_default_db_path() -> Path:
    """Get the default path for the SQLite database in the XDG data directory."""
    return get_data_dir() / "ebdx.db"


@click.group()
def cli():
    """ebdx - eBook Database tool.

    Index and search EPUB metadata from your personal library.
    """
    pass


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
def discover(paths: tuple[Path, ...]):
    """Recursively find and list EPUB files.

    Scans the specified PATHS for .epub files and displays them in a table.
    If no paths are provided, scans the current directory.
    """
    if not paths:
        paths = (Path.cwd(),)

    epub_files = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".epub":
            epub_files.append(path)
        elif path.is_dir():
            epub_files.extend(path.rglob("*.epub"))

    if not epub_files:
        console.print("[yellow]No EPUB files discovered.[/yellow]")
        return

    from rich.table import Table

    table = Table(title=f"Discovered {len(epub_files)} EPUB file(s)")
    table.add_column("Filename", style="cyan")
    table.add_column("Path", style="magenta")

    for epub in epub_files:
        table.add_row(epub.name, str(epub.parent))

    console.print(table)


@cli.command()
@click.argument(
    "root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--database",
    "-d",
    type=click.Path(file_okay=True, dir_okay=False),
    default=None,
    help="Database path (default: XDG data directory)",
)
def index(root: Path, database):
    """Index metadata from EPUB files in the specified directory.

    Recursively scans ROOT for .epub files, extracts their metadata,
    and stores it in a SQLite database with FTS5 search support.
    """
    from ebdx.db import get_database
    from ebdx.scanner import scan_and_index

    if database is None:
        _ensure_data_dir()
        database = get_default_db_path()

    console.print(f"[cyan]Indexing EPUBs in:[/cyan] {root}")
    console.print(f"[cyan]Database:[/cyan] {database}")

    db = get_database(str(database))
    stats = scan_and_index(root, db, console)

    console.print()
    console.print("[green]Indexing complete![/green]")

    from rich.table import Table

    summary = Table(title="Indexing Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="magenta", justify="right")
    summary.add_row("Total found", str(stats["total"]))
    summary.add_row("Successfully indexed", str(stats["indexed"]))
    summary.add_row("Failed", str(stats["failed"]))
    console.print(summary)


@cli.command()
@click.argument("query")
@click.option(
    "--database",
    "-d",
    type=click.Path(file_okay=True, dir_okay=False),
    default=None,
    help="Database path (default: XDG data directory)",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    show_default=True,
    help="Maximum number of results to return",
)
def search(query: str, database, limit: int):
    """Search for indexed eBooks using full-text search.

    Searches across title, author, and series fields using SQLite FTS5.

    Example:

    \b
        ebdx search "Dune"
        ebdx search "Asimov" --limit 10
    """
    from ebdx.db import get_database, search_books

    if database is None:
        database = get_default_db_path()

    if not Path(database).exists():
        console.print(f"[red]No database found at:[/red] {database}")
        console.print(
            "[yellow]Run 'ebdx index <directory>' to create a database first.[/yellow]"
        )
        raise click.Abort()

    db = get_database(str(database))
    results = search_books(db, query, limit=limit)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    from rich.table import Table

    table = Table(title=f"Search Results ({len(results)} found)")
    table.add_column("Title", style="cyan")
    table.add_column("Author", style="magenta")
    table.add_column("Series", style="green")
    table.add_column("Index", style="yellow")

    for row in results:
        table.add_row(
            row["title"],
            row["author"],
            row.get("series") or "",
            str(row.get("series_index", "")),
        )

    console.print(table)


@cli.command()
@click.option(
    "--database",
    "-d",
    type=click.Path(file_okay=True, dir_okay=False),
    default=None,
    help="Show schema for a specific database file",
)
def schema(database):
    """Display the database schema.

    Shows the tables and indexes in the ebdx SQLite database.
    """
    from ebdx.db import get_database

    if database is None:
        database = get_default_db_path()

    if not Path(database).exists():
        console.print(f"[red]No database found at:[/red] {database}")
        console.print(
            "[yellow]Run 'ebdx index <directory>' to create a database first.[/yellow]"
        )
        return

    db = get_database(str(database))

    from rich.table import Table

    table = Table(title="Database Schema")
    table.add_column("Table", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("SQL", style="white")

    results = db.execute(
        "SELECT name, type, sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger') "
        "ORDER BY type, name"
    ).fetchall()

    for name, typ, sql in results:
        table.add_row(name, typ, sql or "")

    console.print(table)


@cli.command()
def about():
    """Display information about the ebdx project.

    Shows project summary, version, and default storage paths.
    """
    summary, repo_url = _parse_pkg_metadata()
    data_dir = get_data_dir()
    db_path = get_default_db_path()

    lines = [
        "ebdx",
        f"  version: {_get_pkg_version()}",
        f"  summary: {summary}",
        f"  repository: {repo_url}",
        "",
        f"  data directory: {data_dir}",
        f"  default database: {db_path}",
        "",
        "  next steps: ebdx index <directory> | ebdx search <query>",
    ]
    console.print("\n".join(lines), soft_wrap=True)


@cli.command()
def version():
    """Display the ebdx version."""
    console.print(f"ebdx, version {_get_pkg_version()}")


def main():
    cli()


if __name__ == "__main__":
    main()
