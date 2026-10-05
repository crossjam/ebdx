# Library Store Specification

## Overview

The library store manages persistent storage of book metadata and file statistics in a SQLite database. This specification defines the extended schema to include file-level information.

## Schema Changes

### Books Table Extensions

The `books` table will be extended with four new columns:

| Column | Type | Description |
|--------|------|-------------|
| `file_size` | INTEGER | Size of the file in bytes |
| `file_mtime` | TEXT | Modification time as ISO-8601 UTC timestamp |
| `content_hash` | TEXT | SHA-256 hash of file contents |
| `indexed_at` | TEXT | When this entry was last written (ISO-8601 UTC) |

### Column Details

1. **`file_size`** (INTEGER, nullable)
   - File size in bytes as reported by `os.stat().st_size`
   - NULL for files that cannot be accessed

2. **`file_mtime`** (TEXT, nullable)
   - File modification time in ISO-8601 UTC format
   - Example: "2026-10-05T14:30:22Z"
   - NULL for files that cannot be accessed

3. **`content_hash`** (TEXT, nullable)
   - SHA-256 hash of the file's contents
   - Lowercase hexadecimal representation
   - NULL when hashing fails or is skipped

4. **`indexed_at`** (TEXT, NOT NULL, DEFAULT CURRENT_TIMESTAMP)
   - Timestamp when this record was last written
   - Updated on every index operation
   - ISO-8601 UTC format

## Migration Strategy

### Version Bump
- Current schema version will be incremented
- Migration will be atomic and rollback-safe

### Backward Compatibility
- New columns are nullable (except `indexed_at` which has a default)
- Existing records will have NULL values until re-indexed
- Database reads will handle NULL values gracefully

### Fresh Database Initialization
- New databases will include the extended schema
- Default values will be applied appropriately
- Migration ensures consistency between fresh and upgraded databases

## Data Flow

### On Index Operations
1. Stat file to get size and modification time
2. Compare with stored values if record exists
3. Skip extraction if unchanged (optimization)
4. Compute SHA-256 hash of file contents
5. Update all fields including `indexed_at`
6. Store results in database

### On Database Reads
1. Query can filter by file characteristics
2. NULL values handled gracefully
3. Missing file detection based on stale timestamps
4. Moved file detection via content hashes

## Error Handling

### File Access Errors
- File size/mtime: Stored as NULL if inaccessible
- Content hash: NULL if hashing fails
- Indexed timestamp: Still updated to show attempted access

### Database Constraints
- All new columns follow existing nullable pattern
- `indexed_at` has default to ensure always populated
- No foreign key constraints affected by changes