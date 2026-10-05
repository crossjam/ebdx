## ADDED Requirements

### Requirement: Book records retain file facts from successful index writes

The store SHALL retain nullable `file_size`, `file_mtime`, `content_hash`, and
`indexed_at` fields with every book record. `file_size` SHALL be the file size in bytes,
`file_mtime` and `indexed_at` SHALL be ISO-8601 UTC timestamps, and `content_hash` SHALL
be a lowercase hexadecimal SHA-256 digest when available. `indexed_at` SHALL identify
the successful write that recorded the metadata and file facts, not a later scan that
skipped the file.

The store SHALL write `indexed_at` explicitly in application code. It SHALL NOT rely on
a SQLite `ALTER TABLE ... ADD COLUMN` default expression for that value.

#### Scenario: A newly indexed book records its file facts

- **WHEN** a readable EPUB is indexed successfully
- **THEN** its book record contains its size, UTC modification time, SHA-256 hash, and
  the UTC time of that write

#### Scenario: A changed book refreshes its facts and write time

- **WHEN** a stored EPUB has changed and is indexed successfully again
- **THEN** its existing record is updated with the newly observed file facts and a later
  `indexed_at` value, without creating another book record

#### Scenario: A skipped book retains its write time

- **WHEN** a scan determines that a stored EPUB is unchanged and skips it
- **THEN** its `indexed_at` value is unchanged

#### Scenario: A hash is unavailable

- **WHEN** metadata and other file facts can be saved but computing the content hash is
  not available
- **THEN** the record may retain `NULL` for `content_hash` without inventing a digest

### Requirement: File facts migrate without discarding history

When upgrading a database written before file facts existed, the store SHALL migrate it
in place using the established atomic migration mechanism. The migration SHALL add
nullable columns without a non-constant SQLite default; existing values in every
pre-existing book and author record SHALL be retained.

#### Scenario: A legacy database opens successfully

- **WHEN** a database at the immediately preceding migratable version is opened
- **THEN** it reaches the current schema version with all pre-existing book and author
  rows intact, and its new file-fact fields are `NULL`

#### Scenario: Legacy timestamp history remains unknown

- **WHEN** a book row existed before `indexed_at` was introduced
- **THEN** its `indexed_at` is `NULL` until that book is successfully written by a later
  index run

### Requirement: The scanner can retrieve saved file facts by path

The store SHALL provide a path-keyed read operation that returns the saved size and
modification time for a book path without modifying the row. It SHALL distinguish a
missing book record from one whose file-fact fields are unknown.

#### Scenario: Saved facts are returned for a known path

- **WHEN** a caller asks for file facts at the absolute path of a book whose facts were
  saved
- **THEN** the stored size and modification time are returned without changing the
  record

#### Scenario: An unindexed path has no saved facts

- **WHEN** a caller asks for file facts at a path with no book record
- **THEN** the operation reports that no matching record exists
