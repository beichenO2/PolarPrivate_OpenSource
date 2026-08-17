"""Media generation codes on PolarPrivate /v1 (image / audio / video)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from app.core.media_routing import (
    AUDIO_CODE,
    IMAGE_CODE,
    VIDEO_CODE,
    apply_audio_caller_aliases,
    apply_image_caller_aliases,
    apply_video_caller_aliases,
    resolve_media_code,
)


def test_image_code_resolves_to_minimax_image_01():
    route = resolve_media_code("I000")
    assert route is not None
    assert route.kind == "image"
    assert route.upstream_model == "image-01"
    assert route.service == "llm.minimax"
    assert route.path == "image_generation"


def test_audio_code_resolves_to_minimax_speech_turbo():
    route = resolve_media_code("A000")
    assert route is not None
    assert route.kind == "audio"
    assert route.upstream_model == "speech-2.8-turbo"
    assert route.service == "llm.minimax"
    assert route.path == "t2a_v2"


def test_video_code_resolves_to_hailuo():
    route = resolve_media_code("D000")
    assert route is not None
    assert route.kind == "video"
    assert route.upstream_model == "MiniMax-Hailuo-2.3"
    assert route.service == "llm.minimax"
    assert route.path == "video_generation"
    assert route.query_path == "query/video_generation"


def test_chat_and_unknown_codes_are_not_media():
    assert resolve_media_code("0001") is None
    assert resolve_media_code("V0010") is None
    assert resolve_media_code("E000") is None
    assert resolve_media_code("I999") is None
    assert resolve_media_code("") is None


def test_openai_image_size_maps_to_aspect_ratio_and_rewrites_model():
    body = apply_image_caller_aliases(
        {"model": IMAGE_CODE, "prompt": "a cat", "size": "1024x1024", "n": 1}
    )
    assert body["model"] == "image-01"
    assert body["prompt"] == "a cat"
    assert body["aspect_ratio"] == "1:1"
    assert "size" not in body


def test_openai_b64_json_maps_to_minimax_base64():
    body = apply_image_caller_aliases(
        {"model": IMAGE_CODE, "prompt": "x", "response_format": "b64_json"}
    )
    assert body["response_format"] == "base64"


def test_openai_speech_input_maps_to_text_and_default_voice():
    body = apply_audio_caller_aliases({"model": AUDIO_CODE, "input": "你好"})
    assert body["model"] == "speech-2.8-turbo"
    assert body["text"] == "你好"
    assert body["voice_setting"]["voice_id"] == "male-qn-qingse"
    assert "input" not in body


def test_audio_keeps_explicit_voice_setting():
    body = apply_audio_caller_aliases(
        {
            "model": AUDIO_CODE,
            "text": "hi",
            "voice_setting": {"voice_id": "presenter_male", "speed": 1.1},
        }
    )
    assert body["voice_setting"]["voice_id"] == "presenter_male"
    assert body["voice_setting"]["speed"] == 1.1


def test_video_rewrites_model_and_keeps_prompt():
    body = apply_video_caller_aliases(
        {"model": VIDEO_CODE, "prompt": "a boat on a lake", "duration": 6}
    )
    assert body["model"] == "MiniMax-Hailuo-2.3"
    assert body["prompt"] == "a boat on a lake"
    assert body["duration"] == 6


def _seed_minimax(client) -> None:
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.minimax.api_key",
                "value": "test-minimax-token",
                "project_id": None,
                "base_url": "https://api.minimaxi.com/v1",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/bindings",
            json={
                "service_name": "llm.minimax",
                "secret_ref_key": "secret.minimax.api_key",
                "project_id": None,
            },
        ).status_code
        == 201
    )


def _mock_json_client(app, payload: dict, status: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.content = httpx.Response(status, json=payload).content
    mock_resp.headers = httpx.Headers({"content-type": "application/json"})
    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client
    return mock_client


def test_image_generations_forwards_to_minimax_image_path(client, app):
    _seed_minimax(client)
    mock_client = _mock_json_client(
        app,
        {
            "id": "img-1",
            "data": {"image_urls": ["https://cdn.example/a.png"]},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    )

    r = client.post(
        "/v1/images/generations",
        json={"model": IMAGE_CODE, "prompt": "a red cube", "size": "1024x1024"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == IMAGE_CODE
    assert body["data"][0]["url"] == "https://cdn.example/a.png"

    mock_client.request.assert_called_once()
    args, kwargs = mock_client.request.call_args
    assert args[0] == "POST"
    assert args[1] == "https://api.minimaxi.com/v1/image_generation"
    import json as _json

    sent = _json.loads(kwargs["content"])
    assert sent["model"] == "image-01"
    assert sent["prompt"] == "a red cube"
    assert sent["aspect_ratio"] == "1:1"
    auth = kwargs["headers"].get("Authorization") or kwargs["headers"].get("authorization")
    assert auth == "Bearer test-minimax-token"


def test_audio_speech_forwards_to_t2a_v2(client, app):
    _seed_minimax(client)
    mock_client = _mock_json_client(
        app,
        {
            "data": {"audio": "deadbeef", "status": 2},
            "extra_info": {"usage_characters": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    )

    r = client.post(
        "/v1/audio/speech",
        json={"model": AUDIO_CODE, "input": "你好"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == AUDIO_CODE
    assert body["data"]["audio"] == "deadbeef"

    args, kwargs = mock_client.request.call_args
    assert args[1] == "https://api.minimaxi.com/v1/t2a_v2"
    import json as _json

    sent = _json.loads(kwargs["content"])
    assert sent["model"] == "speech-2.8-turbo"
    assert sent["text"] == "你好"
    assert sent["voice_setting"]["voice_id"] == "male-qn-qingse"


def test_video_generations_create_and_query(client, app):
    _seed_minimax(client)
    mock_client = _mock_json_client(
        app,
        {
            "task_id": "431737159651622",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    )

    r = client.post(
        "/v1/videos/generations",
        json={"model": VIDEO_CODE, "prompt": "a boat on a lake", "duration": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == VIDEO_CODE
    assert body["task_id"] == "431737159651622"

    args, kwargs = mock_client.request.call_args
    assert args[1] == "https://api.minimaxi.com/v1/video_generation"
    import json as _json

    sent = _json.loads(kwargs["content"])
    assert sent["model"] == "MiniMax-Hailuo-2.3"

    mock_client = _mock_json_client(
        app,
        {
            "task_id": "431737159651622",
            "status": "Success",
            "file_id": "431714170487092",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    )
    q = client.get("/v1/videos/generations/431737159651622")
    assert q.status_code == 200, q.text
    qbody = q.json()
    assert qbody["status"] == "Success"
    assert qbody["file_id"] == "431714170487092"
    args, kwargs = mock_client.request.call_args
    assert args[0] == "GET"
    assert args[1].startswith("https://api.minimaxi.com/v1/query/video_generation")
    assert "task_id=431737159651622" in args[1]


def test_unknown_media_model_rejected(client):
    r = client.post(
        "/v1/images/generations",
        json={"model": "dall-e-3", "prompt": "nope"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "UNKNOWN_MODEL"


def test_minimax_nonzero_base_resp_is_not_success(client, app):
    _seed_minimax(client)
    _mock_json_client(
        app,
        {
            "data": {"audio": ""},
            "base_resp": {
                "status_code": 1008,
                "status_msg": "当前已达到 Token Plan 用量上限",
            },
        },
    )
    r = client.post("/v1/audio/speech", json={"model": AUDIO_CODE, "input": "你好"})
    assert r.status_code == 502
    body = r.json()
    assert body["model"] == AUDIO_CODE
    assert body["ok"] is False
    assert "用量上限" in body["error"]

