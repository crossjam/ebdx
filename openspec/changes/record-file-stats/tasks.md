# Implementation Tasks

## 1. Schema and Store

- [ ] Add nullable `file_size`, `file_mtime`, `content_hash`, and `indexed_at` to the
  current `books` schema map.
- [ ] Add an atomic migration that uses SQLite-compatible `ADD COLUMN` statements with
  no non-constant defaults; do not use `DEFAULT CURRENT_TIMESTAMP`.
- [ ] Keep migrated rows’ new values `NULL` until they are written again.
- [ ] Add a path-keyed store read API for saved size and modification time.
- [ ] Make successful `save_book` writes persist supplied file facts and an explicitly
  generated ISO-8601 UTC `indexed_at` value.

## 2. Scanner Flow

- [ ] Resolve and `stat()` each candidate before calling `extract_metadata`.
- [ ] Look up saved file facts and skip extraction and storage only when both non-null
  saved facts match the current facts.
- [ ] For a non-skipped file, extract metadata, hash its bytes, and pass all file facts
  to the store write.
- [ ] Keep stat, extraction, hash, and write failures distinct from an unchanged-file
  skip and continue processing the rest of the library.

## 3. Reporting and Tests

- [ ] Include `skipped` alongside total, indexed, updated, and failed in index results.
- [ ] Test migration from the preceding version, including `NULL` legacy facts and rows
  retained.
- [ ] Test explicit timestamps and refreshed facts on a changed file.
- [ ] Test that an unchanged second run does not call metadata extraction or update
  `indexed_at`.
- [ ] Test that changed, unreadable, and hash-failing files are respectively updated or
  failed without stopping other files.
