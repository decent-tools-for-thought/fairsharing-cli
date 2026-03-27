from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

OPENAPI_URL = "https://api.fairsharing.org/openapi.json"


def fetch_openapi(timeout: float) -> dict[str, Any]:
    response = httpx.get(OPENAPI_URL, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected OpenAPI payload format")
    return payload


def save_openapi(path: Path, spec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")


def list_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []
    operations: list[dict[str, Any]] = []
    for path, methods in paths.items():
        if not isinstance(path, str) or not isinstance(methods, dict):
            continue
        for method, detail in methods.items():
            if not isinstance(method, str) or not isinstance(detail, dict):
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": detail.get("summary"),
                    "description": detail.get("description"),
                    "parameters": detail.get("parameters", []),
                    "has_request_body": bool(detail.get("requestBody")),
                    "security": detail.get("security", []),
                }
            )
    operations.sort(key=lambda item: (str(item["path"]), str(item["method"])))
    return operations


def get_operation(spec: dict[str, Any], *, method: str, path: str) -> dict[str, Any] | None:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return None
    path_node = paths.get(path)
    if not isinstance(path_node, dict):
        return None
    op = path_node.get(method.lower())
    if not isinstance(op, dict):
        return None
    return op
