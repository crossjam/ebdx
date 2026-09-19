## ADDED Requirements

### Requirement: A dry run makes no durable change

The CLI SHALL accept a dry-run option that, when set, causes every command to leave the
data directory, the database file, and the database's contents and schema exactly as it
found them. A dry run SHALL exit 0 when nothing went wrong.

#### Scenario: Nothing is created where nothing existed

- **WHEN** `index` is run with the dry-run option and no data directory or database file
  exists at the resolved location
- **THEN** no data directory is created, no database file is created, and the exit status
  is 0

#### Scenario: An existing library is left byte-for-byte alone

- **WHEN** `index` is run with the dry-run option against a library already indexed into an
  existing database
- **THEN** the number of book records, the recorded schema version, and the database file's
  modification time are unchanged afterwards

#### Scenario: A read-looking command repairs nothing

- **WHEN** `search` or `schema` is run with the dry-run option against a database whose
  full-text index has been dropped or replaced by an ordinary table
- **THEN** the set of objects in the database and its recorded schema version are unchanged
  afterwards, and no index is rebuilt or repopulated

#### Scenario: An out-of-date database is not rebuilt

- **WHEN** `search` or `schema` is run with the dry-run option against a database whose
  recorded schema version predates path-keyed book identity
- **THEN** no table is dropped or created and the recorded schema version is unchanged

#### Scenario: Read-only commands are unaffected

- **WHEN** `discover`, `about`, or `version` is run with the dry-run option
- **THEN** each behaves exactly as it does without the option

### Requirement: A dry run reports what it would have done

Under the dry-run option, a command SHALL report the state changes it would have made
rather than silently doing nothing, and SHALL mark its output as a dry run so the report
cannot be mistaken for a completed run.

#### Scenario: Each file is classified

- **WHEN** `index` is run with the dry-run option over a library where some books are
  already indexed and others are not
- **THEN** the summary reports how many files would be newly indexed and how many would be
  updated, using the same counts a real run would produce

#### Scenario: Creation of the store is announced

- **WHEN** `index` is run with the dry-run option and no data directory or database exists
- **THEN** the output states that the data directory, the database file, and the schema
  would be created

#### Scenario: Failures stay truthful

- **WHEN** `index` is run with the dry-run option over a library containing a file that
  cannot be read
- **THEN** that file is counted as failed, because determining it requires only reading

#### Scenario: Output is labelled

- **WHEN** any command is run with the dry-run option
- **THEN** the output identifies the run as a dry run

### Requirement: The dry-run option is given before the command

The dry-run option SHALL be accepted in the same position as the verbosity options — before
the subcommand — and the help text SHALL make that ordering discoverable.

#### Scenario: Group position is accepted

- **WHEN** the dry-run option is given before the subcommand name
- **THEN** it takes effect for that subcommand

#### Scenario: The option is documented

- **WHEN** the top-level help is shown
- **THEN** the dry-run option is listed among the options that precede the command
