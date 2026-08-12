"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from app.api import bindings as bindings_routes
from app.api import dashboard as dashboard_routes
from app.api import export as export_routes
from app.api import logs as logs_routes
from app.api import onboarding as onboarding_routes
from app.api import projects as projects_routes
from app.api import proxy as proxy_routes
from app.api import v1_gateway as v1_gateway_routes
from app.api import render as render_routes
from app.api import secrets as secrets_routes
from app.api import settings as settings_routes
from app.api import test_center as test_center_routes
from app.api import user_accounts as user_accounts_routes
from app.api import identity_bindings as identity_bindings_routes
from app.api import vault_routes
from app.api import sanitize as sanitize_routes
from app.api import auth as auth_routes
from app.api import sign as sign_routes
from app.api import d_class as d_class_routes
from app.api import vault_sync as vault_sync_routes
from app.api.exceptions import register_exception_handlers
from app.logging_config import configure_logging
from app.services.vault import VaultService




# Must exceed any single ServiceBudget.max_concurrent and leave headroom when
# several services are hot. Old (20/10) was below dashboard "total_capacity"
# and collapsed under 16 parallel /proxy/llm.deepseek calls (2026-08-12).
# Recalibrated 2026-08-13 for AKM 5-arm + higher lant/deepseek ceilings.
_UPSTREAM_LIMITS = httpx.Limits(
    max_connections=128,
    max_keepalive_connections=64,
    keepalive_expiry=30,
)


def _build_upstream_mounts() -> dict[str, httpx.AsyncBaseTransport] | None:
    """
    上游出网代理策略。**默认 None = 全部直连**，与历史 ``trust_env=False`` 行为完全一致，
    不设任何环境变量时零回归。

    ``trust_env=False`` 只是让 httpx 忽略 ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``ALL_PROXY``；
    它是**硬编码直连**，无法为「某个上游必须经 Clash 才可达」的情况开口子。本函数把这件事
    变成可配置的，两个方向都能表达：

    ==========================================  ===================================================
    ``PRIVPORTAL_UPSTREAM_PROXY``               代理地址，如 ``http://127.0.0.1:7890``。**不设则全部直连。**
    ``PRIVPORTAL_UPSTREAM_PROXY_HOSTS``         白名单：逗号分隔的 host，**仅**这些走代理，其余直连。
    ``PRIVPORTAL_UPSTREAM_DIRECT_HOSTS``        黑名单：未设白名单时，全局走代理，**但**这些 host 强制直连。
    ==========================================  ===================================================

    例：只让中转域名走 Clash，讯飞/阿里保持直连 ::

        PRIVPORTAL_UPSTREAM_PROXY=http://127.0.0.1:7890
        PRIVPORTAL_UPSTREAM_PROXY_HOSTS=88.api456.me

    例：全局走 Clash，但国内直连 ::

        PRIVPORTAL_UPSTREAM_PROXY=http://127.0.0.1:7890
        PRIVPORTAL_UPSTREAM_DIRECT_HOSTS=maas-coding-api.cn-huabei-1.xf-yun.com,dashscope.aliyuncs.com

    httpx 按 pattern 具体度匹配（``all://<host>`` 优先于 ``all://``），与 dict 顺序无关。
    """
    proxy_url = os.environ.get("PRIVPORTAL_UPSTREAM_PROXY", "").strip()
    if not proxy_url:
        return None

    def _hosts(name: str) -> list[str]:
        return [h.strip() for h in os.environ.get(name, "").split(",") if h.strip()]

    proxy_hosts = _hosts("PRIVPORTAL_UPSTREAM_PROXY_HOSTS")
    direct_hosts = _hosts("PRIVPORTAL_UPSTREAM_DIRECT_HOSTS")

    def direct() -> httpx.AsyncBaseTransport:
        return httpx.AsyncHTTPTransport(limits=_UPSTREAM_LIMITS)

    def viaproxy() -> httpx.AsyncBaseTransport:
        return httpx.AsyncHTTPTransport(limits=_UPSTREAM_LIMITS, proxy=proxy_url)

    mounts: dict[str, httpx.AsyncBaseTransport] = {}
    if proxy_hosts:
        for h in proxy_hosts:
            mounts[f"all://{h}"] = viaproxy()
        mounts["all://"] = direct()
        policy = f"whitelist via {proxy_url}: {', '.join(proxy_hosts)}; others direct"
    else:
        for h in direct_hosts:
            mounts[f"all://{h}"] = direct()
        mounts["all://"] = viaproxy()
        policy = f"all via {proxy_url}" + (f"; direct: {', '.join(direct_hosts)}" if direct_hosts else "")

    from app.logging_config import get_logger

    get_logger(__name__).info("upstream_proxy_policy", policy=policy)
    return mounts


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    from app.db.session import SessionLocal

    vault: VaultService = app.state.vault
    session = SessionLocal()
    try:
        if vault.try_auto_unlock(session):
            session.commit()
            from app.logging_config import get_logger
            get_logger(__name__).info("vault_auto_unlocked")

        from app.db.models import CustomPiiPattern
        from app.services.pii_scanner import load_custom_patterns_from_db
        try:
            rows = session.query(CustomPiiPattern).all()
            if rows:
                db_patterns = [(r.label, r.description, r.pattern) for r in rows]
                loaded = load_custom_patterns_from_db(db_patterns)
                if loaded > 0:
                    from app.logging_config import get_logger
                    get_logger(__name__).info("loaded_custom_pii_patterns", count=loaded)
        except Exception:
            pass

        from app.services.browser_session import cleanup_expired
        cleaned = cleanup_expired(session)
        session.commit()
        if cleaned > 0:
            from app.logging_config import get_logger
            get_logger(__name__).info("cleaned_expired_sessions", count=cleaned)
    except Exception:
        from app.logging_config import get_logger
        get_logger(__name__).exception("startup_init_error")
        session.rollback()
    finally:
        session.close()

    # trust_env=False 保留：永不读 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，代理策略只由
    # PRIVPORTAL_UPSTREAM_PROXY* 显式声明（见 _build_upstream_mounts）。
    # mounts=None（默认）时行为与改动前逐字一致 —— 全部直连。
    app.state.httpx_client = httpx.AsyncClient(
        trust_env=False,
        mounts=_build_upstream_mounts(),
        limits=_UPSTREAM_LIMITS,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
        follow_redirects=True,
    )

    from app.core.rate_limiter import get_rate_limiter
    rl = get_rate_limiter()
    rl.start_adaptive_loop()

    try:
        yield
    finally:
        rl.stop()
        await app.state.httpx_client.aclose()


