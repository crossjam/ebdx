# Implementation Tasks

## 1. Schema Design and Migration
- [ ] Define new column types and constraints
- [ ] Create migration script to add columns to existing databases
- [ ] Update `_BOOKS_COLUMNS` mapping with new fields
- [ ] Add `AddedColumn` definitions for migration compatibility
- [ ] Implement `ensure_schema` callback for fresh databases

## 2. File Statistics Collection
- [ ] Add `stat()` call to get file size and modification time
- [ ] Implement SHA-256 hashing with progress reporting
- [ ] Add timing measurements for hash computation
- [ ] Integrate file stats into `save_book` function
- [ ] Handle file access errors gracefully

## 3. Optimization Logic
- [ ] Compare stored vs. current file stats to detect changes
- [ ] Skip extraction when file hasn't changed
- [ ] Update `indexed_at` timestamp on every index operation
- [ ] Add command-line option to force re-indexing

## 4. Database Integration
- [ ] Modify `save_book` to store new fields
- [ ] Update search functionality to handle new schema
- [ ] Add database queries for file-based operations
- [ ] Implement missing file detection logic

## 5. Testing
- [ ] Unit tests for file statistics collection
- [ ] Integration tests for schema migration
- [ ] Performance tests for hash computation
- [ ] Regression tests for existing functionality
- [ ] Test optimization scenarios (skip unchanged files)

## 6. Documentation
- [ ] Update README with new features
- [ ] Document schema changes
- [ ] Explain performance implications
- [ ] Provide migration guidance for users