# library-store Specification

## Purpose
Durable local storage for an indexed eBook library: the book and author records, the identity rule that decides when two indexing runs refer to the same book, and the full-text index kept in step with them.

## Requirements

### Requirement: Library data persists across processes

The store SHALL retain all previously written books and authors when a database file is reopened. Opening an existing database SHALL NOT drop, truncate, or recreate any table that already holds data.

#### Scenario: Data survives reopening

- **WHEN** a book is written to a database file, the database is closed, and the same file is opened again
- **THEN** the book is still present with its original field values

#### Scenario: Repeated opens are harmless

- **WHEN** the same database file is opened repeatedly without any write in between
- **THEN** the set of stored books and authors is unchanged after each open

### Requirement: A book is identified by its file path

Every book record SHALL carry the absolute filesystem path of the EPUB it was extracted from. The store SHALL reject a book with no path, and SHALL hold at most one record per path.

#### Scenario: Path is recorded

- **WHEN** a book is saved from an EPUB at a given absolute path
- **THEN** the stored record's path field equals that absolute path

#### Scenario: Saving the same path twice updates in place

- **WHEN** a book is saved for a path that already has a record
- **THEN** the existing record is updated with the new metadata, its identifier is unchanged, and the total number of book records does not increase

#### Scenario: Distinct paths are distinct books

- **WHEN** two EPUBs at different paths carry identical title and author metadata
- **THEN** the store holds two separate book records

#### Scenario: A book without a path is rejected

- **WHEN** a caller attempts to save a book with an empty or absent path
- **THEN** the store raises an error and writes no record

### Requirement: Authors are stored once and reused

The store SHALL keep one author record per distinct author name and SHALL link each book to its author record rather than duplicating the name.

#### Scenario: Repeated author name reuses one record

- **WHEN** several books by the same author name are saved
- **THEN** exactly one author record exists for that name, and each book references it

#### Scenario: Books with unknown authorship are still stored

- **WHEN** a book whose extracted author is empty is saved
- **THEN** the book is stored and searching or listing it does not fail

### Requirement: Full-text index tracks the book records

The store SHALL maintain a full-text index over book title, author name, series, and tags that reflects the current contents of the book records after every insert, update, and delete.

#### Scenario: New book becomes findable

- **WHEN** a book is saved
- **THEN** a full-text query matching its title returns that book

#### Scenario: Updated book reflects new values

- **WHEN** a book already in the store is saved again with a different title
- **THEN** a full-text query for the new title returns it, and a query for the old title does not

#### Scenario: Deleted book disappears from search

- **WHEN** a book record is deleted
- **THEN** a full-text query matching its former title does not return it

### Requirement: Incompatible existing databases are rebuilt, not silently misread

The store SHALL record a schema version in the database file. When it opens a database whose schema predates path-keyed book identity, it SHALL rebuild the schema from scratch rather than operate against the older layout. A database at an earlier version that postdates path-keyed identity SHALL be migrated in place rather than rebuilt. A database recorded at a version newer than the store knows SHALL be left untouched.

#### Scenario: Pre-path database is rebuilt

- **WHEN** a database written by an earlier version, whose book records have no path, is opened
- **THEN** the schema is recreated at the current version and the tool proceeds without error

#### Scenario: Current database is left intact

- **WHEN** a database already at the current schema version is opened
- **THEN** no table is dropped and all existing records remain

#### Scenario: A migratable database is not rebuilt

- **WHEN** a database at an earlier version that postdates path-keyed identity is opened
- **THEN** it is migrated in place and none of its book or author records is discarded

#### Scenario: A newer database is left alone

- **WHEN** a database recorded at a version newer than the store knows is opened
- **THEN** no table is dropped, created, or altered and the recorded version is unchanged

### Requirement: The store can be opened read-only

The store SHALL offer a read-only open that performs no schema creation, no schema version
stamping, no migration, and no full-text index repair, and under which any attempt to write
is refused by the database engine rather than by convention alone.

#### Scenario: Opening read-only creates nothing

- **WHEN** a database file at the current schema version is opened read-only
- **THEN** its set of tables, indexes, and triggers and its recorded schema version are
  unchanged afterwards

#### Scenario: A broken index is not repaired

- **WHEN** a database whose full-text index is missing or is not a full-text table is
  opened read-only