def create_app() -> FastAPI:
    """Build the FastAPI application with all routes, middleware, and exception handlers."""
    app = FastAPI(title="PrivPortal", lifespan=lifespan)
    app.state.vault = VaultService()
    register_exception_handlers(app)
    allowed_origins = [
        "http://127.0.0.1:12795",
        "http://localhost:12795",
    ]
    funnel_origin = os.environ.get("FUNNEL_ORIGIN")
    if funnel_origin:
        allowed_origins.append(funnel_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "vault_unlocked": app.state.vault.is_unlocked,
        }

    app.include_router(vault_routes.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(dashboard_routes.dashboard_router, prefix="/api")
    app.include_router(dashboard_routes.audit_router, prefix="/api")
    app.include_router(logs_routes.router, prefix="/api")
    app.include_router(onboarding_routes.router, prefix="/api")
    app.include_router(projects_routes.router, prefix="/api")
    app.include_router(secrets_routes.router, prefix="/api")
    app.include_router(bindings_routes.router, prefix="/api")
    app.include_router(render_routes.router, prefix="/api")
    app.include_router(export_routes.router, prefix="/api")
    app.include_router(proxy_routes.router, prefix="/proxy")
    app.include_router(v1_gateway_routes.router, prefix="/v1")
    app.include_router(v1_gateway_routes._rl_router, prefix="/api")
    app.include_router(test_center_routes.router, prefix="/api")
    app.include_router(user_accounts_routes.router, prefix="/api")
    app.include_router(identity_bindings_routes.router, prefix="/api")
    app.include_router(sanitize_routes.router, prefix="/api")
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(sign_routes.router, prefix="")
    app.include_router(d_class_routes.router, prefix="/api")
    app.include_router(vault_sync_routes.router, prefix="/api")

    # ─── 生产模式：serve 前端构建产物 ───────────────────────
    # 当 frontend/dist 存在时，自动挂载静态文件并提供 SPA catch-all
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        index_html = frontend_dist / "index.html"

        # 静态资源（JS/CSS/images 等）
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

        # 其他根级静态文件（favicon 等）
        app.mount("/static-root", StaticFiles(directory=str(frontend_dist)), name="static-root")

        # SPA catch-all：非 API/proxy/health 路径返回 index.html
        @app.get("/{path:path}")
        async def spa_catch_all(path: str) -> FileResponse:
            candidate = frontend_dist / path
            if candidate.is_file() and ".." not in path:
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))

    return app


app = create_app()
