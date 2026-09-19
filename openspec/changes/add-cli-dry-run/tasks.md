## 1. Read-only store access

- [ ] 1.1 Add a `read_only` parameter to `get_database` in `src/ebdx/db.py` that opens via
      `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` and hands the connection to
      `sqlite_utils.Database`, skipping `_ensure_schema` entirely; verify a read-only open
      of an intact database returns the same `search_books` results as an ordinary open.
- [ ] 1.2 Add `tests/test_db.py` coverage that a read-only open of a database whose
      `books_fts` was dropped or replaced by an ordinary table performs no repair; verify
      `sqlite_master` and `PRAGMA user_version` are byte-identical before and after.
- [ ] 1.3 Add `tests/test_db.py` coverage that a read-only open of a `user_version` 0
      database is not rebuilt, and that a write through a read-only open raises
      `sqlite3.OperationalError`; verify both assertions pass.

## 2. Flag propagation

- [ ] 2.1 Add `--dry-run` to the `cli` group callback in `src/ebdx/cli.py`, storing it on
      `ctx.obj` via `ctx.ensure_object(dict)`, with help text noting it precedes the
      command; verify `ebdx --help` lists it and `ebdx --dry-run version` exits 0.
- [ ] 2.2 Take `@click.pass_context` on `index`, `search`, and `schema` and read the flag;
      verify `discover`, `about`, and `version` are untouched by inspection and that their
      existing tests still pass.

## 3. Dry-run behavior per command

- [ ] 3.1 Under `--dry-run`, make `search` and `schema` open read-only and skip
      `_ensure_data_dir`, keeping the existing "No database found at …" guard ahead of the
      open; verify the friendly message still appears for a missing database.
- [ ] 3.2 Under `--dry-run`, make `index` skip `_ensure_data_dir` and perform no write,
      instead classifying each discovered EPUB as a would-be insert or update by reading
      `books.path`; verify counts match those of an equivalent real run.
- [ ] 3.3 Report would-create facts for the data directory, database file, and schema when
      they are absent, and label all dry-run output as a dry run; verify the summary table
      is distinguishable from a real run's.

## 4. CLI acceptance tests

- [ ] 4.1 In `tests/test_cli.py`, assert `ebdx --dry-run index <lib>` against a
      not-yet-existing default location creates no data directory and no database file and
      says both would be created; use `ebdx.scanner.iter_files` for the filesystem
      assertion rather than globs.
- [ ] 4.2 Assert `ebdx --dry-run index <lib>` against an existing database leaves the
      `books` row count, `PRAGMA user_version`, and the file mtime unchanged while listing
      each file as a would-be insert or update.
- [ ] 4.3 Assert `ebdx --dry-run search` and `ebdx --dry-run schema` against a database
      whose `books_fts` was dropped or replaced perform no repair, and the same against a
      `user_version` 0 database; verify `sqlite_master` and `PRAGMA user_version` are
      unchanged. This is the assertion most likely to fail a first implementation.
- [ ] 4.4 Assert `--dry-run` changes nothing for `discover`, `about`, and `version`, and
      that dry-run output is still shown under `--quiet`.

## 5. Close out

- [ ] 5.1 Run `poe qa` (lint, type, test) and `poe format:check`; verify all pass.
- [ ] 5.2 Smoke-test `ebdx --dry-run index /mnt/tank/data/eBooks` against a copy of a real
      indexed database; verify row count, `user_version`, and mtime are unchanged.
