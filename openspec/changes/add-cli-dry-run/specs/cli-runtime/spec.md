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

Under the dry-run option, a command that would otherwise change state SHALL report the
changes it would have made rather than silently doing nothing, and SHALL mark its output as
a dry run so the report cannot be mistaken for a completed run. A command that cannot
change state has no such report to be mistaken, and SHALL NOT be labelled — its output
stays byte-identical so it remains usable in a pipeline.

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

### Requirement: Prediction is exact for databases the tool produced

A dry run SHALL report the counts a real run would produce for any database this tool
wrote — at the current layout, or at an earlier one it knows how to rebuild. It SHALL NOT
attempt to predict the outcome for a layout it does not recognise, since doing so would
require reproducing the whole of the schema-setup and write paths and would drift from
them. Such a database SHALL instead be reported as unusable, naming what is wrong and
directing the user to rebuild it, and the command SHALL exit non-zero.

Recognition SHALL be structural — the tables, their columns, and the indexes and triggers
that are expected to exist. It SHALL NOT extend to the definitions of those objects, since
comparing them means comparing stored SQL text against the text this build happens to emit,
and a database altered to keep an object's name while changing its body is indistinguishable
from a healthy one by any cheaper means.

#### Scenario: A current library is predicted exactly

- **WHEN** `index` is run with the dry-run option against a database this tool wrote
- **THEN** the reported counts equal those of the equivalent real run

#### Scenario: An earlier layout is predicted exactly

- **WHEN** `index` is run with the dry-run option against a database recorded at an
  earlier layout, which a real run rebuilds from scratch
- **THEN** every readable file is reported as a would-be insert, matching the real run

#### Scenario: A rebuild hides what is stored now

- **WHEN** `search` is run with the dry-run option against a database recorded at an
  earlier layout, whose stored rows a real run would discard while rebuilding
- **THEN** no results are shown, and the output says the library must be re-indexed first

#### Scenario: An unrecognised layout is reported, not predicted

- **WHEN** `index` is run with the dry-run option against a database whose tables are not
  the ones this tool writes
- **THEN** no counts are reported, the output names what is wrong, it directs the user to
  rebuild the database, and the exit status is non-zero

#### Scenario: An unrecognised layout is reported by a reading command too

- **WHEN** `search` is run with the dry-run option against a database whose tables are not
  the ones this tool writes
- **THEN** the database is reported as unusable, naming what is wrong and directing the
  user to rebuild it, and the exit status is non-zero — whatever the query says, and
  whatever the real command would have failed on first

#### Scenario: Output is labelled

- **WHEN** a command that would otherwise create or modify the data directory, the database
  file, or its contents is run with the dry-run option
- **THEN** the output identifies the run as a dry run

#### Scenario: Commands with nothing to suppress are not labelled

- **WHEN** a command that cannot change state is run with the dry-run option
- **THEN** no dry-run label is added and its output is byte-identical to the same command
  run without the option

### Requirement: The dry-run option is given before the command

The dry-run option SHALL be accepted in the same position as the verbosity options — before
the subcommand — and the help text SHALL make that ordering discoverable.

#### Scenario: Group position is accepted

- **WHEN** the dry-run option is given before the subcommand name
- **THEN** it takes effect for that subcommand

#### Scenario: The option is documented

- **WHEN** the top-level help is shown
- **THEN** the dry-run option is listed among the options that precede the command
