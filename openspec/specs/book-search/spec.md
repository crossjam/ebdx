# book-search Specification

## Purpose
Querying the indexed library by free text and presenting the matches, so a reader can find a book by remembering part of its title, author, or series and then locate the file on disk.

## Requirements

### Requirement: Search matches indexed metadata

The `search` command SHALL return books whose title, author name, series, or tags match the query, ordered by relevance.

#### Scenario: Title match

- **WHEN** a query matching an indexed book's title is issued
- **THEN** that book is returned

#### Scenario: Author match

- **WHEN** a query matching an indexed book's author name is issued
- **THEN** that author's books are returned

#### Scenario: No matches

- **WHEN** a query matches nothing in the library
- **THEN** the command reports no results and exits successfully

### Requirement: Results identify the file on disk

Each search result SHALL carry the book's title, author, series, series index, and the absolute path of the EPUB it came from.

#### Scenario: Path accompanies each hit

- **WHEN** a search returns a book
- **THEN** the result includes the absolute path of the EPUB that produced it

#### Scenario: Books lacking series data still render

- **WHEN** a returned book has no series or series index
- **THEN** the result is displayed with those fields blank rather than failing

### Requirement: Result count is bounded

Search SHALL accept `--limit/-l`, returning at most the specified positive number of
results and defaulting to 20. Zero SHALL mean unlimited; negative limits SHALL be
rejected. Matching and relevance ordering SHALL be identical in all formats.
Truncated output SHALL report the displayed count and exact total match count, in the
table title for human output and on stderr for structured output.

#### Scenario: Limit is respected

- **WHEN** more books match than the requested positive limit
- **THEN** no more than that many results are returned and the total is reported

#### Scenario: Default limit

- **WHEN** no limit is given
- **THEN** at most 20 results are returned

#### Scenario: Unlimited search

- **WHEN** zero is supplied as the limit
- **THEN** every matching book is returned in relevance order

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

### Requirement: Searching without a library is explained

Search SHALL tell the user how to build an index when the target database does not exist, and SHALL exit non-zero.

#### Scenario: No database yet

- **WHEN** `search` is run and no database file exists at the resolved path
- **THEN** the message names the missing path, points at the `index` command, and the exit status is non-zero

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

#### Scenario: A query holding no words matches nothing

- **WHEN** a query that is empty or contains only whitespace is issued without the expression
  option
- **THEN** no books are returned, no error is reported, and the exit status is zero

### Requirement: Search records preserve result fields

Structured search records SHALL include `id`, `title`, `author`, `series`,
`series_index`, and the absolute `path`. Missing series indexes SHALL serialize as JSON
null or an empty CSV cell.

#### Scenario: A result lacks series data

- **WHEN** a matching book has no series index
- **THEN** its structured record preserves that absence without the string `None`
