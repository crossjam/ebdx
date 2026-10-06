## Context

See proposal.md — Why. Three existing decisions constrain where a live display can go.

First, the stream split: Rich `console` in `cli.py` carries *results* (the summary table,
the search table, the dry-run report) on stdout, and loguru carries diagnostics on stderr.
A progress display is diagnostic — nobody pipes a progress bar into `jq` — so it belongs
with the logs, not with the tables.

Second, `--quiet` means "warnings off, results still shown". A display that survived
`--quiet` would make the flag mean something else.

Third, `discover`, `about` and `version` are specified to stay byte-identical under
`--dry-run` so they remain usable in a pipeline, and the dry-run summary is specified to
stay distinguishable from a real run's. Anything written into stdout by a display would
break the first; anything left half-rendered above the summary would blur the second.

The mid-loop warning is the sharp edge. `scan_and_index` logs a warning per unreadable
file, and loguru writes it straight to the stream while a live display owns the bottom
lines of that same terminal. Two writers, one cursor: the record lands inside the bar and
the bar redraws over the record.

## Goals / Non-Goals

**Goals:**

- A user watching `index` or `discover` on a large library can tell work is happening, what
  it is working on, and roughly how much is left.
- One console owns the diagnostic stream, so a log record and a live display cannot
  interleave destructively.
- Nothing about a redirected or piped run changes: same bytes on stdout, no control codes
  on stderr.

**Non-Goals:**

- Progress for `search` and `schema`. Both are a single query against an already-built
  index; there is no measurable loop to report on.
- A total for the walk. `Path.walk` cannot know how many files it will find without
  walking first, and walking twice to render a truthful bar costs more than the bar is
  worth.
- Per-file throughput or ETA tuning beyond what Rich's own columns give.

## Decisions

**One `Console(stderr=True)` shared by progress and logging.** `progress.py` owns the
instance; `cli._configure_logging` adds a loguru sink that prints each record through it
rather than writing to `sys.stderr` directly. Rich then treats the record as ordinary
console output arriving during a live display: it erases the display, prints the record,
and redraws below it. Verified by capturing a forced-terminal console while a warning is
logged mid-bar — the record appears on its own line, intact, and the bar is re-rendered
after it.

Alternative considered: leave the sink on `sys.stderr` and lean on Rich's
`redirect_stderr`, which swaps `sys.stderr` for a proxy while the display is live.
Rejected — loguru resolves and stores the stream object when the sink is added, so it keeps
writing to the *original* stderr and the redirect never sees it. Making that work would
mean a sink that re-resolves `sys.stderr` on every record, which is a more obscure way of
saying the same thing and only works while a display happens to be live.

The sink decodes each record from ANSI into a `Text` before printing it, and prints with
`soft_wrap=True`. Decoding rather than printing the string keeps loguru's own colours (the
sink asks loguru to colourize, which it does not do for a function sink by default), keeps
Rich's width measurement honest about escape sequences it would otherwise count as
characters, and — because a `Text` is a renderable rather than markup — leaves a path
containing `[...]` alone. Rich then drops the colour itself when the stream is not a
terminal, so a redirected run gets the plain records it got before. Soft wrap is on because
today's records are written raw, and a wrapped record would split a filename across lines
where a test — and a reader grepping the scrollback — expects it whole.

**Progress renders on stderr, results stay on stdout.** "Found N EPUB file(s)" and the
summary table keep going through the existing stdout console. `result.stdout` under the
CliRunner is therefore exactly what it was before this change, which is what keeps the
byte-identical dry-run requirement true for `discover` and friends.

**Disabled unless stderr is a terminal.** `rich.progress.Progress(disable=True)` never
starts its live display and prints nothing at all — not even the single final frame a
non-terminal `Live` would otherwise emit when it stops. One helper computes
`disable = not enabled or not console.is_terminal`, so both the `--quiet` rule and the
non-terminal rule live in one place and no caller can implement half of it.

Alternative considered: let Rich degrade on its own. Rejected — its non-terminal fallback
still prints a frame per display, which would put progress bars into a redirected stderr
and a blank line before the summary.

**Transient displays.** Both displays erase themselves when they finish. The bar is a
statement about work in flight; once the work is done the summary table is the record, and
a finished bar left above it is just something for the table to be confused with.

**Two phases, because the two loops know different things.**

| phase | what is known | rendering |
| --- | --- | --- |
| directory walk | nothing until it ends | spinner, pulsing bar, elapsed time, running found-count |
| pass over the file list | exact total | spinner, determinate bar, `n/total`, current filename, time remaining |

Rejected alternative for the walk: a bar of files-found against a total that advances as
more are found. It renders as a bar that is always nearly full and never finishes, and its
ratio means nothing — the honest rendering of an unknown total is a pulse plus a count.

`discover` gets both phases as well: it walks, and then it builds one table row per file.
The second phase is genuinely proportional work on a large library, and giving `discover`
the same two-phase shape as `index` means the two commands look alike while they work.

**`show_progress` is a parameter, not a global.** `scan_and_index` and `plan_index` take
`show_progress: bool = False`, and the CLI passes `not quiet`. The group callback carries
`quiet` on `ctx.obj` beside `dry_run`, for the reason recorded when `--dry-run` landed: a
module global makes the `CliRunner` tests order-dependent.

The default is off, and the reason is the log sink. What keeps a warning from tearing
through a live bar is not anything in the scanner: it is `progress.log_sink` installed as
loguru's sink, so records and frames share one console. The CLI does that at startup and
then passes its own choice down explicitly. A caller embedding the scanner has loguru
writing to its own stderr handler until it does the same, so a display enabled by default
would be corrupted by the first extraction warning -- the exact failure the shared console
exists to prevent. Defaulting off means a display is only ever enabled by a caller that has
also arranged the coordination it depends on.

## Risks / Trade-offs

**The log sink now goes through Rich.** A record passes through a renderer that could wrap,
highlight, or interpret it. → Every one of those is switched off at the call site, and a
test pins that a warning naming a file survives a run with the display active.

**A display that is disabled must cost nothing.** A disabled `Progress` is still
constructed and still gets `update` calls. → That is a dictionary write per file against
opening and parsing an EPUB; the loop was never going to notice.

**`--verbose` now mixes INFO records into a live display.** More records means more redraws
of the bar. → That is exactly the interleaving path the shared console exists to handle,
and it is the same code path as a warning.

## Migration Plan

Additive and default-off in every context the tests and pipelines run in: without a
terminal on stderr nothing renders, so existing behaviour is byte-identical. No database
migration, no dependency change. Rollback is deleting `progress.py` and the two call sites.
