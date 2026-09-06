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


def test_empty_directory_reports_zero(tmp_path):
    library = tmp_path / "empty"
    library.mkdir()
    db = get_database(str(tmp_path / "ebdx.db"))

    assert scan_and_index(library, db) == {
        "total": 0,
        "indexed": 0,
        "updated": 0,
        "failed": 0,
    }


def test_second_run_reports_every_file_as_updated(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    make_epub("library/b.epub", title="B", author="BB")
    db = get_database(str(tmp_path / "ebdx.db"))

    first = scan_and_index(library, db)
    assert (first["indexed"], first["updated"], first["failed"]) == (2, 0, 0)

    second = scan_and_index(library, db)
    assert (second["total"], second["indexed"], second["updated"], second["failed"]) == (
        2,
        0,
        2,
        0,
    )
    assert db["books"].count == 2


def test_counts_distinguish_a_new_file_from_updates(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    db = get_database(str(tmp_path / "ebdx.db"))
    scan_and_index(library, db)

    make_epub("library/c.epub", title="C", author="CC")
    stats = scan_and_index(library, db)

    assert stats["indexed"] == 1
    assert stats["updated"] == 1
    assert db["books"].count == 2


def test_editing_an_epub_refreshes_its_record(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/book.epub", title="First Title", author="AA")
    db = get_database(str(tmp_path / "ebdx.db"))
    scan_and_index(library, db)

    # Same path, new content.
    make_epub("library/book.epub", title="Second Title", author="AA")
    scan_and_index(library, db)

    rows = list(db["books"].rows)
    assert len(rows) == 1
    assert rows[0]["title"] == "Second Title"


def test_one_bad_file_does_not_stop_the_run(tmp_path, make_epub, make_corrupt_epub):
    library = tmp_path / "library"
    make_epub("library/good-one.epub", title="Good One", author="AA")
    make_epub("library/good-two.epub", title="Good Two", author="BB")
    make_corrupt_epub("library/broken.epub")
    db = get_database(str(tmp_path / "ebdx.db"))

    stats = scan_and_index(library, db)

    assert stats["total"] == 3
    assert stats["indexed"] == 2
    assert stats["failed"] == 1
    assert sorted(r["title"] for r in db["books"].rows) == ["Good One", "Good Two"]
