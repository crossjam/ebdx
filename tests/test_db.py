"""Tests for the ebdx.db storage layer (cii §2 and §3).

§2 — durable schema: data surviving a reopen (the regression test for the
wipe bug), schema-version stamping and the pre-path rebuild, the unique
index on ``path``, and the FTS5 triggers staying in step with ``books``
across insert, update, and delete.

§3 — path-keyed persistence: ``save_book`` identifying a book by its path,
updating in place, reporting inserted vs updated, and ``search_books``
carrying the source path.
"""

import contextlib
import sqlite3
from pathlib import Path

import pytest
import sqlite_utils

from ebdx.db import (
    _FTS_COLUMNS,
    SCHEMA_VERSION,
    InvalidQueryError,
    describe_pending_schema_work,
    get_database,
    plan_mode,
    resolve_query,
    save_book,
    search_books,
    would_repair_search,
)


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
    return db.execute("SELECT count(*) FROM books_fts WHERE books_fts MATCH ?", [term]).fetchone()[
        0
    ]


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
    assert any(ix.unique and ix.columns == ["path"] for ix in db["books"].indexes)


def test_pre_path_database_is_rebuilt(tmp_path):
    db_path = tmp_path / "legacy.db"

    # A database written by an earlier version: books has no `path` column and
    # user_version was never stamped (stays 0).
    legacy = sqlite_utils.Database(str(db_path))
    legacy["authors"].create({"id": int, "name": str}, pk="id")
    legacy["books"].create({"id": int, "title": str, "author_id": int}, pk="id", not_null=["title"])
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
    assert reopened.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 5


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

    assert db["books"].get(saved.id)["path"] == str(epub_path.resolve())


def test_relative_path_is_stored_absolute(tmp_path, monkeypatch):
    db = get_database(str(tmp_path / "ebdx.db"))
    (tmp_path / "library").mkdir()
    monkeypatch.chdir(tmp_path)

    saved = save_book(db, _book(path="library/dune.epub"))

    stored = db["books"].get(saved.id)["path"]
    assert Path(stored).is_absolute()
    assert stored == str((tmp_path / "library" / "dune.epub").resolve())


def test_relative_and_absolute_forms_are_one_book(tmp_path, monkeypatch):
    """A path given both ways names one file, so it gets one record."""
    db = get_database(str(tmp_path / "ebdx.db"))
    (tmp_path / "library").mkdir()
    monkeypatch.chdir(tmp_path)

    first = save_book(db, _book(path="library/dune.epub", title="Draft"))
    second = save_book(
        db, _book(path=(tmp_path / "library" / "dune.epub").resolve(), title="Final")
    )

    assert second.id == first.id
    assert second.created is False
    assert db["books"].count == 1
    assert db["books"].get(first.id)["title"] == "Final"


def test_search_results_carry_the_source_path(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    (hit,) = search_books(db, "Dune")

    assert hit["path"] == "/library/dune.epub"


@pytest.mark.parametrize(
    "bad_query",
    [
        '"unbalanced',  # unterminated string
        "AND",  # bare operator
        "NEAR(",  # truncated NEAR
        "a OR OR b",  # doubled operator
        "^",  # bare anchor
        "* ",  # unknown special query
        "-Dune",  # exclusion with nothing to exclude from
        "x.y:Dune",  # dotted column filter
        "badcol:Dune",  # unknown column filter
        "{nope title}:Dune",  # unknown column in a braced filter
    ],
)
def test_malformed_expression_raises_invalid_query_error(tmp_path, bad_query):
    """Asking for FTS5 syntax means asking for its errors too.

    A user who passes ``fts`` is writing an expression, so one the engine
    cannot parse is reported rather than quietly becoming a search that
    matches nothing -- "you own no such book" would be the wrong answer to a
    mistyped column filter.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    with pytest.raises(InvalidQueryError):
        search_books(db, bad_query, fts=True)


@pytest.mark.parametrize(
    "good_query",
    [
        "Dune",
        "title:Dune",
        "{title author}:Dune",
        '"Dune"',
        "Dune OR Foundation",
        "Frank NEAR Herbert",
        "Dun*",
        "-series:Chronicles title:Dune",
    ],
)
def test_expression_forms_are_accepted_under_fts(tmp_path, good_query):
    """The validator must not reject legitimate FTS5 syntax."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune", author="Frank Herbert"))

    search_books(db, good_query, fts=True)  # must not raise


