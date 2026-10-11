## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Search records preserve result fields

Structured search records SHALL include `id`, `title`, `author`, `series`,
`series_index`, and the absolute `path`. Missing series indexes SHALL serialize as JSON
null or an empty CSV cell.

#### Scenario: A result lacks series data

- **WHEN** a matching book has no series index
- **THEN** its structured record preserves that absence without the string `None`
