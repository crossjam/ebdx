## Context

`_ensure_schema` (`src/ebdx/db.py`) reads `PRAGMA user_version` and branches four ways. A
version newer than `SCHEMA_VERSION` is left alone. An older version with a `books` table is
dropped and rebuilt. A current version with a broken `books_fts` has its index repaired from
`books`. Finally `_create_schema` creates any missing object with `IF NOT EXISTS`, and the
version is stamped.

The dry-run side mirrors each branch without writing. `plan_mode` returns `compare`,
`insert-all`, or `unusable`. `describe_pending_schema_work` lists the repairs, and
`would_discard_existing_rows`, `would_repair_search` and `would_fail_to_open` answer the
narrower questions `search` and `index` ask. Structural recognition
(`_missing_schema_columns`) compares a database against one fixed column set,
`_BOOKS_COLUMNS` / `_AUTHORS_COLUMNS`, which is also what `_create_schema` builds from.

`SCHEMA_VERSION` is 1. Version 0 with a `books` table is the pre-path-keyed layout, the only
earlier layout that has existed.

## Goals / Non-Goals

**Goals:**

- One place to declare a layout change, from which the upgrade, structural recognition at
  every version, and the dry-run report all follow, so they cannot drift apart.
- Upgrades that are safe to interrupt at any point.
- Reuse the existing search-index repair rather than adding a second way to rebuild it.

**Non-Goals:**

- Down-migrations. An older build already leaves a newer database untouched, and that
  stays the rollback story.
- Backfilling newly added fields during the migration. That needs the EPUB files, which the
  open does not have; the next `ebdx index` fills them.
- Any real layout change. The list ships empty; see proposal.md.

## Decisions

### Migrations are Python steps in an ordered tuple, declaring what they add

```python
class Migration(NamedTuple):
    target: int                             # the version this step produces
    description: str                        # shown by --dry-run
    apply: Callable[[Database], None]       # the DDL and data changes
    adds: Mapping[str, Mapping[str, type]]  # table -> {column: type} this step introduces
    rebuilds_search: bool = False           # the step drops books_fts; see below

_MIGRATIONS: tuple[Migration, ...] = ()
```

`SCHEMA_VERSION` is derived as `_BASE_VERSION + len(_MIGRATIONS)`, with `_BASE_VERSION = 1`.
An import-time check asserts the targets run contiguously from `_BASE_VERSION + 1`.

*Alternatives:* SQL files per version would be simpler to read, but a step that changes the
search index needs `_repopulate_fts` (Python), and ydcx will need a data move that joins
through `authors`. Alembic or yoyo bring a dependency and a migrations directory for what is
a handful of steps against a single-user file.

### The expected layout at version N is derived from the current one

`_BOOKS_COLUMNS` and `_AUTHORS_COLUMNS` stay the single source of truth for the current
layout, and `_create_schema` keeps building fresh databases directly from them. No
migrations run for a new file. The layout expected at version N is the current layout minus
every column (and table) that a step with `target > N` adds. `_missing_schema_columns` takes
the recorded version and checks against that. `plan_mode`, `unrecognised_structure` and
`would_fail_to_open` inherit the fix. This is what stops the first added column from
reporting every version-1 database as unusable.

*Alternative:* a frozen snapshot of each version's layout. It is explicit, but every step
would have to restate the whole schema, and a snapshot that disagrees with the step it
describes goes unnoticed.

### Each step runs in its own explicit transaction, using raw SQL only

The upgrade loop runs `BEGIN IMMEDIATE`, then `step.apply(db)`, then
`PRAGMA user_version = step.target`, then `COMMIT`, and rolls back on any exception.
SQLite's DDL and `user_version` are both transactional, so the step and its stamp land
together. `IMMEDIATE` takes the write lock up front, so a concurrent `ebdx index` fails
cleanly at the start instead of midway.

Steps must use `db.execute` (`ALTER TABLE ... ADD COLUMN`, `CREATE TABLE`, `INSERT ...
SELECT`), not sqlite-utils helpers such as `Table.transform` or `add_column`. Several of
those wrap their work in `with db.conn:`, which commits the enclosing transaction early and
would break atomicity silently. A test with a deliberately failing second statement guards
this.