def test_an_expression_filters_on_the_column_it_names(tmp_path):
    """Not merely parseable under the flag: interpreted."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune", author="Frank Herbert"))
    save_book(db, _book(path="/library/about.epub", title="On Herbert", author="A Critic"))

    assert [book["title"] for book in search_books(db, "author:Herbert", fts=True)] == ["Dune"]
    assert [book["title"] for book in search_books(db, "Herbert NOT Dune", fts=True)] == [
        "On Herbert"
    ]


@pytest.mark.parametrize(
    ("query", "expected_title"),
    [
        ("Ender's", "Ender's Game"),  # apostrophe: FTS5 reads it as a string delimiter
        ("ender's", "Ender's Game"),  # matching stays case-insensitive
        ("Ender\u2019s", "Ender's Game"),  # typographic apostrophe
        ("Well-Tempered", "Well-Tempered Clavier"),  # hyphen: read as a column filter
        ("Ender's Game", "Ender's Game"),  # both words, one of them punctuated
        ("Dune, Messiah", "Dune, Messiah"),  # comma
        ("Mr. Mercedes", "Mr. Mercedes"),  # full stop
        ("Rock & Roll", "Rock & Roll"),  # ampersand
        ("R_AND_D, Inc.", "R_AND_D, Inc."),  # underscore: a bareword character to FTS5
        ("Moby-Dick; or, The Whale", "Moby-Dick; or, The Whale"),  # semicolon and a stray `or`
    ],
)
def test_punctuation_in_an_ordinary_query_searches_for_those_words(tmp_path, query, expected_title):
    """A title carrying an apostrophe or a hyphen is a search, not a syntax error.

    Neither is an attempt at FTS5 syntax, so neither should surface the
    engine's parse error at the user.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(
        db,
        _book(path="/library/enders-game.epub", title="Ender's Game", author="Frank Herbert"),
    )
    save_book(db, _book(path="/library/wtc.epub", title="Well-Tempered Clavier"))
    save_book(db, _book(path="/library/messiah.epub", title="Dune, Messiah"))
    save_book(db, _book(path="/library/mercedes.epub", title="Mr. Mercedes"))
    save_book(db, _book(path="/library/rock.epub", title="Rock & Roll"))
    save_book(db, _book(path="/library/rnd.epub", title="R_AND_D, Inc."))
    save_book(db, _book(path="/library/moby.epub", title="Moby-Dick; or, The Whale"))

    results = search_books(db, query)

    assert [book["title"] for book in results] == [expected_title]


@pytest.mark.parametrize(
    "query",
    [
        "AND",  # a bare operator
        "OR,",
        "Dune OR Foundation",  # a spelled-out boolean
        "Dune OR,Foundation",  # an operator with punctuation attached
        "Dune AND.Foundation",
        "-Dune",  # FTS5's exclusion operator
        "badcol:Dune",  # a column filter, mistyped or not
        "x.y:Dune",
        "{nope title}:Dune",
        '"unbalanced',  # an unterminated string
        "NEAR(",
        "^",
        "* ",
    ],
)
def test_operator_like_text_is_literal_by_default(tmp_path, query):
    """No input is malformed in literal mode, whatever it looks like.

    Each of these is reported as a query error under ``fts``, which is where
    the user has said they are writing an expression. Typed as plain text they
    are words, and the search runs.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))
    save_book(db, _book(path="/library/foundation.epub", title="Foundation"))

    search_books(db, query)  # must not raise


@pytest.mark.parametrize(
    "title", ["NOTORIOUS", "R.A.N.D. Corporation", "Band of Brothers", "R_AND_D, Inc."]
)
def test_a_word_merely_containing_an_operator_is_not_one(tmp_path, title):
    """A title is searched for whether or not an operator hides inside it.

    Nothing inspects the query for operator spellings any more, so NOTORIOUS,
    the initials of R.A.N.D. and the underscores of R_AND_D are all just text.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/x.epub", title=title))

    assert [book["title"] for book in search_books(db, title)] == [title]


