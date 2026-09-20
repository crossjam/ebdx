## 1. Query handling

- [ ] 1.1 Replace `resolve_query` with a literal-quoting path and an expression path
- [ ] 1.2 Delete `_is_plain_text`, `_tokens`, `_FTS_METACHARACTERS`, `_FTS_KEYWORDS`
- [ ] 1.3 Give `search_books` an `fts` parameter, defaulting to literal
- [ ] 1.4 Scope `validate_query` to expression mode

## 2. CLI

- [ ] 2.1 Add `--fts` / `--raw` to the `search` command
- [ ] 2.2 Pass the flag through the dry-run preflight as well as the real search

## 3. Tests

- [ ] 3.1 Punctuated titles, including `R_AND_D, Inc.`, searched literally
- [ ] 3.2 Operator-like text (`AND`, `-Dune`, `badcol:Dune`, unbalanced quote) literal by default
- [ ] 3.3 Operator forms working under `--fts`, and malformed ones still erroring there
- [ ] 3.4 Multi-word queries matching non-adjacent words
- [ ] 3.5 Dry-run search agreeing with the real search in both modes

## 4. Documentation

- [ ] 4.1 README: literal default, every operator example moved under `--fts`
