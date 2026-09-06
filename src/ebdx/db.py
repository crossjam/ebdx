"""
SQLite database operations for ebdx.

Provides database connection management and query functions
for indexing and searching EPUB metadata using sqlite_utils.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from loguru import logger

if TYPE_CHECKING:
    from sqlite_utils import Database


class InvalidQueryError(ValueError):
    """Raised when a search query cannot be parsed by SQLite FTS5.

    Carries the underlying SQLite message so the CLI can show it without
    leaking a traceback.
    """


# Bumped whenever the on-disk layout changes incompatibly. Stored in the
# database's ``PRAGMA user_version``; a file below this (with data) is rebuilt.
SCHEMA_VERSION = 1

_FTS_TRIGGERS = ("books_ai", "books_ad", "books_au")

# Searchable columns of ``books_fts``, in order. Single source of truth: the
# table is created from this list, and the query validator below builds its
# scratch table from the same list so column filters resolve identically.
# These are plain identifiers written here, never caller input.
_FTS_COLUMNS = ("title", "author", "series", "tags")


def _validate_fts_query(query: str) -> None:
    """Raise :class:`InvalidQueryError` if FTS5 cannot parse ``query``.

    The query is parsed against a scratch in-memory FTS5 table carrying the
    same columns as ``books_fts``. That table is built here and is known
    good, so any error it raises is the query's fault -- there is no locked
    file, corrupt index, or schema drift in play to confuse the verdict.

    Deciding it this way, rather than by inspecting SQLite's error strings
    after the real query fails, is what keeps the two cases apart: SQLite
    reports a bad query and a broken database through the same exception
    type and overlapping messages (``no such column: badcol`` for a mistyped
    column filter, ``no such column: books_fts`` for a corrupted index), so
    no amount of message matching can reliably tell them apart. With the
    query proven parseable here, every error from the real query is
    unambiguously a database fault and is left to propagate.
    """
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute(
            f"CREATE VIRTUAL TABLE probe USING fts5({', '.join(_FTS_COLUMNS)})"
        )
        probe.execute(
            "SELECT rowid FROM probe WHERE probe MATCH ?", (query,)
        ).fetchall()
    except sqlite3.OperationalError as e:
        raise InvalidQueryError(str(e)) from e
    finally:
        probe.close()


def get_database(db_path: str | Path) -> "Database":
    """Get a database connection, creating the schema if needed.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A sqlite_utils.Database instance.
    """
    import sqlite_utils

    db_path = Path(db_path)
    logger.info(f"Opening database: {db_path}")

    db = sqlite_utils.Database(str(db_path))
    _ensure_schema(db)
    return db


def _ensure_schema(db: "Database") -> None:
    """Ensure the database schema exists and is current.

    The layout version is recorded in ``PRAGMA user_version``. A database
    written before path-keyed book identity (version below ``SCHEMA_VERSION``
    but already carrying a ``books`` table) is rebuilt from scratch rather
    than operated against; a database already at the current version keeps
    all of its data, since every create below is ``IF NOT EXISTS``.

    A database stamped at the current version can still be structurally
    broken -- most visibly a ``books_fts`` that is no longer an FTS5 table,
    which every search and every indexing write fails against. Because the
    creates below are ``IF NOT EXISTS`` they would step over such an object
    forever, so it is dropped and rebuilt from ``books``. The book rows are
    kept: only the derived index was broken, and it can be recomputed.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]

    if version > SCHEMA_VERSION:
        logger.warning(
            f"Database schema version {version} is newer than this build "
            f"expects ({SCHEMA_VERSION}); leaving it untouched"
        )
        return

    repairing_fts = False
    if version < SCHEMA_VERSION and "books" in db.table_names():
        logger.info(
            f"Rebuilding database schema: on-disk version {version}, "
            f"current version {SCHEMA_VERSION}"
        )
        _drop_schema(db)
    elif not _fts_index_is_intact(db):
        logger.warning(
            "The books_fts search index is not an FTS5 table; rebuilding it "
            "from the stored books"
        )
        _drop_fts(db)
        repairing_fts = True

    _create_schema(db)

    if repairing_fts:
        _repopulate_fts(db)

    if version < SCHEMA_VERSION:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _fts_index_is_intact(db: "Database") -> bool:
    """True unless ``books_fts`` exists as something other than an FTS5 table.

    An absent ``books_fts`` counts as intact -- a new or already-dropped
    database -- because ``_create_schema`` will build it. What this catches
    is an object of that name which ``CREATE VIRTUAL TABLE IF NOT EXISTS``
    would skip while every read and write against it fails.
    """
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'books_fts'"
    ).fetchone()
    if row is None:
        return True
    return "fts5" in (row[0] or "").lower()


def _repopulate_fts(db: "Database") -> None:
    """Refill ``books_fts`` from ``books`` after the index was rebuilt.

    FTS5's own ``'rebuild'`` command is not usable here: it reads the
    ``content=`` table directly, and ``books`` stores ``author_id`` rather
    than the ``author`` text the index carries. This mirrors what the insert
    trigger does, for every existing row.
    """
    db.execute(
        """
        INSERT INTO books_fts (rowid, title, author, series, tags)
        SELECT b.id, b.title,
               (SELECT name FROM authors WHERE id = b.author_id),
               b.series, b.tags
        FROM books b
        """
    )


def _drop_fts(db: "Database") -> None:
    """Drop the FTS index and its triggers, leaving book data untouched."""
    for trigger in _FTS_TRIGGERS:
        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    db.execute("DROP TABLE IF EXISTS books_fts")


