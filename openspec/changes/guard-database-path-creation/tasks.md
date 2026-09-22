## 1. The creation guard

- [ ] 1.1 Add a path check shared by every command that resolves `--database`, accepting a
      path that already exists or whose suffix is `.db`/`.sqlite`/`.sqlite3` compared
      case-insensitively; verify with unit tests over `une`, `mylibrary`, `.db`, `ebdx.db`
      and `library.SQLite`
- [ ] 1.2 Refuse creation in `index` when the check fails, naming the accepted suffixes and
      exiting non-zero; verify `ebdx index <dir> -dune` leaves no file in the working
      directory
- [ ] 1.3 Apply the refusal under `--dry-run` as well, reporting the same message and
      creating nothing; verify the dry-run and real verdicts agree

## 2. Reporting

- [ ] 2.1 Name the source of the path in both `No database found at:` sites -- the option
      when `--database` was given, the default location otherwise; verify `ebdx search
      -dune Foundation` names `-d/--database` and that a default-path run does not
- [ ] 2.2 Add the `--` explanation to usage errors raised for a command line carrying a
      token that begins with a dash, one dash or two; verify `ebdx search -Dune`, `ebdx
      search -dune` and `ebdx search --Dune` all carry the hint and still exit non-zero

## 3. Tests

- [ ] 3.1 `index` with a glued short option creates nothing, in both normal and dry-run modes
- [ ] 3.2 An existing extension-less database is still opened, indexed into, and searched
- [ ] 3.3 A refused path reports the accepted suffixes and exits non-zero
- [ ] 3.4 The not-found message names the option, and names the default location when no
      option was given
- [ ] 3.5 A dashed argument after `--` is read as text, in both the `-Dune` and `--Dune`
      shapes, for `search` and for `index`
- [ ] 3.6 Pin the guard's known limitation: `ebdx index <dir> -database.db` still creates
      `atabase.db`, because the fragment names a database. Assert the current behaviour so
      the boundary is recorded rather than assumed

## 4. Documentation

- [ ] 4.1 README: the naming rule for a database that does not yet exist, and the `--`
      separator alongside the existing search note
