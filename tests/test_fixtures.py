"""Smoke tests for the EPUB fixtures in conftest.py.

These assert the generated files round-trip through ``ebooklib.epub.read_epub``
so the rest of the suite can rely on ``make_epub`` / ``make_corrupt_epub``.
"""

import pytest
from ebooklib import epub


def test_make_epub_round_trips_through_read_epub(make_epub):
    path = make_epub(
        "dune.epub",
        title="Dune",
        author="Frank Herbert",
        publisher="Chilton Books",
        language="en",
        subjects=["Science Fiction", "Politics"],
    )

    assert path.exists()
    assert path.suffix == ".epub"

    book = epub.read_epub(str(path))
    assert book.title == "Dune"
    assert book.get_metadata("DC", "creator")[0][0] == "Frank Herbert"
    assert book.get_metadata("DC", "publisher")[0][0] == "Chilton Books"
    assert book.get_metadata("DC", "language")[0][0] == "en"
    assert {s[0] for s in book.get_metadata("DC", "subject")} == {
        "Science Fiction",
        "Politics",
    }


def test_make_epub_defaults_are_minimal(make_epub):
    book = epub.read_epub(str(make_epub()))

    assert book.title == "Untitled"
    assert book.get_metadata("DC", "creator") == []
    assert book.get_metadata("DC", "publisher") == []


def test_make_epub_supports_nested_paths(make_epub):
    path = make_epub("authors/herbert/dune.epub", title="Dune")

    assert path.parent.name == "herbert"
    assert epub.read_epub(str(path)).title == "Dune"


def test_make_corrupt_epub_is_rejected_by_read_epub(make_corrupt_epub):
    path = make_corrupt_epub()

    assert path.suffix == ".epub"
    with pytest.raises(epub.EpubException):
        epub.read_epub(str(path))
