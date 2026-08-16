"""Repair upstream base URLs when libc getaddrinfo cannot see the apex host.

macOS + Tailscale MagicDNS sometimes fails `lant.top` in getaddrinfo/curl
while `dig` and `www.lant.top` still work. PolarPrivate must not stall
the caller with an unresolvable host.
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse, urlunparse

from app.logging_config import get_logger

_LOG = get_logger(__name__)


def _host_resolves(host: str) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
        return True
    except OSError:
        return False


def ensure_resolvable_base_url(url: str) -> str:
    """Return *url*, or a www-prefixed twin if the original host is unresolvable."""
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    if not host or _host_resolves(host):
        return raw
    if host.lower().startswith("www."):
        return raw
    www_host = f"www.{host}"
    if not _host_resolves(www_host):
        return raw
    netloc = www_host
    if parsed.port:
        netloc = f"{www_host}:{parsed.port}"
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{netloc}"
    rewritten = urlunparse(parsed._replace(netloc=netloc))
    _LOG.warning("upstream_host_www_fallback", from_host=host, to_host=www_host)
    return rewritten
