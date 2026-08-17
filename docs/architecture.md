# PolarPrivate 系统架构

## 概览

PolarPrivate 是 Polarisor 生态的**供给平面（supply plane）**：本地密钥保险库 + 统一 LLM Proxy。调用方只提交 QCSA 能力码、Binding 名或 Secret 引用；凭证在 localhost 进程内解密、使用并丢弃，从而让 Agent 拥有能力而不知道秘密。无状态 PII 正则扫描/涂抹作为附属能力保留，文档 Identity 脱敏与导出回填产品线已退役。

## 技术栈

| 层        | 技术                                           | 版本要求         |
| --------- | ---------------------------------------------- | ---------------- |
| 后端运行时 | Python                                         | 3.12.x           |
| Web 框架   | FastAPI + Starlette                            | ≥0.135           |
| ASGI 服务器 | Uvicorn                                        | ≥0.44            |
| ORM        | SQLAlchemy 2.x (sync)                          | ≥2.0.49          |
| 数据库     | SQLite (WAL mode)                              | 3.x (Python 内置) |
| 数据库迁移 | Alembic                                        | ≥1.18            |
| 加密       | cryptography (Fernet / MultiFernet / PBKDF2)   | ≥46.0            |
| HTTP 客户端 | httpx (异步)                                   | ≥0.28            |
| 日志       | structlog                                      | ≥25.0            |
| 前端框架   | React + TypeScript                             | React 18.x       |
| 构建工具   | Vite                                           | ≥6.0             |
| 样式       | Tailwind CSS                                   | ≥3.4             |
| 状态管理   | TanStack React Query + Zustand                 | —                |
| 路由       | react-router-dom                               | ≥6.28            |

## 项目目录结构

