"""Shared command result serialization and listing policy."""

import csv
import io
import json
import math
from dataclasses import dataclass

import click


def output_format() -> str:
    ctx = click.get_current_context(silent=True)
    return (ctx.find_object(dict) or {}).get("format", "table") if ctx else "table"


def limit_option(fn):
    return click.option(
        "--limit",
        "-l",
        type=click.IntRange(min=0),
        default=20,
        show_default=True,
        help="Maximum records to show; 0 shows all records.",
    )(fn)


@dataclass
class Listing:
    rows: list
    total: int

    @classmethod
    def bounded(cls, rows: list, limit: int, *, total: int | None = None):
        return cls(rows[:limit] if limit else rows, len(rows) if total is None else total)

    @property
    def truncated(self) -> bool:
        return len(self.rows) < self.total

    def title(self, default: str) -> str:
        return f"Showing {len(self.rows)} of {self.total}" if self.truncated else default

    def notice(self) -> None:
        if self.truncated:
            click.echo(
                f"Showing {len(self.rows)} of {self.total} records (--limit 0 shows all).", err=True
            )


def emit(records: list[dict], fields: tuple[str, ...], *, single: bool = False) -> None:
    """Write complete records without Rich markup, wrapping, or truncation."""
    records = [{key: _finite(row.get(key)) for key in fields} for row in records]
    fmt = output_format()
    if fmt == "json":
        payload = records[0] if single else records
        click.echo(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    elif fmt == "jsonl":
        for row in records:
            click.echo(json.dumps(row, ensure_ascii=False, allow_nan=False))
    elif fmt == "csv":
        ctx = click.get_current_context()
        if (ctx.find_object(dict) or {}).get("safe_csv", True):
            records = [
                {key: _spreadsheet_cell(value) for key, value in row.items()} for row in records
            ]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
        click.echo(buffer.getvalue(), nl=False)


def _finite(value):
    """Map NaN/Infinity to null so JSON output stays standards-compliant."""
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _spreadsheet_cell(value):
    """Escape formula prefixes and leading control characters in text cells."""
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value
