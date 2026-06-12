"""Unified LLM gateway — /v1/chat/completions and /v1/models.

This layer provides a single OpenAI-compatible entry point.
Callers only need to specify a model name; the gateway resolves the
correct upstream binding automatically via model_routing.MODEL_ROUTING.

Usage (any OpenAI-compatible SDK):
    client = OpenAI(
        base_url="http://127.0.0.1:12790/v1",
        api_key="local",   # ignored — PolarPrivate handles auth
    )
    client.chat.completions.create(model="0001", ...)  # → DS V4 Flash (agent)
    client.chat.completions.create(model="V0000", ...)  # → qwen3.7-plus (vision)

The /proxy/* routes are untouched and remain fully functional.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.api.deps import get_db, get_vault
from app.api.proxy import (
    _NON_STREAM_TIMEOUT,
    _STREAM_TIMEOUT,
    _filter_response_headers,
    _outgoing_auth_header,
    _sanitize_upstream_body,
    _sse_media_type,
    _wrap_upstream_error,
    _check_and_truncate_prompt,
    _record_usage,
    _update_service_status,
    _SKIP_REQUEST_HEADERS,
)
from app.core.model_catalog import MODEL_CATALOG
from app.core.local_model_routing import (
    EMBED_CODE,
    LOCAL_SERVICE_NAME,
    normalize_embed_code,
    ollama_base_url,
    resolve_ollama_embed_model,
    resolve_ollama_chat_model,
)
from app.core.model_routing import (
    caller_facing_model,
    get_capability_fallback,
    get_load_balance_group,
    is_opaque_caller_model,
    select_service_by_weight,
    resolve_model_and_service,
)
from app.db.models import Binding, Secret
from app.logging_config import get_logger
from app.core.rate_limiter import get_rate_limiter, parse_retry_after
from app.services.minimax_gateway import apply_minimax_upstream_defaults
from app.services.vault import VaultService

router = APIRouter(tags=["v1-gateway"])
_LOG = get_logger(__name__)
_rl = get_rate_limiter()

# Max seconds to honour a single upstream Retry-After before retrying anyway,
# so one request can't hang indefinitely on a misbehaving upstream hint.
_RL_RETRY_WAIT_CAP = 30.0
# Backoff schedule for pre-stream transient upstream errors (429/5xx).
_STREAM_RETRY_DELAYS = [1.0, 3.0, 7.0]

# ── Rate-limit monitor ───────────────────────────────────────────────────────

_rl_router = APIRouter(tags=["rate-limits"])


@_rl_router.get("/rate-limits")
def rate_limits_status() -> dict:
    """Live snapshot of per-service rate-limiting state."""
    return _rl.get_stats()


def _build_service_model_map() -> dict[str, list[str]]:
    """Reverse-map: service_name → list of model names routed through it.

    Computed from MODEL_SERVICE_MAP + CAPABILITY_CLOUD_MAP so the dashboard
    shows which models share each key's concurrency/RPM budget.
    """
    from app.core.model_routing import MODEL_SERVICE_MAP, CAPABILITY_CLOUD_MAP
    svc_models: dict[str, list[str]] = {}
    for model_id, svc in MODEL_SERVICE_MAP.items():
        svc_models.setdefault(svc, []).append(model_id)
    for code, (model_id, svc) in CAPABILITY_CLOUD_MAP.items():
        label = f"{code}→{model_id}"
        svc_models.setdefault(svc, [])
        if label not in svc_models[svc]:
            svc_models[svc].append(label)
    return svc_models


_SERVICE_DISPLAY_NAMES: dict[str, str] = {
    "llm.glm51.enterprise": "讯飞星火 MaaS 企业版",
    "llm.aliyun.codingplan": "阿里云 CodingPlan",
    "llm.aliyun.dashscope": "阿里云 DashScope",
    "llm.minimax": "MiniMax",
}


@_rl_router.get("/rate-limits/dashboard")
def rate_limits_dashboard() -> dict:
    """Rich dashboard view for SOTAgent console integration."""
    _rl.ensure_all_configured()
    stats = _rl.get_stats()
    services = stats.get("services", {})

    summary = {
        "total_in_flight": sum(s.get("in_flight", 0) for s in services.values()),
        "total_capacity": sum(s.get("max_concurrent", 0) for s in services.values()),
        "services_cooling": [
            name for name, s in services.items()
            if s.get("cooldown_remaining_sec", 0) > 0
        ],
        "total_acquired": sum(s.get("total_acquired", 0) for s in services.values()),
        "total_rejected": sum(s.get("total_rejected", 0) for s in services.values()),
    }

    svc_model_map = _build_service_model_map()

    utilization = {}
    for name, s in services.items():
        cap = s.get("max_concurrent", 1)
        inflight = s.get("in_flight", 0)
        w = s.get("window_60s", {})
        total_w = sum(w.values())
        utilization[name] = {
            "concurrent_pct": round(inflight / cap * 100, 1) if cap else 0,
            "rpm_pct": round(total_w / s.get("rpm_configured", 1) * 100, 1) if s.get("rpm_configured") else 0,
            "error_rate_pct": round(
                (w.get("429", 0) + w.get("error", 0)) / total_w * 100, 1
            ) if total_w else 0,
        }

    service_meta = {
        name: {
            "display_name": _SERVICE_DISPLAY_NAMES.get(name, name),
            "models": svc_model_map.get(name, []),
        }
        for name in services
    }

    return {
        "summary": summary,
        "services": services,
        "utilization": utilization,
        "service_meta": service_meta,
        "absorbers": stats.get("absorbers", {}),
        "clients": stats.get("clients", {}),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── /v1/models ──────────────────────────────────────────────────────────────

@router.get("/models")
def list_models(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> dict:
    """List all known models available through the PolarPrivate proxy.

    SDK callers (PolarUI, scripts) only need vault unlocked — no browser session cookie.
    """
    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )
    # Collect resolved service names
    bindings = session.scalars(select(Binding)).all()
    secrets_by_key: dict[str, Secret] = {
        s.key: s for s in session.scalars(select(Secret)).all()
    }
    resolved_services: set[str] = set()
    for b in bindings:
        sec = secrets_by_key.get(b.secret_ref_key)
        if sec and sec.enabled and b.project_id is None:
            resolved_services.add(b.service_name)

    now = int(time.time())
    data = []
    for entry in MODEL_CATALOG:
        if entry.service != LOCAL_SERVICE_NAME and entry.service not in resolved_services:
            continue
        data.append({
            "id": entry.id,
            "object": "model",
            "created": now,
            "owned_by": entry.provider,
            "service": entry.service,
            "description": entry.description,
        })

    return {
        "object": "list",
        "data": data,
        "hint": (
            "Pass any model id to POST /v1/chat/completions. "
            "PolarPrivate routes to the correct upstream automatically."
        ),
    }


# ── /v1/chat/completions ─────────────────────────────────────────────────────

def _get_shared_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


def _resolve_binding_and_secret(
    session: Session,
    service_name: str,
) -> tuple[Binding, Secret, str] | None:
    """Return (binding, secret, plaintext) or None if not found/disabled."""
    binding = session.scalars(
        select(Binding)
        .where(Binding.service_name == service_name, Binding.project_id.is_(None))
    ).first()
    if binding is None:
        return None

    secret = session.scalars(
        select(Secret)
        .where(Secret.key == binding.secret_ref_key, Secret.project_id.is_(None))
    ).first()
    if secret is None or not secret.enabled:
        return None

    return binding, secret, ""  # plaintext filled below


@router.post("/embeddings")
async def unified_embeddings(
    request: Request,
) -> Response:
    """Forward embeddings using opaque code E000 (one embedding model slot)."""
    body = await request.body()
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be valid JSON",
            "code": "INVALID_JSON",
        })

    caller_model = str(obj.get("model", EMBED_CODE)).strip()
    embed_code = normalize_embed_code(caller_model)
    if not embed_code:
        raise HTTPException(status_code=422, detail={
            "detail": f"Embedding model must be {EMBED_CODE}.",
            "code": "UNKNOWN_MODEL",
        })

    obj["model"] = resolve_ollama_embed_model(embed_code)
    body = json.dumps(obj).encode("utf-8")
    upstream_url = f"{ollama_base_url()}/v1/embeddings"

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQUEST_HEADERS and k.lower() != "authorization"
    }
    forward_headers["content-type"] = "application/json"

    client = _get_shared_client(request)
    try:
        resp = await client.request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Ollama embeddings timed out"})
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})

    if resp.status_code >= 400:
        return _wrap_upstream_error(resp.status_code, resp.content, "", LOCAL_SERVICE_NAME,
                                    upstream_headers=resp.headers)

    out = _rewrite_response_model(resp.content, embed_code)
    return Response(content=out, status_code=resp.status_code,
                    headers=_filter_response_headers(resp.headers))


def _rewrite_response_model(body: bytes, caller_model: str) -> bytes:
    """Strip upstream model names from JSON responses; echo capability / L-code."""
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    if isinstance(obj, dict) and "model" in obj:
        obj["model"] = caller_facing_model(caller_model, str(obj.get("model", "")))
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return body


async def _forward_local_ollama(
    request: Request,
    client: httpx.AsyncClient,
    body: bytes,
    caller_model: str,
    obj: dict,
) -> Response:
    """Forward to Ollama OpenAI-compatible API; never expose Ollama model tags to callers."""
    ollama_model = resolve_ollama_chat_model(caller_model)
    obj["model"] = ollama_model
    body = json.dumps(obj).encode("utf-8")
    upstream_url = f"{ollama_base_url()}/v1/chat/completions"

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQUEST_HEADERS and k.lower() != "authorization"
    }
    forward_headers["content-type"] = "application/json"

    use_streaming = obj.get("stream") is True
    _LOG.info("v1_gateway_local_ollama", caller_model=caller_model, stream=use_streaming)

    if use_streaming:
        return await _forward_v1_streaming(
            client, upstream_url, forward_headers, body,
            plaintext_secret="", service_name=LOCAL_SERVICE_NAME,
            caller_model=caller_model,
        )

    try:
        resp = await client.request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Ollama request timed out",
            "service": LOCAL_SERVICE_NAME,
            "model": caller_model,
        })
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": LOCAL_SERVICE_NAME,
            "model": caller_model,
            "hint": "Ensure Ollama is running (ollama serve) and OLLAMA_URL is reachable.",
        })

    if resp.status_code >= 400:
        return _wrap_upstream_error(
            resp.status_code, resp.content, "", LOCAL_SERVICE_NAME,
            upstream_headers=resp.headers,
        )

    content = _rewrite_response_model(resp.content, caller_model)
    return Response(
        content=content,
        status_code=resp.status_code,
        headers=_filter_response_headers(resp.headers),
    )


_DASHSCOPE_SERVICES = frozenset({"llm.aliyun.codingplan", "llm.aliyun.dashscope"})

# 讯飞/glm51 endpoint quirk: it returns an EMPTY 200 response (no content, no
# tool_calls) once a conversation carries tool-call / tool-result messages, which
# stalls multi-round agent loops. Requests that contain such messages are routed
# to a tool-reliable provider instead.
_TOOL_CONVO_REROUTE = ("qwen3.7-plus", "llm.aliyun.codingplan")


def _request_has_tool_messages(obj: dict) -> bool:
    """True if the chat payload contains tool-call or tool-result messages."""
    for m in obj.get("messages") or []:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "tool" or m.get("tool_calls"):
            return True
    return False


def _apply_dashscope_tool_choice_fix(obj: dict, service_name: str) -> None:
    """DashScope thinking mode rejects tool_choice=object/required.

    When tool_choice is set to a non-"auto"/non-"none" value and the target is
    a DashScope service, explicitly disable thinking so structured tool output
    works. DashScope uses the non-standard `enable_thinking` boolean.
    """
    if service_name not in _DASHSCOPE_SERVICES:
        return
    tc = obj.get("tool_choice")
    if tc is None or tc in ("auto", "none"):
        return
    obj["enable_thinking"] = False
    _LOG.info("dashscope_tool_choice_fix", action="disable_thinking", tool_choice=str(tc)[:80])


@router.post("/chat/completions")
async def unified_chat_completions(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    """Route a chat completion request to the correct upstream binding by model name.

    The request body must be valid JSON with at least a ``model`` field.
    All other fields are forwarded as-is to the upstream OpenAI-compatible endpoint.
    """
    body = await request.body()

    # Parse body to extract model name
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be valid JSON",
            "code": "INVALID_JSON",
        })

    model = obj.get("model", "")
    if not model:
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'model' is required",
            "code": "VALIDATION_ERROR",
        })

    caller_model = str(model).strip()

    # Resolve service name and exact full model from alias
    full_model, service_name = resolve_model_and_service(caller_model)
    if service_name is None:
        raise HTTPException(status_code=422, detail={
            "detail": "Use 4-bit QCSA codes (0000–1111), V-prefix vision (V0000/V0010/V1000/V0001/V0101), L0000 local, or E000 embed.",
            "code": "UNKNOWN_MODEL",
            "hint": (
                "QCSA: Q=Quality C=Context S=Speed A=Agentic. "
                "0000=GLM-5.1(均衡) 0010=DS-V4-Flash(快速) 0100=DS-V4-Pro(长文本1M) 0110=MiniMax-M3 1000=GLM-5.1(旗舰) 1100=Qwen3.7-Plus(旗舰+长上下文) 1110=M3-Thinking(推理). "
                "Agent: 0001=DS-V4-Flash(tool call最准) 0011=DS-V4-Flash 0101=DS-V4-Pro(长上下文Agent) 1001=DS-V4-Pro(复杂多步). "
                "Vision: V0000=qwen3.7(默认,效果最好,44页可处理) V0010=vl-flash(批量,44页30s最快) "
                "V1000=Kimi-K2.6(单图旗舰,限3-4张) V0001=K2.6(单图Agent+tool) "
                "V0101=qwen3.7(多图Agent,C=1长上下文,44页可处理+tool call)."
            ),
        })

    client = _get_shared_client(request)

    # Local Ollama — no vault / binding required
    if service_name == LOCAL_SERVICE_NAME:
        return await _forward_local_ollama(request, client, body, full_model, obj)

    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )

    # Load-balance override: if model has a multi-source group, pick by weight
    lb_group = get_load_balance_group(full_model)
    if lb_group:
        cooled = frozenset(
            s["service"] for s in lb_group
            if _rl.get_budget(s["service"]).is_cooling_down
        )
        service_name, lb_model_override = select_service_by_weight(lb_group, skip_services=cooled or None)
        if lb_model_override:
            full_model = lb_model_override
        _LOG.info("load_balance_selected", model=full_model, service=service_name,
                   skipped_cooldown=list(cooled) if cooled else None)

    # Compatibility reroute: glm51/讯飞 returns EMPTY on multi-turn tool
    # conversations → send tool-carrying requests to a tool-reliable provider.
    # (Round 0 has no tool messages yet, so the initial tool-call decision can
    # still use the originally routed model; only follow-up rounds reroute.)
    # Diagnostic escape hatch: header `x-pp-no-reroute: 1` disables this, so the
    # raw upstream behaviour can be reproduced/tested directly.
    _no_reroute = request.headers.get("x-pp-no-reroute") == "1"
    if not _no_reroute and service_name == "llm.glm51.enterprise" and _request_has_tool_messages(obj):
        full_model, service_name = _TOOL_CONVO_REROUTE
        _LOG.info("tool_convo_reroute", reason="glm51_empty_on_tool_messages",
                  to_service=service_name, to_model=full_model)

    # Overwrite the model field in the upstream payload to standard full name
    obj["model"] = full_model
    apply_minimax_upstream_defaults(obj)
    _apply_dashscope_tool_choice_fix(obj, service_name)
    body = json.dumps(obj).encode("utf-8")
    opaque_response = is_opaque_caller_model(caller_model)

    # Look up binding + secret
    binding = session.scalars(
        select(Binding)
        .where(Binding.service_name == service_name, Binding.project_id.is_(None))
    ).first()
    if binding is None:
        raise HTTPException(status_code=503, detail={
            "detail": f"Binding '{service_name}' not configured for model '{model}'.",
            "code": "BINDING_NOT_FOUND",
            "hint": "Add the binding in PolarPrivate or check model_routing.py.",
        })

    secret = session.scalars(
        select(Secret)
        .where(Secret.key == binding.secret_ref_key, Secret.project_id.is_(None))
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

    plaintext = vault.decrypt_secret_value(secret.value)
    auth_extra = _outgoing_auth_header(binding, plaintext)

    # Build upstream URL
    base = raw_base.rstrip("/")
    upstream_url = f"{base}/chat/completions"

    # Forward headers (strip hop-by-hop, inject auth)
    forward_headers: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _SKIP_REQUEST_HEADERS:
            continue
        if key.lower() == "authorization":
            continue  # Replace with real auth
        forward_headers[key] = value
    forward_headers.update(auth_extra)

    # Auto-truncate prompt if too long
    body, was_truncated = _check_and_truncate_prompt(body)
    if was_truncated:
        _LOG.info("v1_gateway_prompt_truncated", service=service_name, model=model)

    use_streaming = obj.get("stream") is True

    client_id = request.headers.get("x-client-id", "unknown")
    _LOG.info("v1_gateway_route", model=caller_model, service=service_name, stream=use_streaming, client_id=client_id)

    # ── Rate-limit gate: pace locally by *blocking until capacity is free*.
    # Local rate limiting must never surface as a client error — it only throttles
    # throughput. acquire() waits (incl. through any cooldown); it never rejects.
    await _rl.acquire(service_name, client_id=client_id)

    _rl_released = False

    def _release_budget(*, is_error: bool = False, is_429: bool = False, retry_after: int | None = None) -> None:
        nonlocal _rl_released
        if _rl_released:
            return
        _rl_released = True
        _rl.release(service_name, client_id=client_id, is_error=is_error, is_429=is_429, retry_after=retry_after)

    try:
        if use_streaming:
            return await _forward_v1_streaming_rl(
                client, upstream_url, forward_headers, body,
                plaintext_secret=plaintext, service_name=service_name,
                caller_model=caller_model if opaque_response else "",
                release_fn=_release_budget,
            )

        # Non-streaming
        try:
            resp = await client.request(
                "POST", upstream_url,
                headers=forward_headers,
                content=body,
                timeout=_NON_STREAM_TIMEOUT,
            )
        except httpx.ConnectError:
            import asyncio as _aio
            _LOG.info("v1_gateway_sync_fallback", service=service_name, upstream_url=upstream_url)
            try:
                resp = await _aio.get_event_loop().run_in_executor(
                    None,
                    lambda: httpx.request(
                        "POST", upstream_url,
                        headers=forward_headers,
                        content=body,
                        timeout=_NON_STREAM_TIMEOUT,
                        follow_redirects=True,
                    ),
                )
            except httpx.RequestError as exc2:
                _record_usage(session, service_name, None, is_error=True)
                _update_service_status(session, service_name, is_error=True, error_message=str(exc2)[:500])
                _release_budget(is_error=True)
                return JSONResponse(status_code=502, content={
                    "ok": False,
                    "error": str(exc2),
                    "service": service_name,
                    "model": model,
                    "suggestion": "Cannot connect to upstream. Verify PolarPrivate binding.",
                })
        except httpx.TimeoutException:
            _record_usage(session, service_name, None, is_error=True)
            _update_service_status(session, service_name, is_error=True, error_message="Timeout")
            _release_budget(is_error=True)
            return JSONResponse(status_code=504, content={
                "ok": False,
                "error": "Upstream LLM request timed out (300s limit)",
                "service": service_name,
                "model": model,
                "suggestion": "Try a shorter prompt or a faster model.",
            })
        except httpx.RequestError as exc:
            _record_usage(session, service_name, None, is_error=True)
            _update_service_status(session, service_name, is_error=True, error_message=str(exc)[:500])
            _release_budget(is_error=True)
            return JSONResponse(status_code=502, content={
                "ok": False,
                "error": str(exc),
                "service": service_name,
                "model": model,
                "suggestion": "Cannot connect to upstream. Verify PolarPrivate binding.",
            })

        is_error = resp.status_code >= 400
        _record_usage(session, service_name, None, is_error=is_error)
        _update_service_status(session, service_name, is_error=is_error, error_message=None if not is_error else f"HTTP {resp.status_code}")

        if is_error:
            # Wait-and-retry transient upstream failures on the SAME service.
            # 429 (upstream rate limit) is intentionally included: when upstream
            # signals a limit we WAIT (honouring Retry-After) and retry — the
            # rate-limit error is never passed back to the caller.
            if resp.status_code in (429, 500, 502, 503, 504):
                _RETRY_DELAYS = [1.0, 3.0, 7.0, 15.0]
                for attempt, base_delay in enumerate(_RETRY_DELAYS, 1):
                    if resp.status_code == 429:
                        ra = parse_retry_after(resp.headers)
                        delay = min(float(ra), _RL_RETRY_WAIT_CAP) if ra else base_delay
                    else:
                        delay = base_delay
                    _LOG.warning("v1_gateway_wait_retry", service=service_name, status=resp.status_code, attempt=attempt, delay_s=delay)
                    await asyncio.sleep(delay)
                    try:
                        retry_resp = await client.request(
                            "POST", upstream_url,
                            headers=forward_headers,
                            content=body,
                            timeout=_NON_STREAM_TIMEOUT,
                        )
                        if retry_resp.status_code < 400:
                            _record_usage(session, service_name, None, is_error=False)
                            _update_service_status(session, service_name, is_error=False)
                            retry_body = retry_resp.content
                            if opaque_response:
                                retry_body = _rewrite_response_model(retry_body, caller_model)
                            _release_budget()
                            return Response(
                                content=retry_body,
                                status_code=retry_resp.status_code,
                                headers=_filter_response_headers(retry_resp.headers),
                            )
                        resp = retry_resp
                        if resp.status_code not in (429, 500, 502, 503, 504):
                            break
                    except httpx.RequestError:
                        if attempt == len(_RETRY_DELAYS):
                            break
                        continue

            # Same-service retries exhausted — record outcome and pace future
            # concurrent callers via a brief cooldown (waited through, not rejected).
            if resp.status_code == 429:
                _release_budget(is_429=True, retry_after=parse_retry_after(resp.headers))
            else:
                _release_budget(is_error=True)

            # ── Soft routing: divert to a non-cooling alternative subscription ──
            # On 429/5xx, route this request to a *different* subscription that
            # isn't rate-limited ("引流到没有限流的订阅"), instead of erroring.
            # Order: other healthy members of this tier's load-balance group,
            # then the static per-capability fallback as a last resort.
            if resp.status_code in (429, 500, 502, 503, 504):
                alt_candidates: list[tuple[str, str]] = []  # (model, service)
                seen_services = {service_name}
                for s in (lb_group or []):
                    svc = s["service"]
                    if svc in seen_services or _rl.get_budget(svc).is_cooling_down:
                        continue
                    alt_candidates.append((s.get("model") or full_model, svc))
                    seen_services.add(svc)
                cap_fb = get_capability_fallback(caller_model)
                if cap_fb and cap_fb[1] not in seen_services:
                    alt_candidates.append((cap_fb[0], cap_fb[1]))

                for fb_model, fb_service in alt_candidates:
                    fb_binding = session.scalars(
                        select(Binding).where(Binding.service_name == fb_service, Binding.project_id.is_(None))
                    ).first()
                    fb_secret = session.scalars(
                        select(Secret).where(Secret.key == fb_binding.secret_ref_key, Secret.project_id.is_(None))
                    ).first() if fb_binding else None
                    if not (fb_binding and fb_secret and fb_secret.enabled and (fb_secret.base_url or "").strip()):
                        continue
                    _LOG.warning("v1_gateway_divert", frm=service_name, to_service=fb_service, to_model=fb_model, status=resp.status_code)
                    fb_plain = vault.decrypt_secret_value(fb_secret.value)
                    fb_auth = _outgoing_auth_header(fb_binding, fb_plain)
                    fb_obj = json.loads(body)
                    fb_obj["model"] = fb_model
                    apply_minimax_upstream_defaults(fb_obj)
                    _apply_dashscope_tool_choice_fix(fb_obj, fb_service)
                    fb_body = json.dumps(fb_obj).encode("utf-8")
                    fb_url = fb_secret.base_url.strip().rstrip("/") + "/chat/completions"
                    fb_headers = {k: v for k, v in forward_headers.items() if k.lower() != "authorization"}
                    fb_headers.update(fb_auth)
                    try:
                        fb_resp = await client.request("POST", fb_url, headers=fb_headers, content=fb_body, timeout=_NON_STREAM_TIMEOUT)
                    except httpx.RequestError as fb_exc:
                        _LOG.warning("v1_gateway_divert_failed", to_service=fb_service, error=str(fb_exc)[:200])
                        continue
                    if fb_resp.status_code < 400:
                        _record_usage(session, fb_service, None, is_error=False)
                        _update_service_status(session, fb_service, is_error=False)
                        fb_out = fb_resp.content
                        if opaque_response:
                            fb_out = _rewrite_response_model(fb_out, caller_model)
                        return Response(content=fb_out, status_code=fb_resp.status_code, headers=_filter_response_headers(fb_resp.headers))
                    # Alternative also limited → cool it for routing (no slot held here).
                    if fb_resp.status_code == 429:
                        ra = parse_retry_after(fb_resp.headers)
                        _rl.get_budget(fb_service).set_cooldown(min(float(ra), _RL_RETRY_WAIT_CAP) if ra else 5.0)

            return _wrap_upstream_error(resp.status_code, resp.content, plaintext, service_name,
                                        upstream_headers=resp.headers)

        _release_budget()
        out_body = resp.content
        if opaque_response:
            out_body = _rewrite_response_model(out_body, caller_model)

        return Response(
            content=out_body,
            status_code=resp.status_code,
            headers=_filter_response_headers(resp.headers),
        )
    finally:
        _release_budget()


async def _forward_v1_streaming(
    client: httpx.AsyncClient,
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    plaintext_secret: str = "",
    service_name: str = "",
    caller_model: str = "",
) -> Response:
    """Streaming forward for /v1/chat/completions (no rate-limit awareness)."""
    try:
        req = client.build_request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_STREAM_TIMEOUT,
        )
        upstream = await client.send(req, stream=True)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Upstream streaming request timed out",
            "service": service_name,
            "suggestion": "Try a shorter prompt or disable streaming.",
        })
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": service_name,
        })

    if upstream.status_code >= 400:
        try:
            err_body = await upstream.aread()
        finally:
            await upstream.aclose()
        return _wrap_upstream_error(upstream.status_code, err_body, plaintext_secret, service_name,
                                    upstream_headers=upstream.headers)

    media = _sse_media_type(upstream)
    resp_headers = _filter_response_headers(upstream.headers)
    status = upstream.status_code

    async def aiter_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield _sanitize_upstream_body(chunk, plaintext_secret) if plaintext_secret else chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        aiter_stream(),
        status_code=status,
        headers=resp_headers,
        media_type=media,
    )


_ReleaseFn = Any  # Callable with keyword args is_error, is_429, retry_after


async def _forward_v1_streaming_rl(
    client: httpx.AsyncClient,
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    plaintext_secret: str = "",
    service_name: str = "",
    caller_model: str = "",
    release_fn: _ReleaseFn = None,
) -> Response:
    """Streaming forward with rate-limit release on stream close."""
    try:
        req = client.build_request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_STREAM_TIMEOUT,
        )
        upstream = await client.send(req, stream=True)
    except httpx.TimeoutException:
        if release_fn:
            release_fn(is_error=True)
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Upstream streaming request timed out",
            "service": service_name,
            "suggestion": "Try a shorter prompt or disable streaming.",
        })
    except httpx.RequestError as exc:
        if release_fn:
            release_fn(is_error=True)
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": service_name,
        })

    # Pre-stream transient errors (429/5xx) → wait & retry before streaming.
    # Safe: no bytes forwarded yet. An upstream rate limit becomes a retry here,
    # mirroring the non-stream path, so it never reaches the caller as an error.
    retry_attempt = 0
    while upstream.status_code in (429, 500, 502, 503, 504) and retry_attempt < len(_STREAM_RETRY_DELAYS):
        status_code = upstream.status_code
        ra = parse_retry_after(upstream.headers) if status_code == 429 else None
        try:
            await upstream.aread()
        finally:
            await upstream.aclose()
        delay = min(float(ra), _RL_RETRY_WAIT_CAP) if (status_code == 429 and ra) else _STREAM_RETRY_DELAYS[retry_attempt]
        retry_attempt += 1
        _LOG.warning("v1_gateway_stream_wait_retry", service=service_name, status=status_code, attempt=retry_attempt, delay_s=delay)
        await asyncio.sleep(delay)
        try:
            req = client.build_request(
                "POST", upstream_url,
                headers=forward_headers,
                content=body,
                timeout=_STREAM_TIMEOUT,
            )
            upstream = await client.send(req, stream=True)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            if release_fn:
                release_fn(is_error=True)
            return JSONResponse(status_code=502, content={
                "ok": False,
                "error": str(exc),
                "service": service_name,
            })

    if upstream.status_code >= 400:
        try:
            err_body = await upstream.aread()
        finally:
            await upstream.aclose()
        is_429 = upstream.status_code == 429
        ra = parse_retry_after(upstream.headers) if is_429 else None
        if release_fn:
            release_fn(is_error=not is_429, is_429=is_429, retry_after=ra)
        return _wrap_upstream_error(upstream.status_code, err_body, plaintext_secret, service_name,
                                    upstream_headers=upstream.headers)

    media = _sse_media_type(upstream)
    resp_headers = _filter_response_headers(upstream.headers)
    status = upstream.status_code

    async def aiter_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield _sanitize_upstream_body(chunk, plaintext_secret) if plaintext_secret else chunk
        finally:
            await upstream.aclose()
            if release_fn:
                release_fn()

    return StreamingResponse(
        aiter_stream(),
        status_code=status,
        headers=resp_headers,
        media_type=media,
    )
