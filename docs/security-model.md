# PolarPrivate 安全模型

## 首要原则：明文外发禁令

PolarPrivate 的安全设计围绕一个首要承诺：

> **Secret 明文永远不进入 Agent 可达边界。**

具体约束：

1. **强承诺** — 没有任何 API 端点将 Secret 明文作为 HTTP 响应体返回。`/api/secrets/{id}/reveal` 已永久删除，`/api/vault/service-session` 已永久删除，`service_tokens` 表已通过 alembic migration 011 删除。
2. **弱承诺** — Secret 明文仅在以下三类封闭路径中流动：
   - **A 类（反向代理）** — `/proxy/{service_name}/{path}` — Secret 在代理内部注入 auth header，明文不出现在请求或响应中。
   - **B 类（HMAC 签名）** — `/sign/{provider}/{action}` — Secret 在签名运算中使用，仅返回签名后的 header dict。
   - **D 类（受控信道）** — `/api/d-class/grant` — 唯一的明文授予路径，受 SHA256 白名单约束，仅限第三方 SDK 场景（如 tqsdk 期货）。Agent 进程 hash 不在白名单中。
3. **GUI 只写不可读** — 前端 SecretsPage 已移除所有 reveal/hide 交互，编辑时重新输入新明文。

PII 正则扫描/涂抹是独立的附属能力：`/api/sanitize/scan|redact` 只处理调用方提交的文本，不建立 Identity Vault，也不承诺自动拦截所有发往 LLM 的内容。`scan` 响应会在 localhost 内返回命中片段，不能与上述 Secret 明文外发禁令混为一谈。

## 核心安全约束

1. **Secret 不明文存储** — 所有 Secret 在 SQLite 中以 Fernet 密文形式存储。
2. **Secret 不出现在日志中** — structlog 处理器自动脱敏所有已注册的密钥子串。
3. **Secret 不暴露给 Agent 工作区** — Agent 通过代理访问 API，密钥在代理层注入，Agent 永远看不到明文。

## 加密体系

### 主密码派生 (KDF)

```
用户输入 Master Password
    │
    ▼
PBKDF2-HMAC-SHA256
    ├── iterations: 480,000
    ├── salt: 16 字节随机数 (os.urandom)
    └── output: 32 字节密钥 → base64 编码为 Fernet key
```

- **算法**: `cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC`
- **迭代次数**: 480,000（OWASP 2023 推荐的 SHA-256 最低标准）
- **Salt**: 每次创建数据库或更换密码时随机生成，存储在 `db_metadata.salt`

### Fernet 对称加密

所有 Secret 值使用 **Fernet** 加密（基于 AES-128-CBC + HMAC-SHA256）：

| 组件               | 说明                                              |
| ------------------ | ------------------------------------------------- |
| **Fernet**         | 单密钥加密/解密，提供认证加密（ciphertext tampering 可检测）|
| **MultiFernet**    | 多密钥容器，支持密钥轮换（用第一个密钥加密，用任一密钥解密）|
| **Sentinel**       | 固定明文 `PRIVPORTAL_V1_UNLOCK_SENTINEL` 的密文，用于验证密码正确性 |

### 密钥存储结构

`db_metadata` 表（单行，`id=1`）：

| 字段                  | 类型     | 说明                                     |
| --------------------- | -------- | ---------------------------------------- |
| `salt`                | BLOB     | PBKDF2 盐值                              |
| `sentinel_ciphertext` | TEXT     | Sentinel 明文的 Fernet 加密结果           |
| `schema_version`      | INTEGER  | Schema 版本号                             |
| `fernet_keys_json`    | TEXT     | schema v2：由主密码派生密钥加密存储的 wrapped key payload |
| `auto_unlock_token`   | TEXT     | 启用自动解锁时，由设备密钥加密的 Master Password token |

schema v2 创建数据库时，先用 `Master Password + salt` 派生 Fernet key，再用该 key 加密包含 MultiFernet keys 的 JSON，密文写入 `fernet_keys_json`。解锁时必须先通过 sentinel 验证密码，才能解开 wrapped keys。`schema_version < 2` 的旧库仍保留明文 JSON 读取分支，仅用于向后兼容，不代表当前存储格式。

