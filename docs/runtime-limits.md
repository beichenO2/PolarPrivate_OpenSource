# PolarPrivate 运行时上限（各技术层）

<!-- paperlike-lint: allow-start -->

术语见 [`GLOSSARY.md`](./GLOSSARY.md)。出处表见 [`SOURCES.md`](./SOURCES.md)。评分与 Binding 侧节流见 [`rate-limiting-algorithm.md`](./rate-limiting-algorithm.md)。

2026-08-21：文件 SQLite 的 QueuePool（SQLAlchemy 连接池）从默认 `pool_size=5` + `max_overflow=10`（合计 15）改为 `pool_size=100`、`max_overflow=0`。代码：`backend/app/db/session.py` 常量 `SQLITE_POOL_SIZE` / `SQLITE_MAX_OVERFLOW`。这不是 `ServiceBudget.max_concurrent`，也不是 CPU 核数。

## 前置：三套上限不要并成一套

`POST /v1/chat/completions` 一条在途请求会同时占用下面几层。数字来源不同，不得把 15、24、50、64、100 说成同一个「并发限制」。

| 层 | 对象 | 2026-08-21 本机值 | 满了会怎样 | 出处 |
|----|------|-------------------|------------|------|
| QueuePool | 本进程 SQLite connection | `pool_size=100`，`max_overflow=0`（改前默认 5+10=15） | checkout 在调用线程同步等待，默认最多 30s（SQLAlchemy `timeout`） | SQLAlchemy QueuePool.__init__；`session.py` |
| Session 寿命 | 上述 connection 被谁握着 | 握到 `get_db` 的 `finally: session.close()`（handler 整段返回之后） | `await` 上游期间不还连接 | `deps.py` L16–26；`v1_gateway.py` L496–709 |
| httpx.Limits | 共享 `AsyncClient` 出站 connection | `max_connections=64`，`max_keepalive_connections=32` | 再要 connection 时等 pool timeout | `main.py` lifespan；httpx Limits |
| httpx.Timeout.pool | 等出站 connection 的秒数 | `_NON_STREAM_TIMEOUT` 的 `pool=10.0` | `httpx.TimeoutException` → 网关 JSON 504 | `proxy.py` L117–118；`v1_gateway.py` TimeoutException 分支 |
| ServiceBudget | 每个 Binding `service_name` | 例：`llm.rightapi` 24，`llm.aliyun.dashscope` 50 | `await` Semaphore，不向调用方返回 429 | `rate_limiter.py`；`rate-limiting-algorithm.md` |
| TokenBucket | 同一 ServiceBudget 的 rpm 记账 | 例：rightapi rpm=120（只展示） | acquire **不**按 rpm 停请求 | `ServiceBudget.acquire` 文档字符串 |
| Uvicorn | ASGI 进程数 | `Start/backend.sh` 未传 `--workers` → 1 个进程、1 条 event loop | 所有 `/v1` 与 `/health` 共用这一条 loop | `Start/backend.sh` |

`GET /api/rate-limits` 只反映 ServiceBudget（`in_flight` / `max_concurrent` / `window_60s`）。它看不到 QueuePool checkout 队列。

## QueuePool 默认 15 是为了什么

SQLAlchemy 文档：`create_engine()` 在多数情况下带一个预配置的 QueuePool；`pool_size` 默认 5、`max_overflow` 默认 10；池子一开始是空的，只有真正并发 checkout 时才涨到这个大小。文档原句说明这个默认「without regard to whether or not the application really needs five connections」——面向典型远程 RDBMS，避免进程打开过多 TCP connection。公式（QueuePool.__init__）：同时允许的 connection 数 = `pool_size` + `max_overflow`。

PolarPrivate 用文件 SQLite（`Settings.database_url` 默认 `sqlite:///./privportal.db`）。`create_sync_engine` 在 2026-08-21 之前只设置了 `check_same_thread=False`，没有改 `pool_size` / `max_overflow`，因此吃到上述默认合计 15。

