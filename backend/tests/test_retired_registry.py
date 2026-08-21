"""Retired dead providers must leave the /v1 registry.

xfyun (llm.glm51.enterprise), Aliyun codingPlan, and local Ollama have no
live Binding. Capability codes and aliases that only existed for those
lines must resolve to nothing — not 503 BINDING_NOT_FOUND.
"""

from __future__ import annotations

from app.core.model_catalog import MODEL_CATALOG
from app.core.model_routing import (
    CAPABILITY_CLOUD_MAP,
    CAPABILITY_FALLBACK,
    LOAD_BALANCE_GROUPS,
    MODEL_SERVICE_MAP,
    STRICT_MODEL_MAP,
    get_all_registered_services,
    resolve_model_and_service,
)

RETIRED_SERVICES = (
    "llm.glm51.enterprise",
    "llm.aliyun.codingplan",
    "llm.local.ollama",
)

RETIRED_MODELS = (
    "1100",
    "qwen3.7-plus",
    "qwen-plus",
    "xopglm52",
    "xopglm51",
    "xopkimik26",
    "xopdeepseekv4flash",
    "xopdeepseekv4pro",
    "ds-v4-flash",
    "ds-v4-pro",
    "glm-5.2-xfyun",
    "L0000",
    "L0001",
)


def test_retired_models_do_not_resolve():
    for model in RETIRED_MODELS:
        assert resolve_model_and_service(model) == (None, None), model


def test_retired_services_absent_from_registry():
    registered = set(get_all_registered_services())
    for svc in RETIRED_SERVICES:
        assert svc not in registered, svc

    for svc in RETIRED_SERVICES:
        assert svc not in MODEL_SERVICE_MAP.values(), svc
        assert svc not in {entry[1] for entry in CAPABILITY_CLOUD_MAP.values()}, svc
        assert svc not in {entry[1] for entry in CAPABILITY_FALLBACK.values()}, svc

    for group in LOAD_BALANCE_GROUPS.values():
        for member in group:
            assert member["service"] not in RETIRED_SERVICES, member

    catalog_services = {entry.service for entry in MODEL_CATALOG}
    for svc in RETIRED_SERVICES:
        assert svc not in catalog_services, svc

    catalog_ids = {entry.id for entry in MODEL_CATALOG}
    for model in RETIRED_MODELS:
        assert model not in catalog_ids, model


def test_strict_map_has_no_xfyun_or_codingplan_aliases():
    banned_targets = {
        "xopglm52",
        "xopglm51",
        "xopkimik26",
        "xopdeepseekv4flash",
        "xopdeepseekv4pro",
        "qwen3.7-plus",
        "GLM-5",
        "GLM-5-Turbo",
    }
    for alias, target in STRICT_MODEL_MAP.items():
        assert target not in banned_targets, alias


def test_live_codes_still_resolve():
    assert resolve_model_and_service("V0010") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("V0000") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("V0001") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("V0101") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("V1000") == (
        "MiniMax-M3-Thinking",
        "llm.minimax",
    )
    assert resolve_model_and_service("0110") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("1110") == (
        "MiniMax-M3-Thinking",
        "llm.minimax",
    )
    assert resolve_model_and_service("0000") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("0001") == ("MiniMax-M3", "llm.minimax")
    assert resolve_model_and_service("0100") == ("deepseek-v4-pro", "llm.lant")
    assert resolve_model_and_service("glm-5.2") == ("glm-5.2", "llm.glm2")
    assert resolve_model_and_service("gpt-5.6-sol") == (
        "gpt-5.6-sol",
        "llm.rightapi",
    )
    assert resolve_model_and_service("qwen3-vl-flash") == (
        "qwen3-vl-flash",
        "llm.aliyun.dashscope",
    )
    assert resolve_model_and_service("qwen3.8-27b") == (
        "qwen3.8-27b",
        "llm.aliyun.dashscope",
    )
