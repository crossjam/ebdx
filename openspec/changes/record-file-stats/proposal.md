# Record File Statistics and Content Hashes

## Problem Statement

Currently, the ebdx database only stores metadata extracted from EPUB files. This approach lacks crucial file-level information that could enable significant optimizations and new features:

1. **Inefficient Re-indexing**: Every index run processes all files regardless of whether they've changed
2. **No File Identity**: Cannot track files across path changes or detect moved/deleted files
3. **Missing Performance Metrics**: No insight into indexing costs or progress

## Proposed Solution

Add four new columns to the `books` table to capture essential file statistics:

- `file_size` (bytes)
- `file_mtime` (ISO-8601 UTC timestamp from `stat`)
- `content_hash` (SHA-256 of file bytes)
- `indexed_at` (ISO-8601 UTC timestamp of last index operation)

These fields will enable three major improvements:

### 1. Skip Unchanged Files
When `file_size` and `file_mtime` match stored values, skip expensive extraction entirely - the biggest performance win for large libraries.

### 2. Portable File Identity
The `content_hash` identifies books independently of their path, enabling detection of moved files and robust handling of missing files.

### 3. Missing File Detection
A stale `indexed_at` after a full run, or a failed `stat`, marks files as gone; the hash can recognize moved files.

## Implementation Plan

1. **Schema Migration**: Add the new columns via atomic migration
2. **Data Collection**: Implement file statistics gathering during indexing
3. **Optimization Logic**: Add logic to skip unchanged files when possible
4. **Hash Computation**: Calculate SHA-256 hashes with progress reporting
5. **Index Timestamping**: Record when each book was last processed

## Backward Compatibility

Adding columns requires bumping `SCHEMA_VERSION`. The `_ensure_schema` function currently handles older versions by dropping everything and rebuilding. For existing libraries (1,904 books locally), this means the database would be emptied until re-indexed. 

Options:
- Accept the rebuild and document it in release notes
- Implement in-place migration first (preferred)

## Testing Requirements

- Fields populated on insert
- `indexed_at` advances on re-index
- Changed files update size/mtime/hash
- Unchanged files are skipped (when implemented)
- Progress reporting for hash computation shows cost measurement