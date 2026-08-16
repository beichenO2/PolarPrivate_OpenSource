"""When libc getaddrinfo fails for an apex host, fall back to www."""

from __future__ import annotations

import socket

from app.core.host_resolve import ensure_resolvable_base_url


def test_keeps_url_when_host_resolves(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("1.2.3.4", 443))])
    url = "https://lant.top/relay-api/v1"
    assert ensure_resolvable_base_url(url) == url


def test_rewrites_apex_to_www_when_apex_unresolvable(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "www.lant.top":
            return [(0, 0, 0, "", ("110.42.234.189", 443))]
        raise socket.gaierror(8, "nodename nor servname provided, or not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert ensure_resolvable_base_url("https://lant.top/relay-api/v1") == (
        "https://www.lant.top/relay-api/v1"
    )


def test_does_not_prefix_www_twice(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        raise socket.gaierror(8, "nodename nor servname provided, or not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    url = "https://www.lant.top/relay-api/v1"
    assert ensure_resolvable_base_url(url) == url


def test_leaves_url_when_www_also_fails(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        raise socket.gaierror(8, "nodename nor servname provided, or not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    url = "https://lant.top/relay-api/v1"
    assert ensure_resolvable_base_url(url) == url
