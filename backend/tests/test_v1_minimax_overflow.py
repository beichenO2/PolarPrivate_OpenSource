"""QCSA /v1 tries llm.minimax first, then llm.minimax_1 on 402."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx


def _seed_minimax_pair(client):
    assert client.post("/api/secrets", json={
        "key": "secret.minimax.api_key",
        "value": "primary-token",
        "enabled": True,
        "base_url": "https://primary.minimax.test/v1",
        "category": "minimax",
    }).status_code == 201
    assert client.post("/api/secrets", json={
        "key": "secret.minimax.minimax_1",
        "value": "overflow-token",
        "enabled": True,
        "base_url": "https://overflow.minimax.test/v1",
        "category": "minimax",
    }).status_code == 201
    primary = client.post("/api/bindings", json={
        "service_name": "llm.minimax",
        "secret_ref_key": "secret.minimax.api_key",
        "auth_header": "Authorization",
    })
    assert primary.status_code == 201
    assert client.post("/api/bindings", json={
        "service_name": "llm.minimax_1",
        "secret_ref_key": "secret.minimax.minimax_1",
        "auth_header": "Authorization",
    }).status_code == 201
    assert client.put(
        f"/api/bindings/{primary.json()['id']}/fallback",
        json={"fallback_chain": ["llm.minimax_1"]},
    ).status_code == 200


class _FakeResp:
    def __init__(self, status: int, content: bytes) -> None:
        self.status_code = status
        self.content = content
        self.headers = httpx.Headers({"content-type": "application/json"})


def test_v1_0001_stays_on_primary_when_ok(client, app):
    _seed_minimax_pair(client)
    calls: list[str] = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        return _FakeResp(
            200,
            b'{"id":"ok","choices":[{"message":{"role":"assistant","content":"primary-ok"}}]}',
        )

    mock_client = MagicMock()
    mock_client.request = AsyncMock(side_effect=fake_request)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post("/v1/chat/completions", json={
        "model": "0001",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "primary-ok"
    assert len(calls) == 1
    assert "primary.minimax.test" in calls[0]


def test_v1_0001_overflows_to_minimax_1_on_402(client, app):
    _seed_minimax_pair(client)
    calls: list[str] = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        if "primary.minimax.test" in url:
            return _FakeResp(
                402,
                b'{"error":{"message":"Token Plan","code":"insufficient_balance_error"}}',
            )
        return _FakeResp(
            200,
            b'{"id":"ovf","choices":[{"message":{"role":"assistant","content":"overflow-ok"}}]}',
        )

    mock_client = MagicMock()
    mock_client.request = AsyncMock(side_effect=fake_request)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post("/v1/chat/completions", json={
        "model": "0001",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "overflow-ok"
    assert any("primary.minimax.test" in url for url in calls)
    assert any("overflow.minimax.test" in url for url in calls)
    assert calls[0].startswith("https://primary.minimax.test")
