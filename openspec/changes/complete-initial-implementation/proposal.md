## Why

`ebdx` looks finished — six commands, an FTS5 schema, an EPUB extractor — but it does not work end to end. `_ensure_schema()` calls `db["books"].create(..., replace=True)` on every `get_database()` call, so opening the database drops and recreates `books` and `authors`. Indexing a library in one process and searching it in the next returns nothing:

```
$ ebdx index ~/books     # 120 successfully indexed
$ ebdx search Dune       # No results found.
```

Nothing else in the tool can be trusted until persistence works: `books` has no column recording which file a row came from, so rows cannot be deduplicated, updated, or traced back to an EPUB, and re-running `index` in a single process appends duplicates. Test coverage is a single `assert True` placeholder, so none of this was caught. This change makes the initial implementation actually deliver what the CLI already advertises.

## What Changes

- **BREAKING** (schema, pre-release): `books` gains a `path TEXT NOT NULL UNIQUE` column holding the absolute EPUB path. Existing `ebdx.db` files predate a working index and are recreated rather than migrated.
- Stop recreating tables on open. Schema creation becomes idempotent (`if_not_exists`), so data survives across processes and repeated `get_database()` calls.
- `index` becomes idempotent per file: a book is keyed by its absolute path and re-indexing upserts that row instead of inserting a duplicate. Indexing summary reports indexed / updated / failed.
- FTS5 rows stay consistent with `books` across insert, update, and delete, including for upserts.
- `search` results include the source path so a hit can be located on disk.
- Logging is configured explicitly: loguru currently emits DEBUG to stderr with no setup. Default becomes quiet (warnings and errors), with `-v/--verbose` and `-q/--quiet` on the `ebdx` group.
- Replace `tests/test_placeholder.py` with real coverage of the extractor, database, scanner, and CLI, including a generated EPUB fixture and a regression test for the reopen-loses-data bug.
- Write the empty `README.md` (install, usage, examples) and delete the stale `hello()` stub in `src/ebdx/__init__.py` left over from `uv init`.

Non-goals (deliberately deferred, not oversights):

- Series extraction stays as written. `get_metadata("OPF", "series")` does not match Calibre's `<meta name="calibre:series" content="…">`, so `series` is usually empty. Out of scope by decision; tests assert current behavior rather than the fix.
- No change detection by mtime/size — re-indexing re-reads every EPUB. No incremental skip.
- No formats other than `.epub`. No cover extraction, no full-text-of-contents indexing, no delete/prune of rows whose files disappeared.

## Capabilities

### New Capabilities

- `library-store`: durable SQLite persistence for the book library — schema creation, path-keyed book identity, author records, and an FTS5 index kept in sync with `books`.
- `epub-indexing`: discovering `.epub` files under a root, extracting metadata from them, and indexing the results idempotently.
- `book-search`: full-text query over indexed metadata and the shape of the results returned.
- `cli-runtime`: the `ebdx` command surface — verbosity control, database path resolution, and the informational commands (`about`, `version`, `schema`).

### Modified Capabilities

None. `openspec/specs/` is empty; this change introduces the project's first specs.

## Impact

- `src/ebdx/db.py` — schema creation, `save_book` upsert, `search_books` projection. The bulk of the change.
- `src/ebdx/scanner.py` — pass the path through to `save_book`, distinguish indexed from updated in the returned stats.
- `src/ebdx/cli.py` — verbosity options on the group, logging setup, summary table columns, path column in search output.
- `src/ebdx/extractor.py` — unchanged behavior; gains tests.
- `src/ebdx/__init__.py` — remove the `hello()` stub.
- `tests/` — replaces the placeholder; adds an EPUB fixture builder.
- `README.md` — written from empty.
- No new runtime dependencies. `ebooklib`, `sqlite-utils`, `click`, `rich`, `loguru`, `platformdirs` are already declared.
- Anyone with an existing `~/.local/share/ebdx/ebdx.db` re-runs `ebdx index`; that database never held data across a restart anyway.
