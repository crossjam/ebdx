"""CliRunner tests for cli-runtime behaviour (cii §5).

Covers log verbosity on the group callback (5.1), the indexing-summary and
search-results table shape (5.2), malformed-query handling (5.3), and the
informational commands with no database present (5.4). Every invocation
passes an explicit ``--database`` under ``tmp_path`` so no test touches the
real user data directory.
"""

from __future__ import annotations

import sqlite3
import sys

import pytest
from click.testing import CliRunner
from conftest import terminal_frames
from loguru import logger

from ebdx.cli import cli
from ebdx.scanner import iter_files


@pytest.fixture(autouse=True)
def _restore_loguru():
    """Put loguru's default stderr sink back after each test.

    The group callback calls ``logger.remove()`` and re-adds a sink bound to
    the ``CliRunner``'s captured stream; without this, later test modules
    that log directly would write into a dead buffer.
    """
    yield
    logger.remove()
    logger.add(sys.stderr)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _save_series_book(db_path, *, title, series, author="Frank Herbert"):
    """Add one book carrying a series directly to an indexed database.

    ``make_epub`` has no series argument, and series metadata does not survive
    a round trip through the EPUB writer, so a test that needs a series states
    it at the store instead.
    """
    from ebdx.db import get_database, save_book

    db = get_database(str(db_path))
    save_book(
        db,
        {
            "path": f"/library/{title.lower().replace(' ', '-')}.epub",
            "title": title,
            "author": author,
            "series": series,
            "series_index": 1.0,
            "publisher": "",
            "published": "",
            "isbn": "",
            "language": "en",
            "tags": "",
        },
    )
    db.conn.close()


def _index_library(runner, tmp_path, make_epub, books):
    """Build a library of EPUBs and index it into a tmp database.

    ``books`` is a list of kwargs dicts for ``make_epub``. Returns the
    database path.
    """
    for i, spec in enumerate(books):
        make_epub(f"library/book{i}.epub", **spec)
    db_path = tmp_path / "ebdx.db"
    result = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])
    assert result.exit_code == 0, result.output
    return db_path


# --- 5.1 verbosity -----------------------------------------------------------


def test_no_log_lines_by_default(runner, tmp_path, make_epub):
    db_path = tmp_path / "ebdx.db"
    make_epub("library/a.epub", title="A", author="AA")

    result = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Opening database" not in result.output
    assert "DEBUG" not in result.output


def test_verbose_shows_the_database_open(runner, tmp_path, make_epub):
    db_path = tmp_path / "ebdx.db"
    make_epub("library/a.epub", title="A", author="AA")

    result = runner.invoke(
        cli,
        ["--verbose", "index", str(tmp_path / "library"), "--database", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Opening database" in result.output


def test_verbose_and_quiet_together_is_a_usage_error(runner):
    result = runner.invoke(cli, ["--verbose", "--quiet", "version"])

    assert result.exit_code != 0
    assert "at most one" in result.output


def test_quiet_suppresses_the_unreadable_file_warning(
    runner, tmp_path, make_epub, make_corrupt_epub
):
    """--quiet hides the per-file warning but not the failure it counted."""
    db_path = tmp_path / "ebdx.db"
    make_epub("library/good.epub", title="Good", author="AA")
    make_corrupt_epub("library/broken.epub")
    args = ["index", str(tmp_path / "library"), "--database", str(db_path)]

    loud = runner.invoke(cli, args)
    assert loud.exit_code == 0, loud.output
    assert "broken.epub" in loud.output

    quiet = runner.invoke(cli, ["--quiet", *args])

    assert quiet.exit_code == 0, quiet.output
    assert "broken.epub" not in quiet.output
    failed_row = next(line for line in quiet.output.splitlines() if "Failed" in line)
    assert "1" in failed_row


def test_quiet_still_prints_search_results(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "FH"}])

    result = runner.invoke(cli, ["--quiet", "search", "Dune", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Dune" in result.output


# --- 5.2 table shape -------------------------------------------------------


def test_index_summary_reports_updated(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "A", "author": "AA"}])

    result = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Updated" in result.output


def test_search_results_show_a_path_column(runner, tmp_path, make_epub):
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Dune", "author": "Frank Herbert"}]
    )

    # Widen the render so the (long, tmp_path-rooted) path is not truncated.
    result = runner.invoke(
        cli, ["search", "Dune", "--database", str(db_path)], env={"COLUMNS": "240"}
    )

    assert result.exit_code == 0, result.output
    assert "Path" in result.output
    # The stored path is the resolved EPUB path; it renders in the new column.
    assert "book0.epub" in result.output


