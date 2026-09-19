## ADDED Requirements

### Requirement: The store can be opened read-only

The store SHALL offer a read-only open that performs no schema creation, no schema version
stamping, and no full-text index repair, and under which any attempt to write is refused by
the database engine rather than by convention alone.

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

#### Scenario: Writes are refused by the engine

- **WHEN** a write is attempted against a read-only open
- **THEN** the database engine raises an error and no data is modified

#### Scenario: Reads still work

- **WHEN** a search is run against a read-only open of an intact database
- **THEN** it returns the same results it would return through an ordinary open
