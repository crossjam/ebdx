## MODIFIED Requirements

### Requirement: Database location resolves consistently

Commands that read or write the library SHALL use the path given by the database option when
present, and otherwise a single default path in the user's platform data directory. Only
commands that write SHALL create the data directory.

A database file SHALL be created only at a path whose name ends in a recognised database
suffix. A path that already holds a file SHALL be opened whatever it is named. A writing
command given a path that neither exists nor carries such a suffix SHALL report that it will
not create a database there, name the suffixes it accepts, and exit non-zero without creating
anything.

When a command reports that no database exists at the path it was given, the report SHALL
identify the option that supplied the path, so a path absorbed from a mistyped option is
visible as such rather than reading as a missing library.

#### Scenario: Explicit path is honoured

- **WHEN** a command is given an explicit database path
- **THEN** that file is used and the default location is neither read nor created

#### Scenario: Default path is shared across commands

- **WHEN** `index` is run with no database option and `search` is then run with no database
  option
- **THEN** both resolve to the same default database file

#### Scenario: Read-only commands do not create directories

- **WHEN** `search` is run with no database option and no data directory exists
- **THEN** no data directory is created

#### Scenario: An unnamed path is not created

- **WHEN** a writing command is given a database path that does not exist and whose name
  carries no recognised database suffix
- **THEN** the refusal is reported with the suffixes that are accepted, the exit status is
  non-zero, and no file is created at that path

#### Scenario: An existing database is opened whatever it is called

- **WHEN** a command is given a database path that already holds a file whose name carries no
  recognised database suffix
- **THEN** that file is used as before, and the naming rule does not apply

#### Scenario: A dry run refuses the same path without creating it

- **WHEN** a writing command that would refuse to create a database at the given path is run
  under the dry-run option
- **THEN** the same refusal is reported, and nothing is created

#### Scenario: A missing database names the option it came from

- **WHEN** a reading command is given a database path that does not exist
- **THEN** the report identifies both the path and the option that supplied it

## ADDED Requirements

### Requirement: Usage errors point at the option separator

An argument beginning with a single dash is read as an option, so text a user meant as a
value is claimed before the command sees it. When argument parsing rejects a command line
carrying such a token, the error SHALL explain that text beginning with a dash is separated
from options with `--`.

#### Scenario: A dashed argument is rejected

- **WHEN** a command line containing an argument that begins with a single dash is rejected by
  argument parsing
- **THEN** the error explains that `--` separates text from options, and the exit status is
  non-zero

#### Scenario: A separated argument is read as text

- **WHEN** an argument beginning with a dash is given after `--`
- **THEN** it is used as the command's argument rather than read as an option
