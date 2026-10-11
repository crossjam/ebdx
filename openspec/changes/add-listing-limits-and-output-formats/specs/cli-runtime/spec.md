## ADDED Requirements

### Requirement: Commands support structured output

The CLI SHALL accept a global `--format` option with values `table`, `json`, `jsonl`,
and `csv`, defaulting to `table`. Discovery, search, indexing summaries, schema, about,
and version SHALL support these formats.
Structured stdout SHALL contain only the payload, with complete field values.
Diagnostics and dry-run explanations SHALL go to stderr.
Errors SHALL exit non-zero.

#### Scenario: Structured output round-trips

- **WHEN** records contain commas, quotes, newlines, long paths, or null values
- **THEN** the complete stdout parses in the selected format without lost text and JSON
  preserves nulls and numeric values

#### Scenario: Empty structured listings

- **WHEN** a listing has no records
- **THEN** JSON emits an empty array, JSONL emits no records, CSV emits only its header,
  and the command exits successfully

#### Scenario: Dry-run output remains parseable

- **WHEN** a supported command runs with a structured format and `--dry-run`
- **THEN** stdout contains only its records, planning explanations go to stderr, and no
  durable state changes

#### Scenario: Human output remains compatible

- **WHEN** the format is table and no listing is truncated
- **THEN** existing human output is preserved

#### Scenario: SQL retains native formats

- **WHEN** `sql` is invoked with a non-table global format
- **THEN** a usage error directs the caller to SQL’s native format options

### Requirement: Listings share a limit policy

Discovery and search SHALL accept `--limit/-l`, defaulting to 20, with zero meaning
unlimited and negative values rejected.
The limit SHALL apply equally to every output format.
Truncated human listings SHALL report displayed and total counts; structured listings
SHALL report truncation on stderr.

#### Scenario: A negative limit is rejected

- **WHEN** a caller supplies a negative listing limit
- **THEN** the command exits with a usage error before scanning or opening a database

#### Scenario: Structured exports respect the limit

- **WHEN** more than 20 records exist and no explicit limit is supplied
- **THEN** structured output contains 20 records and stderr reports the total
