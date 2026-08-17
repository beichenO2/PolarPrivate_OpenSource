"""实验室AKM / Nebula /v1 ids are nebula-* and do not steal lant/xfyun names."""

from app.core.model_routing import is_opaque_caller_model, resolve_model_and_service


def test_nebula_prefixed_ids_route_to_nebula():
    assert resolve_model_and_service("nebula-opus-4-6") == (
        "claude-opus-4-6",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-sonnet-4-6") == (
        "claude-sonnet-4-6",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-gpt-5.4") == (
        "gpt-5.4",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-gpt-5.4-mini") == (
        "gpt-5.4-mini",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-gpt-5.4-nano") == (
        "gpt-5.4-nano",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-ds-v4-flash") == (
        "deepseek-v4-flash",
        "llm.nebula",
    )
    assert resolve_model_and_service("nebula-ds-v4-pro") == (
        "deepseek-v4-pro",
        "llm.nebula",
    )


def test_generic_names_do_not_silently_use_nebula():
    assert resolve_model_and_service("claude-opus-4-6") == (None, None)
    assert resolve_model_and_service("claude-sonnet-4-6") == (None, None)
    assert resolve_model_and_service("gpt-5.4") == (None, None)
    assert resolve_model_and_service("opus-4-6") == (None, None)
    assert resolve_model_and_service("sonnet-4-6") == (None, None)


def test_nebula_ids_are_opaque_and_do_not_steal_lant_names():
    assert is_opaque_caller_model("nebula-opus-4-6")
    assert resolve_model_and_service("lant_ds_v4_pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )
    assert resolve_model_and_service("deepseek-v4-pro") == (
        "deepseek-v4-pro",
        "llm.lant",
    )
    assert resolve_model_and_service("ds-v4-flash") == (None, None)