def test_a_bare_near_is_an_ordinary_term_not_an_operator(tmp_path):
    """A literal query quotes every word, NEAR included.

    So `Frank NEAR Herbert's` searches for three words and matches nothing,
    rather than erroring on the apostrophe or reaching for proximity syntax.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Ender's Game", author="Frank Herbert"))

    assert search_books(db, "Frank NEAR Herbert's") == []
    assert resolve_query("Frank NEAR Herbert's") == '"Frank" "NEAR" "Herbert\'s"'


def test_the_same_text_is_a_search_by_default_and_an_error_under_fts(tmp_path):
    """The one query, read two ways, because the user says which.

    Literal text cannot be malformed, so these are searches. Under ``fts``
    they are the errors this project reports on purpose, pinned by
    "Unparseable query".
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))

    for query in ("badcol:Dune", "x.y:Dune", "{nope title}:Dune", '"unbalanced'):
        search_books(db, query)  # must not raise
        with pytest.raises(InvalidQueryError):
            search_books(db, query, fts=True)


@pytest.mark.parametrize("query", ["-Dune", "- Dune"])
def test_a_leading_hyphen_is_literal_text_by_default(tmp_path, query):
    """The bug that started the heuristic, settled by the flag instead.

    A blanket requote of `-Dune` searched for the very term the user was
    asking to drop. Here nothing is guessed: plain text finds the book, and
    the exclusion operator lives under ``fts``, where the user asked for it.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))
    save_book(db, _book(path="/library/foundation.epub", title="Foundation"))

    assert [book["title"] for book in search_books(db, query)] == ["Dune"]
    assert [book["title"] for book in search_books(db, "Dune OR Foundation", fts=True)] == [
        "Dune",
        "Foundation",
    ]
    assert [book["title"] for book in search_books(db, "Foundation NOT Dune", fts=True)] == [
        "Foundation"
    ]


@pytest.mark.parametrize("query", ["Cosmos: A Personal Voyage", "Dune*", 'Say "Hello"'])
def test_an_expression_is_passed_through_verbatim(tmp_path, query):
    """Under ``fts`` the user is writing FTS5, so nothing rewrites the query:
    it runs as typed, or the engine's error is reported."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))

    with contextlib.suppress(InvalidQueryError):  # reported, not rewritten
        assert resolve_query(query, fts=True) == query


def test_literal_queries_quote_every_word(tmp_path):
    """The whole of the default mode, in one line: quoted per word, ANDed."""
    assert resolve_query("Dune*") == '"Dune*"'
    assert resolve_query('Say "Hello"') == '"Say" """Hello"""'
    assert resolve_query("R_AND_D, Inc.") == '"R_AND_D," "Inc."'


def test_multi_word_queries_match_words_in_any_position(tmp_path):
    """Words are quoted one by one and ANDed, never run together into a phrase.

    A phrase would silently narrow the search to adjacent occurrences, so a
    book holding both words apart would stop matching.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(
        db,
        _book(path="/library/hitchhiker.epub", title="The Hitchhiker's Guide to the Galaxy"),
    )
    save_book(db, _book(title="Dune", author="Frank Herbert"))

    # Non-adjacent in the title, and in the other order than they appear.
    assert [book["title"] for book in search_books(db, "Galaxy Hitchhiker's")] == [
        "The Hitchhiker's Guide to the Galaxy"
    ]
    # Across two columns at once.
    assert [book["title"] for book in search_books(db, "Herbert Dune")] == ["Dune"]


@pytest.mark.parametrize("query", ["", "   "])
def test_a_query_with_no_words_finds_nothing_rather_than_erroring(tmp_path, query):
    """A query holding no words resolves to an empty expression, which FTS5
    rejects. There is nothing to match and nothing malformed about asking, so
    it is an empty result -- and never a database error."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))

    assert search_books(db, query) == []


