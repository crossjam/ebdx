## MODIFIED Requirements

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

#### Scenario: A migratable database is not migrated

- **WHEN** `index`, `search`, or `schema` is run with the dry-run option against a database
  recorded at an earlier, migratable schema version
- **THEN** no migration step is applied, the database's tables, columns, indexes, and
  triggers are unchanged, and the recorded schema version is unchanged

#### Scenario: Read-only commands are unaffected

- **WHEN** `discover`, `about`, or `version` is run with the dry-run option
- **THEN** each behaves exactly as it does without the option

### Requirement: Prediction is exact for databases the tool produced

A dry run SHALL report the counts a real run would produce for any database this tool
wrote — at the current layout, at an earlier one it migrates in place, or at an earlier
one it knows how to rebuild. It SHALL NOT
attempt to predict the outcome for a layout it does not recognise, since doing so would
require reproducing the whole of the schema-setup and write paths and would drift from
them. Such a database SHALL instead be reported as unusable, naming what is wrong and
directing the user to rebuild it, and the command SHALL exit non-zero.

Recognition SHALL be structural — the tables, their columns, and the indexes and triggers
that are expected to exist at the schema version the database records, so that an earlier
layout lacking only what later versions add is recognised rather than rejected. It SHALL
NOT extend to the definitions of those objects, since
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

#### Scenario: A migratable earlier layout is predicted exactly

- **WHEN** `index` is run with the dry-run option against a database recorded at an
  earlier layout that a real run migrates in place
- **THEN** the reported counts equal those of the equivalent real run — files already
  stored are reported as updates and the rest as inserts — and the output names each
  migration that would be applied

#### Scenario: A migration keeps stored rows visible

- **WHEN** `search` is run with the dry-run option against a database recorded at an
  earlier layout that a real run migrates in place
- **THEN** results are drawn from the stored rows, the output notes that migrations are
  pending, and it does not say the library must be re-indexed

#### Scenario: A query needing a migrated layout is explained

- **WHEN** `search` is run with the dry-run option against a migratable earlier layout,
  with a query that fails only because it refers to something a pending migration would
  add
- **THEN** the output says the query depends on the pending migration rather than
  reporting an error in the query, and the exit status is 0

#### Scenario: An earlier layout lacking only later additions is recognised

- **WHEN** `index` is run with the dry-run option against a database recorded at an
  earlier, migratable version whose tables have every column that version defines and
  none that later versions add
- **THEN** the database is not reported as unusable

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
