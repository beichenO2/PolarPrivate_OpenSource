"""Model → binding routing table for the /v1 unified LLM gateway.

To add a new provider:
1. Add the binding via PolarPrivate UI or API (POST /api/bindings)
2. Append a new entry here: (model_prefix, service_name)

Order matters: more specific prefixes should come first.
"""

from __future__ import annotations

import os

from app.core.local_model_routing import (
    LOCAL_SERVICE_NAME,
    is_local_chat_code,
    normalize_l_code,
)


def fast_minimax_model() -> str:
    """MiniMax slot for capability code 111 (default: current standard MiniMax-M3)."""
    return os.environ.get("POLARPRIVATE_MINIMAX_FAST_MODEL", "MiniMax-M3").strip()


# Cloud capability codes (4-bit QCSA) — opaque to callers; mapped server-side only.
# Q=Quality(0=standard,1=flagship) C=Context(0=standard,1=long)
# S=Speed(0=balanced,1=fast) A=Agentic(0=conversational,1=agent/tool-use)
# Prefix V = Vision/multimodal (e.g. V0000, V1000)
CAPABILITY_CLOUD_MAP: dict[str, tuple[str, str]] = {
    # ── Text-only (4-bit QCSA) ──
    "0000": ("xopglm52", "llm.glm51.enterprise"),              # 默认均衡 → GLM-5.2（xfyun 现已支持）
    "0010": ("xopdeepseekv4flash", "llm.glm51.enterprise"),    # 快速
    "0100": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # 长上下文
    "0110": ("MiniMax-M3", "llm.minimax"),                     # 快速+长上下文
    "1000": ("xopglm52", "llm.glm51.enterprise"),              # 旗舰（质量优先对话）→ GLM-5.2
    "1100": ("qwen3.7-plus", "llm.aliyun.codingplan"),        # 旗舰+长上下文（Qwen3.7-Plus 纯文本）
    "1110": ("MiniMax-M3-Thinking", "llm.minimax"),            # 旗舰+深度推理
    # ── Agentic (A=1) ──
    "0001": ("xopdeepseekv4flash", "llm.glm51.enterprise"),    # Agent 均衡（tool call 最快最准）
    "0011": ("xopdeepseekv4flash", "llm.glm51.enterprise"),    # Agent 快速
    "0101": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # Agent 长上下文（DS V4 Pro + tool call）
    "1001": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # Agent 旗舰（复杂多步）
    "1011": ("xopdeepseekv4flash", "llm.glm51.enterprise"),    # Agent 旗舰+快速
    "1101": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # Agent 旗舰+长上下文
    # ── Vision/Multimodal (V prefix) ──
    "V0000": ("qwen3.7-plus", "llm.aliyun.codingplan"),        # 默认视觉（效果最好最详细）
    "V0010": ("qwen3-vl-flash", "llm.aliyun.dashscope"),      # 视觉快速（大量图片 44p/30s）
    "V1000": ("xopkimik26", "llm.glm51.enterprise"),           # 单页视觉旗舰（K2.6 单图最强）
    "V0001": ("xopkimik26", "llm.glm51.enterprise"),           # 视觉 Agent 单图（K2.6 + tool call）
    "V0101": ("qwen3.7-plus", "llm.aliyun.codingplan"),        # 视觉 Agent 多图/长文本（qwen3.7 C=1 大量图片）
}


STRICT_MODEL_MAP = {
    # ── 讯飞星火 MaaS 企业版（xfyun）──
    "glm": "xopglm52",
    "glm-5.1": "xopglm51",
    "glm51": "xopglm51",
    "xopglm51": "xopglm51",
    # GLM-5.2 on the working xfyun line (default via QCSA 0000)
    "glm-5.2-xfyun": "xopglm52",
    "glm52": "xopglm52",
    "xopglm52": "xopglm52",
    # Bare glm-5.2 / glm2 alias → dedicated 128K "glm2" line (88.api456.me)
    "glm-5.2": "glm-5.2",
    "glm2": "glm-5.2",
    "glm-5": "GLM-5",
    "glm-5-turbo": "GLM-5-Turbo",
    "glm-turbo": "GLM-5-Turbo",
    "kimi": "xopkimik26",
    "kimi-k2.6": "xopkimik26",
    "xopkimik26": "xopkimik26",
    "deepseek-v4-flash": "xopdeepseekv4flash",
    "ds-v4-flash": "xopdeepseekv4flash",
    "xopdeepseekv4flash": "xopdeepseekv4flash",
    "deepseek-v4-pro": "xopdeepseekv4pro",
    "ds-v4-pro": "xopdeepseekv4pro",
    "xopdeepseekv4pro": "xopdeepseekv4pro",
    # ── 阿里云 codingPlan ──
    "qwen-plus": "qwen3.7-plus",
    "qwen3.5-plus": "qwen3.7-plus",
    "qwen3.6-plus": "qwen3.7-plus",
    "qwen3.7-plus": "qwen3.7-plus",
    # ── 阿里云 DashScope (compatible-mode) — VL 系列 ──
    # 默认 VLM = qwen3.7-plus（效果最好），大量图片时用 qwen3-vl-flash（最快 44 页仅 30s）
    # Kimi-K2.6 单图最强但多图限 3-4 张（xfyun 代理限制），聊天场景单图走 capability 101
    "qwen-vl": "qwen3-vl-flash",
    "qwen3-vl": "qwen3-vl-flash",
    "qwen3-vl-flash": "qwen3-vl-flash",
    # ── MiniMax ──
    "minimax": "MiniMax-M3",
    "minimax-m3": "MiniMax-M3",
    "minimax-m3-thinking": "MiniMax-M3-Thinking",
}

