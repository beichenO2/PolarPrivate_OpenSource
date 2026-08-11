# PolarPrivate 使用指南

PolarPrivate 是 Polarisor 生态的供给平面：本地密钥保险库 + 统一 LLM Proxy。主要工作流是让调用方使用 QCSA 能力码获得模型与第三方服务能力，同时不接触 Secret 明文。

## 系统要求

- Python 3.12.x
- Node.js 18+ 和 npm
- macOS / Linux（Windows 未测试）

## 安装

### 后端

```bash
cd backend

# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .

# 安装开发依赖（pytest、ruff）
uv sync --extra dev
```

### 前端

```bash
cd frontend
npm install
```

## 初始化

### 1. 初始化数据库

首次使用前需要运行数据库迁移：

```bash
cd backend
privportal init-db
```

这会在 `backend/` 目录下创建 `privportal.db` SQLite 文件，并运行所有 Alembic 迁移。

### 2. 启动后端

```bash
cd backend
privportal start
```

后端默认监听 `http://127.0.0.1:12790`。

可通过环境变量调整：

```bash
PRIVPORTAL_API_PORT=9090 privportal start
```

### 3. 启动前端

```bash
cd frontend
npm run dev
```

前端开发服务器默认运行在 `http://localhost:12795`。

### 4. 打开浏览器

访问 `http://localhost:12795`，首次进入会自动弹出 Onboarding 向导。

## 快速开始

### 通过 GUI 初始化

1. 打开浏览器访问 `http://localhost:12795`
2. Onboarding 向导自动弹出
3. 点击 **Next** → 数据库自动初始化
4. 设置 **Master Password**（务必记住，无法恢复！）
5. 选择导入 Demo 数据或跳过
6. 点击 **Get started** 进入 Dashboard

### 通过 CLI 初始化

如果偏好命令行操作：

```bash
cd backend

# 初始化数据库
privportal init-db

# 导入演示数据（会提示输入 Master Password）
privportal import-demo

# 启动服务器
privportal start
```

不建议通过环境变量传入 Master Password；环境变量可能进入 Agent 进程、Shell 历史或诊断信息。请使用交互式提示或本地 GUI。

## 核心使用场景

### 场景 1：通过统一 LLM 网关调用能力

Vault 已解锁且全局 LLM Binding 配置完成后，调用方只传 QCSA 能力码：

```bash
curl -X POST http://127.0.0.1:12790/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "0001",
    "messages": [{"role": "user", "content": "返回 pong"}]
  }'
```

PolarPrivate 在进程内完成能力码解析、Binding 选择、Secret 解密与认证头注入。调用方不会收到 API Key，上游真实模型名也不会替代响应中的能力码。`GET /v1/models` 可查看当前可用模型，`POST /v1/embeddings` 使用 `E000` 嵌入能力码。

### 场景 2：存储 API 密钥

适用于 OpenAI、阿里云灵积等服务的 API Key。

1. 导航到 **Secret Vault** 页面
2. 点击 **Add secret**
3. 填写：
   - Key: `secret.openai.default`
   - Value: `sk-xxxxxxxxxxxx`（明文输入，后端自动加密存储）
   - Base URL: `https://api.openai.com/v1`
   - Category: `openai`
   - Enabled: 勾选
4. 点击 **Create**

### 场景 3：配置代理绑定

将服务名称映射到 Secret，让 AI Agent 通过代理访问 API。

1. 导航到 **Bindings** 页面
2. 点击 **Add binding**
3. 填写：
   - Service Name: `llm.openai`
   - Secret Ref Key: `secret.openai.default`
   - Auth Header: 留空（默认 `Authorization: Bearer`）
4. 点击 **Create**

配置完成后，AI Agent 可以通过以下方式访问 OpenAI API：

```bash
# 原本的请求:
# POST https://api.openai.com/v1/chat/completions
# Authorization: Bearer sk-xxxxxxxxxxxx

# 通过 PolarPrivate 代理:
POST http://127.0.0.1:12790/proxy/llm.openai/v1/chat/completions
# 无需 Authorization header —— PolarPrivate 自动注入
```

### 场景 4：附属 PII 扫描与涂抹

