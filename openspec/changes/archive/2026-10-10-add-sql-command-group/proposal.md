## Why

The ebdx database is already a useful SQLite library, but inspecting it currently
requires a separate SQLite client or ad-hoc Python.
The existing `schema` command is intentionally a friendly summary; it is not a
general-purpose inspection interface.

The project already depends on `sqlite-utils`, whose read and inspection commands are a
good fit for power users.
Exposing a focused, read-only subset under `ebdx sql` keeps the database path and ebdx
defaults in one place while avoiding a second query language or output implementation.

## What Changes

- Add an `ebdx sql` command group with `--database/-d`, defaulting to ebdx’s default
  database path.
- Forward the read-only sqlite-utils commands `query`, `tables`, `views`, `schema`,
  `rows`, `indexes`, `triggers`, and `dump`.
- Share sqlite-utils' repeated output options (`--nl`, `--arrays`, `--csv`, `--tsv`,
  `--no-headers`, `-t/--table`, `--fmt`, and `--json-cols`) and `--load-extension` in
  decorators so the command declarations stay consistent.
- Open the selected database through ebdx’s read-only connection and enforce SQLite
  query-only mode while sqlite-utils renders the result.
  SQL writes, including writes after `ATTACH`, must fail without changing the database.
- Refuse a missing database without creating it, using the same index hint as the
  existing read commands.
  Report corrupt or non-SQLite files as unusable databases without a traceback.
- Keep the existing top-level `ebdx schema` command as the friendly Rich view and
  explain the relationship in help text.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cli-runtime`: add the read-only SQL inspection group and its database/error behavior.

## Impact

- Affected specs: `cli-runtime`
- Affected code: `src/ebdx/sql.py`, `src/ebdx/cli.py`, and `tests/test_sql.py`
- No schema or data migration; no new dependency.
- The existing database file is never modified by an `ebdx sql` command.
