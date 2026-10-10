## 1. Open the read-only SQL group

- [x] 1.1 Add `ebdx sql --database/-d` with the default ebdx database path, accept the
  option after a subcommand too, and add help text describing the `books` and
  `books_fts` tables.
- [x] 1.2 Add shared output and `--load-extension` decorators plus wrappers for `query`,
  `tables`, `views`, `schema`, `rows`, `indexes`, `triggers`, and `dump`.
- [x] 1.3 Reuse the existing top-level database path and unusable-database helpers.

## 2. Enforce read-only behavior

- [x] 2.1 Route the selected database through `get_database(read_only=True)` and SQLite
  `query_only` while invoking sqlite-utils callbacks.
- [x] 2.2 Refuse a missing database without creating it and report the standard index
  hint.
- [x] 2.3 Reject a write query, including an `ATTACH` followed by a write, and verify
  the database file is unchanged.
- [x] 2.4 Report a corrupt or non-SQLite database without a traceback.

## 3. Tests and documentation

- [x] 3.1 Test every subcommand’s default output against a temporary indexed library.
- [x] 3.2 Test one alternate output mode, parameterized `query`, and the
  missing-database path.
- [x] 3.3 Test the rejected write and byte/database-content preservation.
- [x] 3.4 Clarify in the CLI help and README that `ebdx schema` is the friendly view and
  `ebdx sql schema` is the raw sqlite-utils-compatible view.
