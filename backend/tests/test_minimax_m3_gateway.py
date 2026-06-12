"""MiniMax-M3 routing and gateway body defaults."""

from __future__ import annotations

import json

from app.core.model_routing import CAPABILITY_CLOUD_MAP, resolve_model_and_service
from app.services.minimax_gateway import MINIMAX_M3_MODEL_ID, apply_minimax_upstream_defaults


def test_capability_0110_maps_to_minimax_m3():
    assert resolve_model_and_service("0110") == ("MiniMax-M3", "llm.minimax")


def test_capability_1110_maps_to_minimax_thinking():
    assert resolve_model_and_service("1110") == ("MiniMax-M3-Thinking", "llm.minimax")


def test_vision_codes():
    assert resolve_model_and_service("V0000") == ("qwen3.7-plus", "llm.aliyun.codingplan")
    assert resolve_model_and_service("V1000") == ("xopkimik26", "llm.glm51.enterprise")
    assert resolve_model_and_service("V0010") == ("qwen3-vl-flash", "llm.aliyun.dashscope")


def test_resolve_explicit_minimax_m3():
    assert resolve_model_and_service("MiniMax-M3") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("MiniMax-M2.7-highspeed") == (None, None)


def test_apply_m3_disables_thinking_by_default():
    obj = {"model": MINIMAX_M3_MODEL_ID, "messages": [{"role": "user", "content": "hi"}]}
    apply_minimax_upstream_defaults(obj)
    assert obj.get("thinking") == {"type": "disabled"}


def test_apply_m3_preserves_existing_thinking():
    obj = {
        "model": MINIMAX_M3_MODEL_ID,
        "messages": [{"role": "user", "content": "hi"}],
        "thinking": {"type": "adaptive"},
    }
    apply_minimax_upstream_defaults(obj)
    assert obj["thinking"] == {"type": "adaptive"}


def test_apply_m3_ignores_other_models():
    obj = {"model": "qwen3.5-plus", "messages": [{"role": "user", "content": "hi"}]}
    apply_minimax_upstream_defaults(obj)
    assert "extra_body" not in obj
