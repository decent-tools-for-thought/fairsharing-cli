from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import ApiError, AuthError, FairsharingClient, NetworkError, RateLimitError
from .config import (
    AppConfig,
    ConfigError,
    ResolvedSettings,
    config_path,
    load_config,
    resolve_settings,
    save_config,
)
from .core import (
    RenderOptions,
    execute_operation,
    parse_json_body,
    parse_kv_pairs,
    parse_select,
    render,
    stderr,
)
from .docs import fetch_openapi, list_operations, save_openapi
from .docs import get_operation as docs_get_operation

Handler = Callable[[argparse.Namespace, "AppContext"], int]


@dataclass(slots=True)
class AppContext:
    config: AppConfig
    settings: ResolvedSettings


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        cfg = load_config()
        settings = resolve_settings(
            cli_base_url=getattr(args, "base_url", None),
            cli_token=getattr(args, "token", None),
            cli_email=getattr(args, "email", None),
            cli_password=getattr(args, "password", None),
            cli_timeout=getattr(args, "timeout", None),
            config=cfg,
        )
        ctx = AppContext(config=cfg, settings=settings)
        handler = args.handler
        return int(handler(args, ctx))
    except (ConfigError, ValueError) as exc:
        stderr(f"Configuration/Input error: {exc}")
        return 2
    except AuthError as exc:
        stderr(f"Authentication error: {exc}")
        return 3
    except RateLimitError as exc:
        stderr(f"Rate limit error: {exc}")
        return 4
    except NetworkError as exc:
        stderr(f"Network error: {exc}")
        return 5
    except ApiError as exc:
        stderr(str(exc))
        return 6
    except RuntimeError as exc:
        stderr(str(exc))
        return 7


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fairsharing", description="Complete FAIRsharing API CLI")
    parser.add_argument("--base-url", help="Override API base URL")
    parser.add_argument("--token", help="Bearer token")
    parser.add_argument("--email", help="Login email/username")
    parser.add_argument("--password", help="Login password")
    parser.add_argument("--timeout", type=float, help="HTTP timeout seconds")
    parser.add_argument("--output", choices=["json", "text", "jsonl"], default="json")
    parser.add_argument("--select", help="Comma-separated top-level field selection")
    parser.add_argument("--raw", action="store_true", help="Do not normalize/select fields")

    subs = parser.add_subparsers(dest="command")

    _add_routes(subs)
    _add_fairsharing_records(subs)
    _add_fairsharing_record_lookup(subs)
    _add_basic_get_family(subs, name="subjects", singular="subject")
    _add_basic_get_family(subs, name="domains", singular="domain")
    _add_basic_get_family(subs, name="taxonomies", singular="taxonomy")
    _add_crud_family(subs, name="user-defined-tags", api_name="user_defined_tags")
    _add_crud_family(subs, name="organisation-links", api_name="organisation_links")
    _add_crud_family(subs, name="grants", api_name="grants")
    _add_basic_get_family(subs, name="licences", singular="licence")
    _add_basic_get_family(subs, name="organisations", singular="organisation")
    _add_typed_record_family(subs, name="standards", singular_path="standard")
    _add_typed_record_family(subs, name="policies", singular_path="policy")
    _add_typed_record_family(subs, name="databases", singular_path="database")
    _add_typed_record_family(subs, name="collections", singular_path="collection")
    _add_search(subs)
    _add_users(subs)
    _add_user_admin(subs)
    _add_maintenance_requests(subs)
    _add_config(subs)
    _add_docs(subs)
    _add_api_call(subs)
    _add_auth(subs)
    _add_records(subs)
    _add_list_all(subs)
    _add_export(subs)
    _add_maintain(subs)
    _add_batch(subs)
    return parser


def _render_from_args(args: argparse.Namespace, payload: Any) -> None:
    options = RenderOptions(output=args.output, select=parse_select(args.select), raw=args.raw)
    render(payload, options)


def _with_client(ctx: AppContext) -> FairsharingClient:
    return FairsharingClient(
        base_url=ctx.settings.base_url,
        token=ctx.settings.token,
        timeout=ctx.settings.timeout,
    )


