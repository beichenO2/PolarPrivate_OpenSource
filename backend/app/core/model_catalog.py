"""Model catalog for GET /v1/models.

Lists models that are known to be available through the proxy.
This is a static list maintained alongside model_routing.py.

To add a new model:
1. Ensure the provider binding exists (check /proxy/ discovery endpoint)
2. Append an entry below following the ModelEntry structure.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.cloud_embed_routing import EMBED_CODE, EMBED_SERVICE_NAME
from app.core.media_routing import AUDIO_CODE, IMAGE_CODE, MEDIA_SERVICE_NAME, VIDEO_CODE


@dataclass
class ModelEntry:
    id: str           # Exact model ID string (as sent to the upstream API)
    provider: str     # Human-readable provider name
    service: str      # Binding service_name in PolarPrivate
    description: str = ""


MODEL_CATALOG: list[ModelEntry] = [
    ModelEntry(
        id="glm-5.2",
        provider="glm2",
        service="llm.glm2",
        description="GLM-5.2（128K 上下文），独立 glm2 线路（88.api456.me）；别名 glm2。",
    ),
    ModelEntry(
        id="gpt-5.6-sol",
        provider="rightapi",
        service="llm.rightapi",
        description="GPT-5.6 Sol（RightAPI Codex 号池，https://www.rightapi.ai/codex/v1）。",
    ),
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
    ModelEntry(
        id="nebula-opus-4-6",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · Claude Opus 4.6（上游 claude-opus-4-6）。",
    ),
    ModelEntry(
        id="nebula-sonnet-4-6",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · Claude Sonnet 4.6（上游 claude-sonnet-4-6）。",
    ),
    ModelEntry(
        id="nebula-gpt-5.4",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · GPT-5.4（上游 gpt-5.4）。",
    ),
    ModelEntry(
        id="nebula-gpt-5.4-mini",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · GPT-5.4 Mini（上游 gpt-5.4-mini）。",
    ),
    ModelEntry(
        id="nebula-gpt-5.4-nano",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · GPT-5.4 Nano（上游 gpt-5.4-nano）。",
    ),
    ModelEntry(
        id="nebula-ds-v4-flash",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · DeepSeek V4 Flash。",
    ),
    ModelEntry(
        id="nebula-ds-v4-pro",
        provider="nebula",
        service="llm.nebula",
        description="Nebula 渠道 · DeepSeek V4 Pro（勿与 lant_ds_v4_pro / llm.lant 混淆）。",
    ),
    ModelEntry(
        id="qwen3-vl-flash",
        provider="aliyun",
        service="llm.aliyun.dashscope",
        description="Qwen3 VL Flash（DashScope 显式别名，不占 V 码）。",
    ),
    ModelEntry(id="0000", provider="capability", service="llm.minimax", description="默认均衡 → MiniMax-M3"),
    ModelEntry(id="0010", provider="capability", service="llm.minimax", description="快速 → MiniMax-M3"),
    ModelEntry(id="0100", provider="capability", service="llm.lant", description="长上下文 → lant deepseek-v4-pro"),
    ModelEntry(id="0110", provider="capability", service="llm.minimax", description="快速+长上下文 → MiniMax-M3"),
    ModelEntry(id="1000", provider="capability", service="llm.minimax", description="旗舰质量 → MiniMax-M3"),
    ModelEntry(id="1110", provider="capability", service="llm.minimax", description="旗舰+深度推理 → MiniMax-M3-Thinking"),
    ModelEntry(id="0001", provider="capability", service="llm.minimax", description="Agent 均衡 → MiniMax-M3"),
    ModelEntry(id="0011", provider="capability", service="llm.minimax", description="Agent 快速 → MiniMax-M3"),
    ModelEntry(id="0101", provider="capability", service="llm.lant", description="Agent 长上下文 → lant deepseek-v4-pro"),
    ModelEntry(id="1001", provider="capability", service="llm.lant", description="Agent 旗舰 → lant deepseek-v4-pro"),
    ModelEntry(id="V0000", provider="capability", service="llm.minimax", description="默认视觉 → MiniMax-M3"),
    ModelEntry(id="V0010", provider="capability", service="llm.minimax", description="视觉快速 → MiniMax-M3"),
    ModelEntry(id="V1000", provider="capability", service="llm.minimax", description="视觉旗舰 → MiniMax-M3-Thinking"),
    ModelEntry(id="V0001", provider="capability", service="llm.minimax", description="视觉 Agent → MiniMax-M3"),
    ModelEntry(id="V0101", provider="capability", service="llm.minimax", description="视觉 Agent 长上下文 → MiniMax-M3"),
    ModelEntry(
        id=EMBED_CODE,
        provider="cloud",
        service=EMBED_SERVICE_NAME,
        description="Cloud embedding slot → DashScope qwen3.7-text-embedding (POST /v1/embeddings only).",
    ),
    ModelEntry(
        id=IMAGE_CODE,
        provider="capability",
        service=MEDIA_SERVICE_NAME,
        description="生图 → MiniMax image-01（POST /v1/images/generations）。",
    ),
    ModelEntry(
        id=AUDIO_CODE,
        provider="capability",
        service=MEDIA_SERVICE_NAME,
        description="生音频 / TTS → MiniMax speech-2.8-turbo（POST /v1/audio/speech）。",
    ),
    ModelEntry(
        id=VIDEO_CODE,
        provider="capability",
        service=MEDIA_SERVICE_NAME,
        description="生视频 → MiniMax-Hailuo-2.3（POST /v1/videos/generations）。",
    ),
]
