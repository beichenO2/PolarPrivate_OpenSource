"""privportal-sdk — client for the PolarPrivate secret vault and LLM proxy."""

from privportal_sdk.identity import resolve_user, list_user_bindings, create_binding
from privportal_sdk.auth import default_base_url
from privportal_sdk.llm import chat_completion, achat_completion, is_healthy, list_models

__all__ = [
    "resolve_user", "list_user_bindings", "create_binding",
    "default_base_url",
    "chat_completion", "achat_completion", "is_healthy", "list_models",
]
__version__ = "0.7.0"
