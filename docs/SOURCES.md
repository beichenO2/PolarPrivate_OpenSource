# SOURCES

<!-- paperlike-lint: allow-start -->

TOPIC: polarprivate-runtime-limits
每条引文一行。核对走 agent-verify。

| 正文位置 | 断言 | 一次文献 |
|----------|------|----------|
| GLOSSARY QueuePool | QueuePool 是默认 pooling，`:memory:` SQLite 除外 | https://docs.sqlalchemy.org/en/20/core/pooling.html class QueuePool |
| GLOSSARY pool_size / max_overflow | 默认 5 与 10；同时连接数 = pool_size + max_overflow | 同上 QueuePool.__init__；仓内 `sqlalchemy/pool/impl.py` L84–106 |
| GLOSSARY pool timeout | 默认 30.0 秒 | `sqlalchemy/pool/impl.py` timeout: float = 30.0 |
| GLOSSARY QueuePool 与 asyncio | QueuePool is not compatible with asyncio / create_async_engine | https://docs.sqlalchemy.org/en/20/core/pooling.html QueuePool |
| runtime-limits Session 跨 await | `unified_chat_completions` 为 async def，Depends(get_db)；L577/588 session.scalars 后 L658 await client.request；超时分支 L690 仍写 session | `backend/app/api/v1_gateway.py` L496–709 |
| runtime-limits get_db | sync generator：yield Session，finally close | `backend/app/api/deps.py` get_db |
| runtime-limits SQLITE_POOL_SIZE | 100；max_overflow 0 | `backend/app/db/session.py` SQLITE_POOL_SIZE / SQLITE_MAX_OVERFLOW |
| runtime-limits ServiceBudget | acquire 只等 Semaphore，不做 RPM self-throttling | `backend/app/core/rate_limiter.py` ServiceBudget.acquire |
| runtime-limits rightapi / dashscope 数字 | max_concurrent 24 / 50 | `rate_limiter.py` _SERVICE_LIMITS |
| runtime-limits httpx 64 | Limits(max_connections=64, max_keepalive_connections=32) | `backend/app/main.py` lifespan |
| runtime-limits httpx default 100 | DEFAULT_LIMITS max_connections=100 | httpx `_config.py` DEFAULT_LIMITS |
| runtime-limits pool=10.0 | _NON_STREAM_TIMEOUT pool=10.0 | `backend/app/api/proxy.py` L117–118 |
| runtime-limits uvicorn 单进程 | 无 --workers | `Start/backend.sh` exec uvicorn |
| runtime-limits /health 为 def | sync def health | `backend/app/main.py` GET /health |
| runtime-limits FastAPI def vs async def | def 丢进 threadpool；async def 直接在 event loop | https://fastapi.tiangolo.com/async/ Very Technical Details |
| runtime-limits blocking | Blocking code delays all concurrent Tasks | https://docs.python.org/3/library/asyncio-dev.html Running Blocking Code |
| runtime-limits journal_mode | DELETE is the default | https://www.sqlite.org/pragma.html#pragma_journal_mode |
| runtime-limits sqlite3 timeout | connect timeout = busy timeout seconds | https://docs.python.org/3/library/sqlite3.html#sqlite3.connect |
| runtime-limits 实测 15 vs 20 | 2026-08-21 百炼-only：N=15 全 200；N=20 /health 超时 | 本机 `POST /v1/chat/completions` model=qwen3.8-27b，max_tokens=8 |
| runtime-limits 实测改后 | 重启后 N=20 与 N=30 全 200 | 同上，`SQLITE_POOL_SIZE=100` 已加载 |
| runtime-limits 504 文案 | TimeoutException JSON 写 `300s limit` | `v1_gateway.py` L693–696 |
| runtime-limits 单测 | `pool.size()==100`，`_max_overflow==0` | `backend/tests/test_db.py` `test_sqlite_file_pool_allows_100_slots` |

<!-- paperlike-lint: allow-end -->

