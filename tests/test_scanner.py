"""Integration tests for the scan -> extract -> store pipeline.

These exercise ``scan_and_index`` against generated EPUBs and the real
database layer, covering the path the ``ebdx index`` command takes.
"""

import sqlite3

import pytest
from loguru import logger

from ebdx.db import (
    SCHEMA_VERSION,
    UnindexableDatabaseError,
    get_database,
    search_books,
)
from ebdx.scanner import iter_epub_files, iter_files, plan_index, scan_and_index


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


def test_iter_epub_files_recurses_and_filters_by_suffix(tmp_path, make_epub):
    make_epub("lib/a/one.epub", title="One")
    make_epub("lib/a/b/two.EPUB", title="Two")
    (tmp_path / "lib" / "notes.txt").write_text("nope")
    (tmp_path / "lib" / "cover.epubx").write_text("nope")

    found = {p.name for p in iter_epub_files(tmp_path / "lib")}

    assert found == {"one.epub", "two.EPUB"}


def test_iter_files_is_sorted_and_skips_non_directories(tmp_path):
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("c")

    assert [p.name for p in iter_files(tmp_path)] == ["a.txt", "b.txt", "c.txt"]
    # A file (not a directory) as root yields nothing rather than raising.
    assert list(iter_files(tmp_path / "a.txt")) == []


def test_iter_files_does_not_follow_directory_symlink_loops(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "book.epub").write_text("x")
    loop = real / "loop"
    loop.symlink_to(real, target_is_directory=True)

    # Terminates (Path.walk does not descend symlinked dirs) and the symlink
    # is not reported as a file.
    names = [p.name for p in iter_files(tmp_path)]

    assert names == ["book.epub"]


def _legacy_database(db_path):
    """A pre-path database: `books` exists but has no `path` column, version 0."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT)")
    conn.execute("INSERT INTO books (title, author_id) VALUES ('Stale', 1)")
    conn.commit()
    conn.close()


def test_plan_index_handles_a_pre_path_database(tmp_path, make_epub):
    """A real run rebuilds that schema and inserts everything, so the plan says so."""
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    make_epub("library/b.epub", title="B", author="BB")
    db_path = tmp_path / "legacy.db"
    _legacy_database(db_path)

    stats = plan_index(library, get_database(str(db_path), read_only=True))

    assert stats == {"total": 2, "indexed": 2, "updated": 0, "failed": 0}


def test_plan_index_matches_a_real_run_on_a_pre_path_database(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "legacy.db"
    _legacy_database(db_path)

    planned = plan_index(library, get_database(str(db_path), read_only=True))
    actual = scan_and_index(library, get_database(str(db_path)))

    assert planned == actual


def test_plan_index_without_a_database_counts_every_file_as_new(tmp_path, make_epub):
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")

    assert plan_index(library, None) == {"total": 1, "indexed": 1, "updated": 0, "failed": 0}


def _books_table(db_path, columns, version=SCHEMA_VERSION):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(f"CREATE TABLE books ({columns})")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    ("columns", "version"),
    [
        # Opens cleanly but cannot be written: missing only write-only columns.
        (
            "id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, "
            "author_id INT, series TEXT, tags TEXT",
            SCHEMA_VERSION,
        ),
        # Recorded above what this build understands.
        (
            "id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, author_id INT",
            SCHEMA_VERSION + 1,
        ),
    ],
    ids=["missing-write-columns", "newer-version"],
)
def test_plan_index_declines_to_predict_an_unrecognised_layout(
    tmp_path, make_epub, columns, version
):
    """No counts for a layout this build does not write -- see plan_mode."""
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    _books_table(tmp_path / "odd.db", columns, version=version)

    with pytest.raises(UnindexableDatabaseError):
        plan_index(library, get_database(str(tmp_path / "odd.db"), read_only=True))


def test_plan_matches_real_run_when_authors_is_malformed(tmp_path, make_epub):
    """authors.name is read by the FTS triggers and written by the author lookup."""
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    books = (
        "id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, author_id INT, "
        "series TEXT, series_index REAL, publisher TEXT, published TEXT, isbn TEXT, "
        "language TEXT, tags TEXT"
    )
    db_path = tmp_path / "authors.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, fullname TEXT)")
    conn.execute(f"CREATE TABLE books ({books})")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()

    with pytest.raises(UnindexableDatabaseError, match="authors"):
        plan_index(library, get_database(str(db_path), read_only=True))


def test_plan_index_declines_an_unrecognised_layout_even_for_an_empty_library(tmp_path):
    """An empty library must not turn an unpredictable database into a clean zero."""
    library = tmp_path / "empty"
    library.mkdir()
    _books_table(
        tmp_path / "odd.db",
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT",
    )

    with pytest.raises(UnindexableDatabaseError):
        plan_index(library, get_database(str(tmp_path / "odd.db"), read_only=True))


def test_store_failures_are_errors_not_warnings(tmp_path, make_epub):
    """--quiet promises to show errors, so a failed write must not be a warning."""
    library = tmp_path / "library"
    make_epub("library/a.epub", title="A", author="AA")
    _books_table(
        tmp_path / "newer.db",
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT",
        version=SCHEMA_VERSION + 1,
    )

    records = []
    handler_id = logger.add(lambda m: records.append(m.record), level="DEBUG")
    try:
        stats = scan_and_index(library, get_database(str(tmp_path / "newer.db")))
    finally:
        logger.remove(handler_id)

    assert stats["failed"] == 1
    store_failures = [r for r in records if "Failed to store" in r["message"]]
    assert store_failures, "the write failure was not reported at all"
    assert all(r["level"].name == "ERROR" for r in store_failures)


def test_unreadable_files_stay_warnings(tmp_path, make_corrupt_epub):
    """The counterpart: a bad book is a warning, which --quiet is meant to hide."""
    library = tmp_path / "library"
    make_corrupt_epub("library/broken.epub")

    records = []
    handler_id = logger.add(lambda m: records.append(m.record), level="DEBUG")
    try:
        scan_and_index(library, get_database(str(tmp_path / "ebdx.db")))
    finally:
        logger.remove(handler_id)

    reported = [r for r in records if "broken.epub" in r["message"]]
    assert reported
    assert all(r["level"].name == "WARNING" for r in reported)


def test_plan_counts_a_symlink_to_an_indexed_file_as_an_update(tmp_path, make_epub):
    """Both resolve to one path, so a real run inserts once and updates once."""
    library = tmp_path / "library"
    make_epub("library/real.epub", title="Real", author="AA")
    (library / "link.epub").symlink_to(library / "real.epub")

    planned = plan_index(library, None)
    actual = scan_and_index(library, get_database(str(tmp_path / "ebdx.db")))

    assert planned == {"total": 2, "indexed": 1, "updated": 1, "failed": 0}
    assert planned == actual
