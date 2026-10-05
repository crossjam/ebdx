## ADDED Requirements

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

## MODIFIED Requirements

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
