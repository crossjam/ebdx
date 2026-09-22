## Context

See proposal.md — Why. Two facts about the current code shape the approach:

- Every command resolves its database the same way: `--database` when given, otherwise
  `get_default_db_path()`. The reading commands then guard on `Path(database).exists()` and
  abort; `index` does not, and `get_database` creates the file.
- The guard has to sit between resolution and the open. `index` opens through the same
  `_open_database` helper as the readers, so the check belongs where the path is settled,
  not inside the store.

The trigger is argument parsing, which is upstream of all of this and cannot be changed:
a token beginning with `-` is an option by universal convention, and `-d` and `-l` both take
values, so `-dune` and `-lord` are *well-formed* command lines that mean something other
than what was typed. Nothing downstream can recover the user's intent. The design therefore
aims at the consequences — do not create a file, and say where the path came from — rather
than at detecting the mistake.

## Goals / Non-Goals

- **Goals:** a mistyped option never leaves a file behind; a path absorbed from an option is
  recognisable in the error; a user who meets the dash problem is told about `--`.
- **Non-Goals:** inferring that a path *was* absorbed from a glued option; rescuing the
  user's intended command line; changing how an existing database is found, opened, or
  repaired.

## Decisions

### Creation is gated on the name; opening is not

A new database is written only at a path whose name ends in `.db`, `.sqlite` or `.sqlite3`.
Any path that already holds a file is opened regardless of its name.

The asymmetry is the whole point. Gating the open would break databases that already live at
extension-less paths, and would be a rule about other people's files; gating creation is a
rule about what this tool produces, which it is entitled to have. It is also not a guess:
nothing here infers intent, which keeps it clear of the reasoning `cli-runtime` already
settled in "Prediction is exact for databases the tool produced", and of the heuristic the
search path has just finished removing.

**Alternative rejected:** prompt for confirmation before creating at an unusual path. It
stops the file, but it makes `index` interactive, which breaks it in a script — the place
where an unnoticed stray file matters most.

**Alternative rejected:** drop `-d` as a short option, removing the glue at its source. It is
documented and convenient, and `-l` would still do the same thing.

### The suffix list, and how it is compared

`.db`, `.sqlite`, `.sqlite3` — the three conventional SQLite spellings. The tool's own
default is `ebdx.db`, so the rule agrees with what it already produces.

Comparison is case-insensitive, matching how `epub-indexing` already matches `.epub`
("Extension matching ignores case"); `library.SQLite` is accepted.

A path of exactly `.db` is refused, and needs no special rule to be: a leading dot makes it a
stem rather than a suffix, so it carries no extension at all. This matters because `-d.db`
is itself a plausible glued fragment.

### The not-found message names the source of the path, not the option unconditionally

`No database found at: une (given as -d/--database)` is only true when the option was given.
When the path came from the default location, saying so would be false, so the message names
whichever source actually supplied it — the option, or the default data directory. A reader
who sees a path they did not type next to the option that carried it has the whole diagnosis.

### The `--` hint is attached to usage errors, not to individual commands

The hint belongs wherever argument parsing reports a rejected command line, so it is added
once, at the command class that renders usage errors, and applies to every subcommand. It
fires when the rejected command line carries a token beginning with a single dash — which is
a fact about the input, not an inference about intent.

**Alternative rejected:** `ignore_unknown_options`, so unknown dashed tokens fall through to
the argument. It fixes only the tokens that are *not* options: `-d` and `-l` are known, so
`-dune` and `-lord` keep their current behaviour. It also turns a mistyped real option into
silent query text, which is a worse failure than the one being fixed.

## Risks / Trade-offs

- **A user who wants an extension-less database cannot create one directly.** → The refusal
  names the accepted suffixes, and an existing file at that path is still opened, so the
  escape hatch is to create the file before pointing `ebdx` at it. Judged acceptable: the
  cost is one explicit error on an unusual request, against a silent stray file on a common
  typo.
- **The rule does not catch every glued fragment.** A fragment that happens to end in a
  database suffix is still created. No fragment of `-d`, `-l` or their long forms produces
  one, and the residue is a path the user typed something very like on purpose.
- **`ebdx index ~/books -d mylibrary` changes behaviour for anyone relying on it.** → Named
  as BREAKING in the proposal; pre-1.0, no packaged release, and the message says exactly
  what to type instead.

## Migration Plan

No data migration. Existing databases are opened by the existing-file rule whatever they are
named, so no user action is required. The only behaviour change lands on creation.

## Open Questions

None.