MODEL_SERVICE_MAP = {
    # 讯飞星火 MaaS 企业版（所有 xop* 模型共用同一 API key + base_url）
    "xopglm51": "llm.glm51.enterprise",
    "xopglm52": "llm.glm51.enterprise",
    # 独立 glm2 线（新购 128K key，端点 88.api456.me；模型名对上游即 glm-5.2）
    "glm-5.2": "llm.glm2",
    "GLM-5": "llm.glm51.enterprise",
    "GLM-5-Turbo": "llm.glm51.enterprise",
    "xopkimik26": "llm.glm51.enterprise",
    "xopdeepseekv4flash": "llm.glm51.enterprise",
    "xopdeepseekv4pro": "llm.glm51.enterprise",
    # 阿里云 codingPlan
    "qwen3.7-plus": "llm.aliyun.codingplan",
    # 阿里云 DashScope VL 系列
    "qwen3-vl-flash": "llm.aliyun.dashscope",
    # MiniMax (OpenAI-compatible https://api.minimax.io/v1)
    "MiniMax-M3": "llm.minimax",
    "MiniMax-M3-Thinking": "llm.minimax",
}

# ── Capability-code 专用 fallback ─────────────────────────────────────────
# 当 CAPABILITY_CLOUD_MAP 的主路由返回 429/5xx 时，自动切换到备选(model, service)。
# 仅 capability code 使用；普通模型名靠 binding 级 fallback_chain。
CAPABILITY_FALLBACK: dict[str, tuple[str, str]] = {
    "V1000": ("qwen3-vl-flash", "llm.aliyun.dashscope"),      # K2.6 多图/500 → flash
    "0010": ("qwen3.7-plus", "llm.aliyun.codingplan"),         # DS Flash 不可用 → qwen
    "1000": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # GLM 不可用 → DS Pro
    "0001": ("xopdeepseekv4pro", "llm.glm51.enterprise"),      # Agent Flash 不可用 → Pro
}


# ── 负载均衡组 ──────────────────────────────────────────────────────────────
# 模型名 → [{service, weight}, ...]；按权重随机选择提供源。
# 不在组内的模型仍走 MODEL_SERVICE_MAP 单源映射。
# 与 fallback 机制独立：负载均衡是主动分配，fallback 是被动切换。
# Phase 3: overflow 时按权重选备用 service (主 service 冷却中则跳过)。

