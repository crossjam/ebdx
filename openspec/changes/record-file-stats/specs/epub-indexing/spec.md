## MODIFIED Requirements

### Requirement: Indexing is idempotent over a library

The `index` command SHALL walk the given root, resolve each EPUB path, and obtain its
size and modification time before metadata extraction. For a path with a stored record
whose saved non-null size and modification time both match, it SHALL skip metadata
extraction and storage. For every other readable EPUB, it SHALL extract metadata and
store the result against that file’s absolute path. Running it again over an unchanged
library SHALL leave the number of stored books unchanged.

#### Scenario: First run populates the library

- **WHEN** `index` is run against a directory of readable EPUBs
- **THEN** one book record exists per EPUB file

#### Scenario: Second run adds no duplicates

- **WHEN** `index` is run a second time against the same unchanged directory after file
  facts were stored on the first run
- **THEN** no metadata extraction is attempted for those files and the number of book
  records is the same as after the first run

#### Scenario: A legacy row is refreshed rather than skipped

- **WHEN** an existing book record has no saved size or modification time
- **THEN** indexing its path extracts metadata and records current file facts

#### Scenario: Edited book is refreshed

- **WHEN** an EPUB’s size or modification time changes on disk and `index` is run again
- **THEN** that file’s existing record is refreshed rather than skipped

#### Scenario: Indexed library is searchable from a new process

- **WHEN** `index` completes and `search` is invoked afterwards in a separate process
  against the same database
- **THEN** the indexed books are returned by matching queries

### Requirement: One bad file does not stop the run

Indexing SHALL continue past any EPUB it cannot stat, read, hash, or store, and SHALL
report per-run counts of files found, newly indexed, updated, skipped, and failed.

#### Scenario: Unreadable file is counted and skipped

- **WHEN** a directory holds both valid EPUBs and one corrupt or unreadable file, and
  `index` is run
- **THEN** every valid EPUB is indexed or skipped as applicable, the bad file is counted
  as failed, and the command exits successfully

#### Scenario: Counts distinguish new from updated

- **WHEN** `index` is run over a library and is then run again after one EPUB changes
  and one new EPUB is added
- **THEN** the second run reports the new file as indexed, the changed file as updated,
  and every unchanged pre-existing file as skipped

#### Scenario: Empty directory

- **WHEN** `index` is run against a directory containing no EPUBs
- **THEN** it reports zero found and exits successfully
