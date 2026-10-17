# epub-indexing Specification

## Purpose
Finding EPUB files beneath a directory, reading their metadata, and loading that metadata into the library store so it can be searched — including what happens when a file is unreadable and when the same library is indexed more than once.

## Requirements

### Requirement: Discovery lists EPUB files without indexing them

The `discover` command SHALL recursively find `.epub` files under given paths, accept
directories and individual files, and default to the current working directory.
It SHALL NOT create or modify a database.
It SHALL scan every file to determine the total, but SHALL display only the number
allowed by the shared listing limit.
Its selected-format listing SHALL be its only result output.
Structured records SHALL include `filename`, `parent`, and full resolved `path`.

#### Scenario: Files found under a directory

- **WHEN** discovery runs over nested directories with more files than the limit
- **THEN** it finds the full total but emits only the permitted number of records

#### Scenario: Unlimited discovery

- **WHEN** discovery is run with `--limit 0`
- **THEN** every discovered EPUB is listed

#### Scenario: Extension matching ignores case

- **WHEN** files end in `.EPUB` or `.Epub`
- **THEN** they are discovered alongside lowercase `.epub` files

#### Scenario: Non-EPUB files are ignored

- **WHEN** files end in `.pdf`, `.mobi`, or `.txt`
- **THEN** none of them are listed

#### Scenario: Nothing found

- **WHEN** discovery finds no EPUBs
- **THEN** it emits the selected format’s empty result and exits successfully

#### Scenario: Discovery does not touch the database

- **WHEN** discovery runs without an existing database
- **THEN** it creates no database

#### Scenario: The listing is the only result output

- **WHEN** discovery displays progress
- **THEN** progress goes to the diagnostic stream and does not enter the listing

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

### Requirement: Index summaries support structured records

Structured indexing output SHALL emit one summary record with `total`, `indexed`,
`updated`, `skipped`, `failed`, and `dry_run`. Dry-run counts SHALL describe the
predicted run, with `dry_run` true, and SHALL cause no durable changes.

#### Scenario: Incremental summary

- **WHEN** indexing encounters unchanged and changed files
- **THEN** its structured summary includes numeric skipped and updated counts

#### Scenario: Structured dry-run index

- **WHEN** indexing runs with a structured format and `--dry-run`
- **THEN** stdout contains only the prediction record with `dry_run` true and creation
  or migration plans are explained on stderr
