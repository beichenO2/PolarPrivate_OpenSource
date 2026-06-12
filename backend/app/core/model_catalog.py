"""Model catalog for GET /v1/models.

Lists models that are known to be available through the proxy.
This is a static list maintained alongside model_routing.py.

To add a new model:
1. Ensure the provider binding exists (check /proxy/ discovery endpoint)
2. Append an entry below following the ModelEntry structure.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.local_model_routing import (
    EMBED_CODE,
    LOCAL_SERVICE_NAME,
    all_l_codes,
)


@dataclass
class ModelEntry:
    id: str           # Exact model ID string (as sent to the upstream API)
    provider: str     # Human-readable provider name
    service: str      # Binding service_name in PolarPrivate
    description: str = ""


MODEL_CATALOG: list[ModelEntry] = [
    # ── 讯飞星火 MaaS 企业版（xfyun）─────────────────────────────────────
    ModelEntry(
        id="xopglm51",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="GLM-5.1（200K 上下文），国内最强编程模型；别名 glm / glm-5.1 / glm51。",
    ),
    ModelEntry(
        id="xopkimik26",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="Kimi-K2.6（256K 上下文），单图 VLM 最强；⚠️ xfyun 代理限制：最多 3-4 张图片，超出返回 500。",
    ),
    ModelEntry(
        id="xopdeepseekv4flash",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="Deepseek V4 Flash（1M 上下文），快速模型，agent 能力突出。",
    ),
    ModelEntry(
        id="xopdeepseekv4pro",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="Deepseek V4 Pro（1M 上下文），旗舰推理+编程，综合最强国模。",
    ),
    # ── MiniMax ───────────────────────────────────────────────────────────────
    ModelEntry(
        id="MiniMax-M3",
        provider="minimax",
        service="llm.minimax",
        description="MiniMax M3 旗舰，快速响应。",
    ),
    ModelEntry(
        id="MiniMax-M3-Thinking",
        provider="minimax",
        service="llm.minimax",
        description="MiniMax M3 + thinking=adaptive，深度推理模式。",
    ),
    # ── Aliyun / DashScope ───────────────────────────────────────────────────
    ModelEntry(
        id="qwen3.7-plus",
        provider="aliyun",
        service="llm.aliyun.codingplan",
        description="Qwen3.7 Plus，默认视觉模型（效果好、详细度高）；多图无限制，44页文档可处理。",
    ),
    ModelEntry(
        id="qwen3-vl-flash",
        provider="aliyun",
        service="llm.aliyun.dashscope",
        description="Qwen3 VL Flash，批量图片首选（44页仅30s）；多图无限制，速度最快。",
    ),
    # ── Cloud capability codes (4-bit QCSA; opaque to callers) ──────────────
    # Q=Quality C=Context S=Speed A=Agentic (each 0 or 1)
    ModelEntry(id="0000", provider="capability", service="llm.glm51.enterprise", description="默认均衡 → GLM-5.1（200K）"),
    ModelEntry(id="0010", provider="capability", service="llm.glm51.enterprise", description="快速 → DS V4 Flash（1M 上下文）"),
    ModelEntry(id="0100", provider="capability", service="llm.glm51.enterprise", description="长上下文 → DS V4 Pro（1M）"),
    ModelEntry(id="0110", provider="capability", service="llm.minimax", description="快速+长上下文 → MiniMax-M3"),
    ModelEntry(id="1000", provider="capability", service="llm.glm51.enterprise", description="旗舰质量 → GLM-5.1（200K）"),
    ModelEntry(id="1110", provider="capability", service="llm.minimax", description="旗舰+深度推理 → MiniMax-M3-Thinking"),
    # Agentic codes (A=1)
    ModelEntry(id="0001", provider="capability", service="llm.glm51.enterprise", description="Agent 均衡 → DS V4 Flash（tool call 快准）"),
    ModelEntry(id="0011", provider="capability", service="llm.glm51.enterprise", description="Agent 快速 → DS V4 Flash"),
    ModelEntry(id="1001", provider="capability", service="llm.glm51.enterprise", description="Agent 旗舰 → DS V4 Pro（复杂多步）"),
    # Vision/Multimodal (V prefix)
    ModelEntry(id="V0000", provider="capability", service="llm.aliyun.codingplan", description="默认视觉 → qwen3.7-plus（效果最好最详细，44 页 PDF 可处理）"),
    ModelEntry(id="V0010", provider="capability", service="llm.aliyun.dashscope", description="视觉快速 → qwen3-vl-flash（批量图片最快，44 页仅 30s）"),
    ModelEntry(id="V1000", provider="capability", service="llm.glm51.enterprise", description="单页视觉旗舰 → Kimi-K2.6（单图最强，xfyun 代理限 3-4 张）"),
    ModelEntry(id="V0001", provider="capability", service="llm.glm51.enterprise", description="视觉 Agent 单图 → Kimi-K2.6（单图最强 + tool call；⚠️限3-4图）"),
    ModelEntry(id="V0101", provider="capability", service="llm.aliyun.codingplan", description="视觉 Agent 多图 → qwen3.7-plus（44页可处理，C=1 长上下文 + tool call）"),
    # ── Local (L-prefix; embedding only) ───────────────────────────────────
    *[
        ModelEntry(
            id=code,
            provider="local",
            service=LOCAL_SERVICE_NAME,
            description="Local embedding — qwen3-embedding:8b.",
        )
        for code in all_l_codes()
    ],
    ModelEntry(
        id=EMBED_CODE,
        provider="local",
        service=LOCAL_SERVICE_NAME,
        description="Local embedding model slot (POST /v1/embeddings only).",
    ),
]
