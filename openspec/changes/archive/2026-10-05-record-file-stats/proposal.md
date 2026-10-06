# Record File Statistics and Content Hashes

## Problem Statement

The indexer extracts every EPUB on every run and records no facts about the source file.
That makes a large unchanged library unnecessarily expensive to re-index and leaves
future file-identity work without a persisted digest.

## Proposed Solution

Add nullable `file_size`, `file_mtime`, `content_hash`, and `indexed_at` fields to
`books`. The scanner will compare size and modification time with the saved facts before
extraction; only a matching, fully known pair skips the file. Changed or previously
untracked files are extracted, hashed, and saved with an application-generated UTC
`indexed_at` timestamp.

`indexed_at` means the last successful database write, not the last scan encounter, so
skipping does not change it. The digest is recorded when a write is needed; it is not
read on every scan and is therefore not the change detector for this feature.

## Migration

The schema version will advance through the existing atomic in-place migration system.
Its SQLite `ADD COLUMN` statements use nullable columns with no expression defaults. In
particular, `CURRENT_TIMESTAMP` cannot be a default in this migration path. Existing
rows retain `NULL` file facts and are refreshed naturally when re-indexed; new
application writes set `indexed_at` explicitly.

## Scope

This change records the file facts and supports fast path-keyed incremental indexing. It
does not yet use the hash to merge moved or duplicate files, or mark missing files.
Those are later features that can build on these recorded facts.
