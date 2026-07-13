"""Opaque E000 → cloud embedding upstream (server-side only).

E000 is the sole public embedding code. PolarPrivate resolves it to a cloud
provider model and binding; callers never see upstream model names.
"""

from __future__ import annotations

import os

EMBED_CODE = "E000"
EMBED_SERVICE_NAME = "llm.aliyun.dashscope"
DEFAULT_CLOUD_EMBED_MODEL = "text-embedding-v3"


def normalize_embed_code(model: str) -> str | None:
    m = (model or "").strip().upper()
    if m == EMBED_CODE:
        return EMBED_CODE
    return None


def is_embed_code(model: str) -> bool:
    return normalize_embed_code(model) is not None


def resolve_cloud_embed_model(code: str = EMBED_CODE) -> str:
    canonical = normalize_embed_code(code)
    if not canonical:
        raise ValueError(f"invalid embedding code: {code!r} (use {EMBED_CODE})")
    return (
        os.environ.get("CLOUD_EMBED_MODEL")
        or os.environ.get(f"CLOUD_EMBED_MODEL_{canonical}")
        or DEFAULT_CLOUD_EMBED_MODEL
    )
