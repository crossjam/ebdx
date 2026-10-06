## ADDED Requirements

### Requirement: Index results identify unchanged files that were skipped

The `index` command SHALL report the number of discovered files that were skipped
because their saved size, modification time, and content hash matched the file facts
observed before metadata extraction. The result SHALL continue to distinguish newly indexed
files, updated files, and failures from skipped files.

#### Scenario: An unchanged second run reports skips

- **WHEN** `index` is run twice over an unchanged library whose first run saved file
  facts
- **THEN** the second result reports every readable existing file as skipped and reports
  zero indexed and zero updated files

#### Scenario: A changed file is not reported as skipped

- **WHEN** an EPUB’s saved size, modification time, or content hash differs from its
  current file fact
- **THEN** the index result reports it as updated after a successful write, not as
  skipped

#### Scenario: A failed file is distinct from a skipped file

- **WHEN** the index command cannot read or extract metadata from one EPUB, cannot
  store it, or finds that it changed while being read
- **THEN** that file is counted as failed and is not included in the skipped count

#### Scenario: A file without a content hash is never skipped

- **WHEN** an EPUB's metadata can be extracted and stored but its content hash cannot be
  computed
- **THEN** it is reported as indexed or updated rather than failed, and every later run
  refreshes it rather than reporting it as skipped
