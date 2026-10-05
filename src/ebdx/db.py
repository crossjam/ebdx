"""
SQLite database operations for ebdx.

Provides database connection management and query functions
for indexing and searching EPUB metadata using sqlite_utils.
"""

import sqlite3
from collections.abc import Callable, Mapping
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


class AddedColumn(NamedTuple):
    """Complete current-schema definition for a migration-added column."""

    column_type: type
    not_null: bool = False
    default: str | int | float | bool | None = None


class Migration(NamedTuple):
    """One atomic schema upgrade, from the preceding version to ``target``.

    ``apply`` must use raw ``db.execute`` statements only. Helpers such as
    sqlite-utils' ``add_column`` or ``Table.transform`` may commit the enclosing
    transaction and break atomicity. ``ensure_schema`` must idempotently create
    any migration-owned tables or indexes not covered by the core schema; it
    runs on fresh databases as well as existing ones. It must also use raw SQL
    because it may run inside the atomic FTS repair transaction. A step that
    changes what the full-text index reads must drop it with :func:`_drop_fts`
    and set ``rebuilds_search=True``, so the next schema setup recreates and
    refills it.
    """

    target: int
    description: str
    apply: Callable[["Database"], None]
    adds: Mapping[str, Mapping[str, AddedColumn]]
    ensure_schema: Callable[["Database"], None]
    rebuilds_search: bool = False


# Version 1 is the first layout with path-keyed book identity. Older databases
# cannot be migrated safely because they do not have a stable file path.
_BASE_VERSION = 1
_MIGRATIONS: tuple[Migration, ...] = ()


def _validate_migrations() -> None:
    expected = _BASE_VERSION + 1
    for migration in _MIGRATIONS:
        if migration.target != expected:
            raise ValueError(
                f"migration targets must be contiguous: expected {expected}, got {migration.target}"
            )
        expected += 1


_validate_migrations()
SCHEMA_VERSION = _BASE_VERSION + len(_MIGRATIONS)

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


def _validate_migration_columns() -> None:
    """Ensure core added-column metadata matches the fresh schema maps."""
    current = {"books": _BOOKS_COLUMNS, "authors": _AUTHORS_COLUMNS}
    for migration in _MIGRATIONS:
        for table, columns in migration.adds.items():
            if table not in current:
                continue
            for name, definition in columns.items():
                if current[table].get(name) is not definition.column_type:
                    raise ValueError(
                        f"migration {migration.target} adds {table}.{name}, but the current "
                        "schema column map does not have its declared type"
                    )


_validate_migration_columns()


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


def _as_term_query(query: str) -> str:
    """Quote each word of ``query`` as its own FTS5 string literal.

    Per word rather than one phrase over the whole query: the requirement is a
    search for *those words*, so "Ender's Game" should find a book holding both
    terms, not only one where they sit adjacent.

    Quoting is what makes any text searchable. Inside an FTS5 string literal
    every character but ``"`` is ordinary, so a comma, a full stop, a leading
    hyphen, a colon or an underscore is simply part of the term, and an
    embedded quote survives as a doubled one. A query holding no words at all
    yields the empty string, which is not an expression FTS5 accepts -- see
    :func:`search_books`, which treats it as a search with nothing to match.
    """
    return " ".join('"' + word.replace('"', '""') + '"' for word in query.split())


def resolve_query(query: str, *, fts: bool = False) -> str:
    """Return the FTS5 expression to execute for ``query``.

    By default ``query`` is literal text: each of its words is quoted as an
    FTS5 string literal and the words are ANDed, so any text whatsoever is
    searchable and no ordinary title can be reported as a malformed query.
    Under ``fts`` the query is an expression and is passed through as written,
    giving a caller who asked for it the engine's own syntax -- column filters,
    boolean operators, prefixes, proximity and phrases.

    Nothing here infers which of the two the user meant. The caller says which,
    because the alternative is a second copy of FTS5's lexer that drifts from
    the original and turns a missed corner into a silent wrong answer.

    Args:
        query: The search text.
        fts: Read ``query`` as an FTS5 expression rather than as literal text.

    Raises:
        InvalidQueryError: under ``fts`` only, when FTS5 cannot parse ``query``.
    """
    if not fts:
        return _as_term_query(query)
    _validate_fts_query(query)
    return query


