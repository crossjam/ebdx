## Purpose

Querying the indexed library by free text and presenting the matches, so a reader can find a book by remembering part of its title, author, or series and then locate the file on disk.

## ADDED Requirements

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

Search SHALL return at most a caller-specified number of results, defaulting to 20.

#### Scenario: Limit is respected

- **WHEN** more books match than the requested limit
- **THEN** no more than that many results are returned

#### Scenario: Default limit

- **WHEN** no limit is given
- **THEN** at most 20 results are returned

### Requirement: Malformed queries do not crash

Search SHALL report an error message and exit non-zero when the query cannot be parsed by the full-text engine, rather than presenting a traceback.

#### Scenario: Unparseable query

- **WHEN** a query containing unbalanced full-text syntax is issued
- **THEN** an error message is shown, no traceback is printed, and the exit status is non-zero

#### Scenario: Punctuation in an ordinary query

- **WHEN** a query such as a title containing an apostrophe or hyphen is issued
- **THEN** it is treated as a search for those words and matching books are returned

### Requirement: Searching without a library is explained

Search SHALL tell the user how to build an index when the target database does not exist, and SHALL exit non-zero.

#### Scenario: No database yet

- **WHEN** `search` is run and no database file exists at the resolved path
- **THEN** the message names the missing path, points at the `index` command, and the exit status is non-zero