```
PolarPrivate/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用工厂 + ASGI 入口
│   │   ├── cli.py               # Typer CLI (start / init-db / import-demo / test / smoke)
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings 配置 (PRIVPORTAL_* 环境变量)
│   │   │   ├── model_routing.py # QCSA → 模型 / Binding / fallback
│   │   │   ├── model_catalog.py # /v1/models 模型目录
│   │   │   ├── rate_limiter.py  # 并发 / RPM / 冷却
│   │   │   └── CAPABILITY_CODES.md # 能力码 SSOT
│   │   ├── db/
│   │   │   ├── base.py          # SQLAlchemy declarative Base
│   │   │   ├── models.py        # ORM 模型 (DbMetadata, Project, Secret, Binding, UserAccount, AuditLog 等)
│   │   │   └── session.py       # 同步引擎和会话工厂
│   │   ├── api/                  # FastAPI 路由模块
│   │   │   ├── deps.py          # 依赖注入 (get_db, get_vault, require_unlocked_vault)
│   │   │   ├── vault_routes.py  # Vault 解锁 / 改密码
│   │   │   ├── onboarding.py    # 初始化引导
│   │   │   ├── projects.py      # 项目 CRUD
│   │   │   ├── secrets.py       # Secret 元数据 CRUD + rotate + 连通性测试（无明文读取）
│   │   │   ├── bindings.py      # Binding CRUD
│   │   │   ├── v1_gateway.py    # /v1 chat / embeddings / models 统一网关
│   │   │   ├── v1_media.py      # /v1 生图 I000 / 生音频 A000 / 生视频 D000
│   │   │   ├── sanitize.py      # PII scan/redact 附属能力
│   │   │   ├── sign.py          # B 类进程内签名
│   │   │   ├── d_class.py       # D 类受控明文授权
│   │   │   ├── dashboard.py     # 仪表盘汇总 + 审计日志
│   │   │   ├── render.py        # 模板渲染
│   │   │   ├── export.py        # 导出 (Markdown/HTML/TXT)
│   │   │   ├── proxy.py         # 反向代理 (httpx 转发)
│   │   │   ├── logs.py          # 内存日志查询
│   │   │   ├── settings.py      # 应用设置
│   │   │   ├── test_center.py   # LLM / sign / D 类配置探针
│   │   │   └── exceptions.py    # 统一 JSON 错误响应
│   │   ├── services/
│   │   │   ├── vault.py         # VaultService: 加密核心 (Fernet + PBKDF2)
│   │   │   ├── pii_scanner.py   # 无状态 PII 正则扫描/涂抹
│   │   │   ├── template_render.py # 仅渲染 Binding/Secret 引用标记
│   │   │   ├── sign_providers/  # weex / feishu-webhook / aliyun-sigv1
│   │   │   ├── export_format.py # Markdown→HTML/TXT 转换
│   │   │   ├── audit.py         # 审计日志追加
│   │   │   ├── log_buffer.py    # 线程安全环形日志缓冲区
│   │   │   ├── db_bootstrap.py  # Alembic 迁移运行器
│   │   │   └── demo_seed.py     # Demo 数据种子
│   │   └── logging_config.py    # structlog 配置 + 密钥脱敏处理器
│   ├── tests/                    # pytest 测试套件 (35+ 测试模块)
│   ├── alembic/                  # 数据库迁移脚本
│   └── pyproject.toml            # Python 包配置
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 路由定义 (React.lazy 代码分割)
│   │   ├── main.tsx             # React 入口
│   │   ├── lib/
│   │   │   ├── api.ts               # HTTP 客户端封装 (fetch → apiRequest)
│   │   │   ├── toast.ts             # 通知组件 (sonner 封装)
│   │   │   └── use-document-title.ts # 页面标题 Hook
│   │   ├── stores/
│   │   │   └── uiStore.ts       # Zustand UI 状态
│   │   ├── components/           # 布局与通用组件
│   │   │   ├── AppLayout.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── TopBar.tsx
│   │   │   ├── UnlockModal.tsx
│   │   │   ├── OnboardingWizard.tsx
│   │   │   ├── ProjectSelect.tsx
│   │   │   ├── Modal.tsx          # 通用弹窗容器
│   │   │   ├── ConfirmDialog.tsx  # 删除确认对话框
│   │   │   ├── EmptyState.tsx     # 空状态提示组件
│   │   │   ├── Skeleton.tsx       # 加载骨架屏组件
│   │   │   ├── PageHeader.tsx     # 统一页面标题/描述/操作布局
│   │   │   └── CommandPalette.tsx # Cmd+K 快速导航面板
│   │   └── pages/                # 页面组件
│   │       ├── DashboardPage.tsx
│   │       ├── ProjectsPage.tsx
│   │       ├── SecretsPage.tsx
│   │       ├── BindingsPage.tsx
│   │       ├── TestCenterPage.tsx
│   │       ├── SettingsPage.tsx
│   │       ├── LogsPage.tsx
│   │       ├── UsersPage.tsx
│   │       ├── UsagePage.tsx
│   │       ├── AboutPage.tsx
│   │       └── NotFoundPage.tsx   # 404 页面
│   ├── package.json
│   └── vite.config.ts
└── docs/                         # 项目文档
```

## 核心架构分层

### 1. 应用入口层

**`app/main.py`** — FastAPI 应用工厂 `create_app()`:

- 通过 `lifespan` 上下文管理器在启动时配置 structlog。
- 将 `VaultService` 实例挂载到 `app.state.vault`（进程级单例）。
- 注册统一异常处理器。
- 配置 CORS 中间件，仅允许 `localhost:12795`（Vite 开发服务器；5170 已分配给 PolarUI）。
- 注册管理 API（`/api/*`）、通用代理（`/proxy/*`）、统一 LLM 网关（`/v1/*`）与签名路由（`/sign/*`）。

**`app/cli.py`** — Typer CLI，提供以下子命令:

| 命令           | 功能                                      |
| -------------- | ----------------------------------------- |
| `start`        | 启动 Uvicorn 服务器                       |
| `init-db`      | 运行 Alembic 迁移到 head                  |
| `import-demo`  | 初始化 Vault + 导入 Demo 数据             |
| `test`         | 运行 pytest                               |
| `smoke`        | 运行端到端冒烟测试                        |

### 2. 数据层

**数据库**: SQLite 单文件 (`privportal.db`)，同步引擎 + `sessionmaker`。使用 `check_same_thread=False` 支持 FastAPI 多线程访问。

**ORM 模型** (`app/db/models.py`):