SQLAlchemy 写明：QueuePool **is not compatible with asyncio**；`create_async_engine` 才会换 `AsyncAdaptedQueuePool`。PolarPrivate 走的是 sync `create_engine` + sync `Session`，挂在 FastAPI 的 `async def` 路由上。

## PolarPrivate 如何把 15 变成「同时在途 /v1 条数」

1. `unified_chat_completions` 声明为 `async def`，并 `Depends(get_db)`（`v1_gateway.py` L496–499）。
2. `get_db` 是普通 `def` generator：`SessionLocal()` → `yield session` → `finally: session.close()`（`deps.py` L16–26）。FastAPI：普通 `def` 依赖在 threadpool 里跑；`async def` 路由本体在 event loop 上跑（FastAPI async 页 Very Technical Details）。
3. `Session` 第一次执行 SQL 时才 checkout。网关在 `async def` 体内调用 `session.scalars(select(Binding)...)`（L577）与 `select(Secret)`（L588），这是 blocking I/O。
4. 同一 `session` 一直活到 handler 返回（`get_db` 的 `finally`）。L658 `await client.request(...)` 发生在 checkout 之后；L690 超时分支仍 `_record_usage(session, ...)`。上游返回前 **不** `close()`，QueuePool 槽不释放。

因此：在途 `/v1/chat/completions` 条数 ≤ QueuePool 同时 connection 数。改前是 15。这与 `llm.rightapi` 的 24、`llm.aliyun.dashscope` 的 50 无关。

## 第 16 路时 `/health` 为什么也不回答

Python asyncio 文档 Running Blocking Code 写：blocking（该节例子是 CPU-bound 计算 1 秒）若直接在 event loop 所在 thread 上调用，会推迟该 thread 上所有其它 Task 和 IO。QueuePool.checkout 在连接用尽时，在**当前线程**同步等到 `timeout`（默认 30.0 秒）。该调用发生在 `async def` 里、未包进 `run_in_executor`，因此同样没有 `await`，event loop 不能切去跑 `/health`。

`GET /health` 是 `def health()`（`main.py`）。FastAPI 把 `def` 路由丢进 threadpool 再 await。调度这个 await 仍要 event loop。event loop 停在 checkout 上时，`/health` 的 TCP 连接可以建立，响应体出不去。

asyncio 文档：一条 Task 在跑、且没有 `await` 时，同一 thread 上其它 Task 不能跑。checkout 等待不是 `await`。

2026-08-21 对照（`model=qwen3.8-27b`，提示「只回复数字1」，`max_tokens=8`，不重试，rightapi 在途为 0）：

| N | QueuePool 仍为默认 15 时 |
|---|-------------------------|
| 10 | 10 个 HTTP 200，约 2.24s，`/health` 正常 |
| 15 | 15 个 HTTP 200，约 3.33s，`/health` 正常 |
| 20（冷启动） | 20 个客户端 TimeoutError；`/health` 超时 |
| 50 | 客户端超时；随后 `connection refused` |

同一 N=20、只把 `model` 换成 `gpt-5.6-sol`：同样 `/health` 超时。自变量是本进程在途 `/v1` 条数，不是百炼或 rightapi 的 `max_concurrent`。

改 `SQLITE_POOL_SIZE=100` 并 PolarProcess 重启 `privportal-backend` 之后（vault 仍 `unlocked`）：N=20 → 20 个 HTTP 200，约 4.28s；N=30 → 30 个 HTTP 200，约 5.18s；两次 `/health` 均正常。

## 2026-08-21 代码改动

`create_sync_engine` 对**非** `:memory:` 的 SQLite URL：

- `pool_size=100`，`max_overflow=0`（合计 100，不再使用默认 5+10）。
- `connect_args["timeout"]=30`：Python `sqlite3.connect` 的 timeout，单位秒，是 busy handler 等待（https://docs.python.org/3/library/sqlite3.html#sqlite3.connect），与 QueuePool 的 `timeout=30.0` 不是同一个旋钮。