`/api/sanitize/scan` 与 `/api/sanitize/redact` 对调用方提供的文本执行无状态正则检测，不依赖预先登记的身份数据：

```bash
curl -X POST http://127.0.0.1:12790/api/sanitize/redact \
  -H "Content-Type: application/json" \
  -d '{"text":"联系 person@example.invalid","placeholder":"[[{label}]]"}'
```

响应的 `redacted` 字段会把示例邮箱替换为 `[[email]]`。该能力还支持手机号、证件号、Token 等内置 pattern 与自定义正则。它是本地附属能力，不是自动接管所有 LLM 请求的中间件；`scan`/`redact` 响应中的 `matches` 会包含 localhost 请求内的命中片段，调用方仍需按敏感数据处理。

### 场景 5：密钥轮换

当 API Key 过期或泄露时：

1. 导航到 **Secret Vault** 页面
2. 找到需要轮换的 Secret
3. 点击 **Rotate**
4. 输入新的密钥值
5. 点击 **Rotate** 确认

轮换后 `rotated_at` 时间戳自动更新，旧值被新的 Fernet 密文覆盖。

### 场景 6：测试连通性

验证 Secret 关联的外部服务是否可达：

1. 在 **Secret Vault** 页面点击某 Secret 的 **Test connectivity**
2. 系统向该 Secret 的 `base_url` 发送 HEAD 请求（404/405 时回退为 GET）
3. 显示结果：HTTP 状态码和延迟

或者使用 **Test Center** 页面批量测试所有 Binding。

## 已退役：Identity 文档回填

原「Identity Vault → `[[identity.*]]` 模板替换 → 导出真实身份信息」产品线已正式退役：

- 当前后端没有 `Identity` 数据模型或 `/api/identities` CRUD；
- `template_render` 不再解密或回填身份值，遗留的 `decrypt` 参数仅为 deprecated 兼容参数；
- `/api/render` 与 `/api/export` 如被旧客户端调用，只处理 `[[binding.*]]` / `[[secret_ref.*]]`，输出引用标记而不是任何 Secret 或身份明文；
- 需要发现或涂抹文本 PII 时，请使用仍在维护的 `/api/sanitize/scan|redact`。

## CLI 命令参考

| 命令                | 说明                                     |
| ------------------- | ---------------------------------------- |
| `privportal start`  | 启动 API 服务器（Uvicorn）               |
| `privportal init-db`| 运行 Alembic 迁移到最新版本              |
| `privportal import-demo` | 初始化 Vault + 导入 Demo 数据       |
| `privportal test`   | 运行 pytest（可追加 `-- -k xxx` 参数）   |
| `privportal smoke`  | 运行端到端冒烟测试                       |

## 环境变量

| 变量                         | 默认值                      | 说明                   |
| ---------------------------- | --------------------------- | ---------------------- |
| `PRIVPORTAL_API_HOST`        | `127.0.0.1`                 | 后端监听地址           |
| `PRIVPORTAL_API_PORT`        | `12790`                     | 后端监听端口           |
| `PRIVPORTAL_DATABASE_URL`    | `sqlite:///./privportal.db` | SQLite 数据库路径      |
| `PRIVPORTAL_MASTER_PASSWORD` | —                           | 遗留 CLI 输入；不建议在 Agent/Shell 环境设置 |
| `VITE_API_BASE`              | `http://127.0.0.1:12790`    | 前端连接后端的地址     |

## 项目组织

PolarPrivate 使用**项目 (Project)** 作为顶层组织单位：

- 每个 Project 可以包含独立的 Secret 和 Binding
- 切换项目后，所有页面自动过滤为当前项目的数据
- 选择"Global"查看不属于任何项目的数据
- 删除项目会级联删除其下所有数据

## 安全最佳实践

1. **选择强密码** — Master Password 是加密的唯一依赖，不可恢复。
2. **定期轮换密钥** — 使用 Rotate 功能更新过期或可能泄露的 API Key。
3. **不要手动修改数据库** — Secret 值是 Fernet 密文，手动编辑会导致解密失败。
4. **保护数据库文件** — `privportal.db` 包含加密的密钥，应设置合适的文件权限。
5. **检查日志** — 使用 Logs 页面验证敏感信息是否被正确脱敏。
