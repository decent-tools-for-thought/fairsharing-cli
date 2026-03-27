from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fairsharing_cli import cli
from fairsharing_cli.client import ApiError
from fairsharing_cli.config import AppConfig, ResolvedSettings


def _patch_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli,
        "resolve_settings",
        lambda **_: ResolvedSettings(
            base_url="https://api.fairsharing.org",
            token="tok",
            email="u@example.org",
            password="pw",
            timeout=30.0,
        ),
    )


def test_auth_whoami_calls_users_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_call(
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        calls.append((method, path))
        return {"id": 1}

    monkeypatch.setattr(cli, "_call", fake_call)
    rc = cli.main(["auth", "whoami"])
    assert rc == 0
    assert calls == [("GET", "/users/edit")]


def test_auth_logout_requires_action(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    rc = cli.main(["auth", "logout"])
    assert rc == 2


def test_records_resolve_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    attempts: list[str] = []

    def fake_call(
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        attempts.append(path)
        if len(attempts) < 3:
            raise ApiError("not found", status_code=404)
        return {"id": 7}

    monkeypatch.setattr(cli, "_call", fake_call)
    rc = cli.main(["records", "resolve", "7"])
    assert rc == 0
    assert attempts[-1] == "/fairsharing_records/7"


def test_records_search_expand(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)

    def fake_call(
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        if path == "/search/fairsharing_records/":
            return [{"id": 2}, {"id": 1}]
        if path == "/fairsharing_records/1":
            return {"id": 1, "name": "one"}
        if path == "/fairsharing_records/2":
            return {"id": 2, "name": "two"}
        raise AssertionError(path)

    monkeypatch.setattr(cli, "_call", fake_call)
    rc = cli.main(["records", "search-expand", "--q", "x", "--limit", "2", "--concurrency", "2"])
    assert rc == 0


def test_list_all_type_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    rc = cli.main(["list-all", "--family", "subjects", "--type", "x"])
    assert rc == 2


def test_export_search_writes_jsonl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_defaults(monkeypatch)
    monkeypatch.setattr(cli, "_call", lambda *_a, **_k: [{"id": 1}, {"id": 2}])
    out = tmp_path / "out.jsonl"
    rc = cli.main(
        [
            "export",
            "search",
            "--family",
            "organisations",
            "--q",
            "EMBL",
            "--out",
            str(out),
            "--format",
            "jsonl",
        ]
    )
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0]) == {"id": 1}


def test_export_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_defaults(monkeypatch)

    def fake_call(
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        rid = int(path.rsplit("/", 1)[-1])
        return {"id": rid}

    monkeypatch.setattr(cli, "_call", fake_call)
    out = tmp_path / "records.json"
    rc = cli.main(
        [
            "export",
            "records",
            "--ids",
            "3,1",
            "--out",
            str(out),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0]["id"] == 1


def test_maintain_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    seen: list[dict[str, Any]] = []

    def fake_run(
        _args: Any,
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> int:
        seen.append({"method": method, "path": path, "body": body})
        return 0

    monkeypatch.setattr(cli, "_run_simple_request", fake_run)
    rc = cli.main(["maintain", "request", "--record", "10", "--status", "approved"])
    assert rc == 0
    assert seen[0]["body"] == {"fairsharing_record_id": 10, "status": "approved"}


def test_docs_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    monkeypatch.setattr(
        cli,
        "fetch_openapi",
        lambda timeout: {"paths": {"/routes": {"get": {"summary": "x"}}}},
    )
    rc = cli.main(["docs", "endpoint", "--method", "GET", "--path", "/routes"])
    assert rc == 0


def test_batch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_defaults(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_call(
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        calls.append((method, path))
        return {"ok": True}

    monkeypatch.setattr(cli, "_call", fake_call)
    ops = tmp_path / "ops.jsonl"
    ops.write_text(
        '{"method":"GET","path":"/routes"}\n{"method":"POST","path":"/search/organisations/"}\n',
        encoding="utf-8",
    )
    rc = cli.main(["batch", "--file", str(ops)])
    assert rc == 0
    assert calls == [("GET", "/routes"), ("POST", "/search/organisations/")]