def _run_simple_request(
    args: argparse.Namespace,
    ctx: AppContext,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> int:
    client = _with_client(ctx)
    try:
        payload = execute_operation(client, method=method, path=path, params=params, body=body)
    finally:
        client.close()
    _render_from_args(args, payload)
    return 0


def _add_routes(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subs.add_parser("routes", help="GET /routes")
    p.set_defaults(handler=lambda a, c: _run_simple_request(a, c, method="GET", path="/routes"))


def _add_fairsharing_records(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("fairsharing-records", help="CRUD for /fairsharing_records")
    s = grp.add_subparsers(dest="fairsharing_records_cmd", required=True)

    p_list = s.add_parser("list", help="GET /fairsharing_records")
    p_list.add_argument("--page-number", type=int)
    p_list.add_argument("--page-size", type=int)

    def handle_list(args: argparse.Namespace, ctx: AppContext) -> int:
        params: dict[str, Any] = {}
        if args.page_number is not None:
            params["page[number]"] = args.page_number
        if args.page_size is not None:
            params["page[size]"] = args.page_size
        return _run_simple_request(
            args, ctx, method="GET", path="/fairsharing_records", params=params or None
        )

    p_list.set_defaults(handler=handle_list)

    p_create = s.add_parser("create", help="POST /fairsharing_records")
    _add_json_input_args(p_create)
    p_create.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="POST",
            path="/fairsharing_records",
            body=_require_json_body(a),
        )
    )

    p_get = s.add_parser("get", help="GET /fairsharing_records/{id}")
    p_get.add_argument("id", type=int)
    p_get.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="GET", path=f"/fairsharing_records/{a.id}"
        )
    )

    p_update = s.add_parser("update", help="PUT /fairsharing_records/{id}")
    p_update.add_argument("id", type=int)
    _add_json_input_args(p_update)
    p_update.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="PUT",
            path=f"/fairsharing_records/{a.id}",
            body=_require_json_body(a),
        )
    )

    p_delete = s.add_parser("delete", help="DELETE /fairsharing_records/{id}")
    p_delete.add_argument("id", type=int)
    p_delete.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="DELETE", path=f"/fairsharing_records/{a.id}"
        )
    )

    p_can_edit = s.add_parser("can-edit", help="GET /fairsharing_records/can_edit/{id}")
    p_can_edit.add_argument("id", type=int)
    p_can_edit.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="GET", path=f"/fairsharing_records/can_edit/{a.id}"
        )
    )


def _add_fairsharing_record_lookup(
    subs: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    grp = subs.add_parser("fairsharing-record", help="Lookup /fairsharing_record/{doi|legacy_id}")
    s = grp.add_subparsers(dest="fairsharing_record_cmd", required=True)

    p_doi = s.add_parser("by-doi", help="GET /fairsharing_record/{doi}")
    p_doi.add_argument("doi")
    p_doi.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="GET", path=f"/fairsharing_record/{a.doi}"
        )
    )

    p_legacy = s.add_parser("by-legacy-id", help="GET /fairsharing_record/{legacy_id}")
    p_legacy.add_argument("legacy_id")
    p_legacy.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="GET",
            path=f"/fairsharing_record/{a.legacy_id}",
        )
    )


def _add_basic_get_family(
    subs: argparse._SubParsersAction[argparse.ArgumentParser], *, name: str, singular: str
) -> None:
    grp = subs.add_parser(name, help=f"List/get {name}")
    s = grp.add_subparsers(dest=f"{name.replace('-', '_')}_cmd", required=True)

    p_list = s.add_parser("list", help=f"GET /{name.replace('-', '_')}")
    p_list.set_defaults(
        handler=lambda a, c, family=name: _run_simple_request(
            a, c, method="GET", path=f"/{family.replace('-', '_')}"
        )
    )

    p_get = s.add_parser("get", help=f"GET /{name.replace('-', '_')}/{{id}}")
    p_get.add_argument("id", type=int)
    p_get.set_defaults(
        handler=lambda a, c, family=name: _run_simple_request(
            a,
            c,
            method="GET",
            path=f"/{family.replace('-', '_')}/{a.id}",
        )
    )


