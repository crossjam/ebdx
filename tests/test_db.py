"""Tests for the ebdx.db storage layer (cii §2 and §3).

§2 — durable schema: data surviving a reopen (the regression test for the
wipe bug), schema-version stamping and the pre-path rebuild, the unique
index on ``path``, and the FTS5 triggers staying in step with ``books``
across insert, update, and delete.

§3 — path-keyed persistence: ``save_book`` identifying a book by its path,
updating in place, reporting inserted vs updated, and ``search_books``
carrying the source path.
"""

import sqlite3

import pytest
import sqlite_utils

from ebdx.db import SCHEMA_VERSION, get_database, save_book, search_books


def _book(**overrides):
    data = {
        "path": "/library/dune.epub",
        "title": "Dune",
        "author": "Frank Herbert",
        "series": "",
        "series_index": None,
        "publisher": "Chilton Books",
        "published": "1965",
        "isbn": "",
        "language": "en",
        "tags": "science fiction",
    }
    data.update(overrides)
    return data


def _match_count(db, term):
    return db.execute(
        "SELECT count(*) FROM books_fts WHERE books_fts MATCH ?", [term]
    ).fetchone()[0]


def test_data_survives_reopen(tmp_path):
    """Regression test for the wipe bug: opening a DB must not drop its tables."""
    db_path = tmp_path / "ebdx.db"

    db = get_database(str(db_path))
    save_book(db, _book())
    db.conn.close()

    reopened = get_database(str(db_path))
    rows = list(reopened["books"].rows)
    assert len(rows) == 1
    assert rows[0]["title"] == "Dune"
    assert rows[0]["path"] == "/library/dune.epub"


def test_repeated_open_is_stable(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book())
    save_book(db, _book(path="/library/foundation.epub", title="Foundation"))
    db.conn.close()

    for _ in range(3):
        db = get_database(str(db_path))
        assert db["books"].count == 2
        assert db["authors"].count >= 1
        db.conn.close()


def test_get_database_stamps_schema_version(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_books_path_has_unique_index(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    assert any(
        ix.unique and ix.columns == ["path"] for ix in db["books"].indexes
    )


def test_pre_path_database_is_rebuilt(tmp_path):
    db_path = tmp_path / "legacy.db"

    # A database written by an earlier version: books has no `path` column and
    # user_version was never stamped (stays 0).
    legacy = sqlite_utils.Database(str(db_path))
    legacy["authors"].create({"id": int, "name": str}, pk="id")
    legacy["books"].create(
        {"id": int, "title": str, "author_id": int}, pk="id", not_null=["title"]
    )
    legacy["books"].insert({"title": "Stale", "author_id": 1})
    assert "path" not in legacy["books"].columns_dict
    legacy.conn.close()

    db = get_database(str(db_path))
    assert "path" in db["books"].columns_dict
    assert db["books"].count == 0  # rebuilt from scratch, old row gone
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_current_database_is_left_intact(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book())
    db.conn.close()

    reopened = get_database(str(db_path))  # already at SCHEMA_VERSION
    assert reopened["books"].count == 1


def test_newer_schema_version_is_not_downgraded(tmp_path):
    db_path = tmp_path / "future.db"
    db = get_database(str(db_path))
    save_book(db, _book())
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    db.conn.close()

    reopened = get_database(str(db_path))
    assert reopened["books"].count == 1
    assert (
        reopened.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 5
    )


def test_fts_finds_book_after_insert(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Neuromancer"))
    assert _match_count(db, "Neuromancer") == 1


def test_fts_reflects_title_update(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    saved = save_book(db, _book(title="Old Title"))

    db["books"].update(saved.id, {"title": "New Title"})

    assert _match_count(db, "New") == 1
    assert _match_count(db, "Old") == 0


def test_fts_drops_deleted_book(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    saved = save_book(db, _book(title="Ephemeral"))
    assert _match_count(db, "Ephemeral") == 1

    db["books"].delete(saved.id)

    assert _match_count(db, "Ephemeral") == 0


def test_duplicate_path_violates_unique_index(tmp_path):
    """The schema constraint holds even for a direct insert that bypasses save_book."""
    db = get_database(str(tmp_path / "ebdx.db"))
    db["authors"].insert({"name": "Frank Herbert"})
    db["books"].insert({"path": "/dup.epub", "title": "A", "author_id": 1})
    with pytest.raises(sqlite3.IntegrityError):
        db["books"].insert({"path": "/dup.epub", "title": "B", "author_id": 1})


# --- §3: path-keyed persistence ---------------------------------------------


def test_save_book_reports_inserted_then_updated(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))

    first = save_book(db, _book(title="Draft"))
    second = save_book(db, _book(title="Final"))

    assert first.created is True
    assert second.created is False
    assert first.id == second.id


def test_saving_same_path_twice_updates_in_place(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))

    first = save_book(db, _book(title="Draft", publisher="Self"))
    save_book(db, _book(title="Final", publisher="Ace"))

    assert db["books"].count == 1
    row = db["books"].get(first.id)
    assert row["title"] == "Final"
    assert row["publisher"] == "Ace"


def test_distinct_paths_are_distinct_books(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))

    a = save_book(db, _book(path="/library/a.epub"))
    b = save_book(db, _book(path="/library/b.epub"))  # identical title + author

    assert a.id != b.id
    assert db["books"].count == 2
    assert db["authors"].count == 1  # the author record is reused


@pytest.mark.parametrize("bad_path", [None, "", "   "])
def test_save_book_rejects_empty_path(tmp_path, bad_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    with pytest.raises(ValueError):
        save_book(db, _book(path=bad_path))
    assert db["books"].count == 0


def test_save_book_rejects_missing_path(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    data = _book()
    del data["path"]
    with pytest.raises(ValueError):
        save_book(db, data)
    assert db["books"].count == 0


def test_save_book_accepts_a_path_object(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    epub_path = tmp_path / "sub" / "dune.epub"

    saved = save_book(db, _book(path=epub_path))

    assert db["books"].get(saved.id)["path"] == str(epub_path)


def test_search_results_carry_the_source_path(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    (hit,) = search_books(db, "Dune")

    assert hit["path"] == "/library/dune.epub"
