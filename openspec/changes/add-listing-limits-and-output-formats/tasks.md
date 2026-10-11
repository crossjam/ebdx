## 1. Shared listing limits (`rngx`)

- [x] 1.1 Add the shared limit option and listing metadata helper; default to 20,
  interpret zero as unlimited, and reject negative values.
- [x] 1.2 Cap discovery rows after the full walk; preserve total counts and show human
  truncation notices.
- [x] 1.3 Add exact search match counts and unlimited query support while preserving
  relevance ordering, literal queries, FTS validation, and dry-run behavior.
- [x] 1.4 Verify default, explicit, unlimited, negative, and empty cases for both
  commands; check totals and existing untruncated human output.

## 2. Output formats (`cvcj`)

- [x] 2.1 Add the global format option, context propagation, and shared JSON, JSONL, and
  CSV serializers with stable field order and empty output handling.
- [x] 2.2 Render discovery and search records using the shared listing policy; send
  structured truncation notices to stderr.
- [x] 2.3 Render index summaries including skipped counts and a dry-run marker; route
  scanner and planning diagnostics away from structured stdout.
- [x] 2.4 Render schema, about, and version records; give structured-mode errors
  non-zero status and stderr messages.
- [x] 2.5 Preserve SQL native formatting and explain incompatible global formats with a
  usage error.
- [x] 2.6 Parse whole stdout in tests across each command and format; cover nulls,
  commas, quotes, newlines, long paths, empty results, and failed indexing files.
- [x] 2.7 Verify structured dry runs, pending repairs, quiet and verbose modes, stderr
  separation, and unchanged database bytes/schema.

## 3. Integration and handoff

- [x] 3.1 Document option placement, shared limits, unlimited exports, record shapes,
  stream behavior, dry runs, and the SQL formatting boundary.
- [x] 3.2 Run OpenSpec strict validation, repository lint/type checks, and tests.
- [x] 3.3 Record verification evidence on both Kata issues and close only when their
  acceptance criteria are complete.

Verification: `uv run poe qa` passed lint, type checks, and all 333 tests.
`uv run ruff format --check src/ tests/`, `git diff --check`, and strict OpenSpec
validation passed. Both Kata issues are closed with evidence.
Implementation is on `feat/listing-limits-and-output-formats`.
