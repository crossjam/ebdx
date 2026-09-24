## Why

`ebdx index` prints "Found N EPUB file(s)" and then goes silent until the summary table.
Between those two lines it walks the whole tree and opens, unzips, and parses every EPUB it
found — on a real library that is minutes of nothing on screen, indistinguishable from a
hung process. `ebdx discover` is worse: it prints nothing at all until the finished table.

Neither silence is covered by the specs. The only occurrence of "progress" in `openspec/`
is the `cli-runtime` scenario "Verbose exposes progress detail", which is about *log lines*
on the diagnostic stream under `-v` — a different mechanism from a rendered display, and
one worth reconciling with rather than reusing.

Rich is already a dependency and already renders every table this tool prints, so a live
display adds no new package.

## What Changes

- Show a live progress display while `index` and `discover` do their long work: an
  indeterminate, pulsing bar with a running found-count for the directory walk, whose total
  is unknowable until it ends, and a determinate bar labelled with the current file for the
  pass over the now-known file list.
- Render it on **stderr**, through a single `Console` that the log sink also writes
  through, so a warning logged for an unreadable file is lifted above the live display
  instead of tearing through it, and stdout keeps carrying nothing but command results.
- Suppress it under `--quiet`. A progress display is diagnostic, not a result, so the
  established rule — `--quiet` silences warnings while results stay visible — puts it on
  the silenced side.
- Disable it whenever stderr is not a terminal, so a redirected or piped run emits no
  control codes and no partial bars.
- Show it under `--dry-run` too. A dry run performs the same walk and the same extraction
  pass, so it has the same silence to fill; the existing dry-run label and summary are
  unchanged.

## Capabilities

### New Capabilities
<!-- None: this extends existing CLI output behavior rather than introducing a new capability. -->

### Modified Capabilities
- `cli-runtime`: adds the requirement that long-running commands show progress on the
  diagnostic stream, that `--quiet` and a non-terminal stream each suppress it, and that it
  shares a console with logging so neither corrupts the other. Reconciles the existing
  quiet/verbose requirement, which until now described only log lines.
- `epub-indexing`: pins that `discover`'s listing is a result on stdout and is unchanged by
  the display, so the command stays usable in a pipeline.

## Impact

- `src/ebdx/progress.py` (new): the shared stderr console and the two display helpers.
- `src/ebdx/scanner.py`: `scan_and_index` and `plan_index` wrap the walk and the extraction
  loop; both grow a `show_progress` switch defaulting to off, so a display is only enabled
  by a caller that has also installed the shared log sink.
- `src/ebdx/cli.py`: the log sink writes through the shared console; the group callback
  carries `quiet` on `ctx.obj` beside `dry_run`; `index` and `discover` pass it down.
- `tests/test_cli.py`, `tests/test_scanner.py`: coverage for suppression, non-terminal
  degradation, the summary table, and a warning logged mid-display.
- No dependency changes: `rich.progress` ships with Rich.
