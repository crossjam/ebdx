## Why

Any database recorded below `SCHEMA_VERSION` that holds a `books` table is currently rebuilt
from scratch on open: every table is dropped and recreated empty. That was the right call for
the one layout change so far, the move to path-keyed identity, because rows without a path
could not be carried forward. Applied to every future layout change, though, it means each
new stored field empties the user's library until a full re-index, which over a large network
share is slow (1,904 books locally).

Six queued changes each add a column or table: every author (ydcx), description (2kv2),
author sort names (qedj), file facts and indexed-at (rtaq), cover location (00x2), and EPUB
version and modified date (34k3). This change comes first so none of them has to discard the
library (kata d8dt).

## What Changes

- **Migrations replace the rebuild for known versions.** Opening a database recorded at an
  earlier version this build can migrate from applies, in order, each step between the
  recorded version and `SCHEMA_VERSION`. Every stored book and author, and every row id, is
  kept.
- **Each step is atomic.** A step's changes and its version stamp commit together or not at
  all. An interrupted or failing upgrade leaves the database at the last step that completed,
  never half-migrated, and a later open resumes from there.
- **The rebuild remains for layouts that cannot be migrated.** A database from before
  path-keyed identity (version 0 with a `books` table) is still rebuilt from scratch, and is
  still reported as such. A database recorded at a newer version than this build knows is
  still left untouched.
- **Recognition follows the recorded version.** Today an existing layout is checked against
  the columns the current build writes, so the first added column would make every older
  database "unusable". Instead, a database is checked against the layout expected at the
  version it records.
- **Dry runs predict migrations exactly.** `--dry-run` names each pending migration instead
  of a rebuild, predicts the counts a real `index` would produce with rows kept, and applies
  nothing. A dry-run `search` against a migratable database searches the stored rows rather
  than reporting that the library must be re-indexed.
- **No layout change ships in this change.** `SCHEMA_VERSION` stays at 1 and the migration
  list starts empty. The mechanism is exercised by tests that register steps of their own.
  The first real step arrives with whichever of the six queued changes lands first.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `library-store`: the rebuild requirement narrows to layouts that cannot be migrated, and a
  new requirement covers in-place, step-wise, atomic migration that keeps every row.
- `cli-runtime`: dry-run prediction covers migratable earlier layouts (counts as for a
  current database, pending migrations named, search reads stored rows), with the rebuild
  scenarios limited to layouts that are rebuilt.

## Impact

- `src/ebdx/db.py`: `_ensure_schema` gains the migration path; a per-version view of the
  expected layout replaces the single `_BOOKS_COLUMNS` / `_AUTHORS_COLUMNS` check used by
  `plan_mode`, `unrecognised_structure` and `_missing_schema_columns`;
  `describe_pending_schema_work`, `would_discard_existing_rows`, `would_repair_search` and
  `would_fail_to_open` learn the migrate outcome.
- `src/ebdx/cli.py`: the dry-run `search` branch that reports "must be re-indexed" applies
  only when a rebuild would discard rows.
- `tests/test_db.py`, `tests/test_cli.py`: new tests using a test-registered migration list.
- No new dependencies. No change to any command's options or normal (non-dry-run) output for
  a database already at the current version.
