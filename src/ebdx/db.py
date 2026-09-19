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

# The authors table as this build writes it. `name` is read by the FTS triggers
# and written by save_book's author lookup.
_AUTHORS_COLUMNS = {"id": int, "name": str}

# The books table as this build writes it. Single source of truth: the table is
# created from this, and plan_mode checks an existing table against it, so a
# layout missing any of these is recognised as one this build cannot write to.
_BOOKS_COLUMNS = {
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
}


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
        probe.execute(f"CREATE VIRTUAL TABLE probe USING fts5({', '.join(_FTS_COLUMNS)})")
        probe.execute("SELECT rowid FROM probe WHERE probe MATCH ?", (query,)).fetchall()
    except sqlite3.OperationalError as e:
        raise InvalidQueryError(str(e)) from e
    finally:
        probe.close()


def get_database(db_path: str | Path, *, read_only: bool = False) -> "Database":
    """Get a database connection, creating the schema if needed.

    Args:
        db_path: Path to the SQLite database file.
        read_only: When true, open the file through SQLite's ``mode=ro`` URI and
            skip the schema check entirely. Both halves matter. Skipping
            :func:`_ensure_schema` is what makes the open non-mutating --
            it otherwise creates missing tables, stamps ``PRAGMA user_version``,
            and rebuilds a damaged ``books_fts``. Opening read-only is what makes
            that guarantee enforceable: SQLite refuses any write, so a write path
            added later fails loudly instead of quietly mutating a database the
            caller promised not to touch.

    Returns:
        A sqlite_utils.Database instance.

    Raises:
        sqlite3.OperationalError: if ``read_only`` is set and the file does not
            exist. A read-only connection cannot create one, so callers that
            want a friendly "no database yet" message must check for the file
            before calling.
    """
    import sqlite_utils

    db_path = Path(db_path)
    logger.info(f"Opening database{' read-only' if read_only else ''}: {db_path}")

    if read_only:
        # as_uri() percent-escapes the path. Interpolating it raw would let a
        # filename containing "?", "#" or "%" be parsed as URI syntax -- a "?"
        # in particular truncates the path and drops mode=ro, silently handing
        # back a writable connection to a different file.
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        return sqlite_utils.Database(conn)

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

    A database stamped at the current version can still have a broken search
    index, in either of two ways. A ``books_fts`` that is no longer an FTS5
    table fails every search and every indexing write, and the ``IF NOT
    EXISTS`` creates would step over it forever. A ``books_fts`` that is
    simply gone is quieter and worse: the create puts back an empty
    external-content table, and searches then report no matches for books
    that are still sitting in ``books``. Either way the index is dropped,
    recreated, and refilled from ``books``. The book rows are kept -- only
    the derived index was broken, and it can be recomputed.
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
        # Warn only when there are books whose index is being rebuilt; on a
        # new database the index is simply absent and nothing was lost.
        if _stored_book_count(db):
            logger.warning(
                "The books_fts search index is missing or is not an FTS5 "
                "table; rebuilding it from the stored books"
            )
        _drop_fts(db)
        repairing_fts = True

    _create_schema(db)

    if repairing_fts:
        _repopulate_fts(db)

    if version < SCHEMA_VERSION:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


class UnindexableDatabaseError(RuntimeError):
    """Raised when a database cannot be indexed as it stands.

    Carries the reason so a caller can report it. Planning raises this rather
    than returning counts, because any count would describe a run that cannot
    start.
    """


class PlanMode(NamedTuple):
    """How an index run would treat a database, and why."""

    mode: str  # "compare" | "insert-all" | "fail-all" | "abort"
    reason: str


def plan_mode(db: "Database") -> PlanMode:
    """Predict how a real index run would treat ``db``, without touching it.

    Three outcomes, and deliberately no more:

    - ``compare``: the layout is the one this build writes, so existing rows
      say which files would be updated.
    - ``insert-all``: a real open rebuilds the schema from scratch -- recorded
      below :data:`SCHEMA_VERSION`, or with no ``books`` table yet -- so every
      readable file ends up inserted.
    - ``unusable``: the layout is not one this build recognises. No counts are
      predicted for it.

    The last case is a deliberate limit. Predicting what a damaged or foreign
    layout would do means reproducing every branch of :func:`_ensure_schema`
    and :func:`save_book` here, and any corner missed is a dry run that
    promises a run which cannot happen -- which is worse than declining to
    guess. Since a damaged library is cheap to rebuild by re-indexing, the
    useful answer is to say so rather than to model the failure.
    """
    tables = db.table_names()
    version = db.execute("PRAGMA user_version").fetchone()[0]

    # Checked first: a real open drops and recreates this layout wholesale, so
    # whatever shape it is in now does not matter.
    if "books" in tables and version < SCHEMA_VERSION:
        return PlanMode(
            "insert-all",
            f"the schema would be rebuilt from scratch (on-disk version {version})",
        )

    missing = _missing_schema_columns(db)
    if missing:
        described = " and ".join(
            f"the {table} table is missing {', '.join(repr(c) for c in columns)}"
            for table, columns in missing.items()
        )
        return PlanMode("unusable", f"{described} at schema version {version}")

    if not _path_index_usable(db):
        return PlanMode(
            "unusable",
            "books.path holds duplicates, so the unique index on it cannot be created",
        )

    if "books" not in tables:
        # Created whole by a real open, so every readable file is an insert.
        return PlanMode("insert-all", "the books table would be created")

    if version > SCHEMA_VERSION:
        return PlanMode(
            "unusable",
            f"the on-disk schema version {version} is newer than this build "
            f"expects ({SCHEMA_VERSION})",
        )

    return PlanMode("compare", "")


