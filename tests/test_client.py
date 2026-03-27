from __future__ import annotations

import httpx
import pytest

from fairsharing_cli.client import (
    ApiError,
    AuthError,
    FairsharingClient,
    NetworkError,
    RateLimitError,
    RequestSpec,
)


def _transport(handler: httpx.MockTransport) -> httpx.MockTransport:
    return handler


def test_client_success_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "application/json"
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"ok": True})

    client = FairsharingClient(
        base_url="https://api.fairsharing.org",
        token="tok",
        timeout=3.0,
        transport=_transport(httpx.MockTransport(handler)),
    )
    try:
        payload = client.request(RequestSpec(method="GET", path="/routes"))
    finally:
        client.close()
    assert payload == {"ok": True}


def test_client_auth_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad token"})

    client = FairsharingClient(
        base_url="https://api.fairsharing.org",
        token="tok",
        timeout=3.0,
        transport=_transport(httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AuthError):
            client.request(RequestSpec(method="GET", path="/routes"))
    finally:
        client.close()


def test_client_rate_limit_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "too many"})

    client = FairsharingClient(
        base_url="https://api.fairsharing.org",
        token="tok",
        timeout=3.0,
        transport=_transport(httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(RateLimitError):
            client.request(RequestSpec(method="GET", path="/routes"))
    finally:
        client.close()


def test_client_api_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "oops"})

    client = FairsharingClient(
        base_url="https://api.fairsharing.org",
        token=None,
        timeout=3.0,
        transport=_transport(httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(ApiError):
            client.request(RequestSpec(method="GET", path="/routes"))
    finally:
        client.close()


def test_client_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = FairsharingClient(
        base_url="https://api.fairsharing.org",
        token=None,
        timeout=3.0,
        transport=_transport(httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(NetworkError):
            client.request(RequestSpec(method="GET", path="/routes"))
    finally:
        client.close()