def test_a_term_that_only_looks_punctuated_still_finds_nothing(tmp_path):
    """Requoting rescues the parse, not the match.

    A well-formed search for a book that is not there is still no results --
    the fallback must not widen the query into matching something else.
    """
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(title="Dune"))

    assert search_books(db, "Nobody's Business") == []


def test_reopen_repairs_a_non_fts_books_fts_and_keeps_the_books(tmp_path):
    """A books_fts replaced by an ordinary table is rebuilt on the next open,
    with the book rows preserved and searchable again."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune", author="Frank Herbert"))
    db.execute("DROP TABLE books_fts")
    db.execute("CREATE TABLE books_fts (rowid INTEGER, title TEXT)")
    db.conn.commit()
    db.conn.close()

    reopened = get_database(str(db_path))

    assert reopened["books"].count == 1  # book data survived the repair
    assert [hit["title"] for hit in search_books(reopened, "Dune")] == ["Dune"]
    assert [hit["author"] for hit in search_books(reopened, "Herbert")] == ["Frank Herbert"]


def test_reopen_repairs_a_dropped_books_fts_and_keeps_the_books(tmp_path):
    """A books_fts that is simply gone must be refilled, not recreated empty:
    otherwise search silently reports no matches for books still in `books`."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune", author="Frank Herbert"))
    db.execute("DROP TABLE books_fts")
    db.conn.commit()
    db.conn.close()

    reopened = get_database(str(db_path))

    assert reopened["books"].count == 1
    assert [hit["title"] for hit in search_books(reopened, "Dune")] == ["Dune"]


def test_repair_refills_every_stored_book(tmp_path):
    """Repopulation must cover the whole table, not just the first row."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    for n in range(5):
        save_book(db, _book(path=f"/library/{n}.epub", title=f"Book{n}"))
    db.execute("DROP TABLE books_fts")
    db.conn.commit()
    db.conn.close()

    reopened = get_database(str(db_path))

    found = {hit["title"] for hit in search_books(reopened, "Book0 OR Book4", fts=True)}
    assert found == {"Book0", "Book4"}
    assert _match_count(reopened, "Book2") == 1


def test_a_fresh_database_searches_normally(tmp_path):
    """A new database has no books_fts either; that must not confuse the
    repair path or leave the index unusable."""
    db = get_database(str(tmp_path / "ebdx.db"))

    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    assert _match_count(db, "Dune") == 1


def test_repaired_index_still_tracks_later_writes(tmp_path):
    """The rebuilt index must come back with its triggers, not just its rows."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP TABLE books_fts")
    db.execute("CREATE TABLE books_fts (rowid INTEGER, title TEXT)")
    db.conn.commit()
    db.conn.close()

    reopened = get_database(str(db_path))
    save_book(reopened, _book(path="/library/foundation.epub", title="Foundation"))

    assert [hit["title"] for hit in search_books(reopened, "Foundation")] == ["Foundation"]


def test_a_healthy_database_is_not_repaired(tmp_path):
    """The repair must not fire on a sound database, which would double-index."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.conn.close()

    reopened = get_database(str(db_path))

    assert _match_count(reopened, "Dune") == 1


def test_probe_columns_match_the_real_fts_table(tmp_path):
    """The validator's scratch table must carry the same columns as books_fts,
    or a valid column filter could be rejected (or a bad one accepted)."""
    db = get_database(str(tmp_path / "ebdx.db"))

    actual = tuple(row[1] for row in db.execute("PRAGMA table_info(books_fts)"))

    assert actual == _FTS_COLUMNS


def test_unrelated_operational_error_is_not_masked_as_a_bad_query(tmp_path):
    """A missing FTS table is a database fault, not the user's query."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP TABLE books_fts")

    with pytest.raises(sqlite3.OperationalError) as excinfo:
        search_books(db, "Dune")
    assert not isinstance(excinfo.value, InvalidQueryError)
    assert "books_fts" in str(excinfo.value)


