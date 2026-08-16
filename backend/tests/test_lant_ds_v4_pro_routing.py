"""AKM formal suite pins model=lant_ds_v4_pro → llm.lant (not xfyun / QCSA)."""

from app.core.model_routing import resolve_model_and_service


def test_lant_ds_v4_pro_routes_to_lant_relay():
    assert resolve_model_and_service("lant_ds_v4_pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )


def test_xfyun_ds_v4_pro_alias_stays_on_enterprise():
    assert resolve_model_and_service("ds-v4-pro") == (
        "xopdeepseekv4pro",
        "llm.glm51.enterprise",
    )
    assert resolve_model_and_service("xopdeepseekv4pro") == (
        "xopdeepseekv4pro",
        "llm.glm51.enterprise",
    )