def _add_crud_family(
    subs: argparse._SubParsersAction[argparse.ArgumentParser], *, name: str, api_name: str
) -> None:
    grp = subs.add_parser(name, help=f"CRUD operations for /{api_name}")
    s = grp.add_subparsers(dest=f"{name.replace('-', '_')}_cmd", required=True)

    p_list = s.add_parser("list", help=f"GET /{api_name}")
    p_list.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="GET", path=f"/{api_name}")
    )

    p_create = s.add_parser("create", help=f"POST /{api_name}")
    _add_json_input_args(p_create)
    p_create.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="POST", path=f"/{api_name}", body=_require_json_body(a)
        )
    )

    p_get = s.add_parser("get", help=f"GET /{api_name}/{{id}}")
    p_get.add_argument("id", type=int)
    p_get.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="GET", path=f"/{api_name}/{a.id}")
    )

    p_update = s.add_parser("update", help=f"PUT /{api_name}/{{id}}")
    p_update.add_argument("id", type=int)
    _add_json_input_args(p_update)
    p_update.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="PUT",
            path=f"/{api_name}/{a.id}",
            body=_require_json_body(a),
        )
    )

    p_delete = s.add_parser("delete", help=f"DELETE /{api_name}/{{id}}")
    p_delete.add_argument("id", type=int)
    p_delete.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="DELETE", path=f"/{api_name}/{a.id}")
    )


def _add_typed_record_family(
    subs: argparse._SubParsersAction[argparse.ArgumentParser], *, name: str, singular_path: str
) -> None:
    grp = subs.add_parser(name, help=f"List/get/filter {name}")
    s = grp.add_subparsers(dest=f"{name}_cmd", required=True)

    p_list = s.add_parser("list", help=f"GET /{name}")
    p_list.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="GET", path=f"/{name}")
    )

    p_get = s.add_parser("get", help=f"GET /{singular_path}/{{id}}")
    p_get.add_argument("--id", required=True)
    p_get.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="GET", path=f"/{singular_path}/{a.id}"
        )
    )

    p_type = s.add_parser("by-type", help=f"GET /{name}/{{type}}")
    p_type.add_argument("type")
    p_type.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="GET", path=f"/{name}/{a.type}")
    )


def _add_search(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("search", help="POST /search/* endpoints")
    s = grp.add_subparsers(dest="search_cmd", required=True)

    families = [
        "fairsharing_records",
        "domains",
        "subjects",
        "user_defined_tags",
        "taxonomies",
        "grants",
        "licences",
        "organisations",
        "countries",
        "tags",
    ]
    for family in families:
        p = s.add_parser(family.replace("_", "-"), help=f"POST /search/{family}/")
        p.add_argument("--q", help="Search query text")

        def handler(args: argparse.Namespace, ctx: AppContext, fam: str = family) -> int:
            params = {"q": args.q} if args.q is not None else None
            return _run_simple_request(
                args, ctx, method="POST", path=f"/search/{fam}/", params=params
            )

        p.set_defaults(handler=handler)


def _add_users(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("users", help="All /users/* endpoints")
    s = grp.add_subparsers(dest="users_cmd", required=True)

    _add_get_cmd(s, "sign-in-page", "/users/sign_in")

    p_signin = s.add_parser("sign-in", help="POST /users/sign_in")
    p_signin.add_argument("--login", help="Login identifier (email or username)")
    p_signin.add_argument("--password", help="Password (overrides global --password)")
    p_signin.add_argument(
        "--save-token", action="store_true", help="Persist returned token in config"
    )

    def handle_signin(args: argparse.Namespace, ctx: AppContext) -> int:
        login = args.login or ctx.settings.email
        password = args.password or ctx.settings.password
        if not login or not password:
            raise ValueError("users sign-in requires login/email and password")
        body = {"user": {"login": login, "password": password}}
        client = _with_client(ctx)
        try:
            payload = execute_operation(
                client,
                method="POST",
                path="/users/sign_in",
                params=None,
                body=body,
            )
        finally:
            client.close()
        if args.save_token:
            token = _extract_token(payload)
            if not token:
                raise ValueError("Could not extract token from login response")
            cfg = load_config()
            cfg.token = token
            save_config(cfg)
        _render_from_args(args, payload)
        return 0

    p_signin.set_defaults(handler=handle_signin)

    p_signout = s.add_parser("sign-out", help="DELETE /users/sign_out")
    p_signout.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="DELETE", path="/users/sign_out")
    )

    _add_get_cmd(s, "password-new-page", "/users/password/new")

    p_pwd_edit = s.add_parser("password-edit-page", help="GET /users/password/edit")
    p_pwd_edit.add_argument("--reset-password-token", required=True)
    p_pwd_edit.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="GET",
            path="/users/password/edit",
            params={"reset_password_token": a.reset_password_token},
        )
    )

    p_pwd_update = s.add_parser("password-update", help="PUT /users/password")
    _add_json_input_args(p_pwd_update)
    p_pwd_update.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="PUT",
            path="/users/password",
            body=_require_json_body(a),
        )
    )

    p_pwd_reset = s.add_parser("password-reset-request", help="POST /users/password")
    p_pwd_reset.add_argument("--login", required=True)
    p_pwd_reset.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="POST",
            path="/users/password",
            params={"login": a.login},
        )
    )

    _add_get_cmd(s, "cancel", "/users/cancel")
    _add_get_cmd(s, "edit", "/users/edit")
    _add_get_cmd(s, "sign-up-page", "/users/sign_up")

    p_create = s.add_parser("create", help="POST /users")
    _add_json_input_args(p_create)
    p_create.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="POST", path="/users", body=_require_json_body(a)
        )
    )

    p_update = s.add_parser("update", help="PATCH /users")
    _add_json_input_args(p_update)
    p_update.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a, c, method="PATCH", path="/users", body=_require_json_body(a)
        )
    )

    _add_get_cmd(s, "confirmation-new-page", "/users/confirmation/new")
    _add_get_cmd(s, "confirmation-page", "/users/confirmation")

    p_confirm = s.add_parser("confirm", help="POST /users/confirmation")
    p_confirm.add_argument("--confirmation-token", required=True)
    p_confirm.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="POST",
            path="/users/confirmation",
            params={"confirmation_token": a.confirmation_token},
        )
    )


