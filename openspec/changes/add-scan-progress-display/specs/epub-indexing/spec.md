## MODIFIED Requirements

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
