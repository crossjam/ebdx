## 1. Query handling

- [x] 1.1 Replace `resolve_query` with a literal-quoting path and an expression path
- [x] 1.2 Delete `_is_plain_text`, `_tokens`, `_FTS_METACHARACTERS`, `_FTS_KEYWORDS`
- [x] 1.3 Give `search_books` an `fts` parameter, defaulting to literal
- [x] 1.4 Scope `validate_query` to expression mode

## 2. CLI

- [x] 2.1 Add `--fts` / `--raw` to the `search` command
- [x] 2.2 Pass the flag through the dry-run preflight as well as the real search

## 3. Tests

- [x] 3.1 Punctuated titles, including `R_AND_D, Inc.`, searched literally
- [x] 3.2 Operator-like text (`AND`, `-Dune`, `badcol:Dune`, unbalanced quote) literal by default
- [x] 3.3 Operator forms working under `--fts`, and malformed ones still erroring there
- [x] 3.4 Multi-word queries matching non-adjacent words
- [x] 3.5 Dry-run search agreeing with the real search in both modes

## 4. Documentation

- [x] 4.1 README: literal default, every operator example moved under `--fts`
