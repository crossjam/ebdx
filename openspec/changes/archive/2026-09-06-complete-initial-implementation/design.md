## Context

See proposal.md — Why. The relevant current state for this design:

- `db.py` builds the schema with `Table.create(..., replace=True)`, which is `DROP TABLE` + `CREATE TABLE` on every open. `_ensure_schema` runs from `get_database`, so every command wipes the library.
- The FTS5 table is external-content (`content="books"`, `content_rowid="id"`) with three triggers keeping it in step. That part is sound and is kept.
- `books` has no path column. `save_book` always `insert`s, so identity is "whatever row got written last".
- The virtualenv resolves `sqlite_utils` 4.x on SQLite 3.49.1. Two behaviors of that version shape the design and were verified directly:
  - `Table.upsert()` raises `PrimaryKeyRequired` unless the primary key value is supplied. It cannot key on a non-pk unique column.
  - `Table.lookup()` is already get-or-create and idempotent, so the `try/except KeyError` around it in `save_book` is dead code.
- `loguru` is imported and used but never configured, so its default DEBUG-to-stderr sink is live. `extractor.py` logs one DEBUG line per book and `db.py` one INFO line per open.

## Goals / Non-Goals

**Goals:**

- Schema creation that is safe to run on every open, with a version marker so a stale layout is detected rather than half-used.
- One stable identity rule — absolute path — used by both the store and the indexer.
- Test coverage that would have caught the wipe bug, built on a fixture that generates real EPUBs rather than checking binaries into the repo.

**Non-Goals:**

- No migration machinery. This is pre-release; version mismatch means rebuild.
- No abstraction layer over `sqlite_utils`. The store stays a module of functions taking a `Database`.
- No concurrency story. One process at a time against a database file.
- Beyond the proposal's non-goals: no attempt to make `save_book` handle partial metadata dicts from sources other than `extract_metadata`.

## Decisions

### Path-keyed identity via select-then-write, not `upsert()`

`books` keeps its autoincrement integer `id` (the FTS5 `content_rowid` must be an integer) and gains `path TEXT NOT NULL` with a unique index. Saving a book looks the path up first, then `update`s the found id or `insert`s a new row.

*Why not `upsert()`:* it requires the pk value, which the caller does not have — that is the thing being looked up. Verified: `PrimaryKeyRequired: upsert() requires a value for the primary key column: id`.

*Why not `path` as the primary key:* external-content FTS5 needs an integer `content_rowid`; a TEXT pk leaves only the implicit rowid, which is not stable across a `VACUUM`.

*Why not `INSERT OR REPLACE`:* it deletes and reinserts, so the book's id churns on every re-index and the FTS delete/insert trigger pair runs needlessly.

The select-then-write pattern was verified to keep ids stable across re-saves and to fire exactly one insert or update trigger per save, which is what the FTS sync depends on.

### Schema versioning through `PRAGMA user_version`

`_ensure_schema` reads `PRAGMA user_version`. `0` on a non-empty database means the pre-path layout: drop the books, authors, FTS, and trigger objects and rebuild. A version below the current constant is treated the same way. At the current version it does nothing but the `if_not_exists` creates. A fresh file gets the schema and the version stamped.

*Why not sniff for the `path` column:* it answers one question. A version integer covers the next schema change too, and `user_version` needs no table of its own. Verified to round-trip across reopen.

*Why rebuild rather than `ALTER TABLE ADD COLUMN`:* a backfilled `path` would have to be invented for rows that never recorded one, and a unique index cannot be added over the resulting duplicates. Re-running `index` is cheap and correct.

### Absolute, resolved paths

The scanner passes `Path.resolve()` output to the store. Without it, indexing `.` and then `~/books` records the same file twice under different spellings and the unique index does not catch it. This makes the stored path the canonical one, which is also what search results print.

### Logging configured at the group callback

The `cli` group callback removes loguru's default sink and installs one at a level chosen by `-v/--verbose` / `-q/--quiet` (default WARNING, verbose INFO, quiet ERROR). Rich `console.print` output is unaffected — it carries command results, which are not logs and stay visible even under `--quiet`.

*Why the group callback rather than module import time:* the level depends on parsed options, and configuring at import would fire during tests that import `db` or `extractor` directly.

*Why not swap loguru for `logging`:* it is already a declared dependency and used throughout; replacing it is scope the proposal did not ask for.

### Scanner reports indexed vs updated

`save_book` returns whether it inserted or updated so the scanner can keep separate counts. The alternative — having the scanner query for existence itself — duplicates the lookup the store already performs.

### EPUB fixtures are generated, not committed

A `tests/conftest.py` helper builds minimal valid EPUBs with `ebooklib`'s writer at known metadata values, into `tmp_path`. Corrupt-file cases are a text file renamed `.epub`.

*Why not commit sample EPUBs:* real books carry licensing questions, and generated fixtures let a test state the exact metadata it depends on. The risk — that `ebooklib`'s writer produces something its reader accepts but real EPUBs differ from — is accepted for this change; the extractor is exercised against the same library either way.

CLI tests use Click's `CliRunner` with an explicit `--database` under `tmp_path`, so no test touches the real user data directory. The wipe regression gets a dedicated test: save, close, reopen, assert the book is still there.

## Risks / Trade-offs

- **A user's existing `ebdx.db` is silently rebuilt on first run** → It provably could not hold data across a restart, so nothing real is lost. The rebuild is logged at INFO, visible under `--verbose`.
- **Re-indexing re-reads every EPUB, since there is no mtime check** → Accepted per the proposal's non-goals. On a large library this is slow but correct; mtime/size skipping is a clean follow-up because path identity is already in place.
- **Resolved paths make records sensitive to how a library is mounted** → Moving or remounting a library orphans its rows, and re-indexing creates a second set under the new paths. No pruning of missing files is in scope, so the store can accumulate stale rows.
- **`series` stays effectively always empty** → Out of scope by decision. Tests assert observed behavior, so the gap is recorded rather than hidden, and fixing it later will not require a schema change.
- **Unique index creation fails if a rebuild is ever skipped while duplicate paths exist** → The version check runs before the index is created, so the rebuild path clears duplicates first.
- **FTS5 correctness rests on trigger coverage** → The three triggers are covered by tests asserting a title is findable after insert, changed after update, and gone after delete.

## Migration Plan

No deployment step. On first run against an existing database the schema is rebuilt automatically; the user re-runs `ebdx index <directory>`. Rollback is reverting the commit — an older build against a new-schema database drops and recreates the tables on open, which is what it did to every database anyway.
