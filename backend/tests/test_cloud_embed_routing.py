"""E000 maps to DashScope qwen3.7-text-embedding unless CLOUD_EMBED_MODEL overrides."""

from app.core.cloud_embed_routing import (
    DEFAULT_CLOUD_EMBED_MODEL,
    EMBED_CODE,
    EMBED_SERVICE_NAME,
    resolve_cloud_embed_model,
)


def test_default_cloud_embed_is_qwen37_text_embedding(monkeypatch):
    monkeypatch.delenv("CLOUD_EMBED_MODEL", raising=False)
    monkeypatch.delenv("CLOUD_EMBED_MODEL_E000", raising=False)
    assert DEFAULT_CLOUD_EMBED_MODEL == "qwen3.7-text-embedding"
    assert resolve_cloud_embed_model(EMBED_CODE) == "qwen3.7-text-embedding"
    assert EMBED_SERVICE_NAME == "llm.aliyun.dashscope"


def test_cloud_embed_model_env_overrides_default(monkeypatch):
    monkeypatch.setenv("CLOUD_EMBED_MODEL", "text-embedding-v4")
    assert resolve_cloud_embed_model("E000") == "text-embedding-v4"
