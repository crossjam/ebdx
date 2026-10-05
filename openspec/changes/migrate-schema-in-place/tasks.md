## 1. Migration model

- [x] 1.1 Add `AddedColumn` metadata for type, nullability and default, plus the `Migration` NamedTuple with an idempotent `ensure_schema` callback; add an empty `_MIGRATIONS` tuple and `_BASE_VERSION = 1`, derive `SCHEMA_VERSION` from them, and assert contiguous targets at import. Verify `SCHEMA_VERSION` is still 1 and the full suite passes unchanged.
- [x] 1.2 Document the step-author rules in the `Migration` docstring: raw `db.execute` only, complete added-column metadata, an idempotent `ensure_schema` callback for fresh/current schema objects, no sqlite-utils helpers that open their own transaction, and drop the index via `_drop_fts` plus `rebuilds_search=True` when a step changes what the index reads. Verify by review.
- [x] 1.3 Add a `with_migrations` fixture to `tests/conftest.py` that patches `_MIGRATIONS`, `SCHEMA_VERSION`, the current column maps and, when asked, `_FTS_COLUMNS` together. Verify with a smoke test that the patched version and layout are visible inside the test and restored after it.

## 2. Structural recognition per version

- [x] 2.1 Add a helper giving the expected books/authors columns at a version (the current layout minus what later steps add), and make `_missing_schema_columns` take the recorded version. Verify with a test that a version-1 layout lacking only a test step's column is not reported missing, while one lacking a version-1 column still is.
- [x] 2.2 Route `plan_mode`, `unrecognised_structure` and `would_fail_to_open` through the per-version check. Verify with a test that a migratable database plans as `compare` rather than `unusable`.

## 3. Applying migrations on open

- [x] 3.1 Narrow the rebuild branch of `_ensure_schema` to `version < _BASE_VERSION` with a `books` table. Verify the existing pre-path rebuild tests still pass.
- [x] 3.2 Add the upgrade loop: for each pending step, `BEGIN IMMEDIATE`, apply, stamp `user_version = target`, `COMMIT`, rolling back on error and re-raising. Run it before the index repair and `_create_schema`. Verify with a test that a single test step adding a column migrates a populated version-1 database, keeping every book, author and row id.
- [x] 3.3 Verify multi-step ordering: two test steps whose second depends on the first apply in order from version 1, and a database already at the intermediate version applies only the second.
- [x] 3.4 Verify atomicity and resume: a step whose second statement fails leaves `user_version` at the start version and none of its first statement's effect. After swapping in a working step, the next open completes the upgrade.
- [x] 3.5 Verify the search-index path: a test step that adds an indexed column and drops `books_fts` leaves, after open, an index with the new column that returns every previously matching book and matches the new column once a book is re-saved with a value. Inject a refill failure after recreation and verify the repair rolls back so a later open retries it.
- [x] 3.6 Verify added fields fill on re-index: after migrating, `ebdx index` over the same library populates the test step's column for every file, and before re-indexing it holds the empty default.
- [x] 3.7 Verify a read-only open of a migratable database applies nothing: tables, columns, triggers and `user_version` are unchanged.
- [x] 3.8 Verify fresh and migratable partial databases create migration-owned objects and match the added columns' nullability/defaults; a partial database without `books` gets its missing core tables at the recorded layout before its steps apply.

## 4. Dry-run prediction

- [x] 4.1 Make `describe_pending_schema_work` list each pending step (`apply migration to version N: <description>`) ahead of the existing repair lines, and narrow `would_discard_existing_rows` to the rebuild case. Verify with unit tests for both.
- [x] 4.2 Make `would_repair_search` true when a pending step has `rebuilds_search`. Verify with a unit test.
- [x] 4.3 Verify `ebdx --dry-run index` against a migratable database reports the same insert/update counts as the real run, names each pending migration, and leaves the file's mtime, `user_version` and layout unchanged.
- [x] 4.4 Verify `ebdx --dry-run search` against a migratable database shows results from the stored rows, notes the pending migrations, and does not print the "must be re-indexed" message. A `--fts` query on a column only the pending step adds reports "cannot run until that happens" and exits 0.
- [x] 4.5 Verify `ebdx --dry-run schema` against a migratable database leaves it unchanged and lists the pending migrations.

## 5. Wrap-up

- [x] 5.1 Update the `_ensure_schema`, `plan_mode` and `describe_pending_schema_work` docstrings and the `SCHEMA_VERSION` comment to describe migrate-versus-rebuild. Verify by review.
- [x] 5.2 Run `uv run pytest`, `uv run ruff check src tests` and `uv run ruff format --check src tests` and confirm all pass. Confirm `openspec validate migrate-schema-in-place --strict` passes.