def _add_user_admin(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("user-admin", help="/user_admin endpoints")
    s = grp.add_subparsers(dest="user_admin_cmd", required=True)

    p_list = s.add_parser("list", help="GET /user_admin")
    p_list.set_defaults(
        handler=lambda a, c: _run_simple_request(a, c, method="GET", path="/user_admin")
    )

    p_update = s.add_parser("update", help="PUT /user_admin/{id}")
    p_update.add_argument("id", type=int)
    _add_json_input_args(p_update)

    def handle_update(args: argparse.Namespace, ctx: AppContext) -> int:
        # Upstream spec lists id both in path and query for this endpoint.
        return _run_simple_request(
            args,
            ctx,
            method="PUT",
            path=f"/user_admin/{args.id}",
            params={"id": args.id},
            body=_require_json_body(args),
        )

    p_update.set_defaults(handler=handle_update)

    p_delete = s.add_parser("delete", help="DELETE /user_admin/{id}")
    p_delete.add_argument("id", type=int)
    p_delete.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="DELETE",
            path=f"/user_admin/{a.id}",
            params={"id": a.id},
        )
    )


def _add_maintenance_requests(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("maintenance-requests", help="POST /maintenance_requests")
    s = grp.add_subparsers(dest="maintenance_cmd", required=True)

    p_create = s.add_parser("create", help="Create maintenance request")
    _add_json_input_args(p_create)
    p_create.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="POST",
            path="/maintenance_requests",
            body=_require_json_body(a),
        )
    )


