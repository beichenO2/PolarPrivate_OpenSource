"""MiniMax upstream defaults for PolarPrivate /v1 gateway."""

from __future__ import annotations

import os
from typing import Any

# Official OpenAI-compatible id (https://platform.minimax.io/docs/api-reference/api-overview)
MINIMAX_M3_MODEL_ID = "MiniMax-M3"
MINIMAX_M3_THINKING_MODEL_ID = "MiniMax-M3-Thinking"


def _m3_thinking_default() -> str:
    """disabled = lower latency; adaptive = deeper reasoning (MiniMax docs)."""
    return os.environ.get("POLARPRIVATE_MINIMAX_M3_THINKING", "disabled").strip().lower()


def apply_minimax_upstream_defaults(obj: dict[str, Any]) -> None:
    """Inject MiniMax-M3 request knobs before forwarding to llm.minimax binding.

    MiniMax-M3-Thinking forces thinking=adaptive; MiniMax-M3 uses env default
    (disabled by default for lower latency).

    Sets ``thinking`` as a **top-level** key in the request body — this is what
    the MiniMax OpenAI-compatible HTTP API expects (not ``extra_body``).
    """
    model = str(obj.get("model", "")).strip()

    if model == MINIMAX_M3_THINKING_MODEL_ID:
        obj["model"] = MINIMAX_M3_MODEL_ID
        obj["thinking"] = {"type": "adaptive"}
        return

    if model != MINIMAX_M3_MODEL_ID:
        return

    if obj.get("thinking") is None:
        mode = _m3_thinking_default()
        thinking_type = mode if mode in {"disabled", "adaptive"} else "disabled"
        obj["thinking"] = {"type": thinking_type}
