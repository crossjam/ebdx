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
| `ebdx search QUERY` | Full-text search over indexed metadata |
| `ebdx schema` | Print the tables, indexes, and triggers in the database |
| `ebdx about` | Show version, summary, and where data is stored |
| `ebdx version` | Print the version |

Global options, which go before the subcommand:

- `-v`, `--verbose` — show informational logs (database opens, index rebuilds)
- `-q`, `--quiet` — errors only

By default only warnings and errors are logged. Command results are printed regardless.

`index`, `search`, and `schema` accept `-d/--database PATH` to use a database other
than the default. `search` also takes `-l/--limit N` (default 20).

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

Queries use [SQLite FTS5 syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax)
over the indexed columns `title`, `author`, `series`, and `tags`:

```console
$ ebdx search "Dune"                    # bare term
$ ebdx search "title:Dune"              # one column
$ ebdx search "{title author}:Herbert"  # several columns
$ ebdx search "Dune OR Foundation"      # boolean
$ ebdx search "NEAR(Frank Herbert, 5)"  # proximity
$ ebdx search "Found*"                  # prefix
$ ebdx search '"Frank Herbert"'         # exact phrase
```

Note that `NEAR` is a function in FTS5, not an infix operator. The FTS3/4 spelling
`Frank NEAR Herbert` parses without error but is read as three ordinary terms — one
of them the word "near" — so it quietly matches nothing.

A query FTS5 cannot parse is reported and exits non-zero, without a traceback:

```console
$ ebdx search 'badcol:Dune'
Invalid search query: no such column: badcol
Aborted!
```

## Where things live

The database defaults to the XDG data directory — on Linux
`~/.local/share/ebdx/ebdx.db`. Run `ebdx about` to see the resolved paths on your
system, or pass `--database` to put it somewhere else.

Stored paths are absolute and resolved, so indexing `.` and then `~/books` records
each file once rather than twice. Moving a library orphans its rows: index the new
location and the old rows remain until the database is rebuilt.

If the search index is ever found damaged — dropped, or replaced by a non-FTS5
table — it is rebuilt from the stored books the next time the database is opened.
Your book rows are kept; only the derived index is recomputed.

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
