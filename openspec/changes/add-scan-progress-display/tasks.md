## 1. Shared diagnostic console

- [ ] 1.1 Add `src/ebdx/progress.py` owning a single `Console(stderr=True)` and returning it
      from a `diagnostic_console()` accessor, so progress and logging have one writer;
      verify a print through it lands on stderr and not on stdout.
- [ ] 1.2 Point the loguru sink in `cli._configure_logging` at that console, decoding each
      record from ANSI into a `Text` and printing it without wrapping; verify the existing
      quiet/verbose tests still pass and that a record containing `[` and a long path is
      emitted unchanged, coloured on a terminal and plain when redirected.

## 2. Display helpers

- [ ] 2.1 Add a determinate helper that wraps a known sequence of files, labels the bar with
      the current filename, and advances per item; verify it renders a bar on a forced
      terminal console and yields every item.
- [ ] 2.2 Add an indeterminate helper for the directory walk that pulses and reports a
      running found-count; verify it yields every path the walk produced.
- [ ] 2.3 Make both helpers compute `disable = not enabled or not console.is_terminal` in
      one place; verify a non-terminal console produces an empty capture.

## 3. Call sites

- [ ] 3.1 Wrap the walk and the extraction loop in `scan_and_index` with a `show_progress`
      switch defaulting to on; verify the returned counts are unchanged.
- [ ] 3.2 Do the same in `plan_index`, so a dry run shows the display under its existing
      label; verify the dry-run summary and label are untouched.
- [ ] 3.3 Wrap `discover`'s walk and its table-building loop; verify the listed files and
      the table are unchanged.
- [ ] 3.4 Carry `quiet` on `ctx.obj` beside `dry_run` and pass `show_progress=not quiet`
      from `index` and `discover`; verify `--quiet` still prints results.

## 4. Acceptance tests

- [ ] 4.1 In `tests/test_scanner.py`, assert a forced-terminal console shows a bar for the
      extraction pass and a found-count for the walk, and that a warning logged mid-display
      appears in full with the failure still counted.
- [ ] 4.2 In `tests/test_cli.py`, assert `index` and `discover` write no progress output to
      stdout under the CliRunner's non-terminal streams, and that `--quiet` suppresses the
      display while results still print.
- [ ] 4.3 Assert the summary table survives a run with the display active, and that the
      dry-run label and counts are unchanged.
- [ ] 4.4 Assert `discover`'s stdout is byte-identical with and without the display, and
      that `--dry-run discover` stays byte-identical to a plain `discover`.

## 5. Close out

- [ ] 5.1 Run `ruff check`, `ruff format --check`, `ty check src/`, and `pytest -q`; verify
      all pass with no test regressed.
- [ ] 5.2 Smoke-test `ebdx index` and `ebdx discover` under a pty against a generated
      library, then again redirected to a file; verify the display renders in the first and
      the file holds no control sequences in the second.