def validate_query(query: str, *, fts: bool = False) -> None:
    """Raise :class:`InvalidQueryError` if ``query`` cannot be searched for.

    Public entry point for callers that must settle whether a query is usable
    before deciding what else to do -- a dry run has to report a bad query as a
    bad query, whatever it would otherwise have said about the database. It
    accepts exactly what :func:`search_books` accepts, so the two cannot
    disagree about which queries are searchable.

    Literal text cannot be malformed, so this is a no-op unless ``fts`` is set.
    """
    resolve_query(query, fts=fts)


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
    try:
        _ensure_schema(db)
    except BaseException:
        db.conn.close()
        raise
    return db


def _ensure_schema(db: "Database") -> None:
    """Create, migrate, or repair the database schema as needed.

    Layout versions are recorded in ``PRAGMA user_version``. Databases older
    than path-keyed identity are rebuilt because their rows cannot be matched
    safely to files. Known layouts at or above :data:`_BASE_VERSION` migrate
    one step at a time; each step commits its schema changes and version stamp
    atomically. A database at a newer version than this build understands is
    left untouched.

    A missing or damaged full-text index is derived data: it is recreated and
    refilled from ``books`` without discarding book rows. Migrations that
    change the indexed content drop the index in their own transaction, so
    this same repair path rebuilds it after the last pending step.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]

    if version > SCHEMA_VERSION:
        logger.warning(
            f"Database schema version {version} is newer than this build "
            f"expects ({SCHEMA_VERSION}); leaving it untouched"
        )
        return

    tables = db.table_names()
    if version < _BASE_VERSION and "books" in tables:
        logger.info(
            f"Rebuilding database schema: on-disk version {version} predates "
            f"migratable version {_BASE_VERSION}"
        )
        _drop_schema(db)
    elif _BASE_VERSION <= version < SCHEMA_VERSION:
        if "books" not in tables:
            # A partially initialized but versioned database still needs the
            # prior version's core tables before its migrations can run. This
            # preserves any existing authors while avoiding current columns
            # that the pending steps need to add.
            expected = _expected_columns_at_version(version)
            _create_core_tables(db, expected["books"], expected["authors"])
        _apply_migrations(db, version)

    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        logger.warning(
            f"Database schema version {version} is newer than this build "
            f"expects ({SCHEMA_VERSION}); leaving it untouched"
        )
        return

    needs_version_stamp = version < SCHEMA_VERSION
    if _fts_index_is_intact(db):
        if needs_version_stamp:
            _create_schema_and_stamp_atomically(db)
        else:
            _create_schema(db)
    else:
        # Warn only when there are books whose index is being rebuilt; on a
        # new database the index is simply absent and nothing was lost.
        if _stored_book_count(db):
            logger.warning(
                "The books_fts search index is missing or is not an FTS5 "
                "table; rebuilding it from the stored books"
            )
        _repair_search_index_atomically(
            db, target_version=SCHEMA_VERSION if needs_version_stamp else None
        )


def _create_schema_and_stamp_atomically(db: "Database") -> None:
    """Create a fresh or incomplete schema and its version stamp atomically."""
    db.execute("BEGIN IMMEDIATE")
    try:
        _create_schema(db)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.execute("COMMIT")
    except BaseException:
        if db.conn.in_transaction:
            db.execute("ROLLBACK")
        raise


def _repair_search_index_atomically(db: "Database", *, target_version: int | None = None) -> None:
    """Recreate and refill the FTS index in one recoverable transaction.

    A migration may have committed after dropping ``books_fts``. Keeping the
    drop, create, trigger installation, and refill in one transaction means
    an interruption leaves the index absent (and detectable on the next open)
    rather than present but empty.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        _drop_fts(db)
        _create_schema(db)
        _repopulate_fts(db)
        if target_version is not None:
            db.execute(f"PRAGMA user_version = {target_version}")
        db.execute("COMMIT")
    except BaseException:
        if db.conn.in_transaction:
            db.execute("ROLLBACK")
        raise


