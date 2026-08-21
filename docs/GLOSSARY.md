# glossary

TOPIC: polarprivate-runtime-limits
ACK: user 2026-08-21（点名把 QueuePool 上限与各层技术限制写入 PolarPrivate 文档）
AUDIENCE: known=polarprivate-llm-proxy partial=NONE blind=NONE（源 User-is/db/knowledge.md 2026-08-21）
ANCHOR: SQLAlchemy 2.0 Connection Pooling（https://docs.sqlalchemy.org/en/20/core/pooling.html）+ PolarPrivate `backend/app/db/session.py`（2026-08-21 `SQLITE_POOL_SIZE = 100`）

| preferred term | 中文解释 | 来源 | admitted term | deprecated term |
|----------------|----------|------|---------------|-----------------|
| QueuePool | SQLAlchemy 默认连接池：限制同时打开的 DBAPI connection 数 | https://docs.sqlalchemy.org/en/20/core/pooling.html class QueuePool；仓内 `backend/.venv` SQLAlchemy 2.0.50 `sqlalchemy/pool/impl.py` QueuePool | | 槽位；入口并发限制 |
| pool_size | QueuePool 持久保持的连接数上限，默认 5 | 同上 QueuePool.__init__ pool_size；`create_engine` `:param pool_size=5` `sqlalchemy/engine/create.py` | | |
| max_overflow | 超出 pool_size 后仍可临时打开的连接数，默认 10 | 同上 QueuePool.__init__ max_overflow；`create_engine` `:param max_overflow=10` | overflow | |
| pool timeout | QueuePool 等待归还连接的秒数，默认 30.0 | 同上 QueuePool.__init__ timeout | pool_timeout | |
| Session | SQLAlchemy 工作单元；第一次发 SQL 时才从 QueuePool checkout | SQLAlchemy 2.0 Session；PolarPrivate `backend/app/db/session.py` SessionLocal | | |
| checkout | 从 QueuePool 取出一条 connection | https://docs.sqlalchemy.org/en/20/core/pooling.html “checked out from pool” | | 借连接 |
| ServiceBudget | PolarPrivate 按 Binding service_name 的 asyncio.Semaphore + TokenBucket | `backend/app/core/rate_limiter.py` class ServiceBudget | | 限速表；入口限制 |
| max_concurrent | ServiceBudget 信号量上限；acquire 只等待、不向调用方报错 | `rate_limiter.py` ServiceBudget.acquire 文档字符串；`docs/rate-limiting-algorithm.md` | | |
| TokenBucket | ServiceBudget 内按 rpm 记账的令牌桶；acquire 不按它节流 | `rate_limiter.py` TokenBucket；ServiceBudget.acquire：「no local RPM self-throttling」 | RPM 桶 | |
| event loop | asyncio 在单一 OS thread 上调度 Task 的循环 | https://docs.python.org/3/library/asyncio-dev.html Concurrency and Multithreading | | |
| blocking I/O | 在 event loop 所在 thread 上同步等待，期间其它 Task 不能跑 | https://docs.python.org/3/library/asyncio-dev.html Running Blocking Code | | 死锁（未作为 PolarPrivate 源码标识符） |
| httpx.Limits | 共享 AsyncClient 的并发 connection 上限 | httpx `_config.py` class Limits；PolarPrivate `backend/app/main.py` lifespan | | |
| max_connections | httpx.Limits 同时允许的 connection 数 | 同上；PolarPrivate 设为 64（httpx DEFAULT_LIMITS 为 100） | | |
| journal_mode DELETE | SQLite 新建库默认日志模式 | https://www.sqlite.org/pragma.html#pragma_journal_mode 「The DELETE journaling mode is the default.」 | | WAL mode |

分歧项:
- 无。QueuePool / ServiceBudget / httpx.Limits 是三套不同上限，正文分列，不合并成一个「并发限制」。
