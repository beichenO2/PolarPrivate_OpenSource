"""LLM chat completion via PolarPrivate's /v1/ unified gateway.

Callers only need a model name — PolarPrivate handles routing and auth.

Usage::

    from privportal_sdk.llm import chat_completion

    reply = chat_completion("qwen3-coder-plus", [
        {"role": "user", "content": "Hello!"}
    ])

    # With options:
    reply = chat_completion("minimax", messages, temperature=0.3, max_tokens=2048)

    # Async:
    from privportal_sdk.llm import achat_completion
    reply = await achat_completion("qwen3-coder-plus", messages)

Port discovery order: POLARPRIVATE_URL env → POLARPRIVATE_PORT env → default 12790.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


def _base_url() -> str:
    if url := os.environ.get("POLARPRIVATE_URL"):
        return url.rstrip("/")
    port = os.environ.get("POLARPRIVATE_PORT", "12790")
    return f"http://127.0.0.1:{port}"


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


def _normalize_messages(
    messages: list[dict[str, str] | ChatMessage],
) -> list[dict[str, str]]:
    return [
        m.to_dict() if isinstance(m, ChatMessage) else m
        for m in messages
    ]


def _build_payload(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stream:
        payload["stream"] = True
    if extra:
        payload.update(extra)
    return payload


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("LLM returned empty choices")
    return choices[0].get("message", {}).get("content", "")


_DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=300, write=30, pool=10)


def chat_completion(
    model: str,
    messages: list[dict[str, str] | ChatMessage],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    base_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Synchronous chat completion. Returns the assistant's reply text."""
    url = f"{base_url or _base_url()}/v1/chat/completions"
    norm = _normalize_messages(messages)
    payload = _build_payload(model, norm, temperature=temperature, max_tokens=max_tokens, extra=extra)
    t = httpx.Timeout(read=timeout) if timeout else _DEFAULT_TIMEOUT

    resp = httpx.post(url, json=payload, timeout=t)
    resp.raise_for_status()
    return _extract_content(resp.json())


async def achat_completion(
    model: str,
    messages: list[dict[str, str] | ChatMessage],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    base_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Async chat completion. Returns the assistant's reply text."""
    url = f"{base_url or _base_url()}/v1/chat/completions"
    norm = _normalize_messages(messages)
    payload = _build_payload(model, norm, temperature=temperature, max_tokens=max_tokens, extra=extra)
    t = httpx.Timeout(read=timeout) if timeout else _DEFAULT_TIMEOUT

    async with httpx.AsyncClient(timeout=t) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return _extract_content(resp.json())


def is_healthy(*, base_url: str | None = None, timeout: float = 3.0) -> bool:
    """Check if PolarPrivate is reachable and vault is unlocked."""
    try:
        resp = httpx.get(f"{base_url or _base_url()}/health", timeout=timeout)
        return resp.is_success and resp.json().get("vault_unlocked") is True
    except Exception:
        return False


def list_models(*, base_url: str | None = None) -> list[dict[str, Any]]:
    """Return available models from GET /v1/models."""
    resp = httpx.get(f"{base_url or _base_url()}/v1/models", timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", [])
