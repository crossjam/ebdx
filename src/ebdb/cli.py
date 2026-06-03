from pathlib import Path

import click
from loguru import logger
from platformdirs import user_data_dir
from rich.console import Console
from rich.table import Table

APP_NAME = "ebdb"
APP_AUTHOR = "crossjam"


def get_data_dir():
    data_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@click.group()
def cli():
    """ebdb - eBook Database tool."""
    pass


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
def discover(paths: tuple[Path, ...]):
    """Recursively find and list EPUB files."""
    if not paths:
        paths = (Path.cwd(),)

    console = Console()
    epub_files = []

    with console.status("[bold green]Discovering EPUBs..."):
        for path in paths:
            if path.is_file() and path.suffix.lower() == ".epub":
                epub_files.append(path)
            elif path.is_dir():
                epub_files.extend(list(path.rglob("*.epub")))

    if not epub_files:
        console.print("[yellow]No EPUB files discovered.[/yellow]")
        return

    table = Table(title=f"Discovered {len(epub_files)} EPUB files")
    table.add_column("Filename", style="cyan")
    table.add_column("Path", style="magenta")

    for epub in epub_files:
        table.add_row(epub.name, str(epub.parent))

    console.print(table)


@cli.command()
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
def index(root: Path):
    """Recursively find and index EPUB files."""
    console = Console()
    data_dir = get_data_dir()
    logger.info(f"Using data directory: {data_dir}")

    epub_files = []
    with console.status(f"[bold green]Scanning {root} for EPUBs..."):
        for path in root.rglob("*.epub"):
            epub_files.append(path)

    if not epub_files:
        console.print("[yellow]No EPUB files found.[/yellow]")
        return

    table = Table(title=f"Found {len(epub_files)} EPUB files")
    table.add_column("Filename", style="cyan")
    table.add_column("Path", style="magenta")

    for epub in epub_files:
        table.add_row(epub.name, str(epub.parent))

    console.print(table)


@cli.command()
@click.argument("query")
def search(query: str):
    """Search for indexed eBooks."""
    logger.info(f"Searching for: {query}")


def main():
    cli()


if __name__ == "__main__":
    main()