| 模型         | 表名          | 说明                                                |
| ------------ | ------------- | --------------------------------------------------- |
| `DbMetadata` | `db_metadata` | 单行：salt、sentinel 密文、schema 版本、wrapped Fernet keys |
| `AppSettings`| `app_settings`| 单行：API 端口、JSON 偏好设置                       |
| `Project`    | `projects`    | 顶层项目容器                                        |
| `Secret`     | `secrets`     | 点号分隔键 + Fernet 密文值                          |
| `Binding`    | `bindings`    | 服务名 → Secret 引用键的映射                        |
| `UserAccount`| `user_accounts` | 本地用户及其 wrapped Fernet keys                  |
| `IdentityBinding` | `identity_bindings` | 外部服务用户名 → 本地用户；不是文档 PII Vault |
| `CustomPiiPattern` | `custom_pii_patterns` | PII 扫描器的自定义正则                   |
| `AuditLog`   | `audit_log`   | 追加写审计日志                                      |

**关系**: `Project` 与 `Secret`、`Binding`、`AuditLog` 为一对多关系，外键按用途使用 `CASCADE` 或 `SET NULL`。

### 3. 加密层

**`app/services/vault.py`** — `VaultService` 是整个系统的加密中枢:

```
Master Password
    │
    ▼
PBKDF2-HMAC-SHA256 (480,000 iterations) + random 16-byte salt
    │
    ▼
32-byte 派生 Fernet key
    │
    ├── 验证 sentinel
    └── 解开 schema v2 的 wrapped fernet_keys_json
              │
              ▼
        MultiFernet (支持密钥轮换)
    │
    ├── encrypt_secret_value(plaintext) → ciphertext
    └── decrypt_secret_value(ciphertext) → plaintext
```

- **初始化**: `create_new_database()` 生成随机 salt，派生 Fernet 密钥，用该密钥加密 sentinel，并把 Fernet keys JSON 加密包装后写入 `fernet_keys_json`（schema v2）。
- **解锁**: `unlock()` 用输入密码 + salt 重新派生密钥；验证 sentinel 后解开 wrapped keys，构建只驻内存的 MultiFernet。`schema_version < 2` 仅保留旧库兼容读取分支。
- **密码更换**: `change_master_password()` 生成新 salt + 新密钥，重新加密所有 Secret 行。

### 4. API 层

入口按职责分为四组：

- `/v1/*` — OpenAI 兼容的统一 LLM/Embeddings 网关；
- `/proxy/*` — 按 Binding 转发任意上游 HTTP 请求；
- `/api/*` — Vault、Secret、Binding、审计、PII scan/redact 等管理接口；
- `/sign/*` — 使用 Vault 内 Secret 完成 B 类签名。

**依赖注入** (`app/api/deps.py`):

- `get_db()` — 同步 SQLAlchemy Session，自动 commit/rollback/close。
- `get_vault()` — 从 `app.state.vault` 获取 VaultService。
- `require_unlocked_vault()` — 检查 Vault 是否已解锁，未解锁返回 HTTP 423。

### 5. 统一 LLM Gateway

**`app/api/v1_gateway.py`** 提供 `POST /v1/chat/completions`、`POST /v1/embeddings` 与 `GET /v1/models`。**`app/api/v1_media.py`** 提供生图 `POST /v1/images/generations`（`I000`）、生音频 `POST /v1/audio/speech`（`A000`）、生视频 `POST /v1/videos/generations`（`D000`）及任务查询。文本/视觉调用以 QCSA 能力码表达需求，网关负责解析真实模型与 Binding、跨订阅负载均衡、限流等待、失败引流，以及响应 `model` 字段去供应商化。

```
Agent / OpenAI SDK
    │ model: "0001"
    ▼
PolarPrivate /v1/chat/completions
    │
    ├── QCSA → 真实模型 + service_name
    ├── Binding → Secret
    ├── Vault 进程内解密并注入认证头
    └── 上游响应中的模型名改写为调用方能力码
```

### 6. Secret 使用通道

- **A 类反向代理**：`app/api/proxy.py` 的 `{method} /proxy/{service_name}/{path:path}` 按 Binding 解密并注入认证头，支持普通与 SSE 响应。
- **B 类签名**：`app/api/sign.py` 在进程内完成 HMAC/签名运算，只返回签名后的 headers。
- **D 类受控信道**：`app/api/d_class.py` 仅对命中 `service_name + 可执行文件 SHA256` allowlist 的第三方 SDK 授权。

三条通道都以最小作用域使用明文。R9 已永久移除 `POST /api/secrets/{secret_id}/reveal`，GUI 对 Secret 只写不可读。

