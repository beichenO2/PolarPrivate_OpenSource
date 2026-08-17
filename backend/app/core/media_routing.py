"""Opaque media generation codes for PolarPrivate /v1.

Callers pass I000 / A000 / D000. PolarPrivate rewrites to MiniMax upstream
models and paths. Chat QCSA codes stay in model_routing.py.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

IMAGE_CODE = "I000"
AUDIO_CODE = "A000"
VIDEO_CODE = "D000"

MEDIA_SERVICE_NAME = "llm.minimax"
DEFAULT_IMAGE_MODEL = "image-01"
DEFAULT_AUDIO_MODEL = "speech-2.8-turbo"
DEFAULT_VIDEO_MODEL = "MiniMax-Hailuo-2.3"
DEFAULT_AUDIO_VOICE = "male-qn-qingse"

IMAGE_PATH = "image_generation"
AUDIO_PATH = "t2a_v2"
VIDEO_PATH = "video_generation"
VIDEO_QUERY_PATH = "query/video_generation"

MediaKind = Literal["image", "audio", "video"]


@dataclass(frozen=True)
class MediaRoute:
    code: str
    kind: MediaKind
    upstream_model: str
    service: str
    path: str
    query_path: str | None = None


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _image_upstream() -> str:
    return _env("POLARPRIVATE_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


def _audio_upstream() -> str:
    return _env("POLARPRIVATE_AUDIO_MODEL", DEFAULT_AUDIO_MODEL)


def _video_upstream() -> str:
    return _env("POLARPRIVATE_VIDEO_MODEL", DEFAULT_VIDEO_MODEL)


def _audio_voice() -> str:
    return _env("POLARPRIVATE_AUDIO_VOICE", DEFAULT_AUDIO_VOICE)


def resolve_media_code(model: str) -> MediaRoute | None:
    raw = (model or "").strip().upper()
    if raw == IMAGE_CODE:
        return MediaRoute(
            code=IMAGE_CODE,
            kind="image",
            upstream_model=_image_upstream(),
            service=MEDIA_SERVICE_NAME,
            path=IMAGE_PATH,
        )
    if raw == AUDIO_CODE:
        return MediaRoute(
            code=AUDIO_CODE,
            kind="audio",
            upstream_model=_audio_upstream(),
            service=MEDIA_SERVICE_NAME,
            path=AUDIO_PATH,
        )
    if raw == VIDEO_CODE:
        return MediaRoute(
            code=VIDEO_CODE,
            kind="video",
            upstream_model=_video_upstream(),
            service=MEDIA_SERVICE_NAME,
            path=VIDEO_PATH,
            query_path=VIDEO_QUERY_PATH,
        )
    return None


_SIZE_TO_ASPECT = {
    "1024x1024": "1:1",
    "1280x720": "16:9",
    "1792x1024": "16:9",
    "1152x864": "4:3",
    "1248x832": "3:2",
    "832x1248": "2:3",
    "864x1152": "3:4",
    "720x1280": "9:16",
    "1024x1792": "9:16",
    "1344x576": "21:9",
}

_SIZE_RE = re.compile(r"^(\d+)\s*[x×]\s*(\d+)$", re.I)


def apply_image_caller_aliases(obj: dict[str, Any]) -> dict[str, Any]:
    body = dict(obj)
    route = resolve_media_code(str(body.get("model", "")))
    if route is None or route.kind != "image":
        raise ValueError("image model must be I000")
    body["model"] = route.upstream_model

    size = body.pop("size", None)
    if size and "aspect_ratio" not in body:
        key = str(size).strip().lower().replace("×", "x")
        mapped = _SIZE_TO_ASPECT.get(key)
        if mapped:
            body["aspect_ratio"] = mapped
        else:
            match = _SIZE_RE.fullmatch(str(size).strip())
            if match:
                body["width"] = int(match.group(1))
                body["height"] = int(match.group(2))

    if body.get("response_format") == "b64_json":
        body["response_format"] = "base64"
    return body


def apply_audio_caller_aliases(obj: dict[str, Any]) -> dict[str, Any]:
    body = dict(obj)
    route = resolve_media_code(str(body.get("model", "")))
    if route is None or route.kind != "audio":
        raise ValueError("audio model must be A000")
    body["model"] = route.upstream_model

    if "text" not in body and body.get("input") is not None:
        body["text"] = body.pop("input")
    else:
        body.pop("input", None)

    voice_setting = dict(body.get("voice_setting") or {})
    if body.get("voice") and "voice_id" not in voice_setting:
        voice_setting["voice_id"] = body["voice"]
    if body.get("speed") is not None and "speed" not in voice_setting:
        voice_setting["speed"] = body["speed"]
    if "voice_id" not in voice_setting:
        voice_setting["voice_id"] = _audio_voice()
    body["voice_setting"] = voice_setting
    body.pop("voice", None)
    body.pop("speed", None)

    fmt = body.pop("response_format", None)
    if fmt:
        audio_setting = dict(body.get("audio_setting") or {})
        audio_setting.setdefault("format", str(fmt))
        body["audio_setting"] = audio_setting
    return body


def apply_video_caller_aliases(obj: dict[str, Any]) -> dict[str, Any]:
    body = dict(obj)
    route = resolve_media_code(str(body.get("model", "")))
    if route is None or route.kind != "video":
        raise ValueError("video model must be D000")
    body["model"] = route.upstream_model
    return body


def caller_facing_image_payload(obj: dict[str, Any], caller_model: str) -> dict[str, Any]:
    out = dict(obj)
    out["model"] = caller_model
    data = out.get("data")
    if isinstance(data, dict):
        items: list[dict[str, str]] = []
        for url in data.get("image_urls") or []:
            items.append({"url": str(url)})
        for raw in data.get("image_base64") or []:
            items.append({"b64_json": str(raw)})
        if items:
            out["data"] = items
    return out


def stamp_caller_model(obj: Any, caller_model: str) -> Any:
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    out["model"] = caller_model
    return out


def minimax_logical_error(obj: Any) -> tuple[int, str] | None:
    """MiniMax often returns HTTP 200 with base_resp.status_code != 0."""
    if not isinstance(obj, dict):
        return None
    br = obj.get("base_resp")
    if not isinstance(br, dict):
        return None
    raw = br.get("status_code", 0)
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return None
    if code == 0:
        return None
    msg = str(br.get("status_msg") or f"MiniMax status_code={code}")
    if code == 1002:
        return 429, msg
    return 502, msg