def _apply_migrations(db: "Database", version: int) -> None:
    """Apply steps after ``version``, atomically skipping steps committed by peers."""
    for migration in _MIGRATIONS:
        if migration.target <= version:
            continue

        # BEGIN IMMEDIATE serializes schema writers before the first DDL change;
        # the locked version check below prevents a waiting opener from repeating it.
        db.execute("BEGIN IMMEDIATE")
        try:
            # Another opener may have completed this step while this connection
            # waited for the write lock. Re-read under the lock before applying.
            locked_version = db.execute("PRAGMA user_version").fetchone()[0]
            if migration.target <= locked_version:
                db.execute("COMMIT")
                continue
            if migration.target != locked_version + 1:
                raise sqlite3.DatabaseError(
                    f"cannot apply migration {migration.target} from schema version "
                    f"{locked_version}"
                )
            migration.apply(db)
            db.execute(f"PRAGMA user_version = {migration.target}")
            db.execute("COMMIT")
        except BaseException:
            if db.conn.in_transaction:
                db.execute("ROLLBACK")
            raise


class UnindexableDatabaseError(RuntimeError):
    """Raised when a database cannot be indexed as it stands.

    Carries the reason so a caller can report it. Planning raises this rather
    than returning counts, because any count would describe a run that cannot
    start.
    """


class PlanMode(NamedTuple):
    """How an index run would treat a database, and why."""

    mode: str  # "compare" | "insert-all" | "unusable"
    reason: str


def plan_mode(db: "Database") -> PlanMode:
    """Predict how a real index run would treat ``db``, without touching it.

    Three outcomes, and deliberately no more:

    - ``compare``: the current layout, or a known earlier layout that will be
      migrated in place, so existing rows say which files would be updated.
    - ``insert-all``: a real open rebuilds a pre-path database or creates a
      missing ``books`` table, so every readable file ends up inserted.
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

    # Only versions predating path-keyed identity must be rebuilt. Their shape
    # is irrelevant because no stored row can be safely carried forward.
    if "books" in tables and version < _BASE_VERSION:
        return PlanMode(
            "insert-all",
            f"the schema would be rebuilt from scratch (on-disk version {version})",
        )

    missing = _missing_schema_columns(db, version)
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


def _expected_columns_at_version(version: int) -> dict[str, dict[str, type]]:
    """Return the books/authors columns defined by an on-disk version."""
    expected = {"books": dict(_BOOKS_COLUMNS), "authors": dict(_AUTHORS_COLUMNS)}
    for migration in _MIGRATIONS:
        if migration.target <= version:
            continue
        for table, columns in migration.adds.items():
            if table in expected:
                for column in columns:
                    expected[table].pop(column, None)
    return expected


def _missing_schema_columns(db: "Database", version: int | None = None) -> dict[str, list[str]]:
    """Columns expected at ``version`` but absent, by table.

    An absent table is not missing columns: a real open creates it whole. When
    ``version`` is omitted, inspect the version recorded in the database.
    """
    if version is None:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    missing = {}
    for table, expected in _expected_columns_at_version(version).items():
        if table not in db.table_names():
            continue
        present = set(db[table].columns_dict)
        absent = [name for name in expected if name not in present]
        if absent:
            missing[table] = absent
    return missing


def unrecognised_structure(db: "Database") -> str | None:
    """Why this database's structure is not the one this build writes, or None.

    Structure only -- the tables, their columns, and the unique index over
    ``books.path``. Deliberately not the recorded version: a database at a
    newer version with the expected structure is left alone by a real open and
    still reads correctly, so reading commands may use it.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version < _BASE_VERSION and "books" in db.table_names():
        return None  # a real open rebuilds this known pre-path layout

    missing = _missing_schema_columns(db, version)
    if missing:
        described = " and ".join(
            f"the {table} table is missing {', '.join(repr(c) for c in columns)}"
            for table, columns in missing.items()
        )
        return f"{described} at schema version {version}"
    if not _path_index_usable(db):
        return "books.path holds duplicates, so the unique index on it cannot be created"
    return None