def test_non_fts_books_fts_table_is_not_masked_as_a_bad_query(tmp_path):
    """A books_fts replaced by an ordinary table makes MATCH report
    "no such column: books_fts" — a database fault, not the user's query."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP TABLE books_fts")
    db.execute("CREATE TABLE books_fts (rowid INTEGER, title TEXT)")

    with pytest.raises(sqlite3.OperationalError) as excinfo:
        search_books(db, "Dune")
    assert not isinstance(excinfo.value, InvalidQueryError)
    assert "books_fts" in str(excinfo.value)


def test_a_real_column_filter_still_searches(tmp_path):
    """The unknown-filter handling must not break a valid column filter."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    assert [hit["title"] for hit in search_books(db, "title:Dune", fts=True)] == ["Dune"]
    # Without the flag the same text is four literal characters and a word,
    # which no book carries.
    assert search_books(db, "title:Dune") == []


def test_missing_regular_table_column_is_not_masked_as_a_bad_query(tmp_path):
    """Schema drift in ``books`` produces "no such column" for a valid search;
    that must surface as a database fault, not an InvalidQueryError."""
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("ALTER TABLE books DROP COLUMN series_index")

    with pytest.raises(sqlite3.OperationalError) as excinfo:
        search_books(db, "Dune")
    assert not isinstance(excinfo.value, InvalidQueryError)
    assert "series_index" in str(excinfo.value)


# --- read-only opens (dry-run support) -------------------------------------


def _schema_fingerprint(db_path):
    """The objects and schema version of a database, read without mutating it.

    Opened read-only on purpose: an ordinary open would run _ensure_schema and
    change the very thing being measured.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        objects = conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        return objects, version
    finally:
        conn.close()


def test_read_only_open_returns_the_same_results(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.conn.close()

    ordinary = search_books(get_database(str(db_path)), "Dune")
    readonly = search_books(get_database(str(db_path), read_only=True), "Dune")

    assert readonly == ordinary
    assert [hit["title"] for hit in readonly] == ["Dune"]


@pytest.mark.parametrize("breakage", ["dropped", "replaced"])
def test_read_only_open_does_not_repair_the_index(tmp_path, breakage):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    for trigger in ("books_ai", "books_ad", "books_au"):
        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    db.execute("DROP TABLE books_fts")
    if breakage == "replaced":
        db.execute("CREATE TABLE books_fts (title TEXT)")
    db.conn.close()

    before = _schema_fingerprint(db_path)
    get_database(str(db_path), read_only=True)
    after = _schema_fingerprint(db_path)

    assert after == before, "a read-only open rebuilt or repopulated the index"


def test_read_only_open_does_not_rebuild_a_legacy_database(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy = sqlite_utils.Database(str(db_path))
    legacy["authors"].create({"id": int, "name": str}, pk="id")
    legacy["books"].create({"id": int, "title": str, "author_id": int}, pk="id", not_null=["title"])
    legacy["books"].insert({"title": "Stale", "author_id": 1})
    legacy.conn.close()

    before = _schema_fingerprint(db_path)
    assert before[1] == 0  # user_version never stamped
    db = get_database(str(db_path), read_only=True)
    after = _schema_fingerprint(db_path)

    assert after == before, "a read-only open rebuilt a pre-path database"
    assert "path" not in db["books"].columns_dict  # left in its legacy shape
    assert db["books"].count == 1  # the stale row survives untouched


def test_read_only_open_refuses_writes(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.conn.close()

    ro = get_database(str(db_path), read_only=True)

    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("UPDATE books SET title = 'Tampered'")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 99}")

    assert get_database(str(db_path), read_only=True)["books"].get(1)["title"] == "Dune"


def test_read_only_open_of_a_missing_file_raises(tmp_path):
    """Documented failure mode: a read-only connection cannot create the file."""
    with pytest.raises(sqlite3.OperationalError):
        get_database(str(tmp_path / "nope.db"), read_only=True).table_names()


@pytest.mark.parametrize("name", ["lib?x.db", "lib#y.db", "lib%z.db", "lib x.db"])
def test_read_only_open_escapes_uri_significant_names(tmp_path, name):
    """A "?" in the path must not truncate the URI and drop mode=ro."""
    db_path = tmp_path / name
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.conn.close()

    ro = get_database(str(db_path), read_only=True)

    # It opened the intended file, not a truncated-path neighbour...
    assert [hit["title"] for hit in search_books(ro, "Dune")] == ["Dune"]
    # ...and it is genuinely read-only.
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("UPDATE books SET title = 'Tampered'")


def _path_less_books(db_path, version):
    """A `books` table with no `path` column, stamped at `version`."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT)")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (0, "insert-all"),  # genuinely legacy: a real open rebuilds it
        (SCHEMA_VERSION, "unusable"),  # current version, layout we do not write
        (SCHEMA_VERSION + 1, "unusable"),  # newer than this build understands
    ],
)
def test_plan_mode_classifies_a_path_less_books_table(tmp_path, version, expected):
    db_path = tmp_path / "odd.db"
    _path_less_books(db_path, version)

    assert plan_mode(get_database(str(db_path), read_only=True)).mode == expected


