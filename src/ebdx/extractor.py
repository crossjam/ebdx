"""
EPUB metadata extraction module for ebdx.

Extracts metadata from .epub files using ebooklib.
"""

from contextlib import suppress
from pathlib import Path

from loguru import logger


def extract_metadata(epub_path: Path) -> dict | None:
    """Extract metadata from an EPUB file.

    Args:
        epub_path: Path to the .epub file.

    Returns:
        A dictionary with book metadata, or None if extraction fails.
    """
    try:
        from ebooklib import epub

        book = epub.read_epub(str(epub_path))

        # Extract core metadata
        title = book.title if book.title else ""
        creators = book.get_metadata("DC", "creator")
        author = creators[0][0] if creators else ""

        series = ""
        series_index = None
        series_meta = book.get_metadata("OPF", "series")
        if series_meta:
            series = series_meta[0][0]
        series_num_meta = book.get_metadata("OPF", "series_index")
        if series_num_meta:
            with suppress(ValueError, TypeError):
                series_index = float(series_num_meta[0][0])

        publisher_meta = book.get_metadata("DC", "publisher")
        publisher = publisher_meta[0][0] if publisher_meta else ""

        date_meta = book.get_metadata("DC", "date")
        published = date_meta[0][0] if date_meta else ""

        isbn = ""
        for identifier in book.get_metadata("DC", "identifier"):
            if identifier[1] and "isbn" in identifier[1].lower():
                isbn = identifier[0]

        language_meta = book.get_metadata("DC", "language")
        language = language_meta[0][0] if language_meta else ""

        tags = []
        for subject in book.get_metadata("DC", "subject"):
            tags.append(subject[0])

        metadata = {
            "title": title,
            "author": author,
            "series": series,
            "series_index": series_index,
            "publisher": publisher,
            "published": published,
            "isbn": isbn,
            "language": language,
            "tags": ", ".join(tags),
        }

        logger.debug(f"Extracted metadata from {epub_path.name}: {metadata['title']}")
        return metadata

    except Exception as e:
        logger.error(f"Failed to extract metadata from {epub_path}: {e}")
        return None
