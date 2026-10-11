## 1. Add read-only SQL extras

- [x] 1.1 Add the `search` wrapper with sqlite-utils' FTS and output options.
- [x] 1.2 Add the `analyze-tables` wrapper without the mutating `--save` option.
- [x] 1.3 Keep `memory` and `plugins` out of the command group and record why.

## 2. Test and document the extras

- [x] 2.1 Test FTS search output, quoting, and selected output options.
- [x] 2.2 Test table analysis output and verify it does not create `_analyze_tables`.
- [x] 2.3 Document the new commands and deliberate exclusions in the CLI documentation.
