## Why

Every `ebdx` command that touches the library can change it, and two of them do so in ways a
user would not predict: `search` and `schema` look like reads, but both open the database
through `get_database`, and `_ensure_schema` is not read-only — it creates missing tables,
stamps `PRAGMA user_version`, and drops, recreates, and repopulates a `books_fts` it finds
missing or not an FTS5 table. A user pointing `ebdx` at an unfamiliar or precious database
has no way to find out what a command would do without letting it do it.

## What Changes

- Add a global `--dry-run` flag on the `ebdx` group, alongside `-v/--verbose` and
  `-q/--quiet`. Under it, commands report the state changes they would make, make none, and
  exit 0.
- Accept the flag only in group position (`ebdx --dry-run index ~/books`), matching how
  `-v`/`-q` already parse. The ordering is documented in the help text rather than worked
  around with a second per-subcommand option.
- Give `get_database` a `read_only` mode that both skips `_ensure_schema` and opens the
  file through SQLite's `mode=ro` URI, so a stray write raises instead of quietly
  succeeding. This is what makes a dry run of `search` and `schema` honest: their
  mutation happens on open, not in the query.
- Under `--dry-run`, `index` reports per file whether it would be inserted or updated, and
  whether the data directory, the database file, or the schema would be created; it creates
  no data directory and writes no rows. Extraction failures stay accurate, since extracting
  is itself a read.
- Mark dry-run output clearly so its summary cannot be mistaken for a real run.
- `discover`, `about`, and `version` are already read-only and are unaffected.

## Capabilities

### New Capabilities
<!-- None: this extends existing CLI and store behavior rather than introducing a new capability. -->

### Modified Capabilities
- `cli-runtime`: adds the global `--dry-run` option and the requirement that, under it, no
  command creates or modifies the data directory, the database file, or its schema, while
  still reporting what it would have done and exiting 0.
- `library-store`: adds a read-only open mode that performs no schema creation, version
  stamping, or FTS repair, and under which writes are refused by SQLite rather than by
  convention.

## Impact

- `src/ebdx/cli.py`: group callback grows `--dry-run` and carries it on `ctx.obj`;
  subcommands take `@click.pass_context`. `index`, `search`, and `schema` branch on it;
  `_ensure_data_dir` is not called under it.
- `src/ebdx/db.py`: `get_database` grows a `read_only` parameter; a read-only connection
  path that bypasses `_ensure_schema`.
- `tests/test_cli.py`: `CliRunner` coverage for each acceptance criterion, with filesystem
  assertions using `ebdx.scanner.iter_files` rather than globs.
- No dependency changes; `mode=ro` is stock `sqlite3`.
- Unblocks a dry-run availability sweep when the missing-file flagging work lands, which
  should reuse this propagation rather than adding its own.