def _drop_schema(db: "Database") -> None:
    """Drop every ebdx-managed trigger, table, and index."""
    _drop_fts(db)
    db["books"].drop(ignore=True)
    db["authors"].drop(ignore=True)


def _create_schema(db: "Database") -> None:
    """Create the books, authors, and FTS5 objects if they are absent.

    Safe to call on every open: an up-to-date database is left untouched.
    """
    # Authors table
    db["authors"].create(
        {"id": int, "name": str},
        pk="id",
        not_null=["name"],
        if_not_exists=True,
    )

    # Books table. `id` stays an autoincrement integer because the
    # external-content FTS5 index keys on it via content_rowid; `path` is the
    # stable identity used by the indexer and carries a unique index.
    db["books"].create(
        {
            "id": int,
            "path": str,
            "title": str,
            "author_id": int,
            "series": str,
            "series_index": float,
            "publisher": str,
            "published": str,
            "isbn": str,
            "language": str,
            "tags": str,
        },
        pk="id",
        not_null=["title", "path"],
        foreign_keys=["author_id"],
        if_not_exists=True,
    )
    db["books"].create_index(["path"], unique=True, if_not_exists=True)

    # FTS5 full-text search index
    db.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
            {", ".join(_FTS_COLUMNS)},
            content="books",
            content_rowid="id"
        )
        """
    )

    # Triggers to keep FTS5 index in sync
    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO books_fts (rowid, title, author, series, tags)
            SELECT new.id, new.title,
                   (SELECT name FROM authors WHERE id = new.author_id),
                   new.series, new.tags;
        END
        """
    )

    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, title, author, series, tags)
            VALUES ('delete', old.id, old.title,
                    (SELECT name FROM authors WHERE id = old.author_id),
                    old.series, old.tags);
        END
        """
    )

    db.execute(
        """
        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, title, author, series, tags)
            VALUES ('delete', old.id, old.title,
                    (SELECT name FROM authors WHERE id = old.author_id),
                    old.series, old.tags);
            INSERT INTO books_fts (rowid, title, author, series, tags)
            SELECT new.id, new.title,
                   (SELECT name FROM authors WHERE id = new.author_id),
                   new.series, new.tags;
        END
        """
    )


class SavedBook(NamedTuple):
    """Outcome of :func:`save_book`."""

    id: int
    created: bool  # True when a new row was inserted, False when one was updated


def save_book(db: "Database", book_data: dict) -> SavedBook:
    """Insert or update one book, keyed by its filesystem path.

    The book is identified by ``book_data["path"]``. If a row with that path
    already exists it is updated in place and keeps its id; otherwise a new
    row is inserted. The author is looked up or created by name.

    Args:
        db: The database connection.
        book_data: Book metadata. ``path`` is required and must be non-empty;
            everything else defaults to empty.

    Returns:
        A :class:`SavedBook` with the row id and whether it was newly created.

    Raises:
        ValueError: if ``book_data`` carries no non-empty ``path``.
    """
    raw_path = book_data.get("path")
    path = "" if raw_path is None else str(raw_path)
    if not path.strip():
        raise ValueError("save_book requires a non-empty 'path'")

    # lookup() is get-or-create, so an unknown name is inserted and its id
    # returned in one call.
    author_id = db["authors"].lookup({"name": book_data.get("author", "")})

    fields = {
        "path": path,
        "title": book_data.get("title", ""),
        "author_id": author_id,
        "series": book_data.get("series", ""),
        "series_index": book_data.get("series_index"),
        "publisher": book_data.get("publisher", ""),
        "published": book_data.get("published", ""),
        "isbn": book_data.get("isbn", ""),
        "language": book_data.get("language", ""),
        "tags": book_data.get("tags", ""),
    }

    books = db["books"]
    existing_id = next(
        (row["id"] for row in books.rows_where("path = ?", [path])), None
    )

    if existing_id is None:
        books.insert(fields)
        result = SavedBook(id=books.last_pk, created=True)
    else:
        books.update(existing_id, fields)
        result = SavedBook(id=existing_id, created=False)

    logger.debug(
        f"{'Inserted' if result.created else 'Updated'} book "
        f"'{fields['title']}' ({path})"
    )
    return result


def search_books(db: "Database", query: str, limit: int | None = None) -> list[dict]:
    """Search for books using FTS5 full-text search.

    Args:
        db: The database connection.
        query: The search query string.
        limit: Maximum number of results to return.

    Returns:
        List of book dictionaries matching the query.

    Raises:
        InvalidQueryError: if ``query`` is not a parseable FTS5 expression.
        sqlite3.OperationalError: if the database itself cannot serve the
            search (locked file, missing or corrupt index, schema drift).
    """
    if limit is None:
        limit = 20

    # Settle "is this query well formed?" before touching the real database,
    # so the statement below can only fail for database reasons.
    _validate_fts_query(query)

    results = db.execute(
        """
        SELECT b.id, b.path, b.title, a.name as author, b.series, b.series_index
        FROM books_fts
        JOIN books b ON books_fts.rowid = b.id
        JOIN authors a ON b.author_id = a.id
        WHERE books_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()

    books = []
    for row in results:
        books.append(
            {
                "id": row[0],
                "path": row[1],
                "title": row[2],
                "author": row[3],
                "series": row[4],
                "series_index": row[5],
            }
        )

    return books
