"""Model → binding routing table for the /v1 unified LLM gateway.

To add a new provider:
1. Add the binding via PolarPrivate UI or API (POST /api/bindings)
2. Append a new entry here: (model_prefix, service_name)

Order matters: more specific prefixes should come first.

Retired (no Binding, do not re-add without a live secret):
- llm.glm51.enterprise / xfyun xop*
- llm.aliyun.codingplan / qwen3.7-plus / 1100
- llm.local.ollama / L0000 / L0001
"""

from __future__ import annotations

import os


def fast_minimax_model() -> str:
    """MiniMax slot for capability code 111 (default: current standard MiniMax-M3)."""
    return os.environ.get("POLARPRIVATE_MINIMAX_FAST_MODEL", "MiniMax-M3").strip()


# Cloud capability codes (4-bit QCSA) — opaque to callers; mapped server-side only.
# Q=Quality(0=standard,1=flagship) C=Context(0=standard,1=long)
# S=Speed(0=balanced,1=fast) A=Agentic(0=conversational,1=agent/tool-use)
# Prefix V = Vision/multimodal. Only codes with a live Binding stay here.
CAPABILITY_CLOUD_MAP: dict[str, tuple[str, str]] = {
    # ── Text-only (4-bit QCSA) ──
    "0000": ("MiniMax-M3", "llm.minimax"),
    "0010": ("MiniMax-M3", "llm.minimax"),
    "0100": ("deepseek-v4-pro", "llm.lant"),
    "0110": ("MiniMax-M3", "llm.minimax"),
    "1000": ("MiniMax-M3", "llm.minimax"),
    "1110": ("MiniMax-M3-Thinking", "llm.minimax"),
    # ── Agentic (A=1) ──
    "0001": ("MiniMax-M3", "llm.minimax"),
    "0011": ("MiniMax-M3", "llm.minimax"),
    "0101": ("deepseek-v4-pro", "llm.lant"),
    "1001": ("deepseek-v4-pro", "llm.lant"),
    "1011": ("MiniMax-M3", "llm.minimax"),
    "1101": ("deepseek-v4-pro", "llm.lant"),
    # ── Vision / multimodal (MiniMax-M3; DashScope VL remains an explicit alias) ──
    "V0000": ("MiniMax-M3", "llm.minimax"),
    "V0010": ("MiniMax-M3", "llm.minimax"),
    "V0001": ("MiniMax-M3", "llm.minimax"),
    "V0101": ("MiniMax-M3", "llm.minimax"),
    "V1000": ("MiniMax-M3-Thinking", "llm.minimax"),
}


STRICT_MODEL_MAP = {
    # 独立 glm2 线（88.api456.me）；xfyun 别名已退役
    "glm-5.2": "glm-5.2",
    "glm2": "glm-5.2",
    # RightAPI Codex 号池
    "gpt-5.6-sol": "gpt-5.6-sol",
    "gpt-5.6": "gpt-5.6-sol",
    # lant.top relay
    "deepseek-v4-pro": "deepseek-v4-pro",
    "lant_ds_v4_pro": "deepseek-v4-pro",
    # 阿里云百炼 / DashScope
    "qwen3.8-27b": "qwen3.8-27b",
    "qwen-vl": "qwen3-vl-flash",
    "qwen3-vl": "qwen3-vl-flash",
    "qwen3-vl-flash": "qwen3-vl-flash",
    # MiniMax
    "minimax": "MiniMax-M3",
    "minimax-m3": "MiniMax-M3",
    "minimax-m3-thinking": "MiniMax-M3-Thinking",
}

MODEL_SERVICE_MAP = {
    "glm-5.2": "llm.glm2",
    "gpt-5.6-sol": "llm.rightapi",
    "deepseek-v4-pro": "llm.lant",
    "qwen3.8-27b": "llm.aliyun.dashscope",
    "qwen3-vl-flash": "llm.aliyun.dashscope",
    "MiniMax-M3": "llm.minimax",
    "MiniMax-M3-Thinking": "llm.minimax",
}

# Capability-code fallbacks. Empty: every remaining code already points at a
# live Binding. Do not point fallbacks at retired services.
CAPABILITY_FALLBACK: dict[str, tuple[str, str]] = {}


# Soft cross-subscription routing. Empty after retiring xfyun / codingplan
# overflow members — remaining codes are single-source.
LOAD_BALANCE_GROUPS: dict[str, list[dict]] = {}