*Alternative:* one transaction around all pending steps. It is simpler, but a failure then
throws away steps that succeeded. Per-step transactions give the spec's resume-from-last-good
behaviour.

### A step that changes the search index drops it; the existing repair rebuilds it

A step whose change affects `books_fts` (new indexed columns, or triggers that must read
differently, as ydcx's join table will) drops the index and its triggers with `_drop_fts`
inside its own transaction and sets `rebuilds_search=True`. After all steps, `_ensure_schema`
proceeds as it does today. `_fts_index_is_intact` is false, so `_create_schema` recreates the
index from the current `_FTS_COLUMNS` and trigger definitions, and `_repopulate_fts` refills
it.

This keeps one rebuild path. It always builds the current definition, never an intermediate
one, so a jump of several versions rebuilds once. The repair itself runs in one explicit
transaction covering the drop, recreation, trigger installation and refill. If the process
dies after the last migration commits or during the repair, the index remains absent (or
otherwise detectably broken), so the next open retries; an empty index is never committed as
intact.

*Alternative:* each step rebuilds the index to its own version's definition. That repeats the
work on multi-step jumps, and it needs historical copies of the index definition, which is
exactly what the per-version derivation above avoids.

### The rebuild keeps only the pre-path layout

`_ensure_schema` still drops and recreates when `version < _BASE_VERSION` and `books` exists
(today: version 0). Any version from `_BASE_VERSION` to `SCHEMA_VERSION - 1` migrates.
`would_discard_existing_rows` narrows to the same test.

### Dry-run prediction reuses `compare`

A migration keeps every row and its path, so a real `index` after migrating classifies files
exactly as it would against the stored rows today. `plan_mode` therefore returns `compare`
for a migratable database. The existing path lookup in `plan_index` already gives exact
counts. `describe_pending_schema_work` gains one line per pending step,
`apply migration to version N: <description>`, placed before the existing repair lines.
`would_repair_search` returns true when any pending step has `rebuilds_search`. The existing
`search` dry-run branch then turns a query that fails against the old index into "The search
cannot run until that happens", exit 0, which is the spec's "query needing a migrated layout"
scenario.

### Tests register their own steps

A `with_migrations(*steps, adds_to_current=...)` fixture monkeypatches `_MIGRATIONS`,
`SCHEMA_VERSION`, and the current column maps together (and `_FTS_COLUMNS` when a test step
indexes a new column), so the upgrade machinery is tested against realistic steps without a
real layout change shipping. Callers read `SCHEMA_VERSION` through the `ebdx.db` module at
call time, not via `from ... import`, so the patch takes effect.

## Risks / Trade-offs

- **[A step author uses a sqlite-utils helper that commits early]** → The step is no longer
  atomic. Mitigation: the rule is stated in the `Migration` docstring and guarded by the
  failing-step test. Code review of each new step checks it too.
- **[rtaq's skip-unchanged index meets a newly added field]** → If `index` skips files whose
  size and mtime are unchanged, a field added by a later migration would stay empty forever.
  Mitigation: recorded for rtaq. A step that adds extracted fields must also invalidate
  whatever marker the skip relies on (for example, clearing the stored mtime). No action here,
  since the skip does not exist yet.
- **[Deriving past layouts from the current one misses a removed or renamed column]** →
  `adds` only models additions. Mitigation: all six queued changes only add. A future
  rename or removal extends `Migration` with `removes` when it is needed, rather than now.
- **[A long migration holds the write lock]** → ALTER ... ADD COLUMN is constant-time in
  SQLite, and an FTS refill over a few thousand rows takes well under a second, so this is
  acceptable for a single-user tool.
- **[No automatic backup before migrating]** → A backup copy was considered and rejected.
  Per-step atomicity already guarantees a consistent file, everything in it can be re-derived
  by re-indexing, and a silent `.bak` in the data directory is state a dry run would then
  have to predict too.

## Migration Plan

There is nothing to deploy on its own. The first change to add a step (whichever of ydcx,
2kv2, qedj, rtaq, 00x2, 34k3 lands first) is what users first see migrate. Its release note
should say that the library upgrades in place on first open and that new fields fill on the
next `ebdx index`.

Rollback is running the previous build, which leaves the newer database untouched per the
existing requirement. It cannot use that database for writes, so the user either keeps the
new build or re-indexes into a fresh file.
