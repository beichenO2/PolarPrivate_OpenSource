"""Regression tests for repository self-description alignment."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_capabilities_declares_versioned_v1_gateway() -> None:
    manifest = json.loads(_read_repo_file("capabilities.json"))

    version = tuple(int(part) for part in manifest["version"].split("."))
    endpoints = {
        capability.get("endpoint")
        for capability in manifest.get("capabilities", [])
    }

    assert version > (0, 5, 0)
    assert "/v1/chat/completions" in endpoints


def test_security_model_describes_wrapped_fernet_keys() -> None:
    security_model = _read_repo_file("docs/security-model.md")

    assert "Fernet Key 明文存储" not in security_model
    assert "fernet_keys_json" in security_model
    assert "加密存储" in security_model
    assert "wrapped" in security_model.lower()


def test_reveal_is_only_documented_as_removed() -> None:
    removal_markers = ("已移除", "永久删除", "已删除", "不存在", "removed", "r9")

    for relative_path in ("docs/api-reference.md", "docs/architecture.md"):
        document = _read_repo_file(relative_path)
        assert "### `POST /api/secrets/{secret_id}/reveal`" not in document

        for match in re.finditer("reveal", document, flags=re.IGNORECASE):
            context = document[
                max(0, match.start() - 160) : min(len(document), match.end() + 160)
            ].lower()
            assert any(marker in context for marker in removal_markers), (
                f"{relative_path} documents reveal outside a removal context: {context!r}"
            )