### 7. PII 扫描附属能力

**`app/services/pii_scanner.py`** 对调用方文本做无状态正则扫描；`/api/sanitize/scan|redact` 返回命中或涂抹结果，并支持持久化自定义 pattern。它不依赖预登记 Identity，也不会自动介入 `/v1` 请求。

### 8. 遗留模板渲染与导出

文档 Identity 脱敏与导出回填产品线已退役。`app/services/template_render.py` 当前只接受：

- `[[binding.xxx]]` → `[secret_ref:...]`；
- `[[secret_ref.xxx]]` → `[secret_ref:...]`。

`decrypt` 参数仅为 deprecated API 兼容参数，不会解密或回填身份/Secret。`/api/export` 仍可把上述引用文本转为 Markdown、HTML 或 TXT。

### 9. 日志层

**`app/logging_config.py`** — structlog + stdlib 配置:

- `redact_processor` — 递归遍历日志事件字典，将注册的密钥子串替换为 `[REDACTED]`。
- `_SK_LIKE_PATTERN` — 额外匹配 `sk-*` 形式的 API Key 并脱敏。
- `_buffer_log_processor` — 将脱敏后的日志追加到内存环形缓冲区。

**`app/services/log_buffer.py`** — 线程安全的 1000 条环形缓冲区，前端通过 `GET /api/logs` 查询。

### 10. 前端层

React SPA 通过 Vite 开发服务器在 `localhost:12795` 运行。

**路由结构**:

| 路径             | 页面组件             | 功能           |
| ---------------- | -------------------- | -------------- |
| `/`              | DashboardPage        | 仪表盘         |
| `/projects`      | ProjectsPage         | 项目管理       |
| `/secrets`       | SecretsPage          | Secret 管理    |
| `/bindings`      | BindingsPage         | Binding 管理   |
| `/test-center`   | TestCenterPage       | 测试中心       |
| `/settings`      | SettingsPage         | 设置           |
| `/users`         | UsersPage            | 本地用户管理   |
| `/logs`          | LogsPage             | 日志查看       |
| `/usage`         | UsagePage            | 代理用量       |
| `/about`         | AboutPage             | 项目信息       |
| `*`              | NotFoundPage         | 404 页面       |

所有页面组件通过 `React.lazy()` 懒加载并包裹在 `<Suspense>` 中，实现路由级代码分割。

**状态管理**:

- **TanStack React Query** — 管理所有 API 调用的服务器状态（缓存、失效、乐观更新）。
- **Zustand** — 管理 UI 偏好状态（`activeProjectId`、`sidebarCollapsed`），通过 `localStorage`（key: `privportal:ui`）持久化。注意：仅持久化非敏感的 UI 偏好，不存储任何密钥材料。

## 数据流

### 写入 Secret 的流程

```
用户在 GUI 输入明文 API Key
    │
    ▼
POST /api/secrets { key: "secret.openai.default", value: "sk-..." }
    │
    ▼
require_unlocked_vault() 检查 Vault 状态
    │
    ▼
vault.encrypt_secret_value("sk-...") → Fernet 加密
    │
    ▼
INSERT INTO secrets (value = <ciphertext>)
    │
    ▼
返回 SecretOut (不含 value 字段)
```

### 统一 LLM 供给流程

```
AI Agent 发送 POST /v1/chat/completions，model="0001"
    │
    ▼
QCSA 路由解析 → 真实模型 + service_name
    │
    ▼
查找全局 Binding → Secret；Vault 在内存中解密
    │
    ▼
注入认证头并用共享 httpx.AsyncClient 转发
    │
    ▼
上游响应流式或标准返回；对不透明能力码回写 model="0001"
```

## 配置

所有后端配置通过 `PRIVPORTAL_*` 前缀的环境变量控制：

| 变量                      | 默认值                     | 说明            |
| ------------------------- | -------------------------- | --------------- |
| `PRIVPORTAL_API_HOST`     | `127.0.0.1`                | 监听地址        |
| `PRIVPORTAL_API_PORT`     | `12790`                    | 监听端口        |
| `PRIVPORTAL_DATABASE_URL` | `sqlite:///./privportal.db`| 数据库连接字符串 |

前端通过 `VITE_API_BASE` 环境变量指向后端（默认 `http://127.0.0.1:12790`）。
