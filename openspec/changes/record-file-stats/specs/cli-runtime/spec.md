# CLI Runtime Specification

## Overview

This specification defines how file statistics collection integrates into the ebdx command-line interface, focusing on user experience and performance monitoring.

## Command-Line Interface

### Index Command Enhancements

The `ebdx index` command will transparently collect file statistics during normal operation:

```bash
ebdx index [OPTIONS] [PATHS]...
```

No new required flags will be added. The enhanced functionality will be enabled by default.

### Progress Reporting

Hash computation progress will be integrated into existing progress displays:

```
Indexing library: 150/2000 books (7.5%) | Hashing: 25/150 files (16.7%)
```

Performance metrics will be displayed upon completion:
- Total hashing time
- Average time per file
- Files skipped due to unchanged stats

### Verbose Mode

Detailed file statistics will be shown in verbose mode (`-v`):

```
Processing book: "Example Title.epub"
File size: 1,240,356 bytes
Modified: 2026-10-05T14:30:22Z
Content hash: a1b2c3d4e5f6...
```

## Performance Considerations

### Hashing Overhead

SHA-256 computation reads every byte of each file, which can be expensive:

- Progress indicators will show real-time hashing status
- Estimated time to completion based on average file processing speed
- Option to disable hashing for quick re-indexing (advanced usage)

### Optimization Benefits

The implementation will provide clear feedback on benefits achieved:

```
Indexing complete:
- 150 books processed
- 25 files unchanged (skipped)
- Time saved: ~2 minutes
- Total hashing time: 45 seconds
```

## Configuration Options

### Environment Variables

Advanced users can control behavior through environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `EBDX_SKIP_HASHING` | Disable SHA-256 computation | Unset (enabled) |
| `EBDX_FORCE_REINDEX` | Ignore file stats, always extract | Unset (disabled) |

### Hidden Flags

For debugging and development:

```bash
ebdx index --force-reindex    # Skip optimization, always extract
ebdx index --skip-hashing     # Don't compute content hashes
```

## Error Handling

### File Access Issues

When files cannot be accessed:

```
Warning: Cannot access "broken_file.epub": Permission denied
Stored file statistics will be cleared for this entry.
```

### Hashing Failures

When SHA-256 computation fails:

```
Warning: Failed to hash "large_file.epub": Operation timed out
Content hash will be stored as NULL.
```

## User Experience

### First-Time Indexing

Initial indexing with the new features:

```
Indexing library with file statistics tracking...
Collecting file stats: 150/150 files (100%)
Computing content hashes: 150/150 files (100%)
Indexing complete: 150 books processed in 2m30s
```

### Incremental Updates

Subsequent runs show optimization benefits:

```
Indexing library...
Skipping unchanged files: 125/150 files (83.3%)
Processing changed files: 25/150 files (16.7%)
Indexing complete: 150 books processed in 30s (saved ~2 minutes)
```

### Missing File Detection

Detection of moved/deleted files:

```
Detecting file changes...
Found 5 moved files (matched by content hash)
Marked 3 files as missing (failed to access)
```