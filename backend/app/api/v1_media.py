"""Media generation gateway — /v1 images, audio, and videos."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

from app.api.deps import get_db, get_vault
from app.api.proxy import (
    _NON_STREAM_TIMEOUT,
    _SKIP_REQUEST_HEADERS,
    _fallback_service_names,
    _filter_response_headers,
    _outgoing_auth_header,
    _record_usage,
    _should_trigger_fallback,
    _update_service_status,
    _wrap_upstream_error,
)
from app.core.host_resolve import ensure_resolvable_base_url
from app.core.media_routing import (
    AUDIO_CODE,
    IMAGE_CODE,
    VIDEO_CODE,
    apply_audio_caller_aliases,
    apply_image_caller_aliases,
    apply_video_caller_aliases,
    caller_facing_image_payload,
    minimax_logical_error,
    resolve_media_code,
    stamp_caller_model,
)
from app.core.rate_limiter import get_rate_limiter
from app.db.models import Binding, Secret
from app.logging_config import get_logger
from app.services.vault import VaultService

router = APIRouter(tags=["v1-media"])
_LOG = get_logger(__name__)
_rl = get_rate_limiter()
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _get_shared_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


def _unknown_media_model(expected: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "detail": f"Use opaque media code {expected}.",
            "code": "UNKNOWN_MODEL",
            "hint": (
                "Image POST /v1/images/generations model=I000. "
                "Audio POST /v1/audio/speech model=A000. "
                "Video POST /v1/videos/generations model=D000. "
                "Do not pass MiniMax upstream names on /v1."
            ),
        },
    )


def _parse_json_body(raw: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be valid JSON",
            "code": "INVALID_JSON",
        })
    if not isinstance(obj, dict):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be a JSON object",
            "code": "INVALID_JSON",
        })
    return obj


def _require_binding(
    session: Session,
    vault: VaultService,
    service_name: str,
) -> tuple[Binding, Secret, str, str]:
    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )
    binding = session.scalars(
        select(Binding).where(
            Binding.service_name == service_name,
            Binding.project_id.is_(None),
        )
    ).first()
    if binding is None:
        raise HTTPException(status_code=503, detail={
            "detail": f"Binding '{service_name}' not configured for media generation.",
            "code": "BINDING_NOT_FOUND",
        })
    secret = session.scalars(
        select(Secret).where(
            Secret.key == binding.secret_ref_key,
            Secret.project_id.is_(None),
        )
    ).first()
    if secret is None or not secret.enabled:
        raise HTTPException(status_code=503, detail={
            "detail": f"Secret for binding '{service_name}' is missing or disabled.",
            "code": "SECRET_UNAVAILABLE",
        })
    raw_base = (secret.base_url or "").strip()
    if not raw_base:
        raise HTTPException(status_code=503, detail={
            "detail": f"No base_url configured for binding '{service_name}'.",
            "code": "MISSING_BASE_URL",
        })
    raw_base = ensure_resolvable_base_url(raw_base)
    plaintext = vault.decrypt_secret_value(secret.value)
    return binding, secret, plaintext, raw_base.rstrip("/")


def _forward_headers(request: Request, auth_extra: dict[str, str]) -> dict[str, str]:
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQUEST_HEADERS and k.lower() != "authorization"
    }
    headers["content-type"] = "application/json"
    headers.update(auth_extra)
    return headers


def _stamp_json(content: bytes, stamp) -> bytes:
    try:
        obj = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return content
    stamped = stamp(obj)
    if stamped is obj:
        return content
    return json.dumps(stamped, ensure_ascii=False).encode("utf-8")


async def _forward_json(
    *,
    request: Request,
    session: Session,
    vault: VaultService,
    service_name: str,
    method: str,
    path: str,
    body: bytes | None,
    stamp,
) -> Response:
    binding, secret, plaintext, base = _require_binding(session, vault, service_name)
    del secret
    upstream_url = f"{base}/{path.lstrip('/')}"
    auth_extra = _outgoing_auth_header(binding, plaintext)
    forward_headers = _forward_headers(request, auth_extra)
    client = _get_shared_client(request)
    client_id = request.headers.get("x-client-id", "unknown")
    await _rl.acquire(service_name, client_id=client_id)
    released = False

    def _release(*, is_error: bool = False) -> None:
        nonlocal released
        if released:
            return
        released = True
        _rl.release(service_name, client_id=client_id, is_error=is_error)

    try:
        try:
            resp = await client.request(
                method,
                upstream_url,
                headers=forward_headers,
                content=body,
                timeout=_NON_STREAM_TIMEOUT,
            )
        except httpx.TimeoutException:
            _record_usage(session, service_name, None, is_error=True)
            _update_service_status(session, service_name, is_error=True, error_message="Timeout")
            _release(is_error=True)
            return JSONResponse(status_code=504, content={"error": "Media generation timed out"})
        except httpx.RequestError as exc:
            _record_usage(session, service_name, None, is_error=True)
            _update_service_status(session, service_name, is_error=True, error_message=str(exc)[:500])
            _release(is_error=True)
            return JSONResponse(status_code=502, content={"error": str(exc)})

        logical = None
        parsed: dict | None = None
        if resp.status_code < 400:
            try:
                loaded = json.loads(resp.content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                loaded = None
            if isinstance(loaded, dict):
                parsed = loaded
                logical = minimax_logical_error(parsed)

        is_error = resp.status_code >= 400 or logical is not None
        err_msg = None
        if resp.status_code >= 400:
            err_msg = f"HTTP {resp.status_code}"
        elif logical:
            err_msg = logical[1][:500]
        _record_usage(session, service_name, None, is_error=is_error)
        _update_service_status(
            session,
            service_name,
            is_error=is_error,
            error_message=err_msg,
        )
        should_overflow = (
            (resp.status_code >= 400 and _should_trigger_fallback(resp.status_code))
            or logical is not None
        )
        if should_overflow:
            for fb_name in _fallback_service_names(binding):
                try:
                    fb_binding, _, fb_plain, fb_base = _require_binding(session, vault, fb_name)
                except HTTPException:
                    continue
                fb_headers = _forward_headers(request, _outgoing_auth_header(fb_binding, fb_plain))
                try:
                    fb_resp = await client.request(
                        method,
                        f"{fb_base}/{path.lstrip('/')}",
                        headers=fb_headers,
                        content=body,
                        timeout=_NON_STREAM_TIMEOUT,
                    )
                except httpx.RequestError:
                    continue
                fb_logical = None
                if fb_resp.status_code < 400:
                    try:
                        fb_loaded = json.loads(fb_resp.content.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        fb_loaded = None
                    if isinstance(fb_loaded, dict):
                        fb_logical = minimax_logical_error(fb_loaded)
                if fb_resp.status_code < 400 and fb_logical is None:
                    _record_usage(session, fb_name, None, is_error=False)
                    _update_service_status(session, fb_name, is_error=False)
                    _release()
                    out = _stamp_json(fb_resp.content, stamp)
                    return Response(
                        content=out,
                        status_code=fb_resp.status_code,
                        headers=_filter_response_headers(fb_resp.headers),
                    )

        if resp.status_code >= 400:
            _release(is_error=True)
            return _wrap_upstream_error(
                resp.status_code, resp.content, plaintext, service_name,
                upstream_headers=resp.headers,
            )
        if logical:
            http_status, msg = logical
            _release(is_error=True)
            stamped = stamp(parsed)
            payload = stamped if isinstance(stamped, dict) else {"upstream": parsed}
            payload["ok"] = False
            payload["error"] = msg
            return JSONResponse(status_code=http_status, content=payload)
        _release()
        out = _stamp_json(resp.content, stamp)
        return Response(
            content=out,
            status_code=resp.status_code,
            headers=_filter_response_headers(resp.headers),
        )
    finally:
        _release()


@router.post("/images/generations")
async def image_generations(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    obj = _parse_json_body(await request.body())
    caller_model = str(obj.get("model", "")).strip()
    route = resolve_media_code(caller_model)
    if route is None or route.kind != "image":
        raise _unknown_media_model(IMAGE_CODE)
    if not str(obj.get("prompt") or "").strip():
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'prompt' is required",
            "code": "VALIDATION_ERROR",
        })
    upstream = apply_image_caller_aliases(obj)
    _LOG.info("v1_media_route", kind="image", code=IMAGE_CODE, service=route.service)
    return await _forward_json(
        request=request,
        session=session,
        vault=vault,
        service_name=route.service,
        method="POST",
        path=route.path,
        body=json.dumps(upstream).encode("utf-8"),
        stamp=lambda payload: caller_facing_image_payload(payload, IMAGE_CODE),
    )


@router.post("/audio/speech")
async def audio_speech(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    obj = _parse_json_body(await request.body())
    caller_model = str(obj.get("model", "")).strip()
    route = resolve_media_code(caller_model)
    if route is None or route.kind != "audio":
        raise _unknown_media_model(AUDIO_CODE)
    if not str(obj.get("input") or obj.get("text") or "").strip():
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'input' (or MiniMax 'text') is required",
            "code": "VALIDATION_ERROR",
        })
    upstream = apply_audio_caller_aliases(obj)
    _LOG.info("v1_media_route", kind="audio", code=AUDIO_CODE, service=route.service)
    return await _forward_json(
        request=request,
        session=session,
        vault=vault,
        service_name=route.service,
        method="POST",
        path=route.path,
        body=json.dumps(upstream).encode("utf-8"),
        stamp=lambda payload: stamp_caller_model(payload, AUDIO_CODE),
    )


@router.post("/videos/generations")
async def video_generations(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    obj = _parse_json_body(await request.body())
    caller_model = str(obj.get("model", "")).strip()
    route = resolve_media_code(caller_model)
    if route is None or route.kind != "video":
        raise _unknown_media_model(VIDEO_CODE)
    if not str(obj.get("prompt") or "").strip():
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'prompt' is required",
            "code": "VALIDATION_ERROR",
        })
    upstream = apply_video_caller_aliases(obj)
    _LOG.info("v1_media_route", kind="video", code=VIDEO_CODE, service=route.service)
    return await _forward_json(
        request=request,
        session=session,
        vault=vault,
        service_name=route.service,
        method="POST",
        path=route.path,
        body=json.dumps(upstream).encode("utf-8"),
        stamp=lambda payload: stamp_caller_model(payload, VIDEO_CODE),
    )


@router.get("/videos/generations/{task_id}")
async def video_generation_status(
    task_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    if not _TASK_ID_RE.fullmatch(task_id):
        raise HTTPException(status_code=422, detail={
            "detail": "Invalid task_id",
            "code": "VALIDATION_ERROR",
        })
    route = resolve_media_code(VIDEO_CODE)
    assert route is not None and route.query_path
    query = urlencode({"task_id": task_id})
    _LOG.info("v1_media_route", kind="video_query", code=VIDEO_CODE, service=route.service)
    return await _forward_json(
        request=request,
        session=session,
        vault=vault,
        service_name=route.service,
        method="GET",
        path=f"{route.query_path}?{query}",
        body=None,
        stamp=lambda payload: stamp_caller_model(payload, VIDEO_CODE),
    )
