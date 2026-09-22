## Why

A token beginning with `-` is claimed by Click's option parsing before any command sees it.
Where the letter collides with a short option that takes a value, the rest of the token
becomes that value -- and `-d/--database` on a writing command then creates a database named
after the fragment:

    $ ebdx index ./lib -dune
    Indexing EPUBs in: ./lib
    $ ls
    lib  une              <- 32KB of SQLite, named `une`

Read commands create nothing, since `search` and `schema` both guard on the file existing,
but they report the misparse as a missing database -- `No database found at: une` -- which
reads as "your library is gone" rather than "your option was eaten".

Nothing here is specific to search syntax. `search` now reads its argument as literal text,
and `--` already covers a query that genuinely starts with a dash. This is one layer up, in
argument parsing, and `index` is where it leaves a file behind.

## What Changes

- **A database is created only at a path that names one.** A new file is written only when
  its name ends in `.db`, `.sqlite` or `.sqlite3`; anything else is refused with a message
  and a non-zero exit. An existing file is opened whatever it is called, so a database
  already living at an extension-less path keeps working.
- **The not-found message names the option the path came from.** `No database found at: une`
  becomes `No database found at: une (given as -d/--database)`, so a swallowed option is
  visible at the point of failure rather than looking like a missing library.
- **A usage error involving a dashed token mentions `--`.** When argument parsing rejects a
  token beginning with a dash — one dash or two, the `--` separator itself excepted — the
  error carries a line explaining that text is separated from options with `--`.
- **BREAKING** (narrowly): `ebdx index ~/books -d mylibrary` no longer creates `mylibrary`;
  it reports the refusal and asks for a name ending in a database suffix. Creating the same
  database as `mylibrary.db` works, and an existing `mylibrary` is still opened.

## Capabilities

### New Capabilities

None. This constrains behaviour that `cli-runtime` already owns.

### Modified Capabilities

- `cli-runtime`: "Database location resolves consistently" gains a rule about which paths may
  be created, and the reporting of a path that does not exist. A new requirement covers the
  `--` guidance on usage errors.

## Impact

- Affected specs: `cli-runtime`
- Affected code: `src/ebdx/cli.py` -- the `--database` handling shared by `index`, `search`
  and `schema`, the two `No database found at:` sites, and the command class that renders
  usage errors. `README.md` gains the naming rule.
- No change to how an existing database is found, opened, or repaired; the default path
  (`ebdx.db` in the XDG data directory) already satisfies the new rule.
