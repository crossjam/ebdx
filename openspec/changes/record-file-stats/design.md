# Design Document: File Statistics Collection

## Context and Problem

Every index run currently extracts metadata from every EPUB, even when neither its path
nor its file has changed. The store also knows nothing about the file that produced a
book row, which prevents incremental indexing and makes a content-derived identity
available only to future features.

This change records inexpensive file facts, adds a content hash for rows that are
written, and uses the inexpensive facts to avoid metadata extraction for unchanged
paths.

## Data Model

The `books` table gains these nullable columns:

| Column | Value | Meaning |
| --- | --- | --- |
| `file_size` | integer | `stat().st_size`, in bytes |
| `file_mtime` | text | `stat().st_mtime` rendered as an ISO-8601 UTC timestamp |
| `content_hash` | text | lowercase SHA-256 of the file bytes, when hashing succeeds |
| `indexed_at` | text | ISO-8601 UTC time of the last successful metadata-and-file-facts write |

`indexed_at` means **last changed in the database**, not last encountered by a scan. It
is therefore left untouched when an unchanged file is skipped. The column is nullable
because a row that predates this feature has no truthful historical value; it is
populated the next time that row is written. A hash may likewise remain `NULL` for
legacy rows or when hashing cannot be completed.

## Migration Strategy

The project already migrates schema versions atomically. The new migration uses that
path and adds all four columns with `ALTER TABLE ... ADD COLUMN` as nullable columns,
without defaults. In particular, it MUST NOT add `indexed_at` as
`TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`: SQLite’s `ADD COLUMN` path accepts only
constant defaults and rejects that expression.

Fresh databases define the same nullable columns. The application supplies an ISO-8601
UTC `indexed_at` value explicitly whenever it writes file facts and metadata. Existing
rows keep `NULL` for all four new fields until re-indexed, preserving the distinction
between unknown history and a known value. The migration runs inside the existing
transaction/version-stamping mechanism, so a failed step leaves the prior layout intact.

## File Processing Flow

The scanner, which controls when extraction happens, makes the skip decision:

1. Resolve the candidate path and call `stat()` before metadata extraction.
2. Ask the store for the saved `file_size` and `file_mtime` for that resolved path.
3. If a row exists and both saved facts match the current facts, count the file as
   `skipped` and do not call `extract_metadata` or `save_book`.
4. Otherwise extract metadata. For a successful extraction, compute the SHA-256 hash,
   attach the current file facts and an explicitly generated `indexed_at`, then call
   `save_book`.
5. A failed `stat()`, extraction, hash, or write is reported through the run’s failure
   handling and does not turn an existing row into a false “unchanged” row.

The store exposes a small path-keyed read API for step 2. `save_book` remains
responsible only for persisting a supplied successful write; it does not decide whether
extraction can be skipped. This keeps the optimization effective for the actual control
flow and leaves callers that save already-extracted metadata well-defined.

Size and mtime are deliberately a fast invalidation check, not a cryptographic change
proof. A changed file with an unchanged size and mtime can be missed; the hash is
calculated when a write is required and is stored for later identity work, not read on
every scan.

## Progress and Errors

The index result distinguishes `indexed`, `updated`, `skipped`, and `failed`, alongside
the total discovered files. Progress and verbose output may describe hashing and
skipping, but must not imply an unreliable estimate of time saved. Hashing happens
locally and no file contents leave the machine.

Unreadable or invalid EPUBs keep the existing continue-past-failure behavior. A failed
file is not skipped merely because an older row happens to hold matching or incomplete
facts.

## Testing Strategy

- Migration of a version-one database retains its rows and leaves the new fields `NULL`.
- A newly written row has explicit file facts, a SHA-256 hash, and `indexed_at`; a
  changed file refreshes them and advances `indexed_at`.
- An unchanged, previously indexed path is counted as skipped and extraction is not
  invoked.
- A changed size or mtime invokes extraction and updates the existing row without adding
  a duplicate.
- Stat, extraction, hash, and database-write failures are counted and do not stop other
  files.