def test_plan_mode_compares_against_a_current_database(tmp_path):
    db = get_database(str(tmp_path / "ebdx.db"))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))

    assert plan_mode(db).mode == "compare"


def test_plan_mode_treats_an_empty_database_as_all_inserts(tmp_path):
    db_path = tmp_path / "empty.db"
    sqlite3.connect(str(db_path)).close()

    assert plan_mode(get_database(str(db_path), read_only=True)).mode == "insert-all"


def test_plan_mode_rejects_a_books_table_missing_writable_columns(tmp_path):
    """`path` alone is not enough: save_book writes every column in the schema."""
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books "
        "(id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, author_id INT)"
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()

    predicted = plan_mode(get_database(str(db_path), read_only=True))

    assert predicted.mode == "unusable"
    assert "series_index" in predicted.reason


def test_pending_schema_work_reports_creation_for_an_empty_file(tmp_path):
    """An empty database file needs the whole schema, not an index repair."""
    db_path = tmp_path / "empty.db"
    sqlite3.connect(str(db_path)).close()

    work = describe_pending_schema_work(get_database(str(db_path), read_only=True))

    assert work == ["create the books, authors, and full-text schema"]


def test_plan_mode_never_compares_without_a_books_table(tmp_path):
    """authors alone must not read as the current layout: plan_index would crash."""
    db_path = tmp_path / "authors-only.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()

    assert plan_mode(get_database(str(db_path), read_only=True)).mode == "insert-all"


def test_pending_work_reports_a_missing_trigger(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP TRIGGER books_ai")
    db.conn.close()

    work = describe_pending_schema_work(get_database(str(db_path), read_only=True))

    assert any("books_ai" in item for item in work)


def test_pending_work_reports_a_missing_path_index(tmp_path):
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP INDEX idx_books_path")
    db.conn.close()

    work = describe_pending_schema_work(get_database(str(db_path), read_only=True))

    assert any("books.path" in item for item in work)


def test_duplicate_paths_make_the_layout_unusable(tmp_path):
    """A real open cannot recreate the unique index over duplicate paths."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP INDEX idx_books_path")
    db.execute("INSERT INTO books (path, title, author_id) VALUES ('/library/dune.epub', 'Dup', 1)")
    db.conn.close()

    assert plan_mode(get_database(str(db_path), read_only=True)).mode == "unusable"


def test_would_repair_search_is_false_for_a_newer_layout(tmp_path):
    """A newer layout is left untouched, so nothing repairs a broken index."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    for trigger in ("books_ai", "books_ad", "books_au"):
        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    db.execute("DROP TABLE books_fts")
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    db.conn.close()

    assert not would_repair_search(get_database(str(db_path), read_only=True))


def test_a_missing_authors_table_is_pending_work_and_repairable(tmp_path):
    """A real open creates it, so a search that failed on it is not a broken database."""
    db_path = tmp_path / "ebdx.db"
    db = get_database(str(db_path))
    save_book(db, _book(path="/library/dune.epub", title="Dune"))
    db.execute("DROP TABLE authors")
    db.conn.close()

    reopened = get_database(str(db_path), read_only=True)

    assert "create the authors table" in describe_pending_schema_work(reopened)
    assert would_repair_search(reopened)
