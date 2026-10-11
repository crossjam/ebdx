## Why

The first `ebdx sql` slice exposes read-only inspection commands, but it omits two
useful sqlite-utils capabilities: full-text search and column analysis.
Both can run against the existing ebdx database without changing it when the mutating
analysis save option is disabled.

The remaining sqlite-utils commands in the follow-up issue do not fit this command
group. `memory` operates on imported files and an in-memory database rather than the
selected ebdx database, while `plugins` reports the local sqlite-utils environment
rather than inspecting library data.

## What Changes

- Add `ebdx sql search` as a raw sqlite-utils FTS search command, including its output,
  ordering, column, limit, quoting, and SQL-preview options.
- Add `ebdx sql analyze-tables` for read-only column analysis, deliberately omitting
  sqlite-utils' `--save` option so it cannot create `_analyze_tables` in the library.
- Document the two commands and the deliberate exclusions of `memory` and `plugins`.
- Add CLI tests covering useful output and the read-only analysis behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cli-runtime`: extend the read-only SQL inspection group with search and table
  analysis.

## Impact

- Affected specs: `cli-runtime`
- Affected code: `src/ebdx/sql.py`, `tests/test_sql.py`, and `README.md`
- No new dependency and no database schema or data migration.