100 的选取：覆盖当时 `ServiceBudget` 上 `llm.rightapi` 24 + `llm.aliyun.dashscope` 50，并留余量。文件 SQLite connection 是进程内文件句柄；在途请求大部分时间在 `await` HTTP，不在 SQLite 上做 CPU 计算。asyncio-dev 把「1 秒 CPU 计算挡住所有 Task」和「用 executor 跑 blocking」分开写；QueuePool 槽数不是核数。

未改：`ServiceBudget` 数字；未把 `/v1` 改成查完 Binding/Secret 立即 `session.close()` 再 `await` 上游。后一项仍是把 Session 寿命与上游 RTT 解耦的做法，本页只记录现状。

## 其它技术层（未在本次改 QueuePool 时一起改）

### httpx.Limits = 64

`lifespan` 里 `httpx.AsyncClient(limits=Limits(max_connections=64, ...))`。httpx 源码 `DEFAULT_LIMITS` 是 `max_connections=100`。PolarPrivate 把出站并发设成 64，低于 QueuePool 的 100。在途 `/v1` 超过 64 时，多出来的请求在 `_NON_STREAM_TIMEOUT.pool=10.0` 上等待，超时走 504 分支，不一定再卡住 `/health`（那是 async wait，不是 sync checkout）。

### ServiceBudget（按供应商）

`await _rl.acquire(service_name)` 在查出 Binding 之后、`client.request` 之前。满员时协程挂起，event loop 仍可跑 `/health`。`rpm` 字段在 `acquire` 里不节流。看 `GET /api/rate-limits` 的 `in_flight` / `cooldown_remaining_sec` / `window_60s`。

### Uvicorn 1 进程

`Start/backend.sh`：`exec uvicorn app.main:app --host ... --port ...`，没有 `--workers`。一条 event loop 服务全部 HTTP。这是 PolarProcess 管的 `privportal-backend`，不是 PolarPort/PolarProcess/PolarBudget 三个权威服务本身。

### SQLite journal_mode

https://www.sqlite.org/pragma.html#pragma_journal_mode ：「The DELETE journaling mode is the default.」`backend/` 下无 `PRAGMA journal_mode` / `journal_mode=WAL` 的 Python 赋值（2026-08-21 检索）。`docs/architecture.md` 与 `AGENTS.md` 曾写 “WAL mode”；以 `session.py` 为准，默认是 DELETE，除非该库文件此前已被改成 WAL 且 WAL 会跨连接保持（同一 pragma 页：WAL is persistent）。

### `/health` 与 Vault

`health()` 读 `app.state.vault.is_unlocked`，不经过 `get_db`，因此不占 QueuePool。它仍需要 event loop 把 `def` 路由调度到 threadpool。

## 调用方怎么判断撞了哪一层

| 观察 | 更像哪一层 |
|------|------------|
| `/health` 3s 内无 JSON；`GET /api/rate-limits` 同样超时 | event loop 被 sync checkout（或其它 blocking）挡住；改前在途 `/v1` 条数大于 15 |
| `/health` 正常；`rate-limits` 里某 service `in_flight` 顶在 `max_concurrent` | ServiceBudget 在排队 |
| `/health` 正常；响应 504 且 body 含 `Upstream LLM request timed out` | `v1_gateway.py` L689–698 `httpx.TimeoutException`。JSON 文案写 `300s limit`；同请求实际传入的是 `_NON_STREAM_TIMEOUT`（`proxy.py` L118：`read=600.0`，`pool=10.0`）。超时可能来自 pool 等待或 read。 |
| HTTP 429 且 `window_60s.429` 增加 | 上游 429，不是 QueuePool |

重启 `privportal-backend` 后 QueuePool 与 ServiceBudget 内存计数都从零开始；Vault 是否仍解锁取决于该次进程是否 `try_auto_unlock`。

<!-- paperlike-lint: allow-end -->
