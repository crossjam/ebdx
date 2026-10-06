# cli-runtime Specification

## Purpose
The shared behavior of the `ebdx` command line: how much the tool prints while it works, where it puts its database when not told otherwise, and the informational commands that let a user see what version they have and where their data lives.

## Requirements

### Requirement: Output is quiet by default and adjustable

The CLI SHALL emit only warnings and errors on the diagnostic stream by default. It SHALL
accept a verbosity option that raises the level to informational and above, and a quiet
option that suppresses all but errors. The quiet option SHALL also suppress the progress
display, which is diagnostic rather than a command result.

#### Scenario: Default run emits no debug chatter

- **WHEN** any command is run with no verbosity option and nothing goes wrong
- **THEN** no debug or informational log lines appear on the diagnostic stream

#### Scenario: Verbose exposes progress detail

- **WHEN** a command is run with the verbose option
- **THEN** informational log lines, including the database being opened, appear on the
  diagnostic stream — log detail, which the verbosity options govern independently of the
  rendered progress display

#### Scenario: Quiet suppresses warnings

- **WHEN** indexing encounters an unreadable file while the quiet option is set
- **THEN** no warning line is emitted, and the run's failure count still reflects the file

#### Scenario: Quiet suppresses the progress display

- **WHEN** `index` or `discover` is run on a terminal with the quiet option set
- **THEN** no progress display is shown, while the command's own results are still printed

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

#### Scenario: A partial migratable layout names pending migrations

- **WHEN** `schema` is run with the dry-run option against a migratable database without a
  `books` table
- **THEN** the output reports creation of the core schema and names each pending migration
  without changing the database

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

### Requirement: The dry-run option is given before the command

The dry-run option SHALL be accepted in the same position as the verbosity options — before
the subcommand — and the help text SHALL make that ordering discoverable.

#### Scenario: Group position is accepted

- **WHEN** the dry-run option is given before the subcommand name
- **THEN** it takes effect for that subcommand

#### Scenario: The option is documented

- **WHEN** the top-level help is shown
- **THEN** the dry-run option is listed among the options that precede the command

### Requirement: Long-running commands show progress on the diagnostic stream

Commands that walk a library or read every file in one SHALL show a live progress display
while they work, so a long run is distinguishable from a hung one. The display is
diagnostic, not a result: it SHALL be written to the diagnostic stream, never to the
stream that carries command results, and it SHALL share a console with log records so that
a record emitted while the display is live is shown in full and the display is redrawn
after it.

The display SHALL report a determinate position — how many of a known total are done —
once the set of files to process is known, and SHALL report an indeterminate, advancing
state with a running count for the directory walk that produces that set, whose total
cannot be known until the walk ends.

#### Scenario: Indexing reports its position

- **WHEN** `index` is run over a library on a terminal
- **THEN** a display appears while files are processed, reporting how many of the total
  have been done and naming the file in hand

#### Scenario: Discovery reports its position

- **WHEN** `discover` is run over a library on a terminal
- **THEN** a display appears while the directory is walked and while the listing is built

#### Scenario: A walk with no known total still shows activity

- **WHEN** a command is walking a directory tree and the number of files it will find is
  not yet known
- **THEN** the display advances and reports how many EPUB files have been found so far,
  rather than claiming a proportion of a total it cannot know

#### Scenario: A warning during the display stays readable

- **WHEN** indexing encounters an unreadable file while the display is live
- **THEN** the warning is emitted in full on its own line, the run's failure count still
  reflects the file, and the display continues afterwards

#### Scenario: Results are not disturbed

- **WHEN** an indexing run that showed a display finishes
- **THEN** the summary table is rendered whole, with no progress output left interleaved
  with it

#### Scenario: A dry run shows the same display

- **WHEN** `index` is run with the dry-run option over a library on a terminal
- **THEN** the same display appears, because the same walk and the same extraction pass are
  performed, and the dry-run label and summary are unchanged

### Requirement: The progress display never reaches a redirected stream

A progress display SHALL be shown only when the diagnostic stream is a terminal. When that
stream is redirected to a file or a pipe, no display, partial frame, or terminal control
sequence SHALL be written, and the stream carrying command results SHALL be unaffected in
every case.

#### Scenario: A piped run stays clean

- **WHEN** `index` or `discover` is run with its output redirected to a file
- **THEN** the file contains the command's ordinary output and no progress frames or
  cursor-control sequences

#### Scenario: Results are unchanged by the display

- **WHEN** a command that shows a display is run with its diagnostic stream on a terminal
  and again with that stream redirected, its result stream redirected in both runs
- **THEN** the result output is byte-identical between the two runs

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
