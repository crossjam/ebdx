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

    result = runner.invoke(cli, ["search", bad_query, "--database", str(db_path)])

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
