"""Tests for the read-only ``ebdx sql`` command group."""

from __future__ import annotations

import sqlite3

import pytest
from click.testing import CliRunner

from ebdx.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _index_library(runner, tmp_path, make_epub):
    make_epub("library/dune.epub", title="Dune", author="Frank Herbert")
    database = tmp_path / "library.db"
    result = runner.invoke(
        cli,
        ["index", str(tmp_path / "library"), "--database", str(database)],
    )
    assert result.exit_code == 0, result.output
    return database


def _sql(runner, database, *args):
    return runner.invoke(cli, ["sql", "--database", str(database), *args])


def test_sql_inspection_commands_use_the_indexed_database(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)

    commands = [
        ["tables"],
        ["views"],
        ["schema"],
        ["rows", "books"],
        ["indexes"],
        ["triggers"],
        ["dump"],
        ["query", "select title from books"],
    ]
    results = [_sql(runner, database, *command) for command in commands]

    assert all(result.exit_code == 0 for result in results), [
        result.output for result in results if result.exit_code
    ]
    assert "books" in results[0].output
    assert "books_fts" in results[0].output
    assert "Dune" in results[3].output
    assert "CREATE TABLE" in results[5].output or "CREATE TRIGGER" in results[5].output
    assert "Dune" in results[-1].output


def test_sql_query_supports_csv_and_named_parameters(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)

    csv_result = _sql(runner, database, "query", "--csv", "select title from books")
    parameter_result = _sql(
        runner,
        database,
        "query",
        "-p",
        "title",
        "Dune",
        "select title from books where title = :title",
    )

    assert csv_result.exit_code == 0, csv_result.output
    assert csv_result.output.splitlines() == ["title", "Dune"]
    assert parameter_result.exit_code == 0, parameter_result.output
    assert "Dune" in parameter_result.output


def test_sql_search_supports_raw_fts_queries_and_output_options(runner, tmp_path, make_epub):
    make_epub("library/dune.epub", title="Dune", author="World")
    make_epub("library/dune-world.epub", title="Dune World", author="Frank Herbert")
    database = tmp_path / "library.db"
    result = runner.invoke(
        cli,
        ["index", str(tmp_path / "library"), "--database", str(database)],
    )
    assert result.exit_code == 0, result.output

    unquoted = _sql(
        runner,
        database,
        "search",
        "books",
        "Dune OR World",
        "--csv",
        "--column",
        "title",
    )
    quoted = _sql(
        runner,
        database,
        "search",
        "--quote",
        "books",
        "Dune OR World",
        "--csv",
        "--column",
        "title",
    )

    assert unquoted.exit_code == 0, unquoted.output
    assert set(unquoted.output.splitlines()[1:]) == {"Dune", "Dune World"}
    assert quoted.exit_code == 0, quoted.output
    assert quoted.output.splitlines() == ["title"]


def test_sql_analyze_tables_does_not_save_results(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)

    result = _sql(runner, database, "analyze-tables", "books")

    assert result.exit_code == 0, result.output
    assert "title" in result.output
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "select 1 from sqlite_master where name = '_analyze_tables'"
            ).fetchone()
            is None
        )


def test_sql_excludes_non_database_extras(runner):
    result = runner.invoke(cli, ["sql", "--help"])

    assert result.exit_code == 0, result.output
    assert "search" in result.output
    assert "analyze-tables" in result.output
    assert "memory" not in result.output
    assert "plugins" not in result.output


def test_sql_database_option_works_after_the_subcommand(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)

    schema = runner.invoke(cli, ["sql", "schema", "--database", str(database)])
    query = runner.invoke(
        cli,
        ["sql", "query", "--csv", "--database", str(database), "select title from books"],
    )

    assert schema.exit_code == 0, schema.output
    assert "CREATE TABLE" in schema.output
    assert query.exit_code == 0, query.output
    assert query.output.splitlines() == ["title", "Dune"]


def test_sql_dump_restores_non_finite_float_values(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)
    with sqlite3.connect(database) as connection:
        connection.execute("create table special_numbers (value real)")
        connection.execute("insert into special_numbers values (?)", (float("inf"),))

    result = _sql(runner, database, "dump")
    restored = tmp_path / "restored.db"
    with sqlite3.connect(restored) as connection:
        connection.executescript(result.output)
        value = connection.execute("select value from special_numbers").fetchone()[0]

    assert result.exit_code == 0, result.output
    assert value == float("inf")


def test_sql_query_rejects_writes_without_changing_the_database(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)
    before = database.read_bytes()

    result = _sql(runner, database, "query", "delete from books")

    assert result.exit_code != 0
    assert "readonly" in result.output.lower()
    assert database.read_bytes() == before


def test_sql_query_rejects_writes_to_an_attached_database(runner, tmp_path, make_epub):
    database = _index_library(runner, tmp_path, make_epub)
    attached = tmp_path / "attached.db"
    with sqlite3.connect(attached) as connection:
        connection.execute("create table records (value text)")

    result = _sql(
        runner,
        database,
        "query",
        "--attach",
        "other",
        str(attached),
        "insert into other.records values ('changed')",
    )

    assert result.exit_code != 0
    assert "readonly" in result.output.lower()
    with sqlite3.connect(attached) as connection:
        assert connection.execute("select count(*) from records").fetchone()[0] == 0


def test_sql_missing_database_does_not_create_a_file(runner, tmp_path):
    database = tmp_path / "missing.db"

    result = _sql(runner, database, "tables")

    assert result.exit_code != 0
    assert "No database found" in result.output
    assert "ebdx index" in result.output
    assert not database.exists()


def test_sql_non_sqlite_file_is_reported_without_traceback(runner, tmp_path):
    database = tmp_path / "not-sqlite.db"
    database.write_text("not a SQLite database")

    result = _sql(runner, database, "schema")

    assert result.exit_code != 0
    assert "Not a usable ebdx database" in result.output
    assert "Traceback" not in result.output
