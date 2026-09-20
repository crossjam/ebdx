## ADDED Requirements

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

- **WHEN** a command that shows a display is run on a terminal and again with its streams
  redirected
- **THEN** the result output is the same in both runs

## MODIFIED Requirements

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