@pytest.mark.parametrize("query", ["Ender's", "Well-Tempered"])
def test_search_accepts_a_title_with_punctuation(runner, tmp_path, make_epub, query):
    """The reported bug, from the user's side: an ordinary title with an
    apostrophe or a hyphen is searched for, not rejected as a bad query."""
    db_path = _index_library(
        runner,
        tmp_path,
        make_epub,
        [
            {"title": "Ender's Game", "author": "Orson Scott Card"},
            {"title": "Well-Tempered Clavier", "author": "Bach"},
        ],
    )

    result = runner.invoke(cli, ["search", query, "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Invalid search query" not in result.output
    assert "1 found" in result.output


def test_dry_run_search_accepts_a_title_with_punctuation(runner, tmp_path, make_epub):
    """The dry-run preflight validates the query separately, so it has to agree
    with the real search about which queries are searchable."""
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Ender's Game", "author": "Orson Scott Card"}]
    )

    result = runner.invoke(cli, ["--dry-run", "search", "Ender's", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Invalid search query" not in result.output
    assert "1 found" in result.output


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["Ender's Game"], "1 found"),  # literal, punctuated
        (["badcol:Dune"], "No results found"),  # literal, operator-shaped
        (["--fts", "author:Card"], "1 found"),  # expression
        (["--fts", "badcol:Dune"], "Invalid search query"),  # expression, malformed
    ],
)
def test_dry_run_search_agrees_with_the_real_search_in_both_modes(
    runner, tmp_path, make_epub, args, expected
):
    """The dry-run preflight settles the query separately from the real search,
    so the flag has to reach both or the two would disagree about which
    queries are searchable."""
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Ender's Game", "author": "Orson Scott Card"}]
    )
    invocation = ["search", *args, "--database", str(db_path)]

    dry = runner.invoke(cli, ["--dry-run", *invocation])
    real = runner.invoke(cli, invocation)

    assert dry.exit_code == real.exit_code, dry.output
    assert expected in dry.output
    assert expected in real.output


def test_a_query_starting_with_a_dash_is_searched_for_after_a_separator(
    runner, tmp_path, make_epub
):
    """The leading dash is claimed by option parsing, not by FTS5.

    Click reads `-Dune` as an option before the query reaches the search at
    all, so the usual `--` separator is what makes it text -- and once it is
    text, it is searched for literally like any other.
    """
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "Herbert"}])

    result = runner.invoke(cli, ["search", "--database", str(db_path), "--", "-Dune"])

    assert result.exit_code == 0, result.output
    assert "1 found" in result.output
    assert "Dune" in result.output


def test_an_expression_starting_with_a_dash_runs_after_a_separator(runner, tmp_path, make_epub):
    """`--` is not only for literal text: a column filter is where it bites.

    An FTS5 expression beginning with `-` is claimed by option parsing exactly
    like any other dashed token, so the documented form has to carry the
    separator to reach the engine at all.
    """
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "Herbert"}])
    # A second Dune, this one in the series the exclusion names. Written
    # straight to the store because the EPUB fixture carries no series field,
    # and the claim under test is FTS5's, not the extractor's.
    _save_series_book(db_path, title="Dune Chronicles", series="Chronicles")

    result = runner.invoke(
        cli,
        ["search", "--fts", "--database", str(db_path), "--", "-series:Chronicles title:Dune"],
    )

    assert "No such option" not in result.output
    assert result.exit_code == 0, result.output

    # Both books answer the unfiltered query, so the exclusion below has
    # something to remove -- without this the NOT could do nothing and still
    # look right.
    both = runner.invoke(cli, ["search", "--fts", "title:Dune", "--database", str(db_path)])

    assert "2 found" in both.output, both.output

    # And the exclusion the README documents alongside it does exclude.
    excluded = runner.invoke(
        cli, ["search", "--fts", "title:Dune NOT series:Chronicles", "--database", str(db_path)]
    )

    assert excluded.exit_code == 0, excluded.output
    assert "1 found" in excluded.output
    assert "Chronicles" not in excluded.output


