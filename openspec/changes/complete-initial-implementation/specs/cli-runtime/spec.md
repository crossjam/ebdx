## Purpose

The shared behavior of the `ebdx` command line: how much the tool prints while it works, where it puts its database when not told otherwise, and the informational commands that let a user see what version they have and where their data lives.

## ADDED Requirements

### Requirement: Output is quiet by default and adjustable

The CLI SHALL emit only warnings and errors on the diagnostic stream by default. It SHALL accept a verbosity option that raises the level to informational and above, and a quiet option that suppresses all but errors.

#### Scenario: Default run emits no debug chatter

- **WHEN** any command is run with no verbosity option and nothing goes wrong
- **THEN** no debug or informational log lines appear on the diagnostic stream

#### Scenario: Verbose exposes progress detail

- **WHEN** a command is run with the verbose option
- **THEN** informational log lines, including the database being opened, appear on the diagnostic stream

#### Scenario: Quiet suppresses warnings

- **WHEN** indexing encounters an unreadable file while the quiet option is set
- **THEN** no warning line is emitted, and the run's failure count still reflects the file

#### Scenario: Command results are not suppressed

- **WHEN** `search` is run with the quiet option and matches exist
- **THEN** the result table is still printed

### Requirement: Database location resolves consistently

Commands that read or write the library SHALL use the path given by the database option when present, and otherwise a single default path in the user's platform data directory. Only commands that write SHALL create the data directory.

#### Scenario: Explicit path is honoured

- **WHEN** a command is given an explicit database path
- **THEN** that file is used and the default location is neither read nor created

#### Scenario: Default path is shared across commands

- **WHEN** `index` is run with no database option and `search` is then run with no database option
- **THEN** both resolve to the same default database file

#### Scenario: Read-only commands do not create directories

- **WHEN** `search` is run with no database option and no data directory exists
- **THEN** no data directory is created

### Requirement: Informational commands describe the installation

The CLI SHALL provide commands reporting the installed version, and the project summary together with the resolved data directory and default database path.

#### Scenario: Version is reported

- **WHEN** the version command is run
- **THEN** the installed package version is printed

#### Scenario: About names the resolved paths

- **WHEN** the about command is run
- **THEN** the output includes the data directory and default database path that other commands would use

#### Scenario: Informational commands need no database

- **WHEN** the version or about command is run with no database present
- **THEN** it succeeds and creates no database file

### Requirement: Schema inspection reflects the live database

The schema command SHALL list the tables, indexes, and triggers of the resolved database, and SHALL explain how to create one when the file does not exist.

#### Scenario: Schema of an indexed library

- **WHEN** the schema command is run against a database created by indexing
- **THEN** the book, author, and full-text tables are listed

#### Scenario: Schema without a database

- **WHEN** the schema command is run and no database exists at the resolved path
- **THEN** the message names the missing path and points at the `index` command
