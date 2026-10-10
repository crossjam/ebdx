## Reuse sqlite-utils' callbacks

`ebdx sql search` and `ebdx sql analyze-tables` follow the existing SQL wrappers and
invoke the corresponding sqlite-utils Click callbacks through `_invoke`. This preserves
sqlite-utils' output formatting and option handling while the existing database factory
replacement supplies ebdx’s read-only connection.

`search` accepts the sqlite-utils content table, query, ordering, selected columns, row
limit, `--quote`, and `--sql` options.
sqlite-utils joins the selected table to its FTS index internally.
It remains a raw power-user interface; the top-level `ebdx search` command remains the
friendly literal-by-default search command.

`analyze-tables` always passes `save=False`. The command reports its analysis but cannot
create sqlite-utils' `_analyze_tables` table.
Its table and column filters and reporting options are forwarded unchanged.

## Deliberate exclusions

The sqlite-utils `memory` command imports arbitrary CSV, JSON, or stdin data into a
separate in-memory database.
It is not an inspection command for the selected ebdx database, so it stays out of
`ebdx sql`.

The `plugins` command lists installed sqlite-utils plugins and does not inspect the
library database. It is environment inventory rather than an ebdx SQL capability, so it
also stays out.
