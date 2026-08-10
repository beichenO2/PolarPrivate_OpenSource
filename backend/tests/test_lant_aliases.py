"""Explicit lant.* aliases must resolve to llm.lant upstream models."""
from app.core.model_routing import resolve_model_and_service


def test_lant_ds_v4_pro_routes_to_lant_deepseek():
    assert resolve_model_and_service("lant_ds_v4_pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )


def test_lant_glm_52_routes_to_lant_glm():
    assert resolve_model_and_service("lant_glm_52") == ("glm-5.2", "llm.lant")


def test_bare_deepseek_v4_pro_still_lant():
    assert resolve_model_and_service("deepseek-v4-pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )
