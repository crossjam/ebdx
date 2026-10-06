## Context

`search_books` hands its query to `books_fts MATCH ?`, so the argument is an FTS5
expression. FTS5's grammar claims `"`, `:`, `*`, `(`, `)`, `{`, `}`, `^`, `+` and a leading
`-`, and rejects anything else that is not a bareword character — which is most punctuation.
Ordinary titles therefore fail to parse.

The heuristic that preceded this change tried to tell "meant syntax" from "meant prose" by
inspecting the failed query. Four successive corrections each found a new variant: a leading
hyphen silently inverting the user's intent, punctuation beyond apostrophe and hyphen still
rejected, `OR,` slipping past a whitespace-word comparison, `OR,Foundation` slipping past an
end-stripping one, and finally `R_AND_D, Inc.` rejected because the replacement tokenizer
split on an underscore that FTS5 counts as a bareword character.

That last one is the tell. Each fix brought the gate closer to being a copy of FTS5's lexer,
and the gap between a copy and the original is where the bugs live. `cli-runtime` already
settled this argument once, in "Prediction is exact for databases the tool produced": it
declines to reimplement the schema-setup path and reports rather than guesses, because a
copy drifts and a missed corner is a silent wrong answer.

## Goals / Non-Goals

- **Goals:** any text is a valid search; the engine's syntax stays available; no component
  approximates FTS5's grammar.
- **Non-Goals:** inferring intent from the query's shape; supporting a middle mode that is
  partly literal and partly interpreted.

## Decisions

### The default is literal, and the syntax is opt-in

The user knows whether they are typing a title or writing an expression, and saying so is
cheaper than any inference from the text. The default serves the common case — a title,
possibly punctuated — and cannot fail.

**Alternative rejected:** keep the heuristic and fix the fifth variant. The supply is
unbounded and every fix widens the surface the next one must cover.

**Alternative rejected:** default to expression syntax and add `--literal`. This leaves the
failing case as the default, which is the bug being fixed.

### Literal queries are quoted per word and ANDed

`Ender's Game` becomes `"Ender's" "Game"`, which FTS5 reads as both terms in any position,
not as a phrase. A phrase would silently narrow the result to adjacent occurrences.

### The flag is `--fts`, with `--raw` accepted as an alias

`--fts` names the thing being enabled. `--raw` reads naturally for anyone thinking "don't
touch my input" and costs one line to accept.

### `validate_query` keeps its role, scoped to expression mode

The dry-run preflight settles a query error before reporting on the database. Under literal
mode there is nothing to settle, so it becomes a no-op; under `--fts` it behaves as now.

## Risks / Trade-offs

- **Breaking change for anyone using operator syntax.** `ebdx search "title:Dune"` now finds
  nothing rather than filtering. Mitigated by `--fts`, by moving every README operator
  example under the flag, and by the project being pre-1.0 with no packaged release.
- **A literal query can silently find nothing** where an expression would have matched —
  the inverse of today's failure. Judged the better direction: a search that returns no
  results is an ordinary outcome, where an error on a valid title is a wall.