### 信任根

当前信任根由三部分组成：

1. **Master Password** — 解锁 sentinel 与 wrapped Fernet keys 的根凭证。
2. **操作系统文件权限** — 保护 SQLite 密文、salt 与自动解锁 token 不被任意进程篡改或复制。
3. **macOS Keychain（启用自动解锁时）** — 保存设备密钥；SQLite 中只有由该设备密钥加密的 `auto_unlock_token`。非 macOS 平台回退到权限为 `0600` 的设备密钥文件。

因此，仅取得 schema v2 SQLite 文件不足以直接解密 Secret；攻击者还需要 Master Password，或在自动解锁启用时同时突破对应设备的 Keychain/设备密钥保护。

### 密码更换流程

```
验证旧密码 (解密 sentinel)
    │
    ▼
解密所有 Secret 行 → 暂存明文
    │
    ▼
生成新 salt + 新 Fernet key
    │
    ▼
更新 db_metadata (salt, sentinel, wrapped fernet_keys_json)
    │
    ▼
用新密钥重新加密所有 Secret
    │
    ▼
session.flush() 验证所有 DB 变更
    │
    ▼
切换内存中的 MultiFernet 为新密钥
    │
    ▼
清除旧密码的脱敏注册 → 注册新密码
```

安全保证：内存中的 MultiFernet 只在 `session.flush()` 成功后才替换。如果 DB 写入失败，session 回滚，下次 unlock 会从 DB 状态重新派生密钥。

## Vault 生命周期

### 状态机

```
                 create_new_database()
    [不存在] ──────────────────────────→ [已初始化/锁定]
                                              │
                                    unlock(password)
                                              │
                                              ▼
                                        [已解锁]
                                         │      │
                          change_master_password()  lock()
                                         │      │
                                         ▼      ▼
                                   [已解锁/新密钥] [锁定]
```

- **锁定状态**: `VaultService._unlocked = False`，所有加密/解密操作抛出 `RuntimeError("vault is locked")`。
- **解锁状态**: `VaultService._multi_fernet` 持有有效的 MultiFernet 实例。
- **主动锁定**: `lock()` 方法丢弃内存中的密钥材料，回到锁定状态。
- **进程级**: Vault 状态绑定到 FastAPI `app.state.vault`，进程重启后需要重新解锁。

### HTTP 访问控制

- `GET /api/vault/status` — 返回 `{"locked": true/false}`，无鉴权。
- `POST /api/vault/unlock` — 输入 master_password 解锁 Vault。
  - **暴力破解保护**: 连续 10 次失败后锁定 60 秒，返回 **HTTP 429 Too Many Requests**（错误码 `RATE_LIMITED`）。成功解锁后计数器和锁定时间均归零。计数器使用线程锁保护，为进程级内存状态。
- 需要解锁的端点通过 `require_unlocked_vault` 依赖保护，未解锁返回 **HTTP 423 Locked**:
  - Secret 创建/更新/rotate
  - 代理转发
  - Onboarding 导入 Demo 数据

R9 已永久移除 Secret reveal 端点；它不属于任何“需要解锁即可使用”的 API 集合。

## 日志脱敏

### 脱敏处理器

`logging_config.py` 实现两层脱敏：

#### 1. 注册密钥脱敏

```python
_REDACTION_SUBSTRINGS: set[str]  # 全局注册表
```

- 当 Vault 解锁时，`register_secrets_for_redaction([master_password])` 将密码注册。
- `redact_processor` 递归遍历 structlog 事件字典所有叶子节点（str、bytes、嵌套 dict/list/tuple），将匹配的子串替换为 `[REDACTED]`。bytes 值会尝试 UTF-8 解码后脱敏再编码回 bytes。
- 多个密钥按长度降序替换，避免短密钥是长密钥前缀时的部分泄露。

#### 2. API Key 模式匹配

```python
_SK_LIKE_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]{10,}")
```

- `sanitize_user_facing_string()` 在注册脱敏之外，额外匹配 OpenAI 风格的 `sk-*` API Key。
- 用于测试中心等面向用户的输出，确保即使密钥未注册也不会泄露。

### 日志不记录的内容

