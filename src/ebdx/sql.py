"""Read-only sqlite-utils commands for the ebdx database."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import click


def _output_options(fn: Callable) -> Callable:
    """Add the output options shared by sqlite-utils inspection commands."""
    decorators = (
        click.option(
            "--json-cols",
            is_flag=True,
            help="Detect JSON columns and output them as JSON, not escaped strings",
        ),
        click.option("--fmt", help="Table format, such as simple or github"),
        click.option("-t", "--table", is_flag=True, help="Output as a formatted table"),
        click.option("--no-headers", is_flag=True, help="Do not output column headers"),
        click.option("--tsv", is_flag=True, help="Output as TSV"),
        click.option("--csv", is_flag=True, help="Output as CSV"),
        click.option("--arrays", is_flag=True, help="Output JSON arrays instead of objects"),
        click.option("--nl", is_flag=True, help="Output newline-delimited JSON"),
    )
    for decorator in decorators:
        fn = decorator(fn)
    return fn


def _load_extension_option(fn: Callable) -> Callable:
    """Add sqlite-utils' repeated extension option."""
    return click.option(
        "--load-extension",
        multiple=True,
        help="Path to a SQLite extension, with an optional :entrypoint",
    )(fn)


def _database(ctx: click.Context) -> Path:
    obj = ctx.find_object(dict)
    if obj is None:
        raise click.UsageError("The sql command must run under the ebdx CLI group.")
    return cast(dict[str, Path], obj)["sql_database"]


def _require_database(database: Path) -> None:
    from ebdx.cli import console

    if database.exists():
        return
    console.print(f"[red]No database found at:[/red] {database}")
    console.print("[yellow]Run 'ebdx index <directory>' to create a database first.[/yellow]")
    raise click.Abort()


def _same_path(path, database: Path) -> bool:
    try:
        return Path(path).resolve() == database.resolve()
    except (TypeError, ValueError):
        return False


def _quote_dump_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return f"X'{value.hex()}'"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return str(value)


def _quote_dump_identifier(identifier: str) -> str:
    return '"{}"'.format(identifier.replace('"', '""'))


def _safe_iterdump(connection: sqlite3.Connection) -> Iterator[str]:
    """Dump SQLite tables without selecting rows from external-content FTS tables.

    Python's ``Connection.iterdump()`` selects from every table, including an
    external-content FTS virtual table. That select is invalid when the FTS
    columns come from a different content table (as they do in ebdx), while
    the SQLite shell correctly dumps the virtual table through its shadow
    tables. Reproduce that small part of the shell behavior here.
    """
    objects = connection.execute(
        "SELECT type, name, tbl_name, rootpage, sql "
        "FROM sqlite_master WHERE sql IS NOT NULL "
        "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 "
        "WHEN 'trigger' THEN 2 WHEN 'view' THEN 3 ELSE 4 END, name"
    ).fetchall()

    yield "PRAGMA foreign_keys=OFF;"
    yield "BEGIN TRANSACTION;"
    virtual_tables = []
    for object_type, name, table_name, rootpage, sql in objects:
        if object_type == "table" and sql.lstrip().upper().startswith("CREATE VIRTUAL TABLE"):
            virtual_tables.append((name, table_name, rootpage, sql))
            continue
        if object_type == "table":
            yield sql.rstrip(";") + ";"
            rows = connection.execute(f"SELECT * FROM {_quote_dump_identifier(name)}")
            for row in rows:
                values = ",".join(_quote_dump_value(value) for value in row)
                yield f"INSERT INTO {_quote_dump_identifier(name)} VALUES({values});"

    if virtual_tables:
        yield "PRAGMA writable_schema=ON;"
        for name, table_name, rootpage, sql in virtual_tables:
            values = ",".join(
                _quote_dump_value(value) for value in ("table", name, table_name, rootpage, sql)
            )
            yield (f"INSERT INTO sqlite_schema(type,name,tbl_name,rootpage,sql)VALUES({values});")

    for object_type, _name, _table_name, _rootpage, sql in objects:
        if object_type in ("index", "trigger", "view"):
            yield sql.rstrip(";") + ";"

    if virtual_tables:
        yield "PRAGMA writable_schema=OFF;"
    yield "COMMIT;"


@contextmanager
def _sqlite_utils_read_only(database: Path) -> Iterator:
    """Make sqlite-utils callbacks use one enforced read-only connection.

    sqlite-utils' Click callbacks open paths themselves. Temporarily replacing
    its Database factory lets those callbacks keep their output and option
    handling while the selected ebdx database remains the connection opened by
    :func:`get_database` in read-only mode.
    """
    import sqlite_utils.cli as sqlite_cli

    from ebdx.cli import _inspect, _open_database

    db = _open_database(database, read_only=True)
    db.execute("PRAGMA query_only = ON")
    original_database = sqlite_cli.sqlite_utils.Database

    def database_factory(path=None, *args, **kwargs):
        if path is not None and _same_path(path, database):
            return db
        return original_database(path, *args, **kwargs)

    setattr(sqlite_cli.sqlite_utils, "Database", database_factory)  # noqa: B010
    try:
        # A read-only connection to a corrupt file can be opened successfully;
        # force the first read through the common friendly error path.
        _inspect(database, db.table_names)
        yield db
    finally:
        sqlite_cli.sqlite_utils.Database = original_database
        db.conn.close()


