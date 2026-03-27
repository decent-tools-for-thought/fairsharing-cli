from __future__ import annotations

import json

import pytest

from fairsharing_cli.core import (
    RenderOptions,
    parse_json_body,
    parse_kv_pairs,
    parse_select,
    render,
)


def test_parse_json_body_inline() -> None:
    body = parse_json_body('{"x": 1}', None)
    assert body == {"x": 1}


def test_parse_json_body_invalid() -> None:
    with pytest.raises(ValueError):
        parse_json_body("{", None)


def test_parse_json_body_requires_object() -> None:
    with pytest.raises(ValueError):
        parse_json_body("[]", None)


def test_parse_kv_pairs() -> None:
    assert parse_kv_pairs(["a=1", "b=2"]) == {"a": "1", "b": "2"}


def test_parse_kv_pairs_invalid() -> None:
    with pytest.raises(ValueError):
        parse_kv_pairs(["bad"])


def test_parse_select() -> None:
    assert parse_select("a, b , ,c") == ["a", "b", "c"]


def test_render_jsonl_list(capsys: pytest.CaptureFixture[str]) -> None:
    render([{"x": 1}, {"x": 2}], options=RenderOptions(output="jsonl"))
    out = capsys.readouterr().out.strip().splitlines()
    assert json.loads(out[0]) == {"x": 1}
    assert json.loads(out[1]) == {"x": 2}
