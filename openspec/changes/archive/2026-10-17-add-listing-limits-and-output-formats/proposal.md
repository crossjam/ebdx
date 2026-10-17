## Why

Kata issues `rngx` and `cvcj` form one CLI workstream: discovery can flood the terminal,
and friendly commands cannot emit records for scripts.
A shared design keeps limits consistent across human and structured output.

## What Changes

- Share `--limit/-l` between discovery and search: default 20, zero unlimited, negative
  values rejected, and human truncation notices with total counts.
- Add global `--format {table,json,jsonl,csv}`, defaulting to table, for discovery,
  search, indexing summaries, schema inspection, and installation information.
- Keep structured stdout parseable, preserve complete field values and nulls, and send
  diagnostics and dry-run explanations to stderr.
- Preserve existing human output except the intentional limit and truncation changes.

## Capabilities

### New Capabilities

None; these are additions to existing CLI capabilities.

### Modified Capabilities

- `cli-runtime`: output selection, serialization, and shared listing limits.
- `book-search`: unlimited results, total counts, and structured result fields.
- `epub-indexing`: bounded discovery output and structured indexing summaries.

## Impact

Touches CLI rendering, search queries, scanner reporting, tests, and README. No database
schema change or new runtime dependency is expected.
Existing `ebdx sql` commands retain their sqlite-utils formatting options.
