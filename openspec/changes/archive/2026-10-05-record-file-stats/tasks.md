# Implementation Tasks

## 1. Schema and Store

- [x] Add nullable `file_size`, `file_mtime`, `content_hash`, and `indexed_at` to the
  current `books` schema map.
- [x] Add an atomic migration that uses SQLite-compatible `ADD COLUMN` statements with
  no non-constant defaults; do not use `DEFAULT CURRENT_TIMESTAMP`.
- [x] Keep migrated rows’ new values `NULL` until they are written again.
- [x] Read every stored book's saved size, modification time, and content hash in one
  path-keyed query.
- [x] Make successful writes persist supplied file facts and an explicitly generated
  ISO-8601 UTC `indexed_at` value.

## 2. Scanner Flow

- [x] Resolve, `stat()`, and hash each candidate before calling `extract_metadata`.
- [x] Skip extraction and storage only when all three saved facts are non-null and match
  the current facts.
- [x] For a non-skipped file, extract metadata, recheck its facts, and defer it if they
  changed; otherwise pass all file facts to the store write.
- [x] Keep stat, extraction, hash, and write failures distinct from an unchanged-file
  skip and continue processing the rest of the library.
- [x] Apply the same skip and recheck rules in the dry run.

## 3. Reporting and Tests

- [x] Include `skipped` alongside total, indexed, updated, and failed in index results.
- [x] Test migration from the preceding version, including `NULL` legacy facts and rows
  retained.
- [x] Test explicit timestamps and refreshed facts on a changed file.
- [x] Test that an unchanged second run does not call metadata extraction.
- [ ] Test that an unchanged second run leaves `indexed_at` unchanged.
- [x] Test that changed and unreadable files are respectively updated or failed without
  stopping other files.
- [ ] Test that a file whose hash cannot be computed is not skipped and does not stop
  other files.
