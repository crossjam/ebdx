## 1. Test scaffolding

- [ ] 1.1 Add `tests/conftest.py` with a fixture that builds a minimal valid EPUB in `tmp_path` at caller-supplied metadata (title, author, publisher, language, subjects), plus a helper producing a corrupt `.epub`; verify by asserting the generated file is read back by `ebooklib.epub.read_epub` in a smoke test
- [ ] 1.2 Delete `tests/test_placeholder.py` and confirm `poe test` still collects and passes with only the conftest smoke test

## 2. Durable schema

- [ ] 2.1 Add a `SCHEMA_VERSION` constant and a `_ensure_schema` branch that reads `PRAGMA user_version`, rebuilds books/authors/`books_fts`/triggers when it is below current, and stamps the version; verify with a test that opens a database with a hand-built pre-`path` `books` table and asserts the rebuilt table has a `path` column
- [ ] 2.2 Replace every `replace=True` in `_ensure_schema` with `if_not_exists=True` and add `path` (`str`, not null) to the `books` column definitions plus a unique index on `path`; verify with a test that saves a book, closes the database, reopens via `get_database`, and asserts the book is still present — this is the regression test for the wipe bug
- [ ] 2.3 Confirm the FTS5 triggers still reference the correct columns after the schema change and verify with tests that a title is findable after insert, reflects the new value after update, and is absent after delete

## 3. Path-keyed persistence

- [ ] 3.1 Rewrite `save_book` to require a non-empty `path`, raise on a missing one, look the path up in `books`, then `update` the found id or `insert`; verify with tests that saving the same path twice leaves one row with a stable id and updated fields, that two paths with identical title/author give two rows, and that an empty path raises
- [ ] 3.2 Return from `save_book` whether the row was inserted or updated, and drop the dead `try/except KeyError` around `lookup` and the `SELECT last_insert_rowid()` call in favour of `.last_pk`; verify with a test asserting the insert/update flag across two consecutive saves of one path
- [ ] 3.3 Add `path` to the `search_books` projection; verify with a test that a search hit carries the absolute path of the file it was indexed from

## 4. Indexing pipeline

- [ ] 4.1 Pass `epub_path.resolve()` into `save_book` from `scan_and_index` and split the returned stats into `total`, `indexed`, `updated`, `failed`; verify with a test that indexing a directory twice reports all files as updated on the second run with no growth in row count
- [ ] 4.2 Verify the existing continue-past-failure behavior against the corrupt-EPUB fixture with a test asserting valid files are still indexed, the bad file lands in `failed`, and no exception escapes
- [ ] 4.3 Add extractor tests covering a well-formed EPUB, an EPUB declaring only a title (remaining text fields empty, not absent), and a corrupt file returning `None`; record current `series` behavior as-is rather than fixing it

## 5. CLI behavior

- [ ] 5.1 Add `-v/--verbose` and `-q/--quiet` to the `cli` group callback, removing loguru's default sink and installing one at WARNING (default), INFO (verbose), or ERROR (quiet); verify with `CliRunner` tests asserting no debug lines by default and an "Opening database" line under `--verbose`
- [ ] 5.2 Add the `Updated` row to the indexing summary table and a `Path` column to the search results table; verify with `CliRunner` tests asserting both appear in the rendered output
- [ ] 5.3 Wrap the FTS query so an unparseable search query prints an error and exits non-zero instead of raising; verify with a `CliRunner` test on a query with unbalanced quotes asserting non-zero exit and no traceback in the output
- [ ] 5.4 Add `CliRunner` tests for `discover` (nested files, case-insensitive extension, non-EPUBs ignored, no database created), and for `version`/`about`/`schema` succeeding with no database present

## 6. Cleanup and docs

- [ ] 6.1 Remove the `hello()` stub from `src/ebdx/__init__.py` and verify `poe lint` and `poe test` pass with no reference to it remaining (`grep -r hello src tests` returns nothing)
- [ ] 6.2 Write `README.md` with install, the six commands, a worked index-then-search example, and a note that `series` is not currently extracted; verify the example commands run as written against a fixture directory
- [ ] 6.3 Run `poe qa` (lint, type, test) and confirm it passes clean