def _path_index_usable(db: "Database") -> bool:
    """False only when the unique index on ``books.path`` could not be created.

    A missing index is ordinarily recreated on open and is reported as pending
    work. It cannot be recreated if the rows already hold duplicate paths, and
    a real open fails there.
    """
    if "books" not in db.table_names() or "path" not in db["books"].columns_dict:
        return True  # nothing to index yet, or already rejected as unusable
    if _has_path_index(db):
        return True
    row = db.execute("SELECT 1 FROM books GROUP BY path HAVING count(*) > 1 LIMIT 1").fetchone()
    return row is None


def _has_path_index(db: "Database") -> bool:
    """Whether the unique index on ``books.path`` exists."""
    return any(ix.unique and ix.columns == ["path"] for ix in db["books"].indexes)


def _missing_triggers(db: "Database") -> list[str]:
    """FTS triggers a real open would recreate."""
    existing = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    return [name for name in _FTS_TRIGGERS if name not in existing]


def _missing_schema_columns(db: "Database") -> dict[str, list[str]]:
    """Columns the books and authors tables need but do not have, by table.

    An absent table is not missing columns: a real open creates it whole.
    """
    missing = {}
    for table, expected in (("books", _BOOKS_COLUMNS), ("authors", _AUTHORS_COLUMNS)):
        if table not in db.table_names():
            continue
        present = set(db[table].columns_dict)
        absent = [name for name in expected if name not in present]
        if absent:
            missing[table] = absent
    return missing


def would_repair_search_index(db: "Database") -> bool:
    """Whether a real open would rebuild the full-text index.

    This is the only pending work that turns a failing search into a
    succeeding one, so it -- not merely "something is pending" -- is what makes
    a dry run's failed query an expected report rather than an error.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        return False  # the layout is left untouched, so nothing is repaired
    if "books" not in db.table_names():
        return True  # the whole schema, index included, is created
    if version < SCHEMA_VERSION:
        return True  # rebuilt from scratch
    return not _fts_index_is_intact(db)


def describe_pending_schema_work(db: "Database") -> list[str]:
    """Say what :func:`_ensure_schema` would do to ``db``, without doing it.

    Used by dry runs to report the repairs an ordinary open would have
    performed silently. Mirrors the branching in :func:`_ensure_schema`, so the
    two must be changed together.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        return [f"leave the schema untouched (on-disk version {version} is newer)"]
    if version < SCHEMA_VERSION and "books" in db.table_names():
        return [
            f"rebuild the schema from scratch (on-disk version {version}, "
            f"current version {SCHEMA_VERSION}), discarding existing rows"
        ]
    if "books" not in db.table_names():
        return ["create the books, authors, and full-text schema"]

    work = []
    if not _fts_index_is_intact(db):
        # Rebuilding the index drops and recreates its triggers too, so they
        # are not listed separately here.
        work.append(
            "rebuild the books_fts search index and refill it from "
            f"{_stored_book_count(db)} stored book(s)"
        )
    else:
        absent = _missing_triggers(db)
        if absent:
            work.append(f"recreate the search index triggers {', '.join(absent)}")

    if not _has_path_index(db):
        work.append("create the unique index on books.path")

    return work


def _fts_index_is_intact(db: "Database") -> bool:
    """True only when ``books_fts`` exists and is an FTS5 table.

    Both failures are repairable and both must be caught. An object of that
    name which is not FTS5 makes every read and write against it fail, and
    ``CREATE VIRTUAL TABLE IF NOT EXISTS`` would step over it forever. A
    missing one is quieter and worse: the create would put back an empty
    external-content table, and searches would then report no matches for
    books that are still sitting in ``books``.
    """
    row = db.execute("SELECT sql FROM sqlite_master WHERE name = 'books_fts'").fetchone()
    if row is None:
        return False
    return "fts5" in (row[0] or "").lower()


def _stored_book_count(db: "Database") -> int:
    """Number of rows in ``books``, or 0 if the table is not there yet."""
    if "books" not in db.table_names():
        return 0
    return db.execute("SELECT count(*) FROM books").fetchone()[0]


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
        dict(_BOOKS_COLUMNS),
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

    The path is resolved to an absolute path before it is stored or looked
    up, so a caller passing a relative path cannot create a second record for
    a file that is already indexed under its absolute path, and stored paths
    never depend on the working directory a run happened to start in.

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
    path = str(Path(path).resolve())

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
    existing_id = next((row["id"] for row in books.rows_where("path = ?", [path])), None)

    if existing_id is None:
        books.insert(fields)
        result = SavedBook(id=books.last_pk, created=True)
    else:
        books.update(existing_id, fields)
        result = SavedBook(id=existing_id, created=False)

    logger.debug(f"{'Inserted' if result.created else 'Updated'} book '{fields['title']}' ({path})")
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
