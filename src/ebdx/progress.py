"""Live progress display for the long-running parts of ebdx.

A progress display is diagnostic, not a result, so everything here renders on
stderr -- and through the *same* :class:`~rich.console.Console` the log sink
writes through. That sharing is the point of this module: while a live display
owns the bottom lines of a terminal, a second writer emitting a warning there
would land inside the bar and be redrawn over. Routing records through the same
console makes Rich erase the display, print the record whole, and draw the
display again below it.

Results -- the indexing summary, the discover table, the search table -- keep
going through the stdout console in :mod:`ebdx.cli` and are untouched by any of
this.

Nothing renders unless stderr is a terminal, so a redirected or piped run emits
no frames and no cursor-control sequences.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from rich.ansi import AnsiDecoder
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Column

# One console for every diagnostic byte this tool writes. Built with
# ``stderr=True`` rather than a captured stream so it resolves ``sys.stderr``
# at print time, which is what lets Click's CliRunner capture it.
_CONSOLE = Console(stderr=True, emoji=False)

_ANSI_DECODER = AnsiDecoder()


def diagnostic_console() -> Console:
    """Return the stderr console carrying both progress and log records."""
    return _CONSOLE


def log_sink(message: object) -> None:
    """Write one loguru record through the console the display renders on.

    The record arrives already formatted, and already coloured when loguru was
    asked to colourize, so it is decoded from ANSI into a
    :class:`~rich.text.Text` rather than printed as a string. That keeps
    loguru's colours, keeps Rich's width measurement honest about escape
    sequences it would otherwise count as characters, and -- because a ``Text``
    is a renderable, not markup -- leaves a path containing ``[...]`` alone.
    Rich then drops the colour itself when the stream is not a terminal.

    Soft wrap is on so a long path reaches the terminal the way a raw write
    would, rather than being folded in the middle of a filename.
    """
    diagnostic_console().print(
        _ANSI_DECODER.decode_line(str(message).rstrip("\n")),
        soft_wrap=True,
    )


def short_name(path: Path) -> str:
    """A description-sized name for ``path``.

    The description column is the fixed part of the line, so a full library
    path there would crowd the bar off an 80-column terminal. The final
    component is enough to tell two runs apart; the command's own output has
    already printed the whole path.
    """
    return path.name or str(path)


def _description_column() -> TextColumn:
    """The fixed part of the line, naming what is being worked through.

    Markup is off and the style is applied as a style: the description carries
    a directory name, and a directory called ``x[dim]y`` would otherwise have
    the bracketed part read as a tag and silently dropped from the display.
    """
    return TextColumn(
        "{task.description}",
        style="progress.description",
        markup=False,
    )


def _label_column() -> TextColumn:
    """The column naming the item in hand, truncated rather than wrapped.

    Without this the longest filename in a library would decide the layout and
    the bar would jump around as it scrolls past.
    """
    return TextColumn(
        "{task.fields[label]}",
        table_column=Column(no_wrap=True, overflow="ellipsis", ratio=1),
        style="dim",
        markup=False,
    )


def _stream_is_a_terminal(console: Console) -> bool:
    """Report whether the console's destination is genuinely a terminal.

    Rich's ``Console.is_terminal`` is not the same question: ``FORCE_COLOR`` in
    the environment makes it answer true for a stream that is a redirected file,
    and a live display started on that answer writes frames and cursor-control
    sequences into the file. The guarantee this module makes is about the
    destination, so the destination is what gets asked.

    A console built with ``stderr=True`` resolves its file at access time, and a
    stream can be missing its ``isatty`` or already closed; any of those is
    treated as "not a terminal", which is the safe direction to be wrong in.
    """
    try:
        isatty = getattr(console.file, "isatty", None)
        return bool(isatty and isatty())
    except (ValueError, OSError):
        # ValueError: I/O operation on closed file. OSError: detached stream.
        return False


@contextmanager
def _display(*columns: ProgressColumn, enabled: bool) -> Iterator[Progress]:
    """Start a transient display, or a disabled one that renders nothing.

    The two suppression rules -- ``--quiet`` asked for silence, and the
    destination stream is not a terminal -- are both applied here so no caller
    can implement only one of them. A disabled ``Progress`` never starts its
    live display and prints nothing at all, not even the single final frame
    Rich would otherwise emit to a non-terminal when the display stops.

    The display is transient: once the work is done the command's own summary
    is the record, and a finished bar left above it is only something for that
    summary to be confused with.
    """
    console = diagnostic_console()
    progress = Progress(
        *columns,
        console=console,
        transient=True,
        disable=not enabled or not _stream_is_a_terminal(console),
    )
    with progress:
        yield progress


@contextmanager
def walk_progress(
    paths: Iterable[Path],
    description: str,
    *,
    enabled: bool = True,
) -> Iterator[Iterator[Path]]:
    """Yield an iterator over ``paths`` that pulses while the walk runs.

    A directory walk cannot know how many files it will find without walking
    first, so there is no total to report a position against. A pulsing bar
    with a running count says what is true -- work is happening, this much has
    been found -- where a bar measured against a total that grows as it fills
    would be claiming a proportion that means nothing.
    """

    with _display(
        SpinnerColumn(),
        _description_column(),
        BarColumn(),
        _label_column(),
        TimeElapsedColumn(),
        enabled=enabled,
    ) as progress:
        # Seeded rather than left blank: a walk that has found nothing yet --
        # including one crossing a large tree holding no EPUBs at all -- still
        # has a count to report, and "0 found" is that count.
        task = progress.add_task(description, total=None, label="0 found")

        def walked() -> Iterator[Path]:
            for found, path in enumerate(paths, start=1):
                progress.update(task, advance=1, label=f"{found} found")
                yield path

        yield walked()


@contextmanager
def file_progress(
    files: Sequence[Path],
    description: str,
    *,
    enabled: bool = True,
) -> Iterator[Iterator[Path]]:
    """Yield an iterator over ``files`` driving a determinate bar.

    The total is known before the first file is opened, so this reports a real
    position and names the file in hand. Wrapped as a context manager rather
    than returned as a bare generator so the display is stopped -- and the
    cursor restored -- even if the consumer's loop raises.
    """

    with _display(
        SpinnerColumn(),
        _description_column(),
        BarColumn(),
        MofNCompleteColumn(),
        _label_column(),
        TimeRemainingColumn(),
        enabled=enabled,
    ) as progress:
        task = progress.add_task(description, total=len(files), label="")

        def tracked() -> Iterator[Path]:
            for path in files:
                progress.update(task, label=path.name)
                yield path
                progress.advance(task)

        yield tracked()
