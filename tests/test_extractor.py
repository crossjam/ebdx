"""Tests for ebdx.extractor.extract_metadata (cii §4.3).

Covers a well-formed EPUB, one declaring only a title, and unreadable
files. ``series`` is asserted at its current value ("" — the extractor
does not read Calibre's ``calibre:series`` meta) rather than the value a
fix would produce; that fix is out of scope for this change.
"""

from ebdx.extractor import extract_metadata

TEXT_FIELDS = ("title", "author", "series", "publisher", "published", "isbn", "language", "tags")


def test_well_formed_epub_yields_recorded_metadata(make_epub):
    path = make_epub(
        "dune.epub",
        title="Dune",
        author="Frank Herbert",
        publisher="Chilton Books",
        language="en",
        subjects=["Science Fiction", "Politics"],
    )

    md = extract_metadata(path)

    assert md is not None
    assert md["title"] == "Dune"
    assert md["author"] == "Frank Herbert"
    assert md["publisher"] == "Chilton Books"
    assert md["language"] == "en"
    assert md["tags"] == "Science Fiction, Politics"


def test_title_only_epub_leaves_other_text_fields_empty(make_epub):
    path = make_epub("bare.epub", title="Only A Title", language="")

    md = extract_metadata(path)

    assert md is not None
    assert md["title"] == "Only A Title"
    # Present as empty strings, not missing keys and not None.
    for field in ("author", "publisher", "published", "isbn", "language", "tags"):
        assert md[field] == "", field


def test_series_is_not_extracted(make_epub):
    """Current behaviour, recorded as-is: series is always empty."""
    md = extract_metadata(make_epub("x.epub", title="X"))

    assert md is not None
    assert md["series"] == ""
    assert md["series_index"] is None


def test_metadata_always_has_the_same_keys(make_epub):
    rich = extract_metadata(
        make_epub("rich.epub", title="R", author="A", publisher="P", subjects=["s"])
    )
    sparse = extract_metadata(make_epub("sparse.epub", title="S", language=""))

    assert set(rich) == set(sparse)
    for field in TEXT_FIELDS:
        assert field in rich


def test_corrupt_file_returns_none(make_corrupt_epub):
    assert extract_metadata(make_corrupt_epub()) is None


def test_missing_file_returns_none(tmp_path):
    assert extract_metadata(tmp_path / "does-not-exist.epub") is None
