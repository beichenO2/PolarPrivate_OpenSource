"""Tests for PrivPortalMiddleware — pure in-memory, no server needed."""

from __future__ import annotations

import pytest

from privportal_sdk import PrivPortalMiddleware


@pytest.fixture
def mw() -> PrivPortalMiddleware:
    m = PrivPortalMiddleware()
    m.load_from_dict({
        "identities": [
            {"key": "identity.student.name", "value": "张三", "project_id": None},
            {"key": "identity.student.email", "value": "zhangsan@example.com", "project_id": None},
            {"key": "identity.teacher.name", "value": "李老师", "project_id": None},
            {"key": "identity.student.fullname", "value": "张三丰", "project_id": None},
        ],
        "secrets": [
            {"key": "secret.openai.default.api_key", "project_id": None},
        ],
        "version": "1",
    })
    return m


class TestSanitize:
    def test_basic_replacement(self, mw: PrivPortalMiddleware) -> None:
        result = mw.sanitize("你好，我是张三")
        assert "张三" not in result
        assert "[[identity.student.name]]" in result

    def test_multiple_values(self, mw: PrivPortalMiddleware) -> None:
        result = mw.sanitize("张三的邮箱是zhangsan@example.com")
        assert "张三" not in result
        assert "zhangsan@example.com" not in result
        assert "[[identity.student.name]]" in result
        assert "[[identity.student.email]]" in result

    def test_no_match_passthrough(self, mw: PrivPortalMiddleware) -> None:
        text = "今天天气不错"
        assert mw.sanitize(text) == text

    def test_longer_value_takes_priority(self, mw: PrivPortalMiddleware) -> None:
        """'张三丰' should match before '张三'."""
        result = mw.sanitize("张三丰是太极拳的创始人")
        assert "[[identity.student.fullname]]" in result
        assert "张三丰" not in result

    def test_empty_string(self, mw: PrivPortalMiddleware) -> None:
        assert mw.sanitize("") == ""

    def test_not_loaded(self) -> None:
        m = PrivPortalMiddleware()
        assert m.sanitize("张三") == "张三"


class TestResolve:
    def test_basic_resolve(self, mw: PrivPortalMiddleware) -> None:
        result = mw.resolve("[[identity.student.name]]你好")
        assert result == "张三你好"

    def test_multiple_resolve(self, mw: PrivPortalMiddleware) -> None:
        text = "[[identity.student.name]]的邮箱是[[identity.student.email]]"
        result = mw.resolve(text)
        assert result == "张三的邮箱是zhangsan@example.com"

    def test_no_placeholder_passthrough(self, mw: PrivPortalMiddleware) -> None:
        text = "普通文本"
        assert mw.resolve(text) == text

    def test_unknown_placeholder_passthrough(self, mw: PrivPortalMiddleware) -> None:
        text = "[[identity.unknown.field]]保持原样"
        assert mw.resolve(text) == text


class TestRoundTrip:
    def test_sanitize_then_resolve(self, mw: PrivPortalMiddleware) -> None:
        original = "你好，我是张三，邮箱是zhangsan@example.com"
        sanitized = mw.sanitize(original)
        assert "张三" not in sanitized
        assert "zhangsan@example.com" not in sanitized
        resolved = mw.resolve(sanitized)
        assert resolved == original

    def test_mixed_content(self, mw: PrivPortalMiddleware) -> None:
        original = "学生张三和老师李老师在讨论"
        sanitized = mw.sanitize(original)
        assert "张三" not in sanitized
        assert "李老师" not in sanitized
        resolved = mw.resolve(sanitized)
        assert resolved == original


class TestDetectLeaks:
    def test_detect_known_value(self, mw: PrivPortalMiddleware) -> None:
        leaks = mw.detect_leaks("AI 回复了: 你好张三")
        assert len(leaks) >= 1
        assert any(l["value"] == "张三" for l in leaks)

    def test_no_leaks(self, mw: PrivPortalMiddleware) -> None:
        leaks = mw.detect_leaks("一切正常，没有隐私信息")
        assert leaks == []


class TestMetadata:
    def test_counts(self, mw: PrivPortalMiddleware) -> None:
        assert mw.identity_count == 4
        assert mw.secret_count == 1

    def test_is_loaded(self, mw: PrivPortalMiddleware) -> None:
        assert mw.is_loaded

    def test_repr(self, mw: PrivPortalMiddleware) -> None:
        r = repr(mw)
        assert "loaded=True" in r
        assert "identities=4" in r
