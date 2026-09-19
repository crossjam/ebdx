"""
CLI module for the ebdx eBook Database tool.

Provides a Click-based command-line interface with discover, index, and search
commands for managing an EPUB metadata index.
"""

import sqlite3
import sys
from importlib.metadata import metadata as get_metadata
from importlib.metadata import version as get_version
from pathlib import Path

import click
from loguru import logger
from platformdirs import user_data_dir
from rich.console import Console

APP_NAME = "ebdx"
APP_AUTHOR = "crossjam"
console = Console()


def _configure_logging(*, verbose: bool, quiet: bool) -> None:
    """Replace loguru's default sink with one at the requested level.

    Default is WARNING; ``--verbose`` lifts it to INFO (so the per-open
    "Opening database" line shows), ``--quiet`` drops it to ERROR. Rich
    ``console.print`` output is unaffected — it carries command results, not
    logs, and stays visible under ``--quiet``.
    """
    if verbose and quiet:
        raise click.UsageError("Pass at most one of -v/--verbose and -q/--quiet.")
    level = "INFO" if verbose else "ERROR" if quiet else "WARNING"
    logger.remove()
    logger.add(sys.stderr, level=level)


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


def _open_database(database, *, read_only: bool = False):
    """Open ``database``, reporting an unusable file instead of raising.

    Opening runs the schema check, which is itself SQLite work: a locked
    file, a truncated file, or something that is not a database at all fails
    here rather than at query time. Every command goes through this so none
    of them can print a traceback for a bad database file.

    Under ``read_only`` the schema check is skipped and SQLite refuses writes,
    which is what a dry run needs. Callers must confirm the file exists first:
    a read-only connection cannot create one, and the resulting error would be
    reported here as an unusable database rather than a missing one.
    """
    from ebdx.db import get_database

    try:
        return get_database(str(database), read_only=read_only)
    except sqlite3.DatabaseError as e:
        _abort_unusable_database(database, e)


def _abort_unusable_database(database, error) -> None:
    """Report a file SQLite cannot read as an ebdx database, and stop."""
    console.print(f"[red]Cannot open database:[/red] {error}")
    console.print(f"[yellow]Not a usable ebdx database: {database}[/yellow]")
    raise click.Abort() from error


def _inspect(database, fn, *args):
    """Run a read-only schema inspection, reporting a bad file instead of raising.

    A read-only open does no schema work, so a corrupt or locked file is not
    discovered until the first query -- which for a dry run is one of these
    inspections. Without this they would escape as a traceback, the very thing
    _open_database exists to prevent.
    """
    try:
        return fn(*args)
    except sqlite3.DatabaseError as e:
        _abort_unusable_database(database, e)


def _is_dry_run(ctx: click.Context) -> bool:
    """Whether this run was started with the group's ``--dry-run`` flag."""
    return bool((ctx.obj or {}).get("dry_run"))


def _dry_run_banner(action: str) -> None:
    """Announce a dry run so its output cannot be read as a completed one."""
    console.print(f"[bold yellow]DRY RUN[/bold yellow] — {action}; nothing will be changed")


def _summary_table(title: str, rows: list[tuple[str, str]]):
    """Build the two-column metric/count table the index commands report with."""
    from rich.table import Table

    table = Table(title=title)
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="magenta", justify="right")
    for metric, count in rows:
        table.add_row(metric, count)
    return table


def _abort_invalid_query(error) -> None:
    """Report an unparseable search query and stop."""
    console.print(f"[red]Invalid search query:[/red] {error}")
    raise click.Abort() from error


def _report_pending_work(db, database) -> list[str]:
    """Print the schema work a real open would have done, and return it."""
    from ebdx.db import describe_pending_schema_work

    pending = _inspect(database, describe_pending_schema_work, db)
    for item in pending:
        console.print(f"[yellow]Would:[/yellow] {item}")
    return pending


