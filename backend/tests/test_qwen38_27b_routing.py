"""Bailian / DashScope: explicit qwen3.8-27b → llm.aliyun.dashscope."""

from app.core.model_catalog import MODEL_CATALOG
from app.core.model_routing import resolve_model_and_service
from app.services.models_dev_limits import max_context_tokens_for_model


def test_qwen38_27b_routes_to_dashscope():
    assert resolve_model_and_service("qwen3.8-27b") == (
        "qwen3.8-27b",
        "llm.aliyun.dashscope",
    )


def test_qwen38_27b_alias_is_case_insensitive():
    assert resolve_model_and_service("Qwen3.8-27B") == (
        "qwen3.8-27b",
        "llm.aliyun.dashscope",
    )


def test_catalog_lists_qwen38_27b():
    entry = next(e for e in MODEL_CATALOG if e.id == "qwen3.8-27b")
    assert entry.service == "llm.aliyun.dashscope"
    assert entry.provider == "aliyun"


def test_qwen38_27b_context_window():
    assert max_context_tokens_for_model("qwen3.8-27b") == 262144