def would_fail_to_open(db: "Database") -> bool:
    """Whether a real open would fail on this database.

    Reuses the layout recognition rather than modelling failures: an
    unrecognised layout at or below the current version is one the open tries
    to build its schema objects over, and fails. Above the current version the
    open leaves everything alone and returns early, so even an unrecognised
    layout opens cleanly there -- it is the writes that suffer.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        return False
    return plan_mode(db).mode == "unusable"


def would_discard_existing_rows(db: "Database") -> bool:
    """Whether a real open rebuilds a pre-path schema and drops its rows.

    Migratable older versions retain their rows, so a dry-run search can read
    them even while it reports the pending migrations.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    return version < _BASE_VERSION and "books" in db.table_names()


def would_repair_search(db: "Database") -> bool:
    """Whether a real open would make a currently failing search work.

    Not merely "something is pending": a dry run may report work that repairs
    nothing a query needs. This is the narrower question of whether the open
    creates or rebuilds one of the objects the search reads, which is what
    makes a failed query an expected report rather than an error.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        return False  # the layout is left untouched, so nothing is repaired
    tables = db.table_names()
    if "books" not in tables:
        return True  # the whole schema, index included, is created
    if version < _BASE_VERSION:
        return True  # rebuilt from scratch
    if any(migration.target > version and migration.rebuilds_search for migration in _MIGRATIONS):
        return True  # a pending migration rebuilds the index definition
    if "authors" not in tables:
        return True  # created on open; the search joins against it
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
    if version < _BASE_VERSION and "books" in db.table_names():
        return [
            f"rebuild the schema from scratch (on-disk version {version}, "
            f"current version {SCHEMA_VERSION}), discarding existing rows"
        ]
    tables = db.table_names()
    if "books" not in tables:
        work = ["create the books, authors, and full-text schema"]
        if version >= _BASE_VERSION:
            work.extend(
                f"apply migration to version {migration.target}: {migration.description}"
                for migration in _MIGRATIONS
                if migration.target > version
            )
        return work

    work = [
        f"apply migration to version {migration.target}: {migration.description}"
        for migration in _MIGRATIONS
        if migration.target > version
    ]
    if "authors" not in tables:
        # Created on open like any other managed table; the search join needs it.
        work.append("create the authors table")
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


def _quote_identifier(identifier: str) -> str:
    """Quote an internal SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def _fts_value(column: str, row: str) -> str:
    """Expression supplying one FTS value from an aliased book row."""
    if column == "author":
        return f"(SELECT name FROM authors WHERE id = {row}.author_id)"
    return f"{row}.{_quote_identifier(column)}"


def _fts_column_list() -> str:
    return ", ".join(_quote_identifier(column) for column in _FTS_COLUMNS)