def _dry_run_index(root: Path, database, *, using_default: bool) -> None:
    """Report what ``index`` would do, touching neither disk nor database."""
    from ebdx.db import describe_pending_schema_work, plan_mode
    from ebdx.scanner import plan_index

    _dry_run_banner("planning an index run")
    console.print(f"[cyan]Would index EPUBs in:[/cyan] {root}")
    console.print(f"[cyan]Database:[/cyan] {database}")

    would_do = []
    if using_default and not get_data_dir().exists():
        would_do.append(f"create the data directory {get_data_dir()}")

    # Only the default location is created for you. An explicit --database in a
    # directory that does not exist cannot be created by SQLite, so a real run
    # fails on open -- report that rather than a tidy creation plan.
    parent = Path(database).parent
    if not Path(database).exists() and not using_default and not parent.is_dir():
        console.print(f"[red]Cannot index this database:[/red] {parent} does not exist")
        console.print("[yellow]A real run would fail to open the database file.[/yellow]")
        raise click.Abort()

    db = None
    if Path(database).exists():
        db = _open_database(database, read_only=True)
        predicted = _inspect(database, plan_mode, db)
        if predicted.mode == "unusable":
            # Not a layout this build writes, so what a real run would do
            # cannot be predicted without reproducing the whole schema-setup
            # and write paths here. Say what is wrong instead of guessing.
            console.print(f"[red]Not a usable ebdx database:[/red] {predicted.reason}")
            console.print(
                f"[yellow]Delete {database} and run 'ebdx index <directory>' "
                "to rebuild it.[/yellow]"
            )
            raise click.Abort()
        would_do.extend(_inspect(database, describe_pending_schema_work, db))
    else:
        would_do.append(f"create the database file {database}")
        would_do.append("create the books, authors, and full-text schema")

    for item in would_do:
        console.print(f"[yellow]Would:[/yellow] {item}")

    stats = _inspect(database, plan_index, root, db, console)

    console.print()
    console.print("[yellow]Dry run complete — no changes were made.[/yellow]")
    console.print(
        _summary_table(
            "Indexing Summary (dry run)",
            [
                ("Total found", str(stats["total"])),
                ("Would index", str(stats["indexed"])),
                ("Would update", str(stats["updated"])),
                ("Would fail", str(stats["failed"])),
            ],
        )
    )


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
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show informational log output (database opens, rebuilds).",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress warnings; show only errors.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would change without changing it. Give it before the command.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool, dry_run: bool):
    """ebdx - eBook Database tool.

    Index and search EPUB metadata from your personal library.
    """
    _configure_logging(verbose=verbose, quiet=quiet)
    # Carried on ctx.obj rather than a module global so the CliRunner tests
    # stay order-independent; subcommands read it with @click.pass_context.
    ctx.ensure_object(dict)["dry_run"] = dry_run


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
def discover(paths: tuple[Path, ...]):
    """Recursively find and list EPUB files.

    Scans the specified PATHS for .epub files and displays them in a table.
    If no paths are provided, scans the current directory.
    """
    from ebdx.scanner import iter_epub_files

    if not paths:
        paths = (Path.cwd(),)

    epub_files = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".epub":
            epub_files.append(path)
        elif path.is_dir():
            epub_files.extend(iter_epub_files(path))

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
@click.pass_context
def index(ctx: click.Context, root: Path, database):
    """Index metadata from EPUB files in the specified directory.

    Recursively scans ROOT for .epub files, extracts their metadata,
    and stores it in a SQLite database with FTS5 search support.
    """
    from ebdx.scanner import scan_and_index

    dry_run = _is_dry_run(ctx)

    using_default = database is None
    if using_default:
        # Creating the data directory is itself a change, so a dry run only
        # computes the path it would have used.
        if not dry_run:
            _ensure_data_dir()
        database = get_default_db_path()

    if dry_run:
        _dry_run_index(root, database, using_default=using_default)
        return

    console.print(f"[cyan]Indexing EPUBs in:[/cyan] {root}")
    console.print(f"[cyan]Database:[/cyan] {database}")

    db = _open_database(database)
    stats = scan_and_index(root, db, console)

    console.print()
    console.print("[green]Indexing complete![/green]")

    from rich.table import Table

    summary = Table(title="Indexing Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="magenta", justify="right")
    summary.add_row("Total found", str(stats["total"]))
    summary.add_row("Newly indexed", str(stats["indexed"]))
    summary.add_row("Updated", str(stats.get("updated", 0)))
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
@click.pass_context
def search(ctx: click.Context, query: str, database, limit: int):
    """Search for indexed eBooks using full-text search.

    Searches across title, author, and series fields using SQLite FTS5.

    Example:

    \b
        ebdx search "Dune"
        ebdx search "Asimov" --limit 10
    """
    from ebdx.db import InvalidQueryError, search_books, validate_query

    if database is None:
        database = get_default_db_path()

    dry_run = _is_dry_run(ctx)
    if dry_run:
        _dry_run_banner("searching read-only")

    # This guard must stay ahead of the open: under --dry-run the database is
    # opened read-only, and a read-only connection to a file that does not
    # exist raises, which would be reported as an unusable database rather
    # than a missing one.
    if not Path(database).exists():
        console.print(f"[red]No database found at:[/red] {database}")
        console.print("[yellow]Run 'ebdx index <directory>' to create a database first.[/yellow]")
        raise click.Abort()

    db = _open_database(database, read_only=dry_run)

    # Settled before anything the dry run might report: a query that cannot be
    # parsed is a query error whatever state the database is in, and a real
    # search would say so too.
    try:
        validate_query(query)
    except InvalidQueryError as e:
        _abort_invalid_query(e)

    repairable = False
    if dry_run:
        from ebdx.db import would_discard_existing_rows, would_repair_search

        _report_pending_work(db, database)
        if _inspect(database, would_discard_existing_rows, db):
            # Anything stored now is discarded by the rebuild, so showing it
            # would be showing rows a real search never sees.
            console.print(
                "[yellow]No results can be shown: the rebuild discards everything "
                "stored now, and the library must be re-indexed first.[/yellow]"
            )
            return
        repairable = _inspect(database, would_repair_search, db)
    try:
        results = search_books(db, query, limit=limit)
    except InvalidQueryError as e:  # pragma: no cover - settled above
        _abort_invalid_query(e)
    except sqlite3.DatabaseError as e:
        if dry_run and repairable:
            # The query needs an index this dry run is refusing to build. That
            # is the reported outcome, not a failure of the dry run: a real
            # search would have rebuilt the index and succeeded. Anything else
            # -- a layout left untouched, an unrecognised one -- is a genuine
            # database error and falls through to the message below.
            console.print(f"[yellow]The search cannot run until that happens:[/yellow] {e}")
            return
        # search_books validates the query first, so reaching here means the
        # database cannot serve the search: a locked file, a corrupt index,
        # schema drift. Reported separately so it is never mistaken for the
        # user mistyping a query. DatabaseError is the parent of
        # OperationalError and also covers corruption reported directly.
        console.print(f"[red]Database error:[/red] {e}")
        console.print(
            f"[yellow]The database at {database} may be damaged; delete it "
            "and re-run 'ebdx index <directory>' to rebuild.[/yellow]"
        )
        raise click.Abort() from e

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    from rich.table import Table

    table = Table(title=f"Search Results ({len(results)} found)")
    table.add_column("Title", style="cyan")
    table.add_column("Author", style="magenta")
    table.add_column("Series", style="green")
    table.add_column("Index", style="yellow")
    table.add_column("Path", style="blue")

    for row in results:
        series_index = row.get("series_index")
        table.add_row(
            row["title"],
            row["author"],
            row.get("series") or "",
            "" if series_index is None else str(series_index),
            row.get("path") or "",
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
@click.pass_context
def schema(ctx: click.Context, database):
    """Display the database schema.

    Shows the tables and indexes in the ebdx SQLite database.
    """
    if database is None:
        database = get_default_db_path()

    dry_run = _is_dry_run(ctx)
    if dry_run:
        _dry_run_banner("inspecting the schema read-only")

    # Guard before the open, for the same reason as in `search`.
    if not Path(database).exists():
        console.print(f"[red]No database found at:[/red] {database}")
        console.print("[yellow]Run 'ebdx index <directory>' to create a database first.[/yellow]")
        return

    db = _open_database(database, read_only=dry_run)
    if dry_run:
        _report_pending_work(db, database)

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
