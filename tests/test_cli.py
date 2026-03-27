from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from fairsharing_cli import cli
from fairsharing_cli.config import AppConfig, ResolvedSettings


@dataclass
class _Capture:
    method: str
    path: str
    params: dict[str, Any] | None
    body: dict[str, Any] | None


def _patch_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli,
        "resolve_settings",
        lambda **_: ResolvedSettings(
            base_url="https://api.fairsharing.org",
            token=None,
            email=None,
            password=None,
            timeout=30.0,
        ),
    )


def test_bare_invocation_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main([])
    assert rc == 0
    assert "usage: fairsharing" in capsys.readouterr().out


def test_top_level_help() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("argv", "method", "path", "params", "body"),
    [
        (["routes"], "GET", "/routes", None, None),
        (
            ["fairsharing-records", "list", "--page-number", "2", "--page-size", "20"],
            "GET",
            "/fairsharing_records",
            {"page[number]": 2, "page[size]": 20},
            None,
        ),
        (
            ["fairsharing-record", "by-doi", "10.1/abc"],
            "GET",
            "/fairsharing_record/10.1/abc",
            None,
            None,
        ),
        (["subjects", "get", "5"], "GET", "/subjects/5", None, None),
        (
            ["standards", "by-type", "minimal_reporting_guideline"],
            "GET",
            "/standards/minimal_reporting_guideline",
            None,
            None,
        ),
        (
            ["search", "organisations", "--q", "EMBL"],
            "POST",
            "/search/organisations/",
            {"q": "EMBL"},
            None,
        ),
        (
            ["users", "password-reset-request", "--login", "u@example.org"],
            "POST",
            "/users/password",
            {"login": "u@example.org"},
            None,
        ),
        (["user-admin", "delete", "9"], "DELETE", "/user_admin/9", {"id": 9}, None),
    ],
)
def test_parser_dispatches_expected_operations(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    method: str,
    path: str,
    params: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> None:
    _patch_defaults(monkeypatch)
    captured: list[_Capture] = []

    def fake_run(
        _args: Any,
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> int:
        captured.append(_Capture(method=method, path=path, params=params, body=body))
        return 0

    monkeypatch.setattr(cli, "_run_simple_request", fake_run)
    rc = cli.main(argv)
    assert rc == 0
    assert captured == [_Capture(method=method, path=path, params=params, body=body)]


def test_create_requires_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    rc = cli.main(["grants", "create"])
    assert rc == 2


def test_api_call_parses_query_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    captured: list[_Capture] = []

    def fake_run(
        _args: Any,
        _ctx: Any,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> int:
        captured.append(_Capture(method=method, path=path, params=params, body=body))
        return 0

    monkeypatch.setattr(cli, "_run_simple_request", fake_run)
    rc = cli.main(
        [
            "api-call",
            "--method",
            "POST",
            "--path",
            "/grants",
            "--param",
            "q=x",
            "--json",
            '{"name": "G"}',
        ]
    )
    assert rc == 0
    assert captured[0].params == {"q": "x"}
    assert captured[0].body == {"name": "G"}


def test_users_sign_in_save_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_defaults(monkeypatch)
    monkeypatch.setattr(
        cli,
        "resolve_settings",
        lambda **_: ResolvedSettings(
            base_url="https://api.fairsharing.org",
            token=None,
            email="u@example.org",
            password="pw",
            timeout=30.0,
        ),
    )

    class DummyClient:
        def close(self) -> None:
            return None

    monkeypatch.setattr(cli, "_with_client", lambda _ctx: DummyClient())
    monkeypatch.setattr(
        cli,
        "execute_operation",
        lambda *_args, **_kwargs: {"jwt": "token-123"},
    )
    written: list[AppConfig] = []
    monkeypatch.setattr(cli, "save_config", lambda cfg: written.append(cfg))

    rc = cli.main(["users", "sign-in", "--save-token"])
    assert rc == 0
    assert written
    assert written[-1].token == "token-123"


def test_docs_openapi(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch)
    monkeypatch.setattr(
        cli, "fetch_openapi", lambda timeout: {"openapi": "3.1.0", "timeout": timeout}
    )

    rc = cli.main(["docs", "openapi"])
    assert rc == 0


def test_every_api_operation_has_wrapper_command() -> None:
    parser = cli.build_parser()
    operations: dict[tuple[str, str], list[str]] = {
        ("GET", "/routes"): ["routes"],
        ("GET", "/fairsharing_records"): ["fairsharing-records", "list"],
        (
            "POST",
            "/fairsharing_records",
        ): [
            "fairsharing-records",
            "create",
            "--json",
            '{"metadata": {"name": "n", "status": "ready"}, "record_type_id": 1}',
        ],
        ("GET", "/fairsharing_records/{id}"): ["fairsharing-records", "get", "1"],
        (
            "PUT",
            "/fairsharing_records/{id}",
        ): [
            "fairsharing-records",
            "update",
            "1",
            "--json",
            '{"metadata": {"name": "n", "status": "ready"}, "record_type_id": 1}',
        ],
        ("DELETE", "/fairsharing_records/{id}"): ["fairsharing-records", "delete", "1"],
        ("GET", "/fairsharing_records/can_edit/{id}"): ["fairsharing-records", "can-edit", "1"],
        ("GET", "/fairsharing_record/{doi}"): ["fairsharing-record", "by-doi", "10.1/x"],
        ("GET", "/fairsharing_record/{legacy_id}"): ["fairsharing-record", "by-legacy-id", "abc"],
        ("GET", "/subjects"): ["subjects", "list"],
        ("GET", "/subjects/{id}"): ["subjects", "get", "1"],
        ("GET", "/domains"): ["domains", "list"],
        ("GET", "/domains/{id}"): ["domains", "get", "1"],
        ("GET", "/taxonomies"): ["taxonomies", "list"],
        ("GET", "/taxonomies/{id}"): ["taxonomies", "get", "1"],
        ("GET", "/user_defined_tags"): ["user-defined-tags", "list"],
        ("POST", "/user_defined_tags"): [
            "user-defined-tags",
            "create",
            "--json",
            '{"name": "tag"}',
        ],
        ("GET", "/user_defined_tags/{id}"): ["user-defined-tags", "get", "1"],
        ("PUT", "/user_defined_tags/{id}"): [
            "user-defined-tags",
            "update",
            "1",
            "--json",
            '{"name": "tag2"}',
        ],
        ("DELETE", "/user_defined_tags/{id}"): ["user-defined-tags", "delete", "1"],
        ("GET", "/organisation_links"): ["organisation-links", "list"],
        ("POST", "/organisation_links"): [
            "organisation-links",
            "create",
            "--json",
            '{"fairsharing_record_id": 1, "organisation_id": 2, "relation": "funds"}',
        ],
        ("GET", "/organisation_links/{id}"): ["organisation-links", "get", "1"],
        ("PUT", "/organisation_links/{id}"): [
            "organisation-links",
            "update",
            "1",
            "--json",
            '{"relation": "maintains"}',
        ],
        ("DELETE", "/organisation_links/{id}"): ["organisation-links", "delete", "1"],
        ("GET", "/grants"): ["grants", "list"],
        ("POST", "/grants"): ["grants", "create", "--json", '{"name": "g"}'],
        ("GET", "/grants/{id}"): ["grants", "get", "1"],
        ("PUT", "/grants/{id}"): ["grants", "update", "1", "--json", '{"name": "g2"}'],
        ("DELETE", "/grants/{id}"): ["grants", "delete", "1"],
        ("GET", "/licences"): ["licences", "list"],
        ("GET", "/licences/{id}"): ["licences", "get", "1"],
        ("GET", "/organisations"): ["organisations", "list"],
        ("GET", "/organisations/{id}"): ["organisations", "get", "1"],
        ("GET", "/standards"): ["standards", "list"],
        ("GET", "/standard/{id}"): ["standards", "get", "--id", "FSR0001"],
        ("GET", "/standards/{type}"): ["standards", "by-type", "minimal_reporting_guideline"],
        ("GET", "/policies"): ["policies", "list"],
        ("GET", "/policy/{id}"): ["policies", "get", "--id", "FSP0001"],
        ("GET", "/policies/{type}"): ["policies", "by-type", "journal"],
        ("GET", "/databases"): ["databases", "list"],
        ("GET", "/database/{id}"): ["databases", "get", "--id", "FSD0001"],
        ("GET", "/databases/{type}"): ["databases", "by-type", "knowledgebase"],
        ("GET", "/collections"): ["collections", "list"],
        ("GET", "/collection/{id}"): ["collections", "get", "--id", "FSC0001"],
        ("GET", "/collections/{type}"): ["collections", "by-type", "community"],
        ("POST", "/search/fairsharing_records/"): ["search", "fairsharing-records", "--q", "omics"],
        ("POST", "/search/domains/"): ["search", "domains", "--q", "biology"],
        ("POST", "/search/subjects/"): ["search", "subjects", "--q", "genomics"],
        ("POST", "/search/user_defined_tags/"): ["search", "user-defined-tags", "--q", "tag"],
        ("POST", "/search/taxonomies/"): ["search", "taxonomies", "--q", "Homo sapiens"],
        ("POST", "/search/grants/"): ["search", "grants", "--q", "NIH"],
        ("POST", "/search/licences/"): ["search", "licences", "--q", "CC"],
        ("POST", "/search/organisations/"): ["search", "organisations", "--q", "EMBL"],
        ("POST", "/search/countries/"): ["search", "countries", "--q", "United"],
        ("POST", "/search/tags/"): ["search", "tags", "--q", "metadata"],
        ("GET", "/users/sign_in"): ["users", "sign-in-page"],
        ("POST", "/users/sign_in"): [
            "users",
            "sign-in",
            "--login",
            "u@example.org",
            "--password",
            "pw",
        ],
        ("DELETE", "/users/sign_out"): ["users", "sign-out"],
        ("GET", "/users/password/new"): ["users", "password-new-page"],
        ("GET", "/users/password/edit"): [
            "users",
            "password-edit-page",
            "--reset-password-token",
            "t",
        ],
        ("PUT", "/users/password"): [
            "users",
            "password-update",
            "--json",
            '{"password": "x", "password_confirmation": "x"}',
        ],
        ("POST", "/users/password"): [
            "users",
            "password-reset-request",
            "--login",
            "u@example.org",
        ],
        ("GET", "/users/cancel"): ["users", "cancel"],
        ("GET", "/users/edit"): ["users", "edit"],
        ("GET", "/users/sign_up"): ["users", "sign-up-page"],
        ("POST", "/users"): [
            "users",
            "create",
            "--json",
            "{"
            '"user": {"username": "u", "email": "u@example.org", '
            '"password": "x", "password_confirmation": "x"}'
            "}",
        ],
        ("PATCH", "/users"): ["users", "update", "--json", '{"user": {"email": "u2@example.org"}}'],
        ("GET", "/users/confirmation/new"): ["users", "confirmation-new-page"],
        ("GET", "/users/confirmation"): ["users", "confirmation-page"],
        ("POST", "/users/confirmation"): ["users", "confirm", "--confirmation-token", "abc"],
        ("GET", "/user_admin"): ["user-admin", "list"],
        ("PUT", "/user_admin/{id}"): [
            "user-admin",
            "update",
            "1",
            "--json",
            '{"email": "u@example.org"}',
        ],
        ("DELETE", "/user_admin/{id}"): ["user-admin", "delete", "1"],
        ("POST", "/maintenance_requests"): [
            "maintenance-requests",
            "create",
            "--json",
            '{"fairsharing_record_id": 1, "status": "approved"}',
        ],
    }

    for argv in operations.values():
        parsed = parser.parse_args(argv)
        assert hasattr(parsed, "handler")