def _add_config(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("config", help="Manage fairsharing-cli config")
    s = grp.add_subparsers(dest="config_cmd", required=True)

    p_show = s.add_parser("show", help="Show effective config")
    p_show.add_argument("--show-secrets", action="store_true")

    def handle_show(args: argparse.Namespace, ctx: AppContext) -> int:
        data = {
            "config_path": str(config_path()),
            "base_url": ctx.settings.base_url,
            "timeout": ctx.settings.timeout,
            "email": ctx.settings.email,
            "token": ctx.settings.token if args.show_secrets else _mask(ctx.settings.token),
            "password": ctx.settings.password
            if args.show_secrets
            else _mask(ctx.settings.password),
        }
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    p_show.set_defaults(handler=handle_show)

    p_set = s.add_parser("set", help="Set config values")
    p_set.add_argument("--base-url")
    p_set.add_argument("--token")
    p_set.add_argument("--email")
    p_set.add_argument("--password")
    p_set.add_argument("--timeout", type=float)

    def handle_set(args: argparse.Namespace, _ctx: AppContext) -> int:
        cfg = load_config()
        changed = False
        for key in ("base_url", "token", "email", "password", "timeout"):
            value = getattr(args, key)
            if value is not None:
                setattr(cfg, key, value)
                changed = True
        if not changed:
            raise ValueError(
                "No values provided. Use --base-url/--token/--email/--password/--timeout"
            )
        save_config(cfg)
        print(f"Updated config at {config_path()}")
        return 0

    p_set.set_defaults(handler=handle_set)

    p_clear = s.add_parser("clear", help="Clear stored config values")
    p_clear.add_argument("--base-url", action="store_true")
    p_clear.add_argument("--token", action="store_true")
    p_clear.add_argument("--email", action="store_true")
    p_clear.add_argument("--password", action="store_true")
    p_clear.add_argument("--timeout", action="store_true")

    def handle_clear(args: argparse.Namespace, _ctx: AppContext) -> int:
        cfg = load_config()
        flags = {
            "base_url": args.base_url,
            "token": args.token,
            "email": args.email,
            "password": args.password,
            "timeout": args.timeout,
        }
        if not any(flags.values()):
            raise ValueError("Specify at least one field to clear")
        for key, enabled in flags.items():
            if enabled:
                setattr(cfg, key, None)
        save_config(cfg)
        print(f"Updated config at {config_path()}")
        return 0

    p_clear.set_defaults(handler=handle_clear)


def _add_docs(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("docs", help="OpenAPI/spec helper commands")
    s = grp.add_subparsers(dest="docs_cmd", required=True)

    p_openapi = s.add_parser("openapi", help="Fetch FAIRsharing OpenAPI spec")
    p_openapi.add_argument("--save", help="Path to save the fetched spec")

    def handle_openapi(args: argparse.Namespace, ctx: AppContext) -> int:
        spec = fetch_openapi(timeout=ctx.settings.timeout)
        if args.save:
            save_openapi(Path(args.save), spec)
        _render_from_args(args, spec)
        return 0

    p_openapi.set_defaults(handler=handle_openapi)

    p_routes = s.add_parser("routes", help="List operations from OpenAPI")

    def handle_routes(args: argparse.Namespace, ctx: AppContext) -> int:
        spec = fetch_openapi(timeout=ctx.settings.timeout)
        _render_from_args(args, list_operations(spec))
        return 0

    p_routes.set_defaults(handler=handle_routes)

    p_endpoint = s.add_parser("endpoint", help="Inspect one OpenAPI operation")
    p_endpoint.add_argument(
        "--method", required=True, choices=["GET", "POST", "PUT", "PATCH", "DELETE"]
    )
    p_endpoint.add_argument("--path", required=True)

    def handle_endpoint(args: argparse.Namespace, ctx: AppContext) -> int:
        spec = fetch_openapi(timeout=ctx.settings.timeout)
        op = docs_get_operation(spec, method=args.method, path=args.path)
        if op is None:
            raise ValueError(f"No OpenAPI operation found for {args.method} {args.path}")
        _render_from_args(
            args,
            {
                "method": args.method,
                "path": args.path,
                "operation": op,
            },
        )
        return 0

    p_endpoint.set_defaults(handler=handle_endpoint)


def _add_api_call(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subs.add_parser("api-call", help="Direct API escape hatch")
    p.add_argument("--method", required=True, choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    p.add_argument("--path", required=True, help="Absolute API path, e.g. /routes")
    p.add_argument("--param", action="append", help="Query parameter key=value (repeatable)")
    _add_json_input_args(p)

    def handle(args: argparse.Namespace, ctx: AppContext) -> int:
        params = parse_kv_pairs(args.param)
        body = parse_json_body(args.json, args.json_file)
        return _run_simple_request(
            args, ctx, method=args.method, path=args.path, params=params, body=body
        )

    p.set_defaults(handler=handle)


def _add_auth(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("auth", help="Higher-order auth workflows")
    s = grp.add_subparsers(dest="auth_cmd", required=True)

    p_login = s.add_parser("login", help="Login and optionally store JWT")
    p_login.add_argument("--login", help="Login identifier (email or username)")
    p_login.add_argument("--password", help="Password")
    p_login.add_argument("--save-token", action="store_true", help="Save token to config")
    p_login.add_argument("--print-token", action="store_true", help="Print token field if present")

    def handle_login(args: argparse.Namespace, ctx: AppContext) -> int:
        login = args.login or ctx.settings.email
        password = args.password or ctx.settings.password
        if not login or not password:
            raise ValueError("auth login requires --login/--email and --password")
        payload = _call(
            ctx,
            method="POST",
            path="/users/sign_in",
            body={"user": {"login": login, "password": password}},
        )
        token = _extract_token(payload)
        if args.save_token:
            if not token:
                raise ValueError("Could not extract token from login response")
            cfg = load_config()
            cfg.token = token
            save_config(cfg)
        if args.print_token:
            _render_from_args(args, {"token": token})
        else:
            _render_from_args(args, payload)
        return 0

    p_login.set_defaults(handler=handle_login)

    p_whoami = s.add_parser("whoami", help="Validate token and show current user")
    p_whoami.set_defaults(
        handler=lambda a, c: _render_direct(
            a,
            _call(c, method="GET", path="/users/edit"),
        )
    )

    p_logout = s.add_parser("logout", help="Sign out and/or clear local token")
    p_logout.add_argument("--revoke", action="store_true", help="Also call /users/sign_out")
    p_logout.add_argument("--clear-token", action="store_true", help="Clear local stored token")

    def handle_logout(args: argparse.Namespace, ctx: AppContext) -> int:
        result: dict[str, Any] = {}
        if args.revoke:
            result["remote"] = _call(ctx, method="DELETE", path="/users/sign_out")
        if args.clear_token:
            cfg = load_config()
            cfg.token = None
            save_config(cfg)
            result["local"] = "token_cleared"
        if not args.revoke and not args.clear_token:
            raise ValueError("auth logout requires --revoke and/or --clear-token")
        _render_from_args(args, result)
        return 0

    p_logout.set_defaults(handler=handle_logout)


def _add_records(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("records", help="Higher-order record workflows")
    s = grp.add_subparsers(dest="records_cmd", required=True)

    p_resolve = s.add_parser("resolve", help="Resolve identifier via DOI/legacy/direct-id")
    p_resolve.add_argument("identifier")
    p_resolve.add_argument(
        "--typed-family",
        choices=["standards", "policies", "databases", "collections"],
        help="Optional typed family for direct-id fallback",
    )
    p_resolve.add_argument(
        "--not-found-exit",
        type=int,
        default=8,
        help="Exit code used when no resolution path succeeds",
    )

    def handle_resolve(args: argparse.Namespace, ctx: AppContext) -> int:
        ident = args.identifier
        attempts: list[dict[str, Any]] = []
        for mode, path in _resolution_paths(ident, args.typed_family):
            try:
                payload = _call(ctx, method="GET", path=path)
                _render_from_args(
                    args,
                    {"resolved_by": mode, "path": path, "payload": payload, "attempts": attempts},
                )
                return 0
            except ApiError as exc:
                if exc.status_code == 404:
                    attempts.append({"mode": mode, "path": path, "status": 404})
                    continue
                raise
        _render_from_args(
            args,
            {
                "resolved": False,
                "identifier": ident,
                "attempts": attempts,
            },
        )
        return int(args.not_found_exit)

    p_resolve.set_defaults(handler=handle_resolve)

    p_search_expand = s.add_parser(
        "search-expand",
        help="Search fairsharing records then fetch full record objects",
    )
    p_search_expand.add_argument("--q", required=True)
    p_search_expand.add_argument("--limit", type=int, default=25)
    p_search_expand.add_argument("--concurrency", type=int, default=4)

    def handle_search_expand(args: argparse.Namespace, ctx: AppContext) -> int:
        if args.limit <= 0:
            raise ValueError("--limit must be > 0")
        if args.concurrency <= 0:
            raise ValueError("--concurrency must be > 0")
        search_payload = _call(
            ctx,
            method="POST",
            path="/search/fairsharing_records/",
            params={"q": args.q},
        )
        items = _as_list(search_payload)
        ids = _extract_ids(items)[: args.limit]
        details: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(_call, ctx, method="GET", path=f"/fairsharing_records/{rid}"): rid
                for rid in ids
            }
            for fut in as_completed(futures):
                rid = futures[fut]
                details.append({"id": rid, "payload": fut.result()})

        result = {
            "query": args.q,
            "total_search_results": len(items),
            "fetched": len(details),
            "results": sorted(details, key=lambda d: int(d["id"])),
        }
        _render_from_args(args, result)
        return 0

    p_search_expand.set_defaults(handler=handle_search_expand)


def _add_list_all(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subs.add_parser("list-all", help="Unified list for major record families")
    p.add_argument(
        "--family",
        required=True,
        choices=[
            "standards",
            "policies",
            "databases",
            "collections",
            "fairsharing_records",
            "subjects",
            "domains",
            "taxonomies",
            "licences",
            "organisations",
            "grants",
            "user_defined_tags",
            "organisation_links",
        ],
    )
    p.add_argument("--type", help="Typed-filter used by standards/policies/databases/collections")
    p.add_argument("--page-number", type=int, help="For fairsharing_records only")
    p.add_argument("--page-size", type=int, help="For fairsharing_records only")

    def handle_list_all(args: argparse.Namespace, ctx: AppContext) -> int:
        family = args.family
        if args.type:
            if family not in {"standards", "policies", "databases", "collections"}:
                raise ValueError(
                    "--type is supported only for standards/policies/databases/collections"
                )
            path = f"/{family}/{args.type}"
            payload = _call(ctx, method="GET", path=path)
            _render_from_args(args, payload)
            return 0

        params: dict[str, Any] | None = None
        if family == "fairsharing_records":
            params = {}
            if args.page_number is not None:
                params["page[number]"] = args.page_number
            if args.page_size is not None:
                params["page[size]"] = args.page_size
            if not params:
                params = None
        payload = _call(ctx, method="GET", path=f"/{family}", params=params)
        _render_from_args(args, payload)
        return 0

    p.set_defaults(handler=handle_list_all)


def _add_export(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("export", help="Higher-order export workflows")
    s = grp.add_subparsers(dest="export_cmd", required=True)

    p_search = s.add_parser("search", help="Export search results to a file")
    p_search.add_argument(
        "--family",
        required=True,
        choices=[
            "fairsharing_records",
            "domains",
            "subjects",
            "user_defined_tags",
            "taxonomies",
            "grants",
            "licences",
            "organisations",
            "countries",
            "tags",
        ],
    )
    p_search.add_argument("--q", required=True)
    p_search.add_argument("--out", required=True)
    p_search.add_argument("--format", choices=["json", "jsonl"], default="json")

    def handle_export_search(args: argparse.Namespace, ctx: AppContext) -> int:
        payload = _call(
            ctx,
            method="POST",
            path=f"/search/{args.family}/",
            params={"q": args.q},
        )
        out_path = Path(args.out)
        _write_payload(out_path, payload, args.format)
        _render_from_args(
            args,
            {
                "written": str(out_path),
                "format": args.format,
                "family": args.family,
            },
        )
        return 0

    p_search.set_defaults(handler=handle_export_search)

    p_records = s.add_parser("records", help="Export full fairsharing records by ids")
    p_records.add_argument("--ids", required=True, help="Comma-separated integer ids")
    p_records.add_argument("--out", required=True)
    p_records.add_argument("--format", choices=["json", "jsonl"], default="json")
    p_records.add_argument("--concurrency", type=int, default=4)

    def handle_export_records(args: argparse.Namespace, ctx: AppContext) -> int:
        ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
        if not ids:
            raise ValueError("--ids must include at least one id")
        if args.concurrency <= 0:
            raise ValueError("--concurrency must be > 0")
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(_call, ctx, method="GET", path=f"/fairsharing_records/{rid}"): rid
                for rid in ids
            }
            for fut in as_completed(futures):
                rid = futures[fut]
                results.append({"id": rid, "payload": fut.result()})
        results.sort(key=lambda item: int(item["id"]))
        out_path = Path(args.out)
        _write_payload(out_path, results, args.format)
        _render_from_args(
            args,
            {
                "written": str(out_path),
                "format": args.format,
                "count": len(results),
            },
        )
        return 0

    p_records.set_defaults(handler=handle_export_records)


def _add_maintain(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    grp = subs.add_parser("maintain", help="Higher-order maintenance request workflow")
    s = grp.add_subparsers(dest="maintain_cmd", required=True)

    p_request = s.add_parser("request", help="Submit maintenance request with explicit flags")
    p_request.add_argument("--record", required=True, type=int, help="fairsharing_record_id")
    p_request.add_argument("--status", required=True, choices=["approved", "rejected"])
    p_request.set_defaults(
        handler=lambda a, c: _run_simple_request(
            a,
            c,
            method="POST",
            path="/maintenance_requests",
            body={"fairsharing_record_id": a.record, "status": a.status},
        )
    )


def _add_batch(subs: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subs.add_parser("batch", help="Execute JSONL API operations")
    p.add_argument("--file", required=True, help="JSONL file of operations")
    p.add_argument("--stop-on-error", action="store_true", help="Stop at first failed operation")

    def handle_batch(args: argparse.Namespace, ctx: AppContext) -> int:
        lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        results: list[dict[str, Any]] = []
        failures = 0
        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            spec = json.loads(line)
            if not isinstance(spec, dict):
                raise ValueError(f"Invalid JSON object at line {idx}")
            method = str(spec.get("method", "")).upper()
            path = str(spec.get("path", ""))
            params = spec.get("params")
            body = spec.get("body")
            if not method or not path:
                raise ValueError(f"Line {idx} requires method and path")
            try:
                payload = _call(ctx, method=method, path=path, params=params, body=body)
                results.append(
                    {
                        "line": idx,
                        "ok": True,
                        "method": method,
                        "path": path,
                        "payload": payload,
                    }
                )
            except (ApiError, AuthError, NetworkError, RateLimitError) as exc:
                failures += 1
                results.append(
                    {
                        "line": idx,
                        "ok": False,
                        "method": method,
                        "path": path,
                        "error": str(exc),
                    }
                )
                if args.stop_on_error:
                    break
        _render_from_args(args, {"results": results, "failures": failures})
        return 0 if failures == 0 else 9

    p.set_defaults(handler=handle_batch)


def _add_get_cmd(
    subs: argparse._SubParsersAction[argparse.ArgumentParser], name: str, path: str
) -> None:
    p = subs.add_parser(name, help=f"GET {path}")
    p.set_defaults(handler=lambda a, c: _run_simple_request(a, c, method="GET", path=path))


def _add_json_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", help="Inline JSON object payload")
    parser.add_argument("--json-file", help="Path to JSON object payload file")


def _require_json_body(args: argparse.Namespace) -> dict[str, Any]:
    body = parse_json_body(args.json, args.json_file)
    if body is None:
        raise ValueError("This command requires JSON input via --json or --json-file")
    return body


def _mask(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]}"


def _extract_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("jwt", "token", "auth_token"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("jwt", "token", "auth_token"):
            value = user.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _render_direct(args: argparse.Namespace, payload: Any) -> int:
    _render_from_args(args, payload)
    return 0


def _call(
    ctx: AppContext,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    client = _with_client(ctx)
    try:
        return execute_operation(client, method=method, path=path, params=params, body=body)
    finally:
        client.close()


def _resolution_paths(identifier: str, typed_family: str | None) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = [
        ("doi", f"/fairsharing_record/{identifier}"),
        ("legacy_id", f"/fairsharing_record/{identifier}"),
    ]
    if identifier.isdigit():
        paths.append(("fairsharing_records_id", f"/fairsharing_records/{identifier}"))
    if typed_family:
        paths.append((f"{typed_family}_id", f"/{typed_family}/{identifier}"))
    return paths


def _as_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _extract_ids(items: list[Any]) -> list[int]:
    ids: list[int] = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("id")
            if isinstance(value, int):
                ids.append(value)
            elif isinstance(value, str) and value.isdigit():
                ids.append(int(value))
    return ids


def _write_payload(path: Path, payload: Any, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return
    if fmt == "jsonl":
        rows: list[str] = []
        if isinstance(payload, list):
            rows = [json.dumps(item, sort_keys=True) for item in payload]
        else:
            rows = [json.dumps(payload, sort_keys=True)]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return
    raise ValueError(f"Unsupported export format: {fmt}")
