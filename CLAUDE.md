<!-- GSD:project-start source:PROJECT.md -->
## Project

**PrivPortal**

PrivPortal 是一个本地运行的隐私代理与脱敏门户（Local Privacy Proxy & Sanitization Portal）。它为开发者和团队提供一个 Web GUI，用于集中管理两类敏感数据：文档类隐私信息（姓名、邮箱、学号等 identity）和运行时 secret（API key、token、密码等），确保 AI Agent 和开发流程不接触明文敏感数据，同时用户可以在本地预览和导出时回填真实值。

**Core Value:** 用户通过一个本地 Web 界面即可安全地管理所有 identity 和 secret，程序运行时通过本地代理自动注入密钥而不暴露明文，文档导出时可以回填 identity 而不泄露 secret。

### Constraints

- **Tech Stack**: 后端 Python 3.12 + FastAPI + SQLAlchemy + SQLite，前端 React + TypeScript + Vite + Tailwind — 用户明确指定
- **Security**: 见下方 Security Principles — 安全模型核心约束
- **Deployment**: 仅本地运行，localhost only — 不对外暴露
- **UX**: 用户只通过 GUI 操作，CLI 仅供开发调试 — 用户体验约束
- **Monorepo**: 项目结构必须清晰、模块边界明确，适合 Cursor 阅读维护

### Security Principles（安全红线）

**核心原则：明文敏感数据永远不能出现在以下位置：**

1. **磁盘** — Identity 和 Secret 的值必须 Fernet 加密存储，防止被 LLM Agent 通过文件操作读取
2. **非本地 LLM 信息流** — 任何发往云端 LLM API 的请求必须经过 SDK 中间件脱敏（替换为占位符）
3. **日志** — 不允许 log 任何敏感值的明文（使用 structlog 的 redaction processor）
4. **Agent 工作区** — .planning/、inbox/outbox/ 等 Agent 可读目录不能包含明文
5. **Git 仓库** — 只有 Fernet 加密的 vault-backup.json 可以提交

**明文可以出现的位置：**
- 本地 UI（浏览器内存）— 用户自己查看
- API 响应（仅限 localhost）— 前端展示用
- 本地 LLM（需明确标注为本地模型）

