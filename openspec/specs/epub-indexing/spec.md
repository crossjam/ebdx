# epub-indexing Specification

## Purpose
Finding EPUB files beneath a directory, reading their metadata, and loading that metadata into the library store so it can be searched — including what happens when a file is unreadable and when the same library is indexed more than once.

## Requirements

### Requirement: Discovery lists EPUB files without indexing them

The `discover` command SHALL recursively find `.epub` files under the given paths and report them. It SHALL accept both directories and individual files, SHALL default to the current working directory when given no paths, and SHALL NOT create or modify a database. Its listing is a command result and SHALL be the whole of what it writes to the result stream, whatever it shows on the diagnostic stream while it works.

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

#### Scenario: The listing is the only result output

- **WHEN** `discover` is run over a library while showing a progress display
- **THEN** the table it prints is the only thing written to the result stream, and the
  listed files are the same as in a run with no display

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

The `index` command SHALL walk the given root, resolve each EPUB path, and obtain its
size, modification time, and SHA-256 content hash before metadata extraction. For a path
with a stored record whose saved size, modification time, and content hash are all
non-null and all match, it SHALL skip metadata extraction and storage. For every other
readable EPUB, it SHALL extract metadata, confirm the file's facts are unchanged since
they were obtained, and store the result against that file’s absolute path. Running it
again over an unchanged library SHALL leave the number of stored books unchanged.

#### Scenario: First run populates the library

- **WHEN** `index` is run against a directory of readable EPUBs
- **THEN** one book record exists per EPUB file

#### Scenario: Second run adds no duplicates

- **WHEN** `index` is run a second time against the same unchanged directory after file
  facts were stored on the first run
- **THEN** no metadata extraction is attempted for those files and the number of book
  records is the same as after the first run

#### Scenario: A legacy row is refreshed rather than skipped

- **WHEN** an existing book record is missing any of its saved size, modification
  time, or content hash
- **THEN** indexing its path extracts metadata and records current file facts

#### Scenario: Edited book is refreshed

- **WHEN** an EPUB’s size, modification time, or content changes on disk and `index` is
  run again
- **THEN** that file’s existing record is refreshed rather than skipped

#### Scenario: A file that changes during extraction is deferred

- **WHEN** an EPUB’s facts differ after metadata extraction from those obtained before it
- **THEN** nothing is stored for it, it is counted as failed, and a later run indexes
  the stable file

#### Scenario: Indexed library is searchable from a new process

- **WHEN** `index` completes and `search` is invoked afterwards in a separate process
  against the same database
- **THEN** the indexed books are returned by matching queries

### Requirement: One bad file does not stop the run

Indexing SHALL continue past any EPUB it cannot stat, read, hash, or store, and SHALL
report per-run counts of files found, newly indexed, updated, skipped, and failed. A file
is counted as failed only when the current run writes nothing for it, even if an earlier
run's row for it is retained; a file written without some of its facts is counted as
indexed or updated and is ineligible for later skips.

#### Scenario: Unreadable file is counted and skipped

- **WHEN** a directory holds both valid EPUBs and one corrupt or unreadable file, and
  `index` is run
- **THEN** every valid EPUB is indexed or skipped as applicable, the bad file is counted
  as failed, and the command exits successfully

#### Scenario: A file that cannot be hashed is still indexed

- **WHEN** an EPUB's metadata is extracted but its content hash cannot be computed
- **THEN** it is stored with a `NULL` content hash, counted as indexed or updated, and
  refreshed rather than skipped on every later run

#### Scenario: Counts distinguish new from updated

- **WHEN** `index` is run over a library and is then run again after one EPUB changes
  and one new EPUB is added
- **THEN** the second run reports the new file as indexed, the changed file as updated,
  and every unchanged pre-existing file as skipped

#### Scenario: Empty directory

- **WHEN** `index` is run against a directory containing no EPUBs
- **THEN** it reports zero found and exits successfully
