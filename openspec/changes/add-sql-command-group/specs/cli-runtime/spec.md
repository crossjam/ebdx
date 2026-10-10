## MODIFIED Requirements

### Requirement: The CLI provides read-only SQLite inspection commands

The CLI SHALL provide an `sql` command group with a `--database/-d` option that defaults
to the same database path used by the other database commands.
The option SHALL be accepted either before the SQL subcommand or on the subcommand
itself; a subcommand-level value SHALL take precedence.
The group SHALL expose read-only sqlite-utils-compatible commands for `query`, `tables`,
`views`, `schema`, `rows`, `indexes`, `triggers`, and `dump`. It SHALL support the
shared output options `--nl`, `--arrays`, `--csv`, `--tsv`, `--no-headers`,
`-t/--table`, `--fmt`, and `--json-cols`, plus `--load-extension` where sqlite-utils
supports it.

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

### Requirement: SQL inspection is read-only

Every `ebdx sql` command SHALL open the selected database read-only and SHALL refuse any
SQL write. A failed write SHALL leave the selected database unchanged.
The protection SHALL also cover a query that attaches another database and then attempts
to write to it.

#### Scenario: A write query is refused

- **WHEN** `ebdx sql query --database library.db "delete from books"` is run
- **THEN** it exits non-zero, reports the SQLite write failure, and the rows in `books`
  are unchanged

#### Scenario: An attached write is refused

- **WHEN** a query attaches another database and then attempts to write to it
- **THEN** it exits non-zero and neither database is modified

### Requirement: SQL inspection does not create or traceback on bad paths

The `sql` group SHALL not create a database file when the selected path does not exist.
It SHALL report the missing path and direct the user to `ebdx index <directory>`. A path
that exists but is not a usable SQLite database SHALL be reported through the CLI’s
normal unusable-database error without a traceback.

#### Scenario: Missing database

- **WHEN** `ebdx sql tables --database missing.db` is run
- **THEN** it exits non-zero, says no database was found, suggests `ebdx index`, and
  leaves `missing.db` absent

#### Scenario: Non-SQLite file

- **WHEN** `ebdx sql schema --database not-a-database.db` is run against a non-SQLite
  file
- **THEN** it exits non-zero with a friendly unusable-database message and no traceback