def get_load_balance_group(model: str) -> list[dict] | None:
    """Return the load-balance group for *model*, or None if single-source."""
    return LOAD_BALANCE_GROUPS.get(model)


def select_service_by_weight(
    services: list[dict],
    skip_services: frozenset[str] | None = None,
) -> tuple[str, str | None]:
    """Weighted random selection among service candidates.

    *skip_services*: set of service names currently in cooldown — these are
    excluded from selection.  If all are skipped, fall back to the first entry.

    Returns (service_name, model_override_or_None).
    """
    import random
    candidates = services
    if skip_services:
        candidates = [s for s in services if s["service"] not in skip_services]
    if not candidates:
        candidates = services
    total = sum(s["weight"] for s in candidates)
    r = random.random() * total
    cumulative = 0
    for s in candidates:
        cumulative += s["weight"]
        if r <= cumulative:
            return s["service"], s.get("model")
    return candidates[-1]["service"], candidates[-1].get("model")


# Caller-only aliases for 实验室AKM / Nebula. Keys are /v1 model ids (must
# start with nebula-); values are the upstream id sent to llm.nebula.
# Keep these out of MODEL_SERVICE_MAP so they do not steal lant names.
NEBULA_CALLER_ROUTES: dict[str, tuple[str, str]] = {
    "nebula-opus-4-6": ("claude-opus-4-6", "llm.nebula"),
    "nebula-sonnet-4-6": ("claude-sonnet-4-6", "llm.nebula"),
    "nebula-gpt-5.4": ("gpt-5.4", "llm.nebula"),
    "nebula-gpt-5.4-mini": ("gpt-5.4-mini", "llm.nebula"),
    "nebula-gpt-5.4-nano": ("gpt-5.4-nano", "llm.nebula"),
    "nebula-ds-v4-flash": ("deepseek-v4-flash", "llm.nebula"),
    "nebula-ds-v4-pro": ("deepseek-v4-pro", "llm.nebula"),
}


def resolve_model_and_service(model: str) -> tuple[str, str] | tuple[None, None]:
    """Return (resolved_id, service_name).

    * Cloud capability codes (4-bit QCSA or V-prefixed) → upstream vendor models.
    * Explicit model names via STRICT_MODEL_MAP / MODEL_SERVICE_MAP.
    * Nebula caller ids via NEBULA_CALLER_ROUTES.
    """
    raw = (model or "").strip()
    if not raw:
        return None, None

    nebula_route = NEBULA_CALLER_ROUTES.get(raw.lower())
    if nebula_route:
        return nebula_route

    if raw.upper().startswith("V") and len(raw) == 5:
        cap = CAPABILITY_CLOUD_MAP.get(raw.upper())
        if cap:
            return cap

    if len(raw) == 4 and all(c in "01" for c in raw):
        cap = CAPABILITY_CLOUD_MAP.get(raw)
        if cap:
            return cap

    if raw in MODEL_SERVICE_MAP:
        return raw, MODEL_SERVICE_MAP[raw]
    alias = STRICT_MODEL_MAP.get(raw.lower())
    if alias and alias in MODEL_SERVICE_MAP:
        return alias, MODEL_SERVICE_MAP[alias]

    return None, None


def is_opaque_caller_model(model: str) -> bool:
    """True when API should echo *model* as-is (capability / nebula-*), not upstream name."""
    raw = (model or "").strip()
    if raw.lower().startswith("nebula-"):
        return True
    if raw.upper().startswith("V") and len(raw) == 5:
        return True
    if len(raw) == 4 and all(c in "01" for c in raw):
        return True
    return False


def caller_facing_model(requested: str, resolved_upstream: str) -> str:
    """Model id returned to clients (avoid leaking vendor tags)."""
    if is_opaque_caller_model(requested):
        return requested.strip()
    return requested.strip() or resolved_upstream


def get_capability_fallback(capability_code: str) -> tuple[str, str] | None:
    """Return (fallback_model, fallback_service) for a capability code, or None."""
    return CAPABILITY_FALLBACK.get(capability_code)


def get_all_registered_services() -> list[str]:
    """Return all unique service names from MODEL_SERVICE_MAP + Nebula.

    Used by test_center.py to query LLM service status for all registered services.
    """
    services = list(set(MODEL_SERVICE_MAP.values()))
    services.extend(svc for _, svc in NEBULA_CALLER_ROUTES.values() if svc not in services)
    return services
