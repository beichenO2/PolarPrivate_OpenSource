"""Cross-service identity resolution via PolarPrivate identity_bindings API.

Usage::

    from privportal_sdk import resolve_user, ServiceAuth

    # Without auth (public endpoints):
    result = resolve_user("feishu", "ou_abc123")

    # With bearer token auth:
    auth = ServiceAuth(token="ppst_...")
    result = resolve_user("feishu", "ou_abc123", auth=auth)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from privportal_sdk.auth import ServiceAuth


def _default_base_url() -> str:
    port = os.environ.get("POLARPRIVATE_PORT", "12790")
    return f"http://127.0.0.1:{port}"


def _auth_headers(auth: ServiceAuth | None) -> dict[str, str]:
    if auth is None:
        return {}
    return auth.headers


@dataclass
class ResolvedUser:
    user_id: str
    username: str
    service: str
    external_username: str


def resolve_user(
    service: str,
    external_username: str,
    *,
    base_url: str | None = None,
    timeout: float = 5.0,
    auth: ServiceAuth | None = None,
) -> ResolvedUser | None:
    """Resolve an external service identity to a polarisor user_id.

    Returns None if no binding exists (404).
    Raises httpx.HTTPStatusError for other failures.
    """
    url = (base_url or _default_base_url()).rstrip("/")
    with httpx.Client(timeout=timeout, headers=_auth_headers(auth)) as client:
        resp = client.get(
            f"{url}/api/identity-bindings/resolve",
            params={"service": service, "external_username": external_username},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return ResolvedUser(**data)


async def aresolve_user(
    service: str,
    external_username: str,
    *,
    base_url: str | None = None,
    timeout: float = 5.0,
    auth: ServiceAuth | None = None,
) -> ResolvedUser | None:
    """Async variant of resolve_user."""
    url = (base_url or _default_base_url()).rstrip("/")
    async with httpx.AsyncClient(timeout=timeout, headers=_auth_headers(auth)) as client:
        resp = await client.get(
            f"{url}/api/identity-bindings/resolve",
            params={"service": service, "external_username": external_username},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return ResolvedUser(**data)


def list_user_bindings(
    user_id: str,
    *,
    base_url: str | None = None,
    timeout: float = 5.0,
    auth: ServiceAuth | None = None,
) -> list[dict[str, Any]]:
    """List all identity bindings for a given polarisor user_id."""
    url = (base_url or _default_base_url()).rstrip("/")
    with httpx.Client(timeout=timeout, headers=_auth_headers(auth)) as client:
        resp = client.get(f"{url}/api/identity-bindings/user/{user_id}")
        resp.raise_for_status()
        return resp.json().get("items", [])


def create_binding(
    user_id: str,
    service: str,
    external_username: str,
    *,
    display_name: str | None = None,
    base_url: str | None = None,
    timeout: float = 5.0,
    auth: ServiceAuth | None = None,
) -> dict[str, Any]:
    """Create a new identity binding."""
    url = (base_url or _default_base_url()).rstrip("/")
    body: dict[str, Any] = {
        "user_id": user_id,
        "service": service,
        "external_username": external_username,
    }
    if display_name:
        body["display_name"] = display_name
    with httpx.Client(timeout=timeout, headers=_auth_headers(auth)) as client:
        resp = client.post(f"{url}/api/identity-bindings", json=body)
        resp.raise_for_status()
        return resp.json()
