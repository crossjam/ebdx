"""Shared pytest fixtures for the ebdx test suite.

``make_epub`` writes a minimal but valid EPUB into ``tmp_path`` from
caller-supplied metadata; ``make_corrupt_epub`` writes a file with an ``.epub``
suffix that is not a valid EPUB. Fixtures are generated rather than committed so
each test can state the exact metadata it depends on and no book binaries live
in the repo.

``diagnostic_terminal`` and ``terminal_frames`` are for the progress display,
which renders only on a terminal and so is invisible to a test until one is
faked.
"""

from __future__ import annotations

import html
import io
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from ebooklib import epub

EpubFactory = Callable[..., Path]
CorruptFactory = Callable[..., Path]


def _write_epub(
    path: Path,
    *,
    title: str,
    author: str,
    publisher: str,
    language: str,
    subjects: Sequence[str],
) -> Path:
    """Build a small valid EPUB at ``path`` and return it."""
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:ebdx-test-{path.stem}")
    book.set_title(title)
    if language:
        book.set_language(language)
    if author:
        book.add_author(author)
    if publisher:
        book.add_metadata("DC", "publisher", publisher)
    for subject in subjects:
        book.add_metadata("DC", "subject", subject)

    chapter = epub.EpubHtml(title="Start", file_name="chapter.xhtml", lang=language or None)
    heading = html.escape(title or "Untitled")
    chapter.content = f"<h1>{heading}</h1><p>Body text.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.toc = (chapter,)
    book.spine = ["nav", chapter]

    path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def make_epub(tmp_path: Path) -> EpubFactory:
    """Return a factory that writes a valid EPUB beneath ``tmp_path``.

    Call it as ``make_epub("dune.epub", title="Dune", author="Frank Herbert")``.
    A bare name lands directly in ``tmp_path``; a relative path containing
    directories is created beneath it, so a test can build a nested library.
    Every metadata argument has a default, so ``make_epub()`` alone is valid.
    """

    def factory(
        name: str = "book.epub",
        *,
        title: str = "Untitled",
        author: str = "",
        publisher: str = "",
        language: str = "en",
        subjects: Sequence[str] = (),
    ) -> Path:
        return _write_epub(
            tmp_path / name,
            title=title,
            author=author,
            publisher=publisher,
            language=language,
            subjects=subjects,
        )

    return factory


@pytest.fixture
def make_corrupt_epub(tmp_path: Path) -> CorruptFactory:
    """Return a factory that writes a file named like an EPUB but not a valid one."""

    def factory(
        name: str = "corrupt.epub",
        content: str = "this is not a zip archive",
    ) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    return factory


class TerminalStringIO(io.StringIO):
    """An in-memory stream that reports itself as a terminal.

    The progress display decides whether to render by asking its destination
    ``isatty()``, so a capture buffer has to answer that question the way a
    terminal would for a test to see any frames at all.
    """

    def isatty(self) -> bool:
        return True


@pytest.fixture
def diagnostic_terminal(monkeypatch) -> io.StringIO:
    """Point ebdx's shared diagnostic console at a captured, forced-terminal stream.

    Two things resolve their output through ``ebdx.progress``: the progress
    display, which renders only when that console is a terminal, and the log
    sink. Redirecting the one console is therefore what lets a test both see a
    display at all and watch how a log record and a live display behave when
    they land in the same place.

    Colour is off so assertions read against plain text; the cursor and
    erase-line sequences a live display emits are left in, since they are part
    of what is being checked.

    The buffer answers ``isatty()`` truthfully-for-a-terminal because that is
    the question the display now asks. ``force_terminal`` alone would tell Rich
    to render but would leave the suppression check seeing a plain file, so the
    fixture would capture nothing.
    """
    from rich.console import Console

    from ebdx import progress

    buf = TerminalStringIO()
    monkeypatch.setattr(
        progress,
        "_CONSOLE",
        Console(file=buf, force_terminal=True, width=100, color_system=None, emoji=False),
    )
    return buf


def terminal_frames(captured: str) -> list[str]:
    """Split captured terminal output into the lines a screen would have shown.

    A live display overwrites its line with a carriage return rather than a
    newline, so splitting on both is what separates one rendered frame -- or
    one log record -- from the next. Escape sequences are dropped.
    """
    plain = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", captured)
    return [frame for frame in re.split(r"[\r\n]+", plain) if frame.strip()]
