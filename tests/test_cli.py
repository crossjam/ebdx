"""CliRunner tests for cli-runtime behaviour (cii §5).

Covers log verbosity on the group callback (5.1), the indexing-summary and
search-results table shape (5.2), malformed-query handling (5.3), and the
informational commands with no database present (5.4). Every invocation
passes an explicit ``--database`` under ``tmp_path`` so no test touches the
real user data directory.
"""

from __future__ import annotations

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
    result = runner.invoke(
        cli, ["index", str(tmp_path / "library"), "--database", str(db_path)]
    )
    assert result.exit_code == 0, result.output
    return db_path


# --- 5.1 verbosity -----------------------------------------------------------


def test_no_log_lines_by_default(runner, tmp_path, make_epub):
    db_path = tmp_path / "ebdx.db"
    make_epub("library/a.epub", title="A", author="AA")

    result = runner.invoke(
        cli, ["index", str(tmp_path / "library"), "--database", str(db_path)]
    )

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


# --- 5.2 table shape -------------------------------------------------------


def test_index_summary_reports_updated(runner, tmp_path, make_epub):
    db_path = _index_library(runner, tmp_path, make_epub, [{"title": "A", "author": "AA"}])

    result = runner.invoke(
        cli, ["index", str(tmp_path / "library"), "--database", str(db_path)]
    )

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


def test_search_does_not_render_a_missing_series_index_as_none(
    runner, tmp_path, make_epub
):
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Solo", "author": "One"}]
    )

    result = runner.invoke(cli, ["search", "Solo", "--database", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "None" not in result.output


# --- 5.3 malformed query -------------------------------------------------------


@pytest.mark.parametrize("bad_query", ['"unbalanced', "badcol:Dune"])
def test_malformed_query_exits_nonzero_without_a_traceback(
    runner, tmp_path, make_epub, bad_query
):
    db_path = _index_library(
        runner, tmp_path, make_epub, [{"title": "Dune", "author": "Frank Herbert"}]
    )

    result = runner.invoke(cli, ["search", bad_query, "--database", str(db_path)])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "Invalid search query" in result.output


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
    result = runner.invoke(
        cli, ["schema", "--database", str(tmp_path / "nope.db")]
    )

    assert result.exit_code == 0, result.output
    assert "No database found" in result.output