# 软性跨订阅路由（soft routing）：每个文本档位给出跨「订阅」的候选 (service, model)。
# 目的：不靠本地自节流，而是把负载分摊到多个已付费订阅；当某订阅冷却中
# （刚被上游 429）时，select_service_by_weight(skip_services=...) 会跳过它，
# 自动「引流到没有限流的订阅」。weight 仅决定正常时的分配比例（主源占大头）。
#
# 仅文本档位参与：视觉(V*)模型各订阅能力差异大（图片张数/格式限制），
# 保持单源以免把图片请求路由到非视觉模型。
# key = resolve_model_and_service() 解析出的上游模型名（full_model）。
LOAD_BALANCE_GROUPS: dict[str, list[dict]] = {
    # 均衡/旗舰对话（0000 / 1000 → GLM-5.2）：两条 GLM-5.2 线路（xfyun xopglm52
    # + 独立 glm2 线 88.api456.me）**负载均衡**，各 50%；MiniMax 作 overflow 兜底。
    "xopglm52": [
        {"service": "llm.glm51.enterprise", "model": "xopglm52", "weight": 50},
        {"service": "llm.glm2", "model": "glm-5.2", "weight": 50},
        {"service": "llm.minimax", "model": "MiniMax-M3", "weight": 0},
    ],
    # 旧 GLM-5.1 组（保留：显式请求 glm-5.1/xopglm51 时仍走 5.1）
    "xopglm51": [
        {"service": "llm.glm51.enterprise", "model": "xopglm51", "weight": 60},
        {"service": "llm.minimax", "model": "MiniMax-M3", "weight": 20},
        {"service": "llm.aliyun.codingplan", "model": "qwen3.7-plus", "weight": 20},
    ],
    # Agent/快速（0001 / 0010 / 0011）：DS V4 Flash 主（工具最准），
    # Qwen3.7 次（同样支持 tool call），MiniMax-M3 兜底
    "xopdeepseekv4flash": [
        {"service": "llm.glm51.enterprise", "model": "xopdeepseekv4flash", "weight": 70},
        {"service": "llm.aliyun.codingplan", "model": "qwen3.7-plus", "weight": 20},
        {"service": "llm.minimax", "model": "MiniMax-M3", "weight": 10},
    ],
    # Agent 旗舰/长上下文（0100 / 0101 / 1001）：DS V4 Pro 主，Qwen3.7(1M) 分流
    "xopdeepseekv4pro": [
        {"service": "llm.glm51.enterprise", "model": "xopdeepseekv4pro", "weight": 75},
        {"service": "llm.aliyun.codingplan", "model": "qwen3.7-plus", "weight": 25},
    ],
    # 快速+长上下文（0110）：MiniMax-M3 主，DS V4 Flash 分流
    "MiniMax-M3": [
        {"service": "llm.minimax", "model": "MiniMax-M3", "weight": 70},
        {"service": "llm.glm51.enterprise", "model": "xopdeepseekv4flash", "weight": 30},
    ],
    # 深度推理（1110）：MiniMax-M3-Thinking 主，DS V4 Pro 分流
    "MiniMax-M3-Thinking": [
        {"service": "llm.minimax", "model": "MiniMax-M3-Thinking", "weight": 70},
        {"service": "llm.glm51.enterprise", "model": "xopdeepseekv4pro", "weight": 30},
    ],
}


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


def resolve_model_and_service(model: str) -> tuple[str, str] | tuple[None, None]:
    """Return (resolved_id, service_name).

    * Cloud capability codes (4-bit QCSA or V-prefixed) → upstream vendor models.
    * Local code ``L0000`` → ``llm.local.ollama`` (embedding only).
    * Explicit model names via STRICT_MODEL_MAP / MODEL_SERVICE_MAP.
    """
    raw = (model or "").strip()
    if not raw:
        return None, None

    l_code = normalize_l_code(raw)
    if l_code:
        return l_code, LOCAL_SERVICE_NAME

    # V-prefixed vision codes (e.g. V0000, V1000)
    if raw.upper().startswith("V") and len(raw) == 5:
        cap = CAPABILITY_CLOUD_MAP.get(raw.upper())
        if cap:
            return cap

    # 4-bit QCSA codes
    if len(raw) == 4 and all(c in "01" for c in raw):
        cap = CAPABILITY_CLOUD_MAP.get(raw)
        if cap:
            return cap

    # Explicit upstream model ids (e.g. MiniMax-M3)
    if raw in MODEL_SERVICE_MAP:
        return raw, MODEL_SERVICE_MAP[raw]
    alias = STRICT_MODEL_MAP.get(raw.lower())
    if alias and alias in MODEL_SERVICE_MAP:
        return alias, MODEL_SERVICE_MAP[alias]

    return None, None


def is_opaque_caller_model(model: str) -> bool:
    """True when API should echo *model* as-is (capability / L-code), not upstream name."""
    raw = (model or "").strip()
    if is_local_chat_code(raw):
        return True
    if raw.upper().startswith("V") and len(raw) == 5:
        return True
    if len(raw) == 4 and all(c in "01" for c in raw):
        return True
    return False


def caller_facing_model(requested: str, resolved_upstream: str) -> str:
    """Model id returned to clients (avoid leaking vendor / Ollama tags)."""
    if is_opaque_caller_model(requested):
        raw = requested.strip()
        l = normalize_l_code(raw)
        if l:
            return l
        return raw
    return requested.strip() or resolved_upstream


def get_capability_fallback(capability_code: str) -> tuple[str, str] | None:
    """Return (fallback_model, fallback_service) for a capability code, or None."""
    return CAPABILITY_FALLBACK.get(capability_code)


def get_all_registered_services() -> list[str]:
    """Return all unique service names from MODEL_SERVICE_MAP.

    Used by test_center.py to query LLM service status for all registered services.
    """
    services = list(set(MODEL_SERVICE_MAP.values()))
    if LOCAL_SERVICE_NAME not in services:
        services.append(LOCAL_SERVICE_NAME)
    return services
