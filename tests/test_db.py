"""Tests for the durable schema in ebdx.db (cii §2).

Covers: data surviving a reopen (the regression test for the wipe bug),
schema-version stamping and the pre-path rebuild, the unique index on
``path``, and the FTS5 triggers staying in step with ``books`` across
insert, update, and delete.
"""

import sqlite3

import pytest
import sqlite_utils

from ebdx.db import SCHEMA_VERSION, get_database, save_book


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
    book_id = save_book(db, _book(title="Old Title"))

    db["books"].update(book_id, {"title": "New Title"})

    assert _match_count(db, "New") == 1
    assert _match_count(db, "Old") == 0


def test_fts_drops_deleted_book(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    book_id = save_book(db, _book(title="Ephemeral"))
    assert _match_count(db, "Ephemeral") == 1

    db["books"].delete(book_id)

    assert _match_count(db, "Ephemeral") == 0


def test_duplicate_path_violates_unique_index(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book())
    with pytest.raises(sqlite3.IntegrityError):
        save_book(db, _book(title="Dune (other copy)"))
