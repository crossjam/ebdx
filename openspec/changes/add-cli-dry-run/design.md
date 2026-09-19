## Context

See proposal.md — Why. The constraint that shapes everything here is that the mutation in
`search` and `schema` happens on *open*, not in the query: `get_database` calls
`_ensure_schema`, which creates missing tables, stamps `PRAGMA user_version`, and drops,
recreates, and repopulates `books_fts` when it finds that index missing or not FTS5. A
`if dry_run: return` at the top of each command body would therefore still let a database
be repaired or stamped on the way in. `index` mutates in the obvious places as well:
`_ensure_data_dir` creates the XDG directory and `save_book` writes a row per EPUB, each
firing the `books_au`/`books_ai` triggers.

`discover`, `about`, and `version` are already read-only; `about` only computes paths.

## Goals / Non-Goals

**Goals:**

- One place decides whether a run is a dry run, and every command sees the same answer.
- The read-only guarantee is enforced by SQLite, not by our own branching, so a future
  write path added under `--dry-run` fails loudly instead of silently mutating.
- Dry-run counts are the counts a real run would produce, not estimates.

**Non-Goals:**

- A dry run for deletion. No command deletes book rows today.
- A per-subcommand `--dry-run`. Settled: group position only, matching `-v`/`-q`.
- Dry-run coverage of an availability sweep, which does not exist yet; when it lands it
  should consume the propagation built here rather than adding its own.

## Decisions

**Propagate on `ctx.obj`, set in the group callback.** The group callback already exists
and already centralizes cross-cutting setup (`_configure_logging`). It sets
`ctx.ensure_object(dict)["dry_run"]`, and subcommands take `@click.pass_context`.
Alternative considered: a module-level global. Rejected — it makes the `CliRunner` tests
order-dependent, and the existing `_restore_loguru` fixture is already evidence of how
much that costs.

**Group position only.** Click requires group options before the subcommand, so
`ebdx --dry-run index ~/books` parses and `ebdx index ~/books --dry-run` does not.
Alternative considered: define `--dry-run` on both the group and each subcommand and merge
the two values. Rejected — it doubles the definition, creates a "which one wins" question
when both are given, and the codebase already asks the user to put `-v`/`-q` in group
position. The ordering is documented in the option's help text instead.

**`get_database(path, read_only=True)` does both halves.** It skips `_ensure_schema` *and*
opens through `sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)`, handing the
resulting connection to `sqlite_utils.Database`. The URI is built with `as_uri()` rather
than by interpolating the path: a filename containing `?`, `#` or `%` is URI syntax, and a
`?` in particular truncates the path and drops `mode=ro`, handing back a writable
connection to a different file. Confirmed with a database named `lib?x.db`, where the
interpolated form accepted `CREATE TABLE`. Skipping the schema call alone would leave
correctness resting on our own branching; the read-only connection makes SQLite enforce it.
Verified against the real library: reads work through `sqlite_utils` on such a connection
(`select count(*) from books` → 74), while `UPDATE books ...` and `PRAGMA user_version = 99`
both raise `OperationalError: attempt to write a readonly database`. That is what lets the
spec say writes are refused by the engine rather than by convention.

**Dry-run `index` classifies by reading `books.path`.** Whether a file would be inserted or
updated is answerable from the existing rows, which needs only read access, so the reported
counts match what a real run would do. Extraction still happens — it is a read — so failure
counts stay accurate rather than being guessed.

A missing `books.path` is not one situation but four, and they do not share an outcome, so
`plan_mode` predicts which one applies by mirroring `_ensure_schema` and `save_book`
between them:

| database state | real run | dry run |
| --- | --- | --- |
| current version, keyed by `path` | compares against existing rows | `compare` |
| below `SCHEMA_VERSION`, or no `books` yet | rebuilds, inserts everything | `insert-all` |
| at `SCHEMA_VERSION`, `books` lacks `path` | aborts building the schema objects | `abort` |
| above `SCHEMA_VERSION`, `books` lacks `path` | left alone; every write fails | `fail-all` |

Collapsing the last two into `insert-all` — the first attempt — made the dry run promise
successful inserts for runs that cannot succeed: verified that a real `index` against the
third state aborts with "Not a usable ebdx database" and against the fourth reports every
file failed. Tests assert `plan_index` equals `scan_and_index` for the rebuild and
`fail-all` states, and that the dry run aborts without printing a summary for the `abort`
state, so the prediction is pinned to the behavior rather than to my reading of it.

Keeping `plan_mode` in step with `_ensure_schema` and `save_book` is the standing cost of
this approach; its docstring says so, and the equality tests are what would catch a drift.

## Risks / Trade-offs

**A read-only open of a missing file raises instead of returning an empty database.**
Verified: `sqlite3.connect("file:/nope.db?mode=ro", uri=True)` raises
`OperationalError: unable to open database file`. Since `OperationalError` is a
`DatabaseError`, `_open_database` would turn that into "Cannot open database / Not a usable
ebdx database" — the wrong message for a database that simply is not there yet. → Mitigated
by the existing order of checks: `search` and `schema` both test `Path(database).exists()`
and print the "No database found at: … run `ebdx index`" message before opening. The new
failure mode is only reachable if that guard is removed, so the tests pin the friendly
message under `--dry-run` as well.

**A dry run of `index` on a fresh location cannot open a database at all**, because there is
no file and it must not create one. → Report the would-create facts (data directory,
database file, schema) from path existence alone, and classify every discovered EPUB as a
would-be insert, which is correct when no store exists.

**`--dry-run` and `--quiet` interact.** The dry-run report is a result, not a log, so it
goes through Rich and stays visible under `--quiet`, consistent with the rule established
when `--quiet` was fixed. → Covered by an explicit test.

## Migration Plan

Additive and default-off: without the flag every command behaves exactly as today. No
database migration, no dependency change — `mode=ro` is stock `sqlite3`. Rollback is
removing the option.
