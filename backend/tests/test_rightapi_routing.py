"""RightAPI Codex: explicit gpt-5.6-sol → llm.rightapi."""

from app.core.model_catalog import MODEL_CATALOG
from app.core.model_routing import resolve_model_and_service


def test_gpt_56_sol_routes_to_rightapi():
    assert resolve_model_and_service("gpt-5.6-sol") == (
        "gpt-5.6-sol",
        "llm.rightapi",
    )


def test_gpt_56_alias_routes_to_sol():
    assert resolve_model_and_service("gpt-5.6") == (
        "gpt-5.6-sol",
        "llm.rightapi",
    )


def test_catalog_lists_gpt_56_sol():
    entry = next(e for e in MODEL_CATALOG if e.id == "gpt-5.6-sol")
    assert entry.service == "llm.rightapi"
    assert entry.provider == "rightapi"
