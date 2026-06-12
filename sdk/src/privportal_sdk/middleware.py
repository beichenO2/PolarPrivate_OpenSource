"""Core sanitize/resolve middleware.

Loads identity mappings from PolarPrivate once, then performs
pure in-memory string replacement for every message.

PolarPrivate sanitize/mappings API requires no authentication.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class _IdentityEntry:
    key: str
    value: str
    project_id: str | None
    placeholder: str = ""

    def __post_init__(self) -> None:
        self.placeholder = f"[[{self.key}]]"


@dataclass
class _SecretEntry:
    key: str
    project_id: str | None
    placeholder: str = ""

    def __post_init__(self) -> None:
        self.placeholder = f"[[secret_ref.{self.key}]]"


class PrivPortalMiddleware:
    """Stateful middleware that sanitizes and resolves text using PolarPrivate mappings.

    PolarPrivate sanitize/mappings API requires no authentication —
    any localhost caller can use it without tokens or cookies.

    Usage::

        from privportal_sdk import PrivPortalMiddleware

        mw = PrivPortalMiddleware("http://127.0.0.1:12790")
        mw.load_mappings()
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:12790",
        project_id: str | None = None,
        *,
        auto_load: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_id = project_id
        self._identities: list[_IdentityEntry] = []
        self._secrets: list[_SecretEntry] = []
        self._value_to_placeholder: dict[str, str] = {}
        self._placeholder_to_value: dict[str, str] = {}
        self._sanitize_pattern: re.Pattern[str] | None = None
        self._lock = threading.Lock()
        self._loaded = False

        if auto_load:
            self.load_mappings()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_mappings(self, timeout: float = 5.0) -> None:
        """Fetch mappings from PolarPrivate API and build lookup tables."""
        params: dict[str, Any] = {}
        if self._project_id is not None:
            params["project_id"] = self._project_id

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{self._base_url}/api/sanitize/mappings",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        self._rebuild(data)

    async def aload_mappings(self, timeout: float = 5.0) -> None:
        """Async variant of load_mappings."""
        params: dict[str, Any] = {}
        if self._project_id is not None:
            params["project_id"] = self._project_id

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{self._base_url}/api/sanitize/mappings",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        self._rebuild(data)

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Load mappings from a raw dict (useful for testing without a running server)."""
        self._rebuild(data)

    def _rebuild(self, data: dict[str, Any]) -> None:
        """Rebuild internal lookup tables from API response."""
        with self._lock:
            self._identities = [
                _IdentityEntry(
                    key=item["key"],
                    value=item["value"],
                    project_id=item.get("project_id"),
                )
                for item in data.get("identities", [])
            ]
            self._secrets = [
                _SecretEntry(
                    key=item["key"],
                    project_id=item.get("project_id"),
                )
                for item in data.get("secrets", [])
            ]

            self._value_to_placeholder = {}
            self._placeholder_to_value = {}

            # Sort by value length descending so longer values match first
            # (e.g. "张三丰" matches before "张三")
            sorted_ids = sorted(self._identities, key=lambda e: len(e.value), reverse=True)
            for entry in sorted_ids:
                if entry.value:
                    self._value_to_placeholder[entry.value] = entry.placeholder
                    self._placeholder_to_value[entry.placeholder] = entry.value

            if self._value_to_placeholder:
                escaped = [re.escape(v) for v in self._value_to_placeholder]
                self._sanitize_pattern = re.compile("|".join(escaped))
            else:
                self._sanitize_pattern = None

            self._loaded = True

    def sanitize(self, text: str) -> str:
        """Replace known identity values with their placeholders.

        Returns the text with all recognized PII replaced by [[key]] tokens.
        This is the INBOUND path (user message → LLM).
        """
        if not self._loaded or self._sanitize_pattern is None:
            return text

        def _replace(match: re.Match[str]) -> str:
            return self._value_to_placeholder[match.group(0)]

        return self._sanitize_pattern.sub(_replace, text)

    def resolve(self, text: str) -> str:
        """Replace placeholders with real identity values.

        Returns the text with [[key]] tokens replaced by actual values.
        This is the OUTBOUND path (LLM reply → user).
        """
        if not self._loaded or not self._placeholder_to_value:
            return text

        result = text
        for placeholder, value in self._placeholder_to_value.items():
            result = result.replace(placeholder, value)
        return result

    def detect_leaks(self, text: str) -> list[dict[str, str]]:
        """Check if text contains any known identity values (leak detection).

        Returns a list of detected leaks with key and matched value.
        Useful for auditing LLM outputs before sending to user.
        """
        if not self._loaded or self._sanitize_pattern is None:
            return []

        leaks: list[dict[str, str]] = []
        for match in self._sanitize_pattern.finditer(text):
            value = match.group(0)
            placeholder = self._value_to_placeholder[value]
            leaks.append({
                "key": placeholder.strip("[]"),
                "value": value,
                "position": match.start(),
            })
        return leaks

    @property
    def identity_count(self) -> int:
        return len(self._identities)

    @property
    def secret_count(self) -> int:
        return len(self._secrets)

    def __repr__(self) -> str:
        return (
            f"PrivPortalMiddleware(base_url={self._base_url!r}, "
            f"loaded={self._loaded}, "
            f"identities={self.identity_count}, "
            f"secrets={self.secret_count})"
        )