def _invoke(ctx: click.Context, command_name: str, **kwargs):
    """Invoke one sqlite-utils command against the selected database."""
    import sqlite_utils.cli as sqlite_cli

    database = _database(ctx)
    _require_database(database)
    try:
        with _sqlite_utils_read_only(database) as db:
            if command_name == "dump":
                db.iterdump = lambda: _safe_iterdump(db.conn)
            return ctx.invoke(
                getattr(sqlite_cli, command_name),
                path=str(database),
                **kwargs,
            )
    except click.ClickException:
        raise
    except sqlite3.DatabaseError as error:
        from ebdx.cli import _abort_unusable_database

        _abort_unusable_database(database, error)


@click.group(
    help=(
        "Read-only sqlite-utils inspection commands for the ebdx database. "
        "The default database contains the books and books_fts tables. "
        "Use 'ebdx schema' for the friendly Rich view."
    )
)
@click.option(
    "--database",
    "-d",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Database path (default: ebdx's XDG data-directory database)",
)
@click.pass_context
def sql(ctx: click.Context, database: Path | None):
    """Inspect the ebdx SQLite database without changing it."""
    from ebdx.cli import get_default_db_path

    ctx.ensure_object(dict)["sql_database"] = database or get_default_db_path()


@sql.command()
@click.argument("sql")
@click.option(
    "--attach",
    type=(str, click.Path(file_okay=True, dir_okay=False, allow_dash=False)),
    multiple=True,
    help="Additional database to attach: ALIAS FILEPATH",
)
@click.option("-r", "--raw", is_flag=True, help="Output the first column of the first row")
@click.option("--raw-lines", is_flag=True, help="Output the first column of each row")
@click.option(
    "-p",
    "--param",
    multiple=True,
    type=(str, str),
    help="Named :parameter for the SQL query",
)
@click.option(
    "--functions",
    multiple=True,
    help="Python code or a file defining custom SQL functions",
)
@_load_extension_option
@_output_options
@click.pass_context
def query(
    ctx,
    sql,
    attach,
    raw,
    raw_lines,
    param,
    functions,
    load_extension,
    **output,
):
    """Execute a read-only SQL query."""
    return _invoke(
        ctx,
        "query",
        sql=sql,
        attach=attach,
        raw=raw,
        raw_lines=raw_lines,
        param=param,
        functions=functions,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@click.option("--fts4", is_flag=True, help="Show only FTS4 tables")
@click.option("--fts5", is_flag=True, help="Show only FTS5 tables")
@click.option("--counts", is_flag=True, help="Include row counts")
@click.option("--columns", is_flag=True, help="Include columns")
@click.option("--schema", is_flag=True, help="Include table schemas")
@_load_extension_option
@_output_options
@click.pass_context
def tables(ctx, fts4, fts5, counts, columns, schema, load_extension, **output):
    """List tables in the database."""
    return _invoke(
        ctx,
        "tables",
        fts4=fts4,
        fts5=fts5,
        counts=counts,
        columns=columns,
        schema=schema,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@click.option("--counts", is_flag=True, help="Include row counts")
@click.option("--columns", is_flag=True, help="Include columns")
@click.option("--schema", is_flag=True, help="Include view schemas")
@_load_extension_option
@_output_options
@click.pass_context
def views(ctx, counts, columns, schema, load_extension, **output):
    """List views in the database."""
    return _invoke(
        ctx,
        "views",
        counts=counts,
        columns=columns,
        schema=schema,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@click.argument("tables", nargs=-1)
@_load_extension_option
@click.pass_context
def schema(ctx, tables, load_extension):
    """Show the raw sqlite-utils schema."""
    return _invoke(ctx, "schema", tables=tables, load_extension=load_extension)


@sql.command()
@click.argument("dbtable")
@click.option("-c", "--column", multiple=True, help="Column to return")
@click.option("--where", help="SQL WHERE clause")
@click.option("-o", "--order", help="SQL ORDER BY clause")
@click.option("-p", "--param", multiple=True, type=(str, str), help="Named WHERE parameter")
@click.option("--limit", type=int, help="Maximum number of rows")
@click.option("--offset", type=int, help="Number of rows to skip")
@_load_extension_option
@_output_options
@click.pass_context
def rows(ctx, dbtable, column, where, order, param, limit, offset, load_extension, **output):
    """Output rows from a table."""
    return _invoke(
        ctx,
        "rows",
        dbtable=dbtable,
        column=column,
        where=where,
        order=order,
        param=param,
        limit=limit,
        offset=offset,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@click.argument("tables", nargs=-1)
@click.option("--aux", is_flag=True, help="Include auxiliary index columns")
@_load_extension_option
@_output_options
@click.pass_context
def indexes(ctx, tables, aux, load_extension, **output):
    """Show indexes in the database."""
    return _invoke(
        ctx,
        "indexes",
        tables=tables,
        aux=aux,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@click.argument("tables", nargs=-1)
@_load_extension_option
@_output_options
@click.pass_context
def triggers(ctx, tables, load_extension, **output):
    """Show triggers in the database."""
    return _invoke(
        ctx,
        "triggers",
        tables=tables,
        load_extension=load_extension,
        **output,
    )


@sql.command()
@_load_extension_option
@click.pass_context
def dump(ctx, load_extension):
    """Dump the database as SQL without changing it."""
    return _invoke(ctx, "dump", load_extension=load_extension)
