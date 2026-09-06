"""Shared pytest fixtures for the ebdx test suite.

``make_epub`` writes a minimal but valid EPUB into ``tmp_path`` from
caller-supplied metadata; ``make_corrupt_epub`` writes a file with an ``.epub``
suffix that is not a valid EPUB. Fixtures are generated rather than committed so
each test can state the exact metadata it depends on and no book binaries live
in the repo.
"""

from __future__ import annotations

import html
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
    book.set_language(language)
    if author:
        book.add_author(author)
    if publisher:
        book.add_metadata("DC", "publisher", publisher)
    for subject in subjects:
        book.add_metadata("DC", "subject", subject)

    chapter = epub.EpubHtml(title="Start", file_name="chapter.xhtml", lang=language)
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
