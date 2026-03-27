from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import FairsharingClient, RequestSpec

OutputFormat = str


@dataclass(slots=True)
class RenderOptions:
    output: OutputFormat = "json"
    select: list[str] | None = None
    raw: bool = False


def parse_json_body(json_str: str | None, json_file: str | None) -> dict[str, Any] | None:
    if json_str and json_file:
        raise ValueError("Provide either --json or --json-file, not both")
    if not json_str and not json_file:
        return None
    if json_file:
        payload = Path(json_file).read_text(encoding="utf-8")
    else:
        payload = json_str or ""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be a JSON object")
    return parsed


def parse_select(select_arg: str | None) -> list[str] | None:
    if not select_arg:
        return None
    fields = [f.strip() for f in select_arg.split(",") if f.strip()]
    return fields or None


def execute_operation(
    client: FairsharingClient,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> Any:
    return client.request(RequestSpec(method=method, path=path, params=params, json_body=body))


def render(payload: Any, options: RenderOptions) -> None:
    data = payload
    if not options.raw and options.select:
        data = _apply_select(data, options.select)
    if options.output == "json":
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if options.output == "jsonl":
        if isinstance(data, list):
            for item in data:
                print(json.dumps(item, sort_keys=True, ensure_ascii=False))
            return
        print(json.dumps(data, sort_keys=True, ensure_ascii=False))
        return
    if options.output == "text":
        _render_text(data)
        return
    raise ValueError(f"Unsupported output mode: {options.output}")


def _apply_select(payload: Any, fields: list[str]) -> Any:
    if isinstance(payload, dict):
        return {key: payload.get(key) for key in fields}
    if isinstance(payload, list):
        result: list[Any] = []
        for item in payload:
            if isinstance(item, dict):
                result.append({key: item.get(key) for key in fields})
            else:
                result.append(item)
        return result
    return payload


def _render_text(payload: Any) -> None:
    if isinstance(payload, list):
        for idx, item in enumerate(payload, 1):
            print(f"[{idx}] {_summarize_item(item)}")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {_render_scalar(value)}")
        return
    print(_render_scalar(payload))


def _summarize_item(item: Any) -> str:
    if isinstance(item, dict):
        preferred = ["id", "identifier", "name", "title", "type", "email", "doi"]
        values = [f"{k}={item[k]}" for k in preferred if k in item and item[k] is not None]
        if values:
            return ", ".join(values)
        keys = list(item.keys())[:3]
        return ", ".join(f"{k}={item[k]}" for k in keys)
    return _render_scalar(item)


def _render_scalar(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def parse_kv_pairs(pairs: Iterable[str] | None) -> dict[str, str] | None:
    if not pairs:
        return None
    result: dict[str, str] = {}
    for entry in pairs:
        if "=" not in entry:
            raise ValueError(f"Invalid --param value '{entry}', expected key=value")
        key, value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Parameter name cannot be empty")
        result[key] = value
    return result


def stderr(message: str) -> None:
    print(message, file=sys.stderr)
