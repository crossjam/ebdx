# ebdx

Index the metadata of an EPUB library into a SQLite database and search it full text.

`ebdx` walks a directory of `.epub` files, reads the Dublin Core metadata out of each
one, and stores it in SQLite with an FTS5 index over title, author, series, and tags.
Books are keyed by their absolute path, so re-running `index` updates rows in place
rather than piling up duplicates.

## Requirements

Python 3.13 or newer. No services, no configuration file — just a SQLite file.

## Install

From a clone, with [uv](https://docs.astral.sh/uv/):

```console
$ git clone https://github.com/crossjam/ebdx
$ cd ebdx
$ uv tool install .
```

Or run it from the checkout without installing:

```console
$ uv run ebdx --help
```

## Quick start

Index a library, then search it:

```console
$ ebdx index ~/books
Indexing EPUBs in: /home/you/books
Database: /home/you/.local/share/ebdx/ebdx.db
Found 3 EPUB file(s)

Indexing complete!
    Indexing Summary
┏━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric        ┃ Count ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total found   │     3 │
│ Newly indexed │     3 │
│ Updated       │     0 │
│ Failed        │     0 │
└───────────────┴───────┘

$ ebdx search Asimov
                          Search Results (1 found)
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Title      ┃ Author       ┃ Series ┃ Index ┃ Path                        ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Foundation │ Isaac Asimov │        │       │ /home/you/books/scifi/fou… │
└────────────┴──────────────┴────────┴───────┴─────────────────────────────┘
```

Indexing is idempotent. Running it again over an unchanged library updates every row
in place instead of inserting duplicates:

```console
$ ebdx index ~/books
...
│ Total found   │     3 │
│ Newly indexed │     0 │
│ Updated       │     3 │
│ Failed        │     0 │
```

A file that cannot be read is counted under `Failed` and the run continues.

## Commands

| Command | What it does |
| --- | --- |
| `ebdx discover [PATHS...]` | List the `.epub` files under one or more paths, without touching a database |
| `ebdx index ROOT` | Scan `ROOT` recursively, extract metadata, and store it |
| `ebdx search QUERY` | Full-text search over indexed metadata (literal text; `--fts` for FTS5 syntax) |
| `ebdx schema` | Print the tables, indexes, and triggers in the database |
| `ebdx about` | Show version, summary, and where data is stored |
| `ebdx version` | Print the version |

Global options, which go before the subcommand:

- `-v`, `--verbose` — show informational logs (database opens, index rebuilds)
- `-q`, `--quiet` — errors only
- `--dry-run` — report what would change, and change nothing ([Dry run](#dry-run))

By default only warnings and errors are logged. Command results are printed regardless.

`index`, `search`, and `schema` accept `-d/--database PATH` to use a database other
than the default. `search` also takes `-l/--limit N` (default 20) and
`--fts`/`--raw`, which reads the query as an FTS5 expression instead of literal
text ([search](#search)).

### discover

Finds `.epub` files without creating or opening a database. The extension is matched
case-insensitively, so `BOOK.EPUB` is found too, and directory symlinks are not
followed.

```console
$ ebdx discover ~/books
                               Discovered 3 EPUB file(s)
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Filename          ┃ Path                               ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ frankenstein.epub │ /home/you/books/classics           │
│ dune.epub         │ /home/you/books/scifi              │
│ foundation.epub   │ /home/you/books/scifi              │
└───────────────────┴────────────────────────────────────┘
```

### search

A query is **literal text**. Its words are searched for together across the indexed
columns `title`, `author`, `series`, and `tags`, and a book matches when it carries
all of them — in any column, adjacent or not:

```console
$ ebdx search "Dune"
$ ebdx search "Herbert Dune"      # both words, wherever they sit
```

Punctuation is part of the words, so nothing needs escaping and no title can be
rejected as a bad query:

```console
$ ebdx search "Ender's"
                          Search Results (1 found)
```

`Dune, Messiah`, `Mr. Mercedes`, `Moby-Dick; or, The Whale` and `R_AND_D, Inc.` are
all ordinary queries. So is anything that merely looks like syntax — `AND`, `-Dune`,
`badcol:Dune`, an unbalanced quote — which is searched for rather than interpreted
or refused.

A query *starting* with `-` is the one that needs help, and not from the search
engine: the shell convention is that a leading dash introduces an option, so `ebdx`
reads it as one before the query is ever looked at. Separate it with `--`, as with
any other command:

```console
$ ebdx search -- "-Dune"
```

#### Expression syntax: `--fts`

Pass `--fts` (or `--raw`) to write
[SQLite FTS5 syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax) instead.
The query reaches the engine exactly as typed:

```console
$ ebdx search --fts "title:Dune"              # one column
$ ebdx search --fts "{title author}:Herbert"  # several columns
$ ebdx search --fts "Dune OR Foundation"      # boolean
$ ebdx search --fts "NEAR(Frank Herbert, 5)"  # proximity
$ ebdx search --fts "Found*"                  # prefix
$ ebdx search --fts '"Frank Herbert"'         # exact phrase
$ ebdx search --fts "-series:Chronicles title:Dune"  # exclude a column
```

Note that `NEAR` is a function in FTS5, not an infix operator. The FTS3/4 spelling
`Frank NEAR Herbert` parses without error but is read as three ordinary terms — one
of them the word "near" — so it quietly matches nothing.

Under the flag the engine's errors are yours too: a query FTS5 cannot parse is
reported and exits non-zero, rather than quietly matching nothing.

```console
$ ebdx search --fts 'badcol:Dune'
Invalid search query: no such column: badcol
Aborted!

$ ebdx search 'badcol:Dune'      # without the flag, an ordinary search
No results found.
```

Why the default is literal: FTS5's grammar claims `"`, `:`, `*`, `(`, `)`, `{`, `}`,
`^`, `+` and a leading `-`, and rejects most other punctuation outright, so ordinary
titles fail to parse as expressions. Guessing which of the two a user meant needs a
copy of FTS5's lexer, and a copy drifts. Asking is cheaper and cannot be wrong.

### Dry run

`--dry-run` goes before the subcommand, like `-v` and `-q`. It reports what the command
would do and leaves the data directory, the database file, and its contents and schema
exactly as it found them.

Against a library that has not been indexed yet, it names everything it would create:

```console
$ ebdx --dry-run index ~/books
DRY RUN — planning an index run; nothing will be changed
Would index EPUBs in: /home/you/books
Database: /home/you/.local/share/ebdx/ebdx.db
Would: create the data directory /home/you/.local/share/ebdx
Would: create the database file /home/you/.local/share/ebdx/ebdx.db
Would: create the books, authors, and full-text schema
Found 3 EPUB file(s)

Dry run complete — no changes were made.
 Indexing Summary (dry
          run)
┏━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric       ┃ Count ┃
┡━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total found  │     3 │
│ Would index  │     3 │
│ Would update │     0 │
│ Would fail   │     0 │
└──────────────┴───────┘
```

The counts are the ones a real run would produce, read from the stored `books.path`, so
adding one book to an indexed library separates the insert from the updates:

```console
$ ebdx --dry-run index ~/books
...
│ Total found  │     4 │
│ Would index  │     1 │
│ Would update │     3 │
│ Would fail   │     0 │
```

A file that cannot be read is still counted under `Would fail` — determining that needs
only a read.

`search` and `schema` look like reads, but a normal open of the database creates missing
tables, stamps the schema version, and rebuilds a damaged search index. Under `--dry-run`
they skip that check and connect through SQLite's read-only URI, so the open cannot write
even by accident. They report the repairs a real open would have performed instead of
performing them:

```console
$ ebdx --dry-run schema
DRY RUN — inspecting the schema read-only; nothing will be changed
Would: rebuild the books_fts search index and refill it from 3 stored book(s)
```

`discover`, `about`, and `version` cannot change anything, so `--dry-run` leaves them
alone — no label is added and their output stays byte-identical, which keeps them usable
in a pipeline.

#### It declines to guess

For a database layout `ebdx` did not write, a dry run does not predict counts. It names
what is wrong, tells you to rebuild, and exits non-zero:

```console
$ ebdx --dry-run search Asimov
DRY RUN — searching read-only; nothing will be changed
Not a usable ebdx database: the books table is missing 'title', 'author_id', … and
the authors table is missing 'name' at schema version 0
Delete /home/you/.local/share/ebdx/ebdx.db and run 'ebdx index <directory>' to rebuild it.
Aborted!
```

Predicting those cases would mean reproducing the whole schema-setup and write path, and
any subset of tables, columns, indexes, and triggers can be absent. A copy of that logic
drifts from the original, and a missed corner is a dry run promising a run that cannot
happen. Re-indexing from the EPUBs on disk is cheap, so it says so.

Recognition is structural: which tables and columns exist, that `books_fts` is an FTS5
table, and that the index over `books.path` exists and is unique. It stops there — stored
SQL text is never compared against the text this build emits, so a trigger kept under its
own name with a rewritten body still reads as healthy.

A database recorded at an earlier layout is a different case: a real run rebuilds it from
scratch, so the dry run reports every readable file as a would-be insert. Because that
rebuild discards what is stored now, `ebdx --dry-run search` shows no results against
one and says the library must be re-indexed first.

## Where things live

The database defaults to the XDG data directory — on Linux
`~/.local/share/ebdx/ebdx.db`. Run `ebdx about` to see the resolved paths on your
system, or pass `--database` to put it somewhere else.

Stored paths are absolute and resolved, so indexing `.` and then `~/books` records
each file once rather than twice. Moving a library orphans its rows: index the new
location and the old rows remain until the database is rebuilt.

If the search index is ever found damaged — dropped, or replaced by a non-FTS5
table — it is rebuilt from the stored books the next time the database is opened.
Your book rows are kept; only the derived index is recomputed. Run the command under
`--dry-run` to see that a rebuild is pending without triggering it.

## Limitations

These are deliberate for now, not oversights:

- **`series` is not extracted.** The extractor reads Dublin Core metadata, and
  Calibre records series as `<meta name="calibre:series" content="…">`, which it does
  not match. The `Series` and `Index` columns are therefore empty for essentially
  every book. The schema and the FTS index already carry the fields, so filling them
  in later needs no migration.
- **No change detection.** Re-indexing re-reads every EPUB; there is no mtime or size
  check to skip unchanged files.
- **`.epub` only.** No other formats, no cover extraction, no indexing of book text —
  metadata only.
- **No pruning.** Rows whose files have been deleted or moved are not removed.

## Development

```console
$ uv sync
$ uv run poe qa          # ruff + ty + pytest
```

Individual tasks: `poe lint`, `poe lint:fix`, `poe format`, `poe type`, `poe test`,
`poe test:cov`. Run `uv run poe --help` for the full list.

Test EPUBs are generated rather than committed: `tests/conftest.py` builds minimal
valid files at whatever metadata a test needs, so no book binaries live in the repo.
