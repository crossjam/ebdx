## MODIFIED Requirements

### Requirement: The CLI provides read-only SQLite inspection commands

The CLI SHALL provide an `sql` command group with a `--database/-d` option that defaults
to the same database path used by the other database commands.
The option SHALL be accepted either before the SQL subcommand or on the subcommand
itself; a subcommand-level value SHALL take precedence.
The group SHALL expose read-only sqlite-utils-compatible commands for `query`, `tables`,
`views`, `schema`, `rows`, `indexes`, `triggers`, `dump`, `search`, and
`analyze-tables`. It SHALL support the shared output options `--nl`, `--arrays`,
`--csv`, `--tsv`, `--no-headers`, `-t/--table`, `--fmt`, and `--json-cols`, plus
`--load-extension` where sqlite-utils supports it.
`search` SHALL provide sqlite-utils' full-text search options for the selected table.
`analyze-tables` SHALL provide its read-only analysis options but SHALL NOT expose
sqlite-utils' `--save` option.

The group SHALL NOT expose sqlite-utils' `memory` or `plugins` commands: `memory` works
on a separate in-memory import database, and `plugins` reports installed environment
extensions rather than inspecting the selected library database.

#### Scenario: SQL inspection uses the default database

- **WHEN** `ebdx sql tables` is run without `--database` after a library has been
  indexed
- **THEN** it lists the tables in ebdx’s default database, including `books` and
  `books_fts`

#### Scenario: SQL inspection uses an explicit database

- **WHEN** `ebdx sql schema --database library.db` is run
- **THEN** it reads `library.db` and does not read or create the default database

#### Scenario: Query output supports sqlite-utils formats

- **WHEN** `ebdx sql query --csv --database library.db "select title from books"` is run
- **THEN** stdout is valid CSV produced from the query result

#### Scenario: SQL search uses the selected table’s FTS index

- **WHEN** `ebdx sql search books dune` is run against an indexed library
- **THEN** it returns matching book rows using sqlite-utils output formatting

#### Scenario: SQL search can quote a raw term

- **WHEN** `ebdx sql search --quote books "science fiction"` is run
- **THEN** the search term is passed through sqlite-utils' FTS quoting rules

#### Scenario: Table analysis does not save results

- **WHEN** `ebdx sql analyze-tables books` is run
- **THEN** it reports column analysis and the database has no `_analyze_tables` table

#### Scenario: Excluded commands are absent

- **WHEN** `ebdx sql --help` is run
- **THEN** `memory` and `plugins` are not listed as subcommands
