"""PolarPrivate pp_files: read local files and inject into messages; strip the field."""

from __future__ import annotations

import pytest

from app.core.file_inject import FileInjectError, expand_pp_files


def test_no_pp_files_is_noop():
    obj = {"model": "gpt-5.6-sol", "messages": [{"role": "user", "content": "hi"}]}
    out = expand_pp_files(obj)
    assert out["messages"][0]["content"] == "hi"
    assert "pp_files" not in out


def test_path_injected_and_field_stripped(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("INJECTED_MARKER_NEBULA_TEST\n", encoding="utf-8")
    obj = {
        "model": "gpt-5.6-sol",
        "messages": [{"role": "user", "content": "brief"}],
        "pp_files": [{"path": str(p.resolve())}],
    }
    out = expand_pp_files(obj)
    assert "pp_files" not in out
    body = out["messages"][0]["content"]
    assert "brief" in body
    assert "INJECTED_MARKER_NEBULA_TEST" in body
    assert f'path="{p.resolve()}"' in body
    assert "<<PP_FILE" in body
    assert "<</PP_FILE" in body


def test_relative_path_rejected(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("x", encoding="utf-8")
    obj = {
        "messages": [{"role": "user", "content": "hi"}],
        "pp_files": [{"path": "x.txt"}],
    }
    with pytest.raises(FileInjectError) as ei:
        expand_pp_files(obj)
    assert ei.value.status_code == 422
    assert ei.value.code == "PP_FILE_PATH_NOT_ABSOLUTE"


def test_missing_file_rejected(tmp_path):
    missing = tmp_path / "nope.txt"
    obj = {
        "messages": [{"role": "user", "content": "hi"}],
        "pp_files": [{"path": str(missing.resolve())}],
    }
    with pytest.raises(FileInjectError) as ei:
        expand_pp_files(obj)
    assert ei.value.status_code == 422
    assert ei.value.code == "PP_FILE_NOT_FOUND"


def test_inline_content_for_tests():
    obj = {
        "messages": [{"role": "user", "content": "hi"}],
        "pp_files": [{"name": "inline.txt", "content": "INLINE_BODY"}],
    }
    out = expand_pp_files(obj)
    assert "INLINE_BODY" in out["messages"][0]["content"]
    assert 'path="inline.txt"' in out["messages"][0]["content"]
    assert "pp_files" not in out


def test_too_large_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVPORTAL_PP_FILE_MAX_BYTES", "8")
    p = tmp_path / "big.txt"
    p.write_text("0123456789", encoding="utf-8")
    obj = {
        "messages": [{"role": "user", "content": "hi"}],
        "pp_files": [{"path": str(p.resolve())}],
    }
    with pytest.raises(FileInjectError) as ei:
        expand_pp_files(obj)
    assert ei.value.status_code == 413
    assert ei.value.code == "PP_FILE_TOO_LARGE"


def test_pp_files_must_be_list():
    obj = {
        "messages": [{"role": "user", "content": "hi"}],
        "pp_files": {"path": "/tmp/x"},
    }
    with pytest.raises(FileInjectError) as ei:
        expand_pp_files(obj)
    assert ei.value.code == "PP_FILES_TYPE"


def test_expand_request_pp_files_maps_http():
    from fastapi import HTTPException

    from app.api.proxy import expand_request_pp_files

    with pytest.raises(HTTPException) as ei:
        expand_request_pp_files({
            "messages": [{"role": "user", "content": "hi"}],
            "pp_files": [{"path": "x.txt"}],
        })
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "PP_FILE_PATH_NOT_ABSOLUTE"


def test_v1_chat_rejects_relative_pp_files(client):
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-5.6-sol",
            "messages": [{"role": "user", "content": "hi"}],
            "pp_files": [{"path": "x.txt"}],
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "PP_FILE_PATH_NOT_ABSOLUTE"