@pytest.mark.parametrize("query", ["", "   "])
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_a_query_with_no_words_finds_nothing_in_either_mode(
    runner, tmp_path, make_epub, query, dry_run
):
    """A query holding no words resolves to an empty FTS5 expression, which the
    engine rejects. That must never surface as database damage: there is
    nothing to match and nothing malformed about asking, in either mode."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "Herbert"}])
    prefix = ["--dry-run"] if dry_run else []

    result = runner.invoke(cli, [*prefix, "search", query, "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "No results found" in result.output
    assert "Database error" not in result.output
    assert "Invalid search query" not in result.output


def test_search_still_reports_a_mistyped_column_filter_under_fts(runner, tmp_path, make_epub):
    """Under the flag the user is writing syntax, so a wrong filter is an error
    rather than a silent empty result reading as "you own no such book"."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "Herbert"}])

    result = runner.invoke(cli, ["search", "--fts", "badcol:Dune", "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Invalid search query" in result.output
    assert "Traceback" not in result.output


def test_the_same_filter_without_the_flag_is_an_ordinary_search(runner, tmp_path, make_epub):
    """Typed as text it is text: a search that finds nothing, not an error."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "Herbert"}])

    result = runner.invoke(cli, ["search", "badcol:Dune", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Invalid search query" not in result.output
    assert "No results found" in result.output


@pytest.mark.parametrize("flag", ["--fts", "--raw"])
def test_expression_syntax_is_available_under_the_flag(runner, tmp_path, make_epub, flag):
    """Both spellings of the flag reach the engine's own syntax."""
    db_path = _index_library(
        runner,
        tmp_path,
        make_epub,
        [{"title": "Dune", "author": "Frank Herbert"}, {"title": "Foundation", "author": "Asimov"}],
    )

    result = runner.invoke(cli, ["search", flag, "author:Herbert", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "1 found" in result.output
    assert "Dune" in result.output


def test_search_does_not_render_a_missing_series_index_as_none(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Solo", "author": "One"}])

    result = runner.invoke(cli, ["search", "Solo", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "None" not in result.output


# --- 5.3 malformed query -------------------------------------------------------


@pytest.mark.parametrize("bad_query", ['"unbalanced', "badcol:Dune"])
def test_malformed_query_exits_nonzero_without_a_traceback(runner, tmp_path, make_epub, bad_query):
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Dune", "author": "Frank Herbert"}]
    )

    result = runner.invoke(cli, ["search", "--fts", bad_query, "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "Invalid search query" in result.output


def test_a_damaged_search_index_is_repaired_on_open(runner, tmp_path, make_epub):
    """A books_fts replaced by an ordinary table is rebuilt when the database
    is next opened, so search works again without re-indexing."""
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Dune", "author": "Frank Herbert"}]
    )
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE books_fts")
    conn.execute("CREATE TABLE books_fts (rowid INTEGER, title TEXT)")
    conn.commit()
    conn.close()

    result = runner.invoke(cli, ["search", "Dune", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Dune" in result.output


def test_unrepairable_damage_reports_a_database_error_not_a_bad_query(runner, tmp_path, make_epub):
    """Schema drift the opener cannot repair must exit cleanly as a database
    fault, never as a malformed query, and never as a traceback."""
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Dune", "author": "Frank Herbert"}]
    )
    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE books DROP COLUMN series_index")
    conn.commit()
    conn.close()

    result = runner.invoke(cli, ["search", "Dune", "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "Database error" in result.output
    assert "Invalid search query" not in result.output


def test_a_file_that_is_not_a_database_is_reported_cleanly(runner, tmp_path):
    """Opening runs schema work, so a non-database file fails there; it must
    not reach the user as a traceback."""
    junk = tmp_path / "junk.db"
    junk.write_text("this is not a sqlite database")

    for argv in (
        ["search", "Dune", "--database", str(junk)],
        ["schema", "--database", str(junk)],
        ["index", str(tmp_path), "--database", str(junk)],
    ):
        result = runner.invoke(cli, argv)
        assert result.exit_code != 0, argv
        assert "Traceback" not in result.output, argv
        assert "Cannot open database" in result.output, argv


# --- 5.4 discover and informational commands --------------------------------


def test_discover_finds_nested_epubs_case_insensitively_and_ignores_others(
    runner, tmp_path, make_epub
):
    make_epub("lib/a/one.epub", title="One")
    make_epub("lib/a/b/two.EPUB", title="Two")
    (tmp_path / "lib" / "notes.txt").write_text("not a book")

    result = runner.invoke(cli, ["discover", str(tmp_path / "lib")])

    assert result.exit_code == 0, result.output
    assert "one.epub" in result.output
    assert "two.EPUB" in result.output
    assert "notes.txt" not in result.output
    # discover never creates a database.
    assert not any(p.suffix == ".db" for p in iter_files(tmp_path))


def test_discover_reports_when_nothing_is_found(runner, tmp_path):
    (tmp_path / "empty").mkdir()

    result = runner.invoke(cli, ["discover", str(tmp_path / "empty")])

    assert result.exit_code == 0, result.output
    assert "No EPUB files discovered" in result.output


def test_version_runs_without_a_database(runner):
    result = runner.invoke(cli, ["version"])

    assert result.exit_code == 0, result.output
    assert "ebdx, version" in result.output


def test_about_runs_without_a_database(runner):
    result = runner.invoke(cli, ["about"])

    assert result.exit_code == 0, result.output
    assert "ebdx" in result.output


def test_schema_reports_a_missing_database(runner, tmp_path):
    result = runner.invoke(cli, ["schema", "--database", str(tmp_path / "nope.db")])

    assert result.exit_code == 0, result.output
    assert "No database found" in result.output


# --- 5.5 dry run -------------------------------------------------------------


def _fingerprint(db_path):
    """Objects and schema version of a database, read without mutating it."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        objects = conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        return objects, conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _break_fts(db_path, *, replace: bool = False):
    """Drop the FTS index (and optionally leave a plain table in its place)."""
    conn = sqlite3.connect(str(db_path))
    try:
        for trigger in ("books_ai", "books_ad", "books_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        conn.execute("DROP TABLE books_fts")
        if replace:
            conn.execute("CREATE TABLE books_fts (title TEXT)")
        conn.commit()
    finally:
        conn.close()


def test_dry_run_index_creates_nothing_where_nothing_existed(
    runner, tmp_path, make_epub, monkeypatch
):
    """The default location is the one a real run would create, so it is the one to test."""
    make_epub("library/a.epub", title="A", author="AA")
    data_dir = tmp_path / "xdg"
    monkeypatch.setattr("ebdx.cli.user_data_dir", lambda *a, **k: str(data_dir))

    result = runner.invoke(cli, ["--dry-run", "index", str(tmp_path / "library")])

    assert result.exit_code == 0, result.output
    assert not data_dir.exists()
    # Nothing was written anywhere beneath tmp_path except the library itself.
    written = {p.name for p in iter_files(tmp_path)}
    assert written == {"a.epub"}
    assert "DRY RUN" in result.output
    assert f"create the data directory {data_dir}" in result.output.replace("\n", "")


def test_dry_run_index_leaves_an_existing_database_untouched(runner, tmp_path, make_epub):
    db_path = _index_library(
        runner,
        tmp_path,
        make_epub,
        [{"title": "A", "author": "AA"}, {"title": "B", "author": "BB"}],
    )
    make_epub("library/fresh.epub", title="Fresh", author="CC")
    before = _fingerprint(db_path)
    before_rows = sqlite3.connect(str(db_path)).execute("SELECT count(*) FROM books").fetchone()[0]
    before_mtime = db_path.stat().st_mtime_ns

    result = runner.invoke(
        cli, ["--dry-run", "index", str(tmp_path / "library"), "--database", str(db_path)]
    )

    assert result.exit_code == 0, result.output
    after_rows = sqlite3.connect(str(db_path)).execute("SELECT count(*) FROM books").fetchone()[0]
    assert (after_rows, _fingerprint(db_path), db_path.stat().st_mtime_ns) == (
        before_rows,
        before,
        before_mtime,
    )
    # Two already indexed, one new -- the counts a real run would report.
    assert "Would index" in result.output
    assert "Would update" in result.output


def test_dry_run_index_counts_match_a_real_run(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "A", "author": "AA"}])
    make_epub("library/new.epub", title="New", author="BB")

    dry = runner.invoke(
        cli, ["--dry-run", "index", str(tmp_path / "library"), "--database", str(db_path)]
    )
    real = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])

    def counts(output, labels):
        # Only table rows: "Would index" also appears in the "Would index
        # EPUBs in: ..." header line above the summary.
        rows = [line for line in output.splitlines() if line.startswith("│")]
        return [next(r for r in rows if label in r).split("│")[2].strip() for label in labels]

    assert dry.exit_code == 0 and real.exit_code == 0
    assert counts(dry.output, ["Total found", "Would index", "Would update"]) == counts(
        real.output, ["Total found", "Newly indexed", "Updated"]
    )


@pytest.mark.parametrize("replace", [False, True], ids=["dropped", "replaced"])
@pytest.mark.parametrize("command", [["search", "A"], ["schema"]])
def test_dry_run_read_commands_repair_nothing(runner, tmp_path, make_epub, command, replace):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "A", "author": "AA"}])
    _break_fts(db_path, replace=replace)
    before = _fingerprint(db_path)

    result = runner.invoke(cli, ["--dry-run", *command, "--database", str(db_path)])

    assert _fingerprint(db_path) == before, f"{command[0]} repaired the index under --dry-run"
    assert "DRY RUN" in result.output


@pytest.mark.parametrize("command", [["search", "A"], ["schema"]])
def test_dry_run_read_commands_do_not_rebuild_a_legacy_database(runner, tmp_path, command):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT)")
    conn.execute("INSERT INTO books (title, author_id) VALUES ('Stale', 1)")
    conn.commit()
    conn.close()
    before = _fingerprint(db_path)
    assert before[1] == 0

    runner.invoke(cli, ["--dry-run", *command, "--database", str(db_path)])

    assert _fingerprint(db_path) == before, "a dry run rebuilt a pre-path database"


def test_dry_run_search_still_reports_a_missing_database(runner, tmp_path):
    """The exists() guard must stay ahead of the read-only open."""
    result = runner.invoke(
        cli, ["--dry-run", "search", "A", "--database", str(tmp_path / "nope.db")]
    )

    assert "No database found" in result.output
    assert "Not a usable ebdx database" not in result.output


@pytest.mark.parametrize("command", [["discover"], ["about"], ["version"]])
def test_dry_run_changes_nothing_for_read_only_commands(runner, tmp_path, command):
    plain = runner.invoke(cli, command)
    dry = runner.invoke(cli, ["--dry-run", *command])

    assert dry.exit_code == plain.exit_code == 0
    # Byte-identical, label included: a command that cannot change state has no
    # report that could be mistaken for a completed run, and staying identical
    # keeps it usable in a pipeline.
    assert dry.output == plain.output
    assert "DRY RUN" not in dry.output


def test_dry_run_output_survives_quiet(runner, tmp_path, make_epub):
    make_epub("library/a.epub", title="A", author="AA")

    result = runner.invoke(
        cli,
        [
            "--quiet",
            "--dry-run",
            "index",
            str(tmp_path / "library"),
            "--database",
            str(tmp_path / "ebdx.db"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "Total found" in result.output


def test_dry_run_index_declines_an_unrecognised_layout(runner, tmp_path, make_epub):
    """A books table this build did not write gets a rebuild instruction, not a plan."""
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "unusable.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INT)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    real = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])
    dry = runner.invoke(
        cli, ["--dry-run", "index", str(tmp_path / "library"), "--database", str(db_path)]
    )

    # The real run aborts on open; the dry run must not promise inserts instead.
    assert real.exit_code != 0
    assert dry.exit_code != 0
    assert "Not a usable ebdx database" in dry.output
    assert "rebuild" in dry.output
    # No summary table at all: it declines to predict rather than guessing.
    assert not [line for line in dry.output.splitlines() if line.startswith("│")]


def test_dry_run_index_refuses_a_database_in_a_missing_directory(runner, tmp_path, make_epub):
    """Only the default location is created for you; an explicit path is not."""
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "no-such-dir" / "ebdx.db"

    real = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])
    dry = runner.invoke(
        cli, ["--dry-run", "index", str(tmp_path / "library"), "--database", str(db_path)]
    )

    assert real.exit_code != 0
    assert dry.exit_code != 0
    assert "Cannot index this database" in dry.output
    assert not [line for line in dry.output.splitlines() if line.startswith("│")]
    assert not db_path.parent.exists()


def test_dry_run_search_reports_the_repair_instead_of_failing(runner, tmp_path, make_epub):
    """A real search repairs the index and succeeds, so the dry run must not look broken."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "FH"}])
    _break_fts(db_path)
    before = _fingerprint(db_path)

    # The dry run reports the repair and leaves the database alone...
    dry = runner.invoke(cli, ["--dry-run", "search", "Dune", "--database", str(db_path)])

    assert dry.exit_code == 0, dry.output
    assert "Would:" in dry.output
    assert "books_fts" in dry.output
    assert _fingerprint(db_path) == before

    # ...while the real run performs that repair and succeeds. Checked after
    # the assertions above, since running it first would repair the database
    # out from under them.
    real = runner.invoke(cli, ["search", "Dune", "--database", str(db_path)])

    assert real.exit_code == 0, real.output
    assert _fingerprint(db_path) != before


def test_dry_run_schema_reports_pending_work(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "FH"}])
    _break_fts(db_path)
    before = _fingerprint(db_path)

    result = runner.invoke(cli, ["--dry-run", "schema", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Would:" in result.output
    assert _fingerprint(db_path) == before


def test_dry_run_search_shows_no_stale_results_before_a_rebuild(runner, tmp_path):
    """A real open discards these rows, so showing them would be showing ghosts."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, "
        "author_id INT, series TEXT, series_index REAL, publisher TEXT, published TEXT, "
        "isbn TEXT, language TEXT, tags TEXT)"
    )
    conn.execute("INSERT INTO authors (id, name) VALUES (1, 'Old Author')")
    conn.execute("INSERT INTO books (path, title, author_id) VALUES ('/x/s.epub', 'Stale', 1)")
    conn.execute("CREATE VIRTUAL TABLE books_fts USING fts5(title, author, series, tags)")
    conn.execute("INSERT INTO books_fts (rowid, title, author) VALUES (1, 'Stale', 'Old Author')")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    dry = runner.invoke(cli, ["--dry-run", "search", "Stale", "--database", str(db_path)])
    real = runner.invoke(cli, ["search", "Stale", "--database", str(db_path)])

    assert dry.exit_code == 0, dry.output
    assert "Stale" not in dry.output.replace("--dry-run", "")
    assert "re-indexed" in dry.output
    # The real run rebuilds and finds nothing, which is what the dry run promised.
    assert "No results found" in real.output


def test_dry_run_search_reports_a_bad_query_before_anything_else(runner, tmp_path):
    """A query that cannot be parsed is a query error whatever the database is doing."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL, "
        "author_id INT, series TEXT, series_index REAL, publisher TEXT, published TEXT, "
        "isbn TEXT, language TEXT, tags TEXT)"
    )
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    dry = runner.invoke(
        cli, ["--dry-run", "search", "--fts", 'broken"(', "--database", str(db_path)]
    )
    real = runner.invoke(cli, ["search", "--fts", 'broken"(', "--database", str(db_path)])

    assert dry.exit_code != 0
    assert "Invalid search query" in dry.output
    assert "re-indexed" not in dry.output
    # Same verdict as the run it predicts.
    assert real.exit_code != 0
    assert "Invalid search query" in real.output


def test_dry_run_search_reports_a_missing_authors_table(runner, tmp_path, make_epub):
    """A real search creates the table and succeeds, so this is not a damaged database."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "FH"}])
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE authors")
    conn.commit()
    conn.close()

    dry = runner.invoke(cli, ["--dry-run", "search", "Dune", "--database", str(db_path)])
    real = runner.invoke(cli, ["search", "Dune", "--database", str(db_path)])

    assert dry.exit_code == 0, dry.output
    assert "create the authors table" in dry.output
    assert "damaged" not in dry.output
    assert real.exit_code == 0, real.output


@pytest.mark.parametrize(
    "command",
    [["index", "LIBRARY"], ["schema"], ["search", "Dune"]],
    ids=["index", "schema", "search"],
)
def test_dry_run_reports_a_corrupt_file_without_a_traceback(runner, tmp_path, make_epub, command):
    """A read-only open does no schema work, so corruption surfaces at first query."""
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "garbage.db"
    db_path.write_bytes(b"\x00\x01\x02not a database at all" * 64)
    args = [str(tmp_path / "library") if a == "LIBRARY" else a for a in command]

    result = runner.invoke(cli, ["--dry-run", *args, "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Cannot open database" in result.output
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, sqlite3.DatabaseError)


def test_dry_run_search_reports_a_bad_file_ahead_of_a_bad_query(runner, tmp_path):
    """A real search opens the database before it looks at the query."""
    db_path = tmp_path / "garbage.db"
    db_path.write_bytes(b"\x00\x01\x02not a database at all" * 64)
    args = ["search", 'broken"(', "--database", str(db_path)]

    dry = runner.invoke(cli, ["--dry-run", *args])
    real = runner.invoke(cli, args)

    for result in (dry, real):
        assert result.exit_code != 0
        assert "Cannot open database" in result.output
        assert "Invalid search query" not in result.output


def test_dry_run_search_reports_an_unopenable_layout_before_the_query(runner, tmp_path):
    """A real search fails building the schema before it ever parses the query."""
    db_path = tmp_path / "damaged.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL, "
        "title TEXT NOT NULL, author_id INT)"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    args = ["search", 'broken"(', "--database", str(db_path)]

    dry = runner.invoke(cli, ["--dry-run", *args])
    real = runner.invoke(cli, args)

    assert dry.exit_code != 0
    assert "Not a usable ebdx database" in dry.output
    assert "Invalid search query" not in dry.output
    # The real command also fails on the database, not the query.
    assert real.exit_code != 0
    assert "Cannot open database" in real.output
    assert "Invalid search query" not in real.output


def test_dry_run_search_still_works_on_a_newer_layout(runner, tmp_path, make_epub):
    """A newer version is left untouched, so the open succeeds and the search runs."""
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "Dune", "author": "FH"}])
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    result = runner.invoke(cli, ["--dry-run", "search", "Dune", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Dune" in result.output


@pytest.mark.parametrize("query", ["Dune", 'broken"('], ids=["valid-query", "invalid-query"])
def test_dry_run_search_reports_an_unrecognised_layout_that_would_open(runner, tmp_path, query):
    """The spec asks for the unusable report whatever the real command fails on first.

    This layout opens cleanly -- only write-time columns are absent -- so a real
    search reaches the query and reports that instead. Reporting the query here
    too would mean suppressing the unusable report the spec requires, so the
    divergence is deliberate.
    """
    db_path = tmp_path / "write-only.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL, "
        "title TEXT NOT NULL, author_id INT, series TEXT, tags TEXT)"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    result = runner.invoke(cli, ["--dry-run", "search", query, "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Not a usable ebdx database" in result.output
    assert "series_index" in result.output  # names what is wrong
    assert "rebuild" in result.output
    # "whatever the query says": the unusable report wins over a bad query too.
    assert "Invalid search query" not in result.output


@pytest.mark.parametrize("command", [["search", "Dune"], ["schema"]], ids=["search", "schema"])
def test_dry_run_reading_commands_reject_an_unrecognised_structure(runner, tmp_path, command):
    """Structure, not version: a newer database with missing columns is still unusable."""
    db_path = tmp_path / "newmiss.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL, "
        "title TEXT NOT NULL, author_id INT, series TEXT, tags TEXT)"
    )
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    result = runner.invoke(cli, ["--dry-run", *command, "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Not a usable ebdx database" in result.output
    assert "Database error" not in result.output


def test_dry_run_index_reports_a_blocked_data_directory(runner, tmp_path, make_epub, monkeypatch):
    """A real run cannot mkdir over a regular file, so the plan must not promise it."""
    make_epub("library/a.epub", title="A", author="AA")
    blocked = tmp_path / "datadir"
    blocked.write_text("not a directory")
    monkeypatch.setattr("ebdx.cli.user_data_dir", lambda *a, **k: str(blocked))

    dry = runner.invoke(cli, ["--dry-run", "index", str(tmp_path / "library")])
    real = runner.invoke(cli, ["index", str(tmp_path / "library")])

    for result in (dry, real):
        assert result.exit_code != 0
        assert "Cannot create the data directory" in result.output
        # Reported, not raised: no OSError escapes to the user.
        assert not isinstance(result.exception, OSError)
    assert blocked.read_text() == "not a directory"


# --- 5.6 progress display ----------------------------------------------------


def test_no_progress_reaches_a_redirected_run(runner, tmp_path, make_epub):
    """The CliRunner's streams are not a terminal, which is what a pipe looks like."""
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "ebdx.db"

    result = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Extracting metadata" not in result.output
    assert "Scanning" not in result.output
    # No cursor hiding, no erase-line, nothing else a terminal would swallow.
    assert "\x1b" not in result.output
    assert "Indexing Summary" in result.stdout


def test_index_shows_progress_on_a_terminal(runner, tmp_path, make_epub, diagnostic_terminal):
    make_epub("library/a.epub", title="A", author="AA")
    db_path = tmp_path / "ebdx.db"

    result = runner.invoke(cli, ["index", str(tmp_path / "library"), "--database", str(db_path)])

    shown = diagnostic_terminal.getvalue()
    assert result.exit_code == 0, result.output
    assert "Scanning library" in shown
    assert "Extracting metadata" in shown
    assert "1/1" in shown
    # The display stayed on the diagnostic stream; the summary is whole.
    assert "Extracting metadata" not in result.stdout
    assert "Indexing Summary" in result.stdout
    assert "│ Total found   │     1 │" in result.stdout


def test_quiet_suppresses_the_progress_display(runner, tmp_path, make_epub, diagnostic_terminal):
    """Progress is diagnostic, so --quiet silences it -- results still print."""
    make_epub("library/a.epub", title="A", author="AA")
    args = ["index", str(tmp_path / "library"), "--database", str(tmp_path / "ebdx.db")]

    loud = runner.invoke(cli, args)
    assert loud.exit_code == 0, loud.output
    assert "Extracting metadata" in diagnostic_terminal.getvalue()

    diagnostic_terminal.truncate(0)
    diagnostic_terminal.seek(0)
    quiet = runner.invoke(cli, ["--quiet", *args])

    assert quiet.exit_code == 0, quiet.output
    assert diagnostic_terminal.getvalue() == ""
    assert "Indexing Summary" in quiet.stdout


def test_discover_shows_progress_without_changing_its_listing(
    runner, tmp_path, make_epub, diagnostic_terminal
):
    make_epub("library/a/one.epub", title="One")
    make_epub("library/b/two.epub", title="Two")
    args = ["discover", str(tmp_path / "library")]

    shown_run = runner.invoke(cli, args)
    shown = diagnostic_terminal.getvalue()

    diagnostic_terminal.truncate(0)
    diagnostic_terminal.seek(0)
    silent_run = runner.invoke(cli, ["--quiet", *args])

    assert shown_run.exit_code == silent_run.exit_code == 0
    assert "Scanning library" in shown
    assert "2 found" in shown
    assert "Listing files" in shown
    assert "2/2" in shown
    assert diagnostic_terminal.getvalue() == ""
    # The listing is a result: identical whether or not a display was drawn.
    assert shown_run.stdout == silent_run.stdout
    assert "one.epub" in shown_run.stdout


def test_dry_run_index_shows_the_same_display(runner, tmp_path, make_epub, diagnostic_terminal):
    """A dry run walks and extracts exactly as a real run does, so it shows the same."""
    make_epub("library/a.epub", title="A", author="AA")

    result = runner.invoke(
        cli,
        ["--dry-run", "index", str(tmp_path / "library"), "--database", str(tmp_path / "ebdx.db")],
    )

    shown = diagnostic_terminal.getvalue()
    assert result.exit_code == 0, result.output
    assert "Scanning library" in shown
    assert "Extracting metadata" in shown
    # The label and the summary are untouched by the display.
    assert "DRY RUN" in result.stdout
    assert "Dry run complete" in result.stdout
    assert "│ Would index  │     1 │" in result.stdout
    assert "\x1b" not in result.stdout


def test_a_failure_stays_counted_and_readable_under_the_display(
    runner, tmp_path, make_epub, make_corrupt_epub, diagnostic_terminal
):
    """The CLI's own wiring of sink and display, over a library with a bad book."""
    make_epub("library/good.epub", title="Good", author="AA")
    corrupt = make_corrupt_epub("library/broken.epub")

    result = runner.invoke(
        cli,
        ["index", str(tmp_path / "library"), "--database", str(tmp_path / "ebdx.db")],
    )

    shown = diagnostic_terminal.getvalue()
    assert result.exit_code == 0, result.output
    records = [frame for frame in terminal_frames(shown) if "WARNING" in frame]
    assert records, "the warning never reached the terminal"
    assert all(str(corrupt) in frame for frame in records), records
    assert not any("━" in frame for frame in records)
    failed_row = next(line for line in result.stdout.splitlines() if "Failed" in line)
    assert "1" in failed_row


def test_discover_lists_a_bracketed_filename_verbatim(runner, tmp_path, make_epub):
    """Square brackets in a real filename are not markup.

    Rich parses them as tags when a cell is handed over as a string, so
    ``x[dim]y.epub`` would be listed as ``xy.epub`` -- a name that is not the
    name on disk, in the output a user would copy a path out of.
    """
    make_epub("lib/x[dim]y.epub", title="Dim")

    result = runner.invoke(cli, ["discover", str(tmp_path / "lib")])

    assert result.exit_code == 0, result.output
    assert "x[dim]y.epub" in result.output


def test_discover_lists_a_bracketed_parent_directory_verbatim(
    runner, tmp_path, make_epub, monkeypatch
):
    """The path column is as exposed to markup as the filename column.

    The terminal is widened for this one: the path column ellipsizes a long
    ``tmp_path``, and a truncated cell would hide the very thing under test.
    """
    make_epub("lib/[series]/one.epub", title="One")
    monkeypatch.setenv("COLUMNS", "300")

    result = runner.invoke(cli, ["discover", str(tmp_path / "lib")])

    assert result.exit_code == 0, result.output
    assert "[series]" in result.output
