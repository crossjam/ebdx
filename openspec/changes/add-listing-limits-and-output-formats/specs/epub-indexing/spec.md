## MODIFIED Requirements

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

## ADDED Requirements

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
