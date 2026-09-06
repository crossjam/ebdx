"""Integration tests for the scan -> extract -> store pipeline.

These exercise ``scan_and_index`` against generated EPUBs and the real
database layer, covering the path the ``ebdx index`` command takes.
"""

from ebdx.db import get_database, search_books
from ebdx.scanner import scan_and_index


def test_scan_and_index_stores_an_extracted_epub(tmp_path, make_epub):
    library = tmp_path / "library"
    epub_path = make_epub(
        "library/dune.epub",
        title="Dune",
        author="Frank Herbert",
        subjects=["Science Fiction"],
    )
    db = get_database(str(tmp_path / "ebdx.db"))

    stats = scan_and_index(library, db)

    assert stats["total"] == 1
    assert stats["indexed"] == 1
    assert stats["failed"] == 0

    rows = list(db["books"].rows)
    assert len(rows) == 1
    assert rows[0]["title"] == "Dune"
    assert rows[0]["path"] == str(epub_path.resolve())

    assert [hit["title"] for hit in search_books(db, "Dune")] == ["Dune"]


def test_scan_and_index_finds_epubs_at_depth(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/a/one.epub", title="One", author="A")
    make_epub("library/a/b/two.epub", title="Two", author="B")
    db = get_database(str(tmp_path / "ebdx.db"))

    stats = scan_and_index(library, db)

    assert stats["indexed"] == 2
    assert db["books"].count == 2
