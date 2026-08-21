"""Sync SQLAlchemy engine and session.

Production uses `alembic upgrade head`; tests may use `Base.metadata.create_all` for speed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

# SQLAlchemy QueuePool default is pool_size=5 + max_overflow=10 = 15.
# /v1/chat/completions holds the Session across await upstream, so each
# in-flight LLM call occupies one SQLite connection until the handler
# returns. 15 was not an LLM or CPU cap — it deadlocked the asyncio loop
# (checkout blocks the event loop; /health stops answering) at the 16th
# concurrent /v1 request. 100 covers rightapi 24 + dashscope 50 + headroom.
# Idle HTTP-waiting connections are cheap (file handles + a few MB), not
# 100 extra CPU cores.
SQLITE_POOL_SIZE = 100
SQLITE_MAX_OVERFLOW = 0


def get_database_url() -> str:
    return Settings().database_url


def _sqlite_is_memory(url: str) -> bool:
    base = url.split("?", 1)[0].rstrip("/")
    return base.endswith(":memory:") or base in (
        "sqlite://",
        "sqlite+pysqlite://",
    )


def create_sync_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    url = database_url or get_database_url()
    kwargs: dict[str, Any] = {"echo": echo}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if not _sqlite_is_memory(url):
            kwargs["pool_size"] = SQLITE_POOL_SIZE
            kwargs["max_overflow"] = SQLITE_MAX_OVERFLOW
    return create_engine(url, **kwargs)


engine: Engine = create_sync_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(bind=engine, autoflush=False, autocommit=False)
