## Why

`search` passes its argument straight to FTS5, so the user's text is read as an expression
in a query language they did not ask to write. An apostrophe opens a string literal, a
hyphen begins a column exclusion, a comma or full stop is not in the grammar at all — so
`Ender's`, `-Dune`, `Dune, Messiah` and `Mr. Mercedes` are all reported as bad queries
rather than searched for.

The current answer is a heuristic: try the query as FTS5, and if it fails, decide from its
shape whether the user meant syntax or prose, requoting only in the second case. That gate
has now been wrong four times in a row, and each correction found the next variant rather
than the last one:

1. it swallowed `-Dune`, searching for the term the user asked to exclude;
2. it rejected every punctuation mark but apostrophe and hyphen;
3. it missed `OR,` because it compared whitespace words, not tokens;
4. it missed `OR,Foundation`, and then rejected `R_AND_D, Inc.` because its own tokenizer
   split on an underscore that FTS5 treats as part of a bareword.

The supply of variants is unbounded, because the heuristic is an approximation of FTS5's
lexer maintained separately from FTS5's lexer. This is the same reasoning that led
`cli-runtime` to decline to predict unrecognised database layouts: a copy of another
component's rules drifts from them, and a missed corner is a silent wrong answer.

## What Changes

- **`search` treats its argument as literal text by default.** Every whitespace-separated
  word is quoted as an FTS5 string and the words are ANDed, so any text whatsoever is a
  valid search and no ordinary title can be reported as a malformed query.
- **Add `--fts` (alias `--raw`) to opt into FTS5 expression syntax.** Under it the query is
  passed through verbatim, and a query FTS5 cannot parse is reported and exits non-zero, as
  every query does today.
- **Remove the heuristic.** `_is_plain_text`, `_tokens`, the metacharacter set and the
  keyword set all go; nothing has to guess what the user meant, because the user says.

## Impact

- Affected specs: `book-search`
- Affected code: `src/ebdx/db.py` (`resolve_query`, `search_books`, `validate_query`),
  `src/ebdx/cli.py` (the `search` command), `README.md`
- **Behaviour change.** `ebdx search "title:Dune"` now searches for the literal word
  `title:Dune` and finds nothing; the operator forms need `--fts`. Every documented
  operator example in the README moves under the flag. This is the deliberate cost of
  making the common case — typing a title — correct without guessing.
