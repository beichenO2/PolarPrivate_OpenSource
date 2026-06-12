"""PolarPrivate SDK auth — simplified after plaintext export ban.

Service tokens and service-session have been removed.
All downstream callers now use the proxy/sign/d-class interfaces,
which never expose plaintext secrets.
"""

from __future__ import annotations

import os


def default_base_url() -> str:
    """Return the PolarPrivate API base URL from environment or default."""
    port = os.environ.get("POLARPRIVATE_PORT", "12790")
    return os.environ.get("POLARPRIVATE_URL", f"http://127.0.0.1:{port}")
