"""Regression guard: the document-identity sanitize middleware is retired.

PolarPrivate is a secret vault + LLM proxy (Agent supply plane). The
``/api/sanitize/mappings`` endpoint returns secret keys only, so a client-side
sanitize/resolve middleware has no data to work with and must not be shipped.
"""

from __future__ import annotations

import importlib

import pytest

import privportal_sdk


class TestSanitizeMiddlewareRetired:
    def test_package_does_not_export_middleware(self) -> None:
        assert not hasattr(privportal_sdk, "PrivPortalMiddleware")

    def test_all_has_no_middleware_symbol(self) -> None:
        assert all("Middleware" not in name for name in privportal_sdk.__all__)

    def test_middleware_module_is_gone(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("privportal_sdk.middleware")


class TestSupplyPlaneSurfaceRetained:
    """Removing the middleware must not take the supply-plane API with it."""

    @pytest.mark.parametrize(
        "name",
        [
            "resolve_user",
            "list_user_bindings",
            "create_binding",
            "default_base_url",
            "chat_completion",
            "achat_completion",
            "is_healthy",
            "list_models",
        ],
    )
    def test_symbol_still_exported(self, name: str) -> None:
        assert hasattr(privportal_sdk, name)
        assert name in privportal_sdk.__all__
