"""Upstream 429 stays inside PolarPrivate: unlimited 15s retries."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.api import v1_gateway


def test_429_hold_interval_is_15s():
    assert v1_gateway._UPSTREAM_429_HOLD_S == 15.0


def test_hold_until_not_429_retries_every_15s_then_returns_ok(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(v1_gateway.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def request_once() -> SimpleNamespace:
        calls["n"] += 1
        return SimpleNamespace(status_code=200 if calls["n"] >= 3 else 429)

    first = SimpleNamespace(status_code=429)

    async def run() -> SimpleNamespace:
        return await v1_gateway._hold_until_not_429(
            request_once,
            first,  # type: ignore[arg-type]
            service_name="llm.lant",
        )

    out = asyncio.run(run())
    assert out.status_code == 200
    assert sleeps == [15.0, 15.0, 15.0]
    assert calls["n"] == 3


def test_hold_until_not_429_keeps_going_after_request_error(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(v1_gateway.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def request_once() -> SimpleNamespace:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return SimpleNamespace(status_code=200)

    first = SimpleNamespace(status_code=429)

    out = asyncio.run(
        v1_gateway._hold_until_not_429(
            request_once,
            first,  # type: ignore[arg-type]
            service_name="llm.lant",
        )
    )
    assert out.status_code == 200
    assert sleeps == [15.0, 15.0]
    assert calls["n"] == 2


def test_first_429_branch_releases_slot_before_hold():
    """Infinite 429 hold must not keep llm.lant's 3 concurrency slots."""
    src = Path(v1_gateway.__file__).read_text()
    marker = "# 429 stays in PolarPrivate"
    idx = src.find(marker)
    assert idx != -1
    chunk = src[idx : idx + 500]
    assert "_release_budget" in chunk
    assert "_hold_until_not_429" in chunk
    assert chunk.find("_release_budget") < chunk.find("_hold_until_not_429")
