# PolarPrivate

**[Polarisor](https://github.com/beichenO2/Polarisor) 生态的供给平面（supply plane）：本地密钥保险库 + 统一 LLM Proxy。** Agent 与脚本只传 QCSA 能力码（如 `0001`、`V0000`），API Key 在 PolarPrivate 进程内解密注入。目标只有一句：**让 Agent 拥有全部能力，而不知道任何秘密。**

`/api/sanitize/scan|redact` 的无状态 PII 正则扫描/涂抹作为附属能力保留；原「文档 Identity 脱敏 + 导出回填」产品线已正式退役。

---

## Agent 接入

独立使用者把 QCSA 能力码发给 `http://127.0.0.1:12790/v1`，不要把 API Key 放进 Agent 工作区。用法见 [`docs/usage.md`](docs/usage.md)。

Polarisor 生态内另有本机 Skill（不随公开仓发布）。

## 安装

### Polarisor 生态（推荐）

```bash
git clone https://github.com/beichenO2/Polarisor.git
cd Polarisor
./install.sh infra    # 安装 PolarPrivate 及 SOTAgent / PolarPort 等配套
```

生态内启动后端请用 **`privportal start`**（经 PolarProcess 管理生命周期）；该命令在独立环境**不可用**。

### 独立安装（公开仓 · 开箱即用）

```bash
git clone https://github.com/beichenO2/PolarPrivate_OpenSource.git
cd PolarPrivate_OpenSource

# 方式 A（推荐）：Docker Compose — 单端口 API + Web UI
docker compose up --build
# → http://127.0.0.1:12790

# 方式 B：本地 uv（不依赖 PolarProcess）
cd backend && uv sync && privportal init-db && privportal serve
# → http://127.0.0.1:12790（若存在 frontend/dist 则同端口托管 UI）
```

可选 demo 数据（明显假口令，勿用于生产）：

```bash
PRIVPORTAL_MASTER_PASSWORD=demo-only-not-a-secret privportal import-demo
```

威胁模型见根目录 [`SECURITY.md`](SECURITY.md)。

| 路径 | 地址 | 说明 |
|------|------|------|
| Docker / `privportal serve` | `http://127.0.0.1:12790` | API + 代理 + 内置 Web UI（同端口） |
| 生态内 Vite dev | `http://localhost:12795` | 仅 Polarisor 开发态；生产由 PolarProcess 管 12790 |

---

## 设计思考

### 为什么用本地代理，而不是 `.env` / 环境变量？

环境变量会进入 Agent 进程、Shell 历史、IDE 配置和日志栈。PolarPrivate 把密钥留在 **127.0.0.1 保险库**内，调用方只需指向 `http://127.0.0.1:12790/v1`，**零密钥接触**。

### 为什么用 QCSA 能力码，而不是直接传模型名？

调用方传 `0001`（Agent 均衡）或 `V0000`（默认视觉），不传 `xopdeepseekv4flash` / `qwen3.7-plus`。路由策略（上游模型、Binding、负载均衡、Fallback）集中在服务端 **14 条 QCSA 规则** + **4 条降级链**，换供应商时 Agent 配置不用改。

### 为什么用 SQLite + Fernet 本地保险库，而不是云端 Secret Manager？

PolarPrivate 的设计前提是 **仅 localhost 运行、不对外暴露**。SQLite 单文件 + PBKDF2（480,000 迭代）+ Fernet（AES-128-CBC + HMAC-SHA256）满足离线、零云依赖、Master Password 一人掌控；MultiFernet 支持密钥轮换。

### 为什么禁止 Reveal API，改用 A/B/D 三类封闭通道？

R9「明文外发禁令」删除了 `/api/secrets/{id}/reveal` 与 service-token 路径。Secret 只经三条路流动：**A 类**反向代理注入 Header、**B 类** HMAC 签名（3 个 provider）、**D 类** SHA256 白名单受控 grant — GUI 只写不可读。

---

## 核心亮点

| 维度 | 数据 |
|------|------|
| **QCSA 能力码** | 14 个云端码（文本 9 + 视觉 5）+ 本地嵌入 `L0000` / `E000` |
| **上游 LLM 通道** | 4 个 Binding：`llm.glm51.enterprise`、`llm.aliyun.codingplan`、`llm.aliyun.dashscope`、`llm.minimax` |
| **上游模型槽位** | 8 个真实模型 ID（GLM-5.1、Kimi-K2.6、DS V4 Flash/Pro、MiniMax-M3 等） |
| **负载均衡** | DS V4 Flash/Pro 跨讯飞 + 阿里云 **80:20** 权重；429/5xx 自动 Fallback（4 条链） |
| **并发保护** | 压测标定：enterprise 并发 **10**、codingplan **8**、minimax **12**、dashscope **50** |
| **加密** | PBKDF2-HMAC-SHA256 **480,000** 次迭代 + Fernet；Secret 密文存 SQLite |
| **测试** | **327** 个 pytest 用例；**14** 版 Alembic 迁移 |
| **Web UI** | **11** 个管理页面：Dashboard、Secrets、Projects、Bindings、Test Center、Logs 等 |
| **SDK** | Python `privportal-sdk` + TypeScript `sdk-ts` 遗留客户端；Identity 查询与脱敏中间件已退役，新接入优先使用 OpenAI 兼容 `/v1` |

---

## 架构

```
PolarPrivate/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口 + 路由注册
│   │   ├── cli.py                  # privportal CLI（start / init-db / smoke）
│   │   ├── core/
│   │   │   ├── model_routing.py    # QCSA 码 → 上游模型 + Binding
│   │   │   ├── model_catalog.py    # GET /v1/models 静态目录
│   │   │   ├── rate_limiter.py     # 并发 Semaphore + RPM TokenBucket
│   │   │   └── CAPABILITY_CODES.md # 能力码 SSOT 文档
│   │   ├── api/
│   │   │   ├── v1_gateway.py       # /v1/chat/completions 统一网关
│   │   │   ├── proxy.py            # /proxy/{service}/{path} 反向代理
│   │   │   ├── sign.py             # /sign/{provider}/{action} B 类签名
│   │   │   ├── vault_routes.py     # 保险库解锁 / 改密
│   │   │   └── …                   # secrets / bindings / sanitize / test_center
│   │   ├── services/
│   │   │   ├── vault.py            # PBKDF2 + Fernet 加密中枢
│   │   │   └── sign_providers/     # weex / feishu-webhook / aliyun-sigv1
│   │   └── db/models.py            # Project / Secret / Binding / AuditLog
│   ├── alembic/versions/           # 14 版数据库迁移
│   └── tests/                      # 327 个 pytest 用例
├── frontend/src/                   # Web UI（Dashboard · Secrets · Bindings · Test Center 等）
│   ├── pages/                      # Dashboard / Secrets / Bindings / Logs …
│   └── components/                 # OnboardingWizard / UnlockModal / Sidebar
├── sdk/                            # Python SDK
├── sdk-ts/                         # TypeScript SDK
├── docs/                           # architecture / security-model / api-reference
├── capabilities.json               # 能力发现声明
```

**请求路径（LLM 调用）**

```
Agent / Cursor / OpenAI SDK
    │  model: "0001"  (QCSA 能力码)
    ▼
POST /v1/chat/completions  @ 127.0.0.1:12790
    │  resolve → xopdeepseekv4flash @ llm.glm51.enterprise
    │  Vault 解密 Secret → 注入 Authorization
    ▼
上游 API（讯飞 / 阿里云 / MiniMax）
    │  响应 model 字段回显 "0001"（不回显真实模型名）
    ▼
Agent 收到结果 — 全程未接触 API Key
```

---

## 快速开始

### 独立用户（≤5 步）

1. `git clone https://github.com/beichenO2/PolarPrivate_OpenSource.git && cd PolarPrivate_OpenSource`
2. `docker compose up --build`
3. 浏览器打开 `http://127.0.0.1:12790`
4. 按 Onboarding 设置 **Master Password**
5. （可选）`PRIVPORTAL_MASTER_PASSWORD=demo-only-not-a-secret` 下在容器内或本地执行 `privportal import-demo`

不用 Docker 时：`cd backend && uv sync && privportal init-db && privportal serve`（**不要**使用 `privportal start`）。

### Polarisor 生态内

```bash
cd backend
privportal init-db      # 首次
privportal start        # 经 PolarProcess → http://127.0.0.1:12790

cd frontend
npm run dev             # → http://localhost:12795
```

浏览器打开 Web UI，在 Secrets 页录入 API Key，在 Bindings 页创建 `llm.*` 绑定。

**OpenAI 兼容调用**（任意 SDK 均可，`api_key` 被忽略）：

```bash
curl -X POST http://127.0.0.1:12790/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "0001",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**能力码速查**（完整表见 [`backend/app/core/CAPABILITY_CODES.md`](backend/app/core/CAPABILITY_CODES.md)）：

| 码 | 场景 |
|----|------|
| `0000` | 默认均衡对话 → GLM-5.1 |
| `0001` | Agent 杂活 / tool call → DS V4 Flash |
| `0010` | 快速 + 超长上下文 |
| `V0000` | 默认视觉 → qwen3.7-plus |
| `V1000` | 单图旗舰 → Kimi-K2.6 |

---

## 生态依赖

| 项目 | 角色 | 是否必须 |
|------|------|----------|
| — | 独立运行即可 | ✅ 可以 |
| [SOTAgent](https://github.com/beichenO2/SOTAgent) | 进程守护、自动启动、PeerSync 多设备同步 | 推荐 |
| [PolarPort](https://github.com/beichenO2/PolarPort) | 端口分配与管理（12790 / 12795） | 推荐 |
| [Agent_core](https://github.com/beichenO2/Agent_core) | 安全协议与 Polarisor 集成规范 | 推荐 |
| [PolarCopilot](https://github.com/beichenO2/PolarCopilot) | Agent 默认经 PolarPrivate 路由 LLM | 生态内推荐 |
| [KnowLever](https://github.com/beichenO2/KnowLever) | 超长 Prompt 自动压缩（>120K tokens） | 可选 |

**被依赖方**（生态内）：PolarCopilot、KnowLever、PolarClaw、digist、tqsdk 等。

---

## 测试

**QCSA 路由冒烟测试** — 自动遍历所有 QCSA 能力码，验证 PolarPrivate 路由是否正常：

```bash
bash scripts/test-qcsa-routing.sh                     # 默认 http://127.0.0.1:12790
bash scripts/test-qcsa-routing.sh http://host:port     # 自定义端口
PP_MAX_TOKENS=5 bash scripts/test-qcsa-routing.sh      # 控制 max_tokens
```

区分三种结果：
- `✓` — 路由成功且上游返回有效 response
- `⚡ upstream` — 路由正确（非 422），上游拒绝（如视觉模型需真实图片、Ollama 未启动）
- `✗ ROUTING FAIL` — 422 UNKNOWN_MODEL，说明 `CAPABILITY_CLOUD_MAP` 缺失该码

---

## 文档

- [系统架构](docs/architecture.md)
- [安全模型](docs/security-model.md)
- [API 参考](docs/api-reference.md)
- [使用指南](docs/usage.md)
- [能力码 SSOT](backend/app/core/CAPABILITY_CODES.md)

---

## License

MIT — Copyright (c) Polarisor Contributors
