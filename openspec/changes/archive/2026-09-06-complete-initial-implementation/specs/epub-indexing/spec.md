## Purpose

Finding EPUB files beneath a directory, reading their metadata, and loading that metadata into the library store so it can be searched — including what happens when a file is unreadable and when the same library is indexed more than once.

## ADDED Requirements

### Requirement: Discovery lists EPUB files without indexing them

The `discover` command SHALL recursively find `.epub` files under the given paths and report them. It SHALL accept both directories and individual files, SHALL default to the current working directory when given no paths, and SHALL NOT create or modify a database.

#### Scenario: Files found under a directory

- **WHEN** `discover` is run against a directory containing EPUBs at several nesting depths
- **THEN** every `.epub` file beneath it is listed

#### Scenario: Extension matching ignores case

- **WHEN** a directory contains files ending in `.EPUB` and `.Epub`
- **THEN** they are listed alongside lowercase `.epub` files

#### Scenario: Non-EPUB files are ignored

- **WHEN** a directory contains `.pdf`, `.mobi`, and `.txt` files
- **THEN** none of them are listed

#### Scenario: Nothing found

- **WHEN** `discover` is run against a directory with no EPUBs
- **THEN** it reports that none were discovered and exits successfully

#### Scenario: Discovery does not touch the database

- **WHEN** `discover` is run and no database file exists
- **THEN** no database file is created

### Requirement: Metadata extraction reports failure rather than raising

Extraction SHALL return the available metadata for a readable EPUB, and SHALL signal failure without propagating an exception when a file is missing, unreadable, or not a valid EPUB.

#### Scenario: Valid EPUB yields metadata

- **WHEN** metadata is extracted from a well-formed EPUB
- **THEN** the title, author, publisher, language, and subject tags recorded in the file are returned

#### Scenario: Missing fields come back empty, not absent

- **WHEN** an EPUB declares only a title
- **THEN** extraction succeeds and the remaining text fields are empty rather than missing

#### Scenario: Corrupt file fails cleanly

- **WHEN** extraction is attempted on a file that is not a valid EPUB
- **THEN** failure is signalled to the caller and no exception escapes

### Requirement: Indexing is idempotent over a library

The `index` command SHALL walk the given root, extract metadata from each EPUB found, and store each result against that file's absolute path. Running it again over an unchanged library SHALL leave the number of stored books unchanged.

#### Scenario: First run populates the library

- **WHEN** `index` is run against a directory of readable EPUBs
- **THEN** one book record exists per EPUB file

#### Scenario: Second run adds no duplicates

- **WHEN** `index` is run a second time against the same unchanged directory
- **THEN** the number of book records is the same as after the first run

#### Scenario: Edited book is refreshed

- **WHEN** an EPUB's title is changed on disk and `index` is run again
- **THEN** that file's existing record shows the new title

#### Scenario: Indexed library is searchable from a new process

- **WHEN** `index` completes and `search` is invoked afterwards in a separate process against the same database
- **THEN** the indexed books are returned by matching queries

### Requirement: One bad file does not stop the run

Indexing SHALL continue past any EPUB it cannot read, and SHALL report per-run counts of files found, newly indexed, updated, and failed.

#### Scenario: Unreadable file is counted and skipped

- **WHEN** a directory holds both valid EPUBs and one corrupt file, and `index` is run
- **THEN** every valid EPUB is indexed, the corrupt file is counted as failed, and the command exits successfully

#### Scenario: Counts distinguish new from updated

- **WHEN** `index` is run over a library, then run again after one new EPUB is added
- **THEN** the second run reports the new file as indexed and the pre-existing files as updated

#### Scenario: Empty directory

- **WHEN** `index` is run against a directory containing no EPUBs
- **THEN** it reports zero found and exits successfully
