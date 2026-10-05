# Design Document: File Statistics Collection

## Context and Problem

The ebdx system currently indexes EPUB files by extracting metadata and storing it in a SQLite database. However, it lacks awareness of the underlying file characteristics, which limits optimization opportunities and prevents advanced file management features.

Key limitations:
1. Every index run processes all files regardless of changes
2. No portable file identity beyond path (breaks when files move)
3. No visibility into indexing performance costs
4. Cannot detect missing or moved files

## Solution Overview

Extend the database schema to include file-level statistics:
- File size and modification time for change detection
- Content hash for portable identity
- Index timestamp for tracking operations

This enables:
1. Skipping unchanged files (major performance improvement)
2. Tracking files across path changes
3. Measuring and optimizing indexing costs
4. Detecting missing files

## Detailed Design

### Database Schema Extension

Add four columns to the `books` table:

1. `file_size` (INTEGER, nullable)
   - File size in bytes from `os.stat().st_size`
   - NULL when file is inaccessible

2. `file_mtime` (TEXT, nullable)
   - Modification time as ISO-8601 UTC timestamp
   - NULL when file is inaccessible

3. `content_hash` (TEXT, nullable)
   - SHA-256 hash of file contents
   - NULL when hashing fails or is disabled

4. `indexed_at` (TEXT, NOT NULL, DEFAULT CURRENT_TIMESTAMP)
   - Last write timestamp in ISO-8601 UTC
   - Always populated, updated on every index operation

### Migration Strategy

Implement atomic schema migration compatible with existing architecture:

1. Define `AddedColumn` metadata for new fields
2. Create migration step that adds columns to existing databases
3. Update `_BOOKS_COLUMNS` for fresh database initialization
4. Add `ensure_schema` callback for migration-owned objects
5. Handle backward compatibility (NULL values for existing records)

### File Processing Flow

Enhanced `save_book` function:

1. Before extraction:
   - `stat()` file to get size and mtime
   - Compare with stored values if record exists
   - Skip extraction if unchanged (optimization)

2. During processing:
   - Compute SHA-256 hash with progress reporting
   - Measure and report hashing performance

3. Storage:
   - Update all fields including `indexed_at`
   - Handle file access errors gracefully

### Performance Monitoring

Integrate with existing progress reporting:

1. Show real-time hashing progress
2. Display performance metrics upon completion
3. Report optimization benefits (files skipped)
4. Measure average processing time per file

### Error Handling

Graceful degradation:

1. File access errors: Store NULL for size/mtime/hash
2. Hashing failures: Store NULL for content_hash
3. Database constraints: Follow existing nullable patterns
4. User feedback: Clear warnings for any issues

## Implementation Plan

### Phase 1: Schema and Core Infrastructure
- Define column types and constraints
- Implement atomic migration
- Update database initialization
- Add file statistics collection

### Phase 2: Optimization Logic
- Compare file stats to skip unchanged files
- Implement content hashing with progress reporting
- Update indexing timestamp logic

### Phase 3: Integration and Testing
- Integrate with CLI progress reporting
- Add verbose mode details
- Comprehensive testing
- Documentation updates

## Security and Privacy Considerations

1. Content hashes are for internal identification only
2. No personal information extracted from file contents
3. File access follows existing permission model
4. Hashing occurs locally, no data transmission

## Performance Impact

Positive:
- Major reduction in re-indexing time for large libraries
- Better progress reporting and user feedback

Negative:
- Initial SHA-256 computation overhead
- Slightly larger database storage requirements

Mitigation:
- Progress indicators showing real-time status
- Option to disable hashing for quick re-indexing
- Clear reporting of time saved vs. hashing costs

## Backward Compatibility

Fully maintained:
- Existing databases migrate safely
- NULL values handled gracefully
- New features work with old data
- No breaking changes to existing APIs

## Testing Strategy

1. Unit tests for file statistics collection
2. Integration tests for schema migration
3. Performance tests for hash computation
4. Regression tests for existing functionality
5. Scenario tests for optimization cases

## Future Extensions

1. Advanced file tracking (duplicate detection)
2. Smart backup scheduling based on file changes
3. Integration with cloud storage services
4. Enhanced missing file recovery workflows