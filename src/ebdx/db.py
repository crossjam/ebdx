"""
SQLite database operations for ebdx.

Provides database connection management and query functions
for indexing and searching EPUB metadata.
"""

import sqlite3
from pathlib import Path

from loguru import logger


def get_database(db_path: str | Path) -> sqlite3.Connection:
    """Get a database connection, creating the schema if needed.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A sqlite3.Connection instance.
    """
    db_path = Path(db_path)
    logger.info(f"Opening database: {db_path}")

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    _ensure_schema(db)
    return db


def _ensure_schema(db: sqlite3.Connection) -> None:
    """Ensure the database schema exists.

    Creates tables for books, authors, and FTS5 search index if they
    do not already exist.
    """
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS authors (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS books (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            author_id      INTEGER NOT NULL REFERENCES authors(id),
            series         TEXT,
            series_index   REAL,
            publisher      TEXT,
            published      TEXT,
            isbn           TEXT,
            language       TEXT,
            tags           TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
            title,
            author,
            series,
            tags,
            content="books",
            content_rowid="id"
        );

        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO books_fts (rowid, title, author, series, tags)
            SELECT new.id, new.title,
                   (SELECT name FROM authors WHERE id = new.author_id),
                   new.series, new.tags;
        END;

        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, title, author, series, tags)
            VALUES ('delete', old.id, old.title,
                    (SELECT name FROM authors WHERE id = old.author_id),
                    old.series, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            INSERT INTO books_fts (books_fts, rowid, title, author, series, tags)
            VALUES ('delete', old.id, old.title,
                    (SELECT name FROM authors WHERE id = old.author_id),
                    old.series, old.tags);
            INSERT INTO books_fts (rowid, title, author, series, tags)
            SELECT new.id, new.title,
                   (SELECT name FROM authors WHERE id = new.author_id),
                   new.series, new.tags;
        END;
        """
    )
    db.commit()


def save_book(db: sqlite3.Connection, book_data: dict) -> int:
    """Save a single book and its author to the database.

    Args:
        db: The database connection.
        book_data: Dictionary with book metadata (title, author, series, etc.).

    Returns:
        The ID of the saved book.
    """
    author_name = book_data.get("author", "")

    # Upsert author
    cursor = db.execute(
        "INSERT OR IGNORE INTO authors (name) VALUES (?)", (author_name,)
    )
    if cursor.rowcount == 0:
        cursor = db.execute(
            "SELECT id FROM authors WHERE name = ?", (author_name,)
        )
        author_id = cursor.fetchone()[0]
    else:
        author_id = cursor.lastrowid

    # Upsert book
    cursor = db.execute(
        """
        INSERT INTO books (
            title, author_id, series, series_index,
            publisher, published, isbn, language, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            author_id = excluded.author_id,
            series = excluded.series,
            series_index = excluded.series_index,
            publisher = excluded.publisher,
            published = excluded.published,
            isbn = excluded.isbn,
            language = excluded.language,
            tags = excluded.tags
        """,
        (
            book_data.get("title", ""),
            author_id,
            book_data.get("series", ""),
            book_data.get("series_index"),
            book_data.get("publisher", ""),
            book_data.get("published", ""),
            book_data.get("isbn", ""),
            book_data.get("language", ""),
            book_data.get("tags", ""),
        ),
    )

    db.commit()
    book_id = cursor.lastrowid or cursor.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    logger.debug(f"Saved book: {book_data.get('title', '')}")
    return book_id


def search_books(db: sqlite3.Connection, query: str, limit: int | None = None) -> list[dict]:
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
