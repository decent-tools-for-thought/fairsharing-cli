from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(RuntimeError):
    """Base API failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(ApiError):
    """Authentication/authorization failure."""


class RateLimitError(ApiError):
    """Rate limit reached."""


class NetworkError(ApiError):
    """Network layer failure."""


@dataclass(slots=True)
class RequestSpec:
    method: str
    path: str
    params: dict[str, Any] | None = None
    json_body: dict[str, Any] | None = None


class FairsharingClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def request(self, spec: RequestSpec) -> Any:
        try:
            response = self._http.request(
                method=spec.method,
                url=spec.path,
                params=spec.params,
                json=spec.json_body,
            )
        except httpx.HTTPError as exc:
            raise NetworkError(
                f"Network error while calling {spec.method} {spec.path}: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise AuthError(_format_error(response, spec))
        if response.status_code == 429:
            raise RateLimitError(_format_error(response, spec))
        if response.status_code >= 400:
            raise ApiError(_format_error(response, spec), status_code=response.status_code)

        if not response.content:
            return {}

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return response.json()
            except ValueError as exc:
                message = (
                    "Malformed JSON response for "
                    f"{spec.method} {spec.path} "
                    f"(status {response.status_code})"
                )
                raise ApiError(message) from exc
        return {"raw_text": response.text}


def _format_error(response: httpx.Response, spec: RequestSpec) -> str:
    detail: str
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = str(payload.get("error") or payload.get("message") or payload)
        else:
            detail = str(payload)
    except ValueError:
        detail = response.text.strip() or "<empty body>"
    return f"API error {response.status_code} for {spec.method} {spec.path}: {detail}"
