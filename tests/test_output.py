"""Tests for structured output serialization."""

import json

import click
from click.testing import CliRunner

from ebdx.output import emit


def test_emit_json_maps_non_finite_floats_to_null():
    @click.command()
    @click.pass_context
    def cmd(ctx):
        ctx.obj = {"format": "json"}
        emit([{"a": float("inf"), "b": float("nan"), "c": 1.5}], ("a", "b", "c"))

    result = CliRunner().invoke(cmd)
    assert json.loads(result.output, parse_constant=lambda c: 1 / 0) == [
        {"a": None, "b": None, "c": 1.5}
    ]