- **THEN** the index is neither dropped, recreated, nor repopulated

#### Scenario: An out-of-date database is not rebuilt

- **WHEN** a database whose recorded schema version predates path-keyed book identity is
  opened read-only
- **THEN** no table is dropped or created and the recorded version is unchanged

#### Scenario: A migratable database is not migrated

- **WHEN** a database at an earlier, migratable schema version is opened read-only
- **THEN** no migration step is applied, its tables, columns, indexes, and triggers are
  unchanged, and the recorded version is unchanged

#### Scenario: Writes are refused by the engine

- **WHEN** a write is attempted against a read-only open
- **THEN** the database engine raises an error and no data is modified

#### Scenario: Reads still work

- **WHEN** a search is run against a read-only open of an intact database
- **THEN** it returns the same results it would return through an ordinary open

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

The scanner SHALL read the saved size, modification time, and content hash of every
stored book in one query, keyed by absolute path, without modifying any row. The result
SHALL distinguish a missing book record from one whose file-fact fields are unknown.

#### Scenario: Saved facts are returned for a known path

- **WHEN** the saved facts are read and a book's facts were saved
- **THEN** its absolute path maps to the stored size, modification time, and content
  hash, and the record is unchanged

#### Scenario: An unindexed path has no saved facts

- **WHEN** the saved facts are read and a path has no book record
- **THEN** that path is absent from the result, while a legacy record is present with
  `NULL` facts

### Requirement: Earlier layouts are migrated in place

When the store opens a database recorded at an earlier schema version that it knows how to
migrate from, it SHALL bring the database to the current version by applying, in order, each
migration step between the recorded version and the current one. Migration SHALL keep every
stored book and author record, with its identifier and field values unchanged. A field that a
step adds SHALL hold the empty value that extraction would give a book lacking that
metadata, until the book is next indexed.

Each step SHALL be atomic: its changes and the advance of the recorded version to that
step's target SHALL take effect together or not at all. A step that fails SHALL leave the
database at the last version whose step completed, with that version's records intact. A
later open SHALL resume from there.

#### Scenario: Rows and identifiers survive a migration

- **WHEN** a database holding books at an earlier, migratable version is opened
- **THEN** the recorded version is the current one, every previously stored book and author
  is present with the same identifier and field values, and no book record was added or
  removed

#### Scenario: Several steps apply in order

- **WHEN** a database recorded two or more versions behind the current one is opened
- **THEN** every intervening step is applied in version order and the recorded version is
  the current one

#### Scenario: Concurrent openers do not repeat a committed step

- **WHEN** two openers observe the same earlier version and the second waits for the first
  to finish a migration step
- **THEN** the second re-reads the version under the write lock and skips that already
  committed step

#### Scenario: Fresh databases include migration-owned schema objects

- **WHEN** a new database is created while migrations define additional managed tables or
  indexes
- **THEN** the core current schema and every migration-owned schema object are present at the
  current recorded version

#### Scenario: A partial migratable database receives pending schema changes

- **WHEN** a database at a migratable version has no `books` table but contains other managed
  data and is opened
- **THEN** missing core tables are created in the layout expected at its recorded version,
  pending migrations are applied in order, and the database reaches the current version

#### Scenario: Search works after a migration

- **WHEN** a database is migrated on open and a search is run that matched a book before the
  migration
- **THEN** the search returns that book, including after a step that rebuilds the full-text
  index

#### Scenario: An interrupted full-text rebuild is retried

- **WHEN** a migration commits after dropping the full-text index and the process is
  interrupted while the index is being recreated and refilled
- **THEN** the incomplete repair is rolled back, the index remains detectably absent or
  broken, and a later open recreates and refills it before returning

#### Scenario: Added fields are empty until re-indexed

- **WHEN** a migration adds a field to book records and the library is then indexed
- **THEN** the field is empty for every book immediately after the migration, and holds the
  extracted value for each book the index run wrote

#### Scenario: A failing step leaves the last good version

- **WHEN** a migration step fails partway through
- **THEN** the open reports an error, the recorded version is the version the step started
  from, no change made by that step remains, and every record present before the step is
  still present

#### Scenario: An interrupted upgrade resumes

- **WHEN** a database left at an intermediate version by an earlier failed upgrade is opened
  again
- **THEN** the remaining steps are applied from that version and the recorded version is the
  current one
