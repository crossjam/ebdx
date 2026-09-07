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

The store SHALL record a schema version in the database file. When it opens a database whose schema predates path-keyed book identity, it SHALL rebuild the schema from scratch rather than operate against the older layout.

#### Scenario: Pre-path database is rebuilt

- **WHEN** a database written by an earlier version, whose book records have no path, is opened
- **THEN** the schema is recreated at the current version and the tool proceeds without error

#### Scenario: Current database is left intact

- **WHEN** a database already at the current schema version is opened
- **THEN** no table is dropped and all existing records remain
