## Context

Work is tracked by `rngx` and `cvcj` on branch `feat/listing-limits-and-output-formats`.
Dry-run support, incremental indexing, and the SQL command group have shipped since the
original issues were written.
Index summaries must include `skipped`; dry-run formatting must cover existing planning
and repair reports.

## Decisions

### Shared listing policy

Use one reusable Click option decorator and a helper carrying displayed rows, total
count, and truncation state.
`discover` and `search` default to 20, accept zero as unlimited, and reject negative
values before doing work.
Apply the same cap in every format.
Discovery still scans all files to obtain its total.
Search obtains the exact match count with the same query semantics as its result query,
without fetching every row just to count them.
Preserve relevance ordering and existing literal versus FTS behavior.

Untruncated human tables keep their existing titles.
Truncated tables say `Showing N of M`. Structured records remain plain arrays or rows;
put truncation notices on stderr so pipelines can parse the whole stdout payload.

### Format selection and serialization

Add a global option before the command, carried through Click context alongside
`dry_run` and `quiet`. Default `table` keeps existing human renderers.
A shared serializer writes directly through Click rather than Rich.

JSON emits one array for listings and one object for summaries and informational
commands. JSONL emits one object per record.
CSV has a stable header and uses the standard library writer.
Empty listings are `[]`, zero JSONL lines, or header-only CSV. Nulls become JSON null
and empty CSV cells; numbers stay numeric in JSON.

Record shapes:

- Discovery: `filename`, `parent`, and full resolved `path`.
- Search: `id`, `title`, `author`, `series`, `series_index`, and `path`.
- Schema: `name`, `type`, and `sql`.
- Index: `total`, `indexed`, `updated`, `skipped`, `failed`, and `dry_run`.
- About: `version`, `summary`, `repository`, `data_directory`, and `database`.
- Version: `version` (one object or record in structured modes).

Index emits one summary record, including under JSONL. Per-file indexing events are
deferred. `--limit` applies to discovery and search, not to summary metrics, schema
inspection, or delegated SQL commands.

### Diagnostics and dry runs

Structured stdout contains only results.
Route progress, indexing preambles, warnings, errors, repair plans, and dry-run banners
to stderr in structured modes.
Human rendering retains its existing stream behavior.
Errors exit non-zero; fix the existing schema missing-database success exit in
structured modes.

Dry-run index counts retain their predicted meaning and set `dry_run: true`. Dry-run
search or schema emits available records while pending work is explained on stderr.
A successful dry run that cannot query an index it refuses to repair emits an empty
structured listing and explains the reason on stderr.
Keep all existing no-write guarantees.

### SQL command boundary

The new global format is for ebdx’s own commands.
SQL subcommands keep their existing sqlite-utils serializers and options; they do not
inherit a competing serializer.
Reject a non-table global format for `sql` with a usage error pointing to its native
format flags. Default invocations remain compatible.

## Risks and Validation

Count and result queries must share matching semantics, including blank literal queries
and invalid FTS expressions.
Truncation intentionally changes large human listings; reconcile `cvcj`’s byte-identical
goal with that explicit `rngx` change.
Parse complete stdout in tests, including empty results, special characters, null series
indexes, errors, verbosity, quiet mode, and dry runs.
Verify dry-run database bytes and schema remain unchanged and SQL commands retain their
behavior.
