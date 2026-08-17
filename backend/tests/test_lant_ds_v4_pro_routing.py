"""AKM formal suite pins model=lant_ds_v4_pro → llm.lant (not xfyun / QCSA)."""

from app.core.model_routing import resolve_model_and_service


def test_lant_ds_v4_pro_routes_to_lant_relay():
    assert resolve_model_and_service("lant_ds_v4_pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )


def test_retired_xfyun_ds_aliases_do_not_resolve():
    assert resolve_model_and_service("ds-v4-pro") == (None, None)
    assert resolve_model_and_service("xopdeepseekv4pro") == (None, None)