- **代理请求/响应体** — `_forward_streaming()` 注释标注 "no request/response body logging (D-70)"。
- **Secret 明文** — R9 已移除明文读取响应；写入、轮换和代理注入路径均不得记录 payload。
- **上游响应内容** — 代理日志仅记录元数据（service_name、method、upstream_host），不记录 body。

## 网络安全

### 仅本地运行

- 后端监听 `127.0.0.1:12790`（默认）。
- CORS 仅允许 `http://127.0.0.1:12795` 和 `http://localhost:12795`。
- 无 TLS（本地 loopback 不需要）。
- 无外部访问端口暴露。

### 代理安全

- 代理路由 (`/proxy/{service_name}/{path}`) 通过 Binding 映射确定上游目标，不接受任意 URL。
- Secret 解密后的明文仅在 `proxy_request()` 函数作用域内存在，不写入日志或响应。
- 上游响应中的 `Authorization` header 被过滤，不回传给客户端。
- 如果 Secret 被禁用 (`enabled=false`)，代理返回 **HTTP 403**。
- **上游响应体脱敏** — `_sanitize_upstream_body()` 在返回上游错误响应前，将响应体中出现的明文 Secret 替换为 `[REDACTED]`，防止上游 echo 回 API Key。
- **异常信息脱敏** — `_sanitize_error_detail()` 从 httpx 异常消息中移除可能包含的 Secret 材料。

## 审计日志覆盖

所有安全相关操作通过 `append_audit_log()` 记录到 `audit_log` 表，支持事后审计和异常检测。

| Action                  | 触发时机           | Detail 内容           |
| ----------------------- | ------------------ | --------------------- |
| `vault.unlock`          | 成功解锁 Vault     | —                     |
| `vault.change_password` | 更改 Master Password | —                   |
| `project.create`        | 创建项目           | `name=<项目名>`       |
| `project.delete`        | 删除项目           | `name=<项目名>`       |
| `secret.create`         | 创建 Secret        | `key=<Secret key>`    |
| `secret.rotate`         | 轮换 Secret        | `key=<Secret key>`    |
| `secret.delete`         | 删除 Secret        | `key=<Secret key>`    |

> **注意**: detail 字段仅记录 key 名称，不记录 Secret 明文值。此约束由 `test_security_audit_log.py` 中的回归测试保护，确保审计日志永远不会泄露 secret 值或 master password。

## 数据保护层次

| 层次       | 保护机制                                         | 攻击场景                        |
| ---------- | ------------------------------------------------ | ------------------------------- |
| 磁盘       | Fernet 加密 Secret 值                            | 数据库文件被复制                |
| 内存       | 明文仅在加密/解密/代理转发时短暂存在             | 内存转储                        |
| 日志       | structlog 脱敏处理器 + sk-* 模式匹配             | 日志文件泄露                    |
| 网络       | 仅 localhost、CORS 限制                          | 远程访问尝试                    |
| API        | Vault 锁定状态保护加密端点                       | 未授权 API 调用                 |
| 代理       | 不记录请求/响应体、过滤 Authorization header     | 代理日志分析                    |
| 导出       | 模板渲染不解密 Secret（渲染为 `[secret_ref:...]`） | 导出文件包含密钥                |

## 已知限制

1. **本地用户模型** — 支持 admin/user 角色与浏览器 session，但不是面向公网的多租户认证系统。
2. **无闲置自动锁定** — Vault 不会按空闲时长自动锁定；管理员可主动锁定，进程终止也会清除内存密钥。
3. **Master Password 不明文存储** — 忘记密码无法恢复；启用自动解锁时，SQLite 仅保存设备密钥加密后的 token，设备密钥由 macOS Keychain（或非 macOS 的 `0600` 文件）保护。
4. **SQLite 文件保护** — 依赖操作系统文件权限，PolarPrivate 不加密整个数据库文件。
5. **无审计日志加密** — `audit_log` 表中的 `detail` 字段为明文（但不应包含 Secret 值）。
6. **旧 schema 兼容边界** — `schema_version < 2` 的历史数据库仍可从未包装的 `fernet_keys_json` 读取 keys；schema v2 已改为加密存储 wrapped keys。旧库应通过改密/迁移升级，不能套用 v2 的静态文件防护结论。