**加密方案：**
- Identity.value 和 Secret.value 统一使用 Fernet (PBKDF2-HMAC-SHA256 + AES-128-CBC + HMAC-SHA256)
- 密钥仅存在于内存中，由 Master Password + Salt 派生
- 备份/恢复/密码轮换时自动 re-encrypt 所有数据
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12.x | Backend runtime | Matches project constraint; stable ABI, performance, typing; broad wheel support for `cryptography`. |
| FastAPI | 0.135.x | HTTP API + ASGI app | De facto standard for typed Python APIs: OpenAPI, dependency injection, Starlette underneath for middleware and streaming. **Confidence: HIGH** |
| Starlette | ≥0.46 (via FastAPI) | ASGI primitives | FastAPI’s documented lower bound; use the resolver-picked version—do not pin Starlette independently unless you hit a bug. **Confidence: HIGH** |
| Uvicorn | 0.44.x | ASGI server | Standard production/dev server for FastAPI; HTTP/1.1, WebSockets, `--reload` for local dev. **Confidence: HIGH** |
| SQLAlchemy | 2.0.49 | ORM + Core | 2.x style (`select()`, `Mapped`) is the maintained path; SQLite + async (`aiosqlite`) fits a local app. **Confidence: HIGH** |
| SQLite | 3.x (bundled with Python) | Embedded DB | Zero ops, single file, matches “local single user”; use WAL + busy timeout for concurrent API + proxy. **Confidence: HIGH** |
| Alembic | 1.18.x | Migrations | Official companion to SQLAlchemy; required once schema evolves beyond bootstrap. **Confidence: HIGH** |
| React | 19.2.x | UI | Current stable line on npm; works with Vite 8 and modern concurrent patterns. **Confidence: HIGH** |
| TypeScript | 6.0.x | Typed frontend | Aligns with React 19 / tooling; use `strict` + path aliases in Vite. **Confidence: HIGH** |
| Vite | 8.0.x | Dev server & build | Default for new React TS apps; fast HMR for local GUI iteration. **Confidence: HIGH** |
| Tailwind CSS | 4.2.x | Utility styling | Current major uses `@tailwindcss/vite` plugin and CSS-first config; fewer files than v3 for greenfield. **Confidence: HIGH** |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **cryptography** | 46.x | **Fernet** (encrypt-at-rest blobs), **MultiFernet** (key rotation), **hazmat** KDFs (PBKDF2/Argon2id from master password) | Always for secret ciphertext and deriving a Fernet key from the master password per [official Fernet + password docs](https://cryptography.io/en/latest/fernet/). **Confidence: HIGH** |
| **argon2-cffi** | 25.x | Optional: explicit Argon2id parameters / parity with other stacks | If you prefer a dedicated API for tuning Argon2id alongside `cryptography` Fernet; otherwise KDF inside `cryptography` alone is enough. **Confidence: MEDIUM** |
| **httpx** | 0.28.x | Async upstream HTTP client for proxy forwarding | Always for “receive → modify headers/body → forward → stream back” without blocking the event loop. **Confidence: HIGH** |
| **Pydantic** | 2.12.x | Request/response models, settings | FastAPI-native; use **`SecretStr`** / **`SecretBytes`** for values that must never appear in reprs/logs. **Confidence: HIGH** |
| **pydantic-settings** | 2.13.x | Typed config from env/files | Non-secret config only; master password stays in memory/session, not in `.env` committed to disk. **Confidence: HIGH** |
| **python-multipart** | 0.0.24 | Multipart bodies if GUI uploads files | When export/import or file upload endpoints exist. **Confidence: HIGH** |
| **structlog** | 25.x | Structured logging | Always: bind `request_id`, use processors to **strip/redact** fields; never log raw upstream payloads that might contain injected secrets. **Confidence: HIGH** |
| **@tanstack/react-query** | 5.96.x | Server state (API ↔ UI) | Default for FastAPI-backed CRUD, caching, invalidation, optimistic updates for vault entries. **Confidence: HIGH** |
| **zustand** | 5.0.x | Client UI / session slice | Short-lived **UI state** (e.g. reveal toggles, wizard step); optionally hold **session key material only in memory**—do not persist secret store to `localStorage`. **Confidence: HIGH** |
| **react-router-dom** | 7.14.x | SPA routing | Standard for multi-page GUI (Dashboard, Settings, Logs, Test Center). **Confidence: HIGH** |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** or **pip-tools** | Lockfile & reproducible installs | Pin backend with `uv lock` or `pip-compile`; commit lockfile. **Confidence: HIGH** |
| **Ruff** | Lint + format Python | Fast replacement for flake8/black stack; single config. **Confidence: HIGH** |
| **pytest** + **httpx** `ASGITransport` | API + proxy tests | Test FastAPI app in-process without opening real ports; add fixtures that never print secrets. **Confidence: HIGH** |
| **ESLint** + **Prettier** (or **Biome**) | TS/React quality | Align with Vite template; keep rules that forbid `console.log` of API payloads in production build if policy requires. **Confidence: MEDIUM** |
## Installation
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **httpx** + hand-rolled Starlette route for proxy | **fastapi-proxy-lib** (builds on httpx / streaming) | You need **battle-tested** header/cookie forwarding and WebSocket proxying with less custom code—evaluate license and maintenance before adopting. |
| **Fernet + KDF** (cryptography) | **age** CLI or **libsodium** bindings | You need asymmetric recipients or file encryption workflows beyond a single master password—adds complexity for little gain in v1 local tool. |
| **Zustand** (+ minimal context) | **Redux Toolkit** | Large team already standardized on Redux DevTools patterns; otherwise Zustand is less boilerplate for a single-user app. |
| **TanStack Query** alone | **TanStack Query + Redux** | Only if you split “server cache” vs “complex client workflows” across two layers—usually unnecessary here. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **PyCrypto / pycrypto** | Unmaintained; historic vulnerabilities | **`cryptography`** (PyCA) |
| **Raw `print()` / f-strings with secrets** | Violates “never in logs” requirement | **`structlog`** + redaction processors; **`SecretStr`** in models |
| **Storing master password or Fernet key in `localStorage`/IndexedDB** | Any XSS or disk inspection exposes vault | **Memory-only** session (Zustand store not persisted) + backend-only decrypt |
| **`requests` in async proxy hot path** | Blocks event loop under load | **`httpx.AsyncClient`** with connection pooling |
| **Rolling crypto (AES-GCM by hand)** | Easy to get nonce/storage wrong | **Fernet** (authenticated encryption with fixed semantics) or hazmat only with expert review |
| **Logging full `httpx` request/response in DEBUG** | Upstream bodies can contain injected API keys | Log **metadata only** (status, latency, route id); opt-in safe dump behind env flag with redaction |
## Stack Patterns by Variant
- Use **`httpx.AsyncClient`** with timeouts, limits, and a single shared client on app lifespan.
- Stream responses with **`StreamingResponse`** when upstream streams tokens.
- Prefer **Starlette WebSocket** + **`httpx-ws`** or a maintained proxy helper library; do not duplicate TLS and header forwarding blindly.
- Derive a **32-byte** key with **PBKDF2HMAC** or **Argon2id** (per [cryptography Fernet password guidance](https://cryptography.io/en/latest/fernet/)), store **salt** alongside DB, tune iterations for local UX (not cloud-scale latency).
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `fastapi@0.135.x` | `starlette>=0.46` | Let FastAPI pull Starlette; test after upgrades. |
| `httpx@0.28.x` | `httpcore` (transitive) | Keep client timeouts aligned with proxy SLAs. |
| `sqlalchemy@2.0.x` | `aiosqlite` current | Use `async_sessionmaker` + `create_async_engine` for non-blocking DB under async routes. |
| `react@19.x` | `vite@8.x`, `@types/react` matching | Use npm `overrides` only if peer conflicts appear. |
| `tailwindcss@4.x` | Vite 6+ | Use **`@tailwindcss/vite`** plugin per Tailwind v4 docs (not the old PostCSS-only v3 flow). |
## Secret Management Patterns (Prescriptive)
## Sources
- [PyPI JSON](https://pypi.org/pypi/cryptography/json) — versions for `cryptography`, `httpx`, `fastapi`, `sqlalchemy`, `alembic`, `pydantic`, `uvicorn`, `structlog`, `python-multipart`, `pydantic-settings` (queried 2026-04-06). **Confidence: HIGH**
- [npm registry `latest`](https://registry.npmjs.org/) — `react`, `vite`, `tailwindcss`, `@tanstack/react-query`, `zustand`, `typescript`, `react-router-dom` (queried 2026-04-06). **Confidence: HIGH**
- [cryptography.io — Fernet](https://cryptography.io/en/latest/fernet/) — Fernet semantics, password + KDF, MultiFernet. **Confidence: HIGH**
- [FastAPI 0.135.3 metadata](https://pypi.org/pypi/fastapi/0.135.3/json) — `starlette>=0.46.0` requirement. **Confidence: HIGH**
- [HTTPX documentation](https://www.python-httpx.org/) — async client, proxies, timeouts (verify streaming for your routes). **Confidence: MEDIUM** (behavior details: read per-version changelog when pinning)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