def _repopulate_fts(db: "Database") -> None:
    """Refill ``books_fts`` from ``books`` after the index was rebuilt.

    FTS5's own ``'rebuild'`` command is not usable here: it reads the
    ``content=`` table directly, and ``books`` stores ``author_id`` rather
    than the ``author`` text the index carries. The same value expressions as
    the triggers are selected here for every existing row.
    """
    values = ", ".join(_fts_value(column, "b") for column in _FTS_COLUMNS)
    db.execute(
        f"""
        INSERT INTO books_fts (rowid, {_fts_column_list()})
        SELECT b.id, {values}
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


def _core_column_options(
    table: str, columns: Mapping[str, type], base_not_null: list[str]
) -> tuple[list[str], dict[str, str | int | float | bool]]:
    """Return nullability/default options declared by migration-added columns."""
    not_null = list(base_not_null)
    defaults = {}
    for migration in _MIGRATIONS:
        for name, definition in migration.adds.get(table, {}).items():
            if name not in columns:
                continue  # this older layout predates the added column
            if columns[name] is not definition.column_type:
                raise ValueError(f"current {table}.{name} type disagrees with migration metadata")
            if definition.not_null and name not in not_null:
                not_null.append(name)
            if definition.default is not None:
                defaults[name] = definition.default
    return not_null, defaults


def _create_core_tables(
    db: "Database",
    books_columns: Mapping[str, type],
    authors_columns: Mapping[str, type],
) -> None:
    """Create the core tables and path index for a specified layout version."""
    authors_not_null, authors_defaults = _core_column_options("authors", authors_columns, ["name"])
    books_not_null, books_defaults = _core_column_options("books", books_columns, ["title", "path"])
    db["authors"].create(
        dict(authors_columns),
        pk="id",
        not_null=authors_not_null,
        defaults=authors_defaults,
        if_not_exists=True,
    )
    db["books"].create(
        dict(books_columns),
        pk="id",
        not_null=books_not_null,
        defaults=books_defaults,
        foreign_keys=["author_id"],
        if_not_exists=True,
    )
    db["books"].create_index(["path"], unique=True, if_not_exists=True)


def _create_schema(db: "Database") -> None:
    """Create the books, authors, and FTS5 objects if they are absent.

    Safe to call on every open: an up-to-date database is left untouched.
    """
    _create_core_tables(db, _BOOKS_COLUMNS, _AUTHORS_COLUMNS)

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

    # Triggers to keep FTS5 in sync. Values are generated from the same column
    # list as the table and the refill query, so a migration can extend the
    # indexed columns without leaving any of those paths out of step.
    columns = _fts_column_list()
    new_values = ", ".join(_fts_value(column, "new") for column in _FTS_COLUMNS)
    old_values = ", ".join(_fts_value(column, "old") for column in _FTS_COLUMNS)

    db.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO books_fts (rowid, {columns})
            SELECT new.id, {new_values};
        END
        """
    )

    db.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, {columns})
            VALUES ('delete', old.id, {old_values});
        END
        """
    )

    db.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, {columns})
            VALUES ('delete', old.id, {old_values});
            INSERT INTO books_fts (rowid, {columns})
            SELECT new.id, {new_values};
        END
        """
    )

    # Migrations may own additional managed tables or indexes that are not
    # represented by the core column maps above. Their idempotent schema
    # callbacks make those objects part of both fresh and upgraded databases.
    for migration in _MIGRATIONS:
        migration.ensure_schema(db)


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
    # Keep future extracted columns flowing through the same path-keyed write
    # logic once a schema migration adds them to the store.
    for column in _BOOKS_COLUMNS:
        if column not in fields and column != "id" and column in book_data:
            fields[column] = book_data[column]

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


def search_books(
    db: "Database", query: str, limit: int | None = None, *, fts: bool = False
) -> list[dict]:
    """Search for books using FTS5 full-text search.

    Args:
        db: The database connection.
        query: The search query string, literal text unless ``fts`` is set.
        limit: Maximum number of results to return.
        fts: Read ``query`` as an FTS5 expression rather than as literal text.

    Returns:
        List of book dictionaries matching the query.

    Raises:
        InvalidQueryError: under ``fts`` only, when FTS5 cannot parse ``query``.
            Literal text is always searchable.
        sqlite3.OperationalError: if the database itself cannot serve the
            search (locked file, missing or corrupt index, schema drift).
    """
    if limit is None:
        limit = 20

    # Settle the query before touching the real database, so the statement
    # below can only fail for database reasons. The resolved form is what runs:
    # literal text arrives here quoted term by term, an expression as written.
    query = resolve_query(query, fts=fts)

    # A query holding no words resolves to the empty expression, which FTS5
    # rejects. There is nothing to match and nothing malformed about asking,
    # so it is an empty result rather than an error -- and answering here keeps
    # the error that would otherwise surface from reading as a database fault.
    if not query:
        return []

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
