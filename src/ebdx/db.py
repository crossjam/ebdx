"""
SQLite database operations for ebdx.

Provides database connection management and query functions
for indexing and searching EPUB metadata using sqlite_utils.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from sqlite_utils import Database


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
    """Ensure the database schema exists.

    Creates tables for books, authors, and FTS5 search index if they
    do not already exist.
    """
    # Authors table
    db["authors"].create(
        {"id": int, "name": str},
        pk="id",
        not_null=["name"],
        replace=True,
    )

    # Books table
    db["books"].create(
        {
            "id": int,
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
        not_null=["title"],
        foreign_keys=["author_id"],
        replace=True,
    )

    # FTS5 full-text search index
    db.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
            title,
            author,
            series,
            tags,
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


def save_book(db: "Database", book_data: dict) -> int:
    """Save a single book and its author to the database.

    Args:
        db: The database connection.
        book_data: Dictionary with book metadata (title, author, series, etc.).

    Returns:
        The ID of the saved book.
    """
    author_name = book_data.get("author", "")

    # Upsert author by name (using lookup to find existing)
    try:
        author_id = db["authors"].lookup({"name": author_name})
    except KeyError:
        db["authors"].insert({"name": author_name})
        author_id = db["authors"].lookup({"name": author_name})

    # Insert book (no upsert since auto-increment PK)
    db["books"].insert(
        {
            "title": book_data.get("title", ""),
            "author_id": author_id,
            "series": book_data.get("series", ""),
            "series_index": book_data.get("series_index"),
            "publisher": book_data.get("publisher", ""),
            "published": book_data.get("published", ""),
            "isbn": book_data.get("isbn", ""),
            "language": book_data.get("language", ""),
            "tags": book_data.get("tags", ""),
        },
    )

    book_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    logger.debug(f"Saved book: {book_data.get('title', '')}")
    return book_id


def search_books(db: "Database", query: str, limit: int | None = None) -> list[dict]:
    """Search for books using FTS5 full-text search.

    Args:
        db: The database connection.
        query: The search query string.
        limit: Maximum number of results to return.

    Returns:
        List of book dictionaries matching the query.
    """
    if limit is None:
        limit = 20

    results = db.execute(
        """
        SELECT b.id, b.title, a.name as author, b.series, b.series_index
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
                "title": row[1],
                "author": row[2],
                "series": row[3],
                "series_index": row[4],
            }
        )

    return books
