## ADDED Requirements

### Requirement: A query is literal text unless declared otherwise

The `search` command SHALL treat its query argument as literal text by default, matching
books that contain those words. Any text whatsoever SHALL be a usable query: no input in
this mode can be reported as malformed, whatever punctuation or operator-like wording it
carries.

The command SHALL accept an option that instead passes the query to the full-text engine as
an expression, enabling the engine's own syntax for column filters, boolean operators,
prefixes, proximity and phrases.

#### Scenario: A punctuated title is searched for

- **WHEN** a query carrying an apostrophe, hyphen, comma, full stop or other punctuation is
  issued without the expression option
- **THEN** the words are searched for literally, matching books are returned, and no query
  error is reported

#### Scenario: Operator-like text is still literal

- **WHEN** a query that resembles engine syntax -- a bare `AND`, a leading `-`, a
  `name:value` pair, an unbalanced quote -- is issued without the expression option
- **THEN** it is searched for as literal words rather than interpreted or rejected

#### Scenario: Underscores and other bareword punctuation are ordinary

- **WHEN** a query such as `R_AND_D, Inc.` is issued without the expression option
- **THEN** it is searched for literally, with no part of it treated as an operator

#### Scenario: Expression syntax is available on request

- **WHEN** a query using column-filter, boolean, prefix or phrase syntax is issued with the
  expression option
- **THEN** the engine interprets it as an expression and the matching books are returned

#### Scenario: Words are matched together, not as a phrase

- **WHEN** a multi-word query is issued without the expression option
- **THEN** a book containing all of those words matches, whether or not they are adjacent

## MODIFIED Requirements

### Requirement: Malformed queries do not crash

Search SHALL report an error message and exit non-zero when a query given as a full-text
expression cannot be parsed by the engine, rather than presenting a traceback. A query taken
as literal text cannot be malformed and SHALL always be searched for.

#### Scenario: Unparseable query

- **WHEN** a query containing unbalanced full-text syntax is issued as an expression
- **THEN** an error message is shown, no traceback is printed, and the exit status is
  non-zero

#### Scenario: Punctuation in an ordinary query

- **WHEN** a query such as a title containing an apostrophe or hyphen is issued
- **THEN** it is treated as a search for those words and matching books are returned
