## Context

`sqlite_utils.cli` exposes Click commands that open a path themselves with a normal,
writable SQLite connection.
Calling those commands directly would violate the read-only promise of `ebdx sql query`:
sqlite-utils deliberately supports statements that modify a database.

ebdx already has the required primitives.
`get_database(path, read_only=True)` opens a SQLite URI in `mode=ro` and skips schema
setup, while the returned sqlite-utils Database object provides the same interface used
by sqlite-utils' command callbacks.

## Decisions

### Reuse sqlite-utils callbacks and output formatting

Each ebdx subcommand declares the options relevant to its sqlite-utils counterpart and
invokes that command’s Click callback with `ctx.invoke`. A small context manager
supplies ebdx’s already-open read-only Database whenever the callback opens the selected
path. The original sqlite-utils factory is restored immediately after the callback, so
the adapter does not change sqlite-utils behavior outside the command invocation.

The database option is declared on both the group and each subcommand.
This accepts the natural `ebdx sql --database library.db query ...` form as well as
`ebdx sql query --database library.db ...`, while a subcommand-level value takes
precedence when both are supplied.

This preserves sqlite-utils' JSON, JSONL, CSV, TSV, table, and schema formatting,
including its parameter handling and quoting behavior, without copying that
implementation into ebdx.

### Defense in depth for writes

The main database is opened with SQLite `mode=ro`, and the connection also sets
`PRAGMA query_only = ON`. `mode=ro` prevents writes to the ebdx database; `query_only`
also prevents a query from attaching another writable database and then writing to it.
The command group does not expose sqlite-utils' mutating subcommands.

### Missing and unusable databases

The group checks that the selected path exists before opening it.
A missing path reports that `ebdx index <directory>` creates the database and does not
create a file. The first read against an existing path is performed before forwarding to
sqlite-utils, so a corrupt or non-SQLite file is routed through
`_abort_unusable_database` rather than escaping as a traceback.

### Relationship with `ebdx schema`

The existing command remains unchanged: it is the human-oriented Rich inspection view.
`ebdx sql schema` is the sqlite-utils-compatible raw schema view and belongs to the SQL
group’s composable, machine-oriented interface.

## Out of Scope

- Mutating sqlite-utils commands such as `insert`, `update`, `transform`, `drop-table`,
  `vacuum`, or `analyze-tables --save`.
- The sqlite-utils `search`, `memory`, and `plugins` commands; they are separate
  decisions recorded by the coordinating issue.
- A new output format or a `--format` option for the existing ebdx commands.
