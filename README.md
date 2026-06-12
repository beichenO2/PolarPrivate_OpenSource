# PolarPrivate

**本地 LLM 代理 + 密钥保险库** — Agent 与脚本只传 QCSA 能力码（如 `0001`、`V0000`），API Key 在 PolarPrivate 进程内解密注入，**明文永不进入 Agent 工作区**。[Polarisor](https://github.com/beichenO2/Polarisor) 生态的安全基础设施。

---

## 安装

### Polarisor 生态（推荐）

```bash
git clone https://github.com/beichenO2/Polarisor.git
cd Polarisor
./install.sh infra    # 安装 PolarPrivate 及 SOTAgent / PolarPort 等配套
```

### 独立安装

```bash
git clone https://github.com/beichenO2/PolarPrivate.git
cd PolarPrivate

# 后端
cd backend && uv sync && privportal init-db

# 前端（新终端）
cd frontend && npm install
```

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API + 代理 | `http://127.0.0.1:12790` | FastAPI，仅监听 localhost |
| 前端 Web UI | `http://localhost:5170` | Vite dev server |

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
| **SDK** | Python `privportal-sdk` + TypeScript `sdk-ts`（Identity 查询 + 脱敏中间件） |

---

## 页面预览

![仪表盘 — 概览统计与最近操作](screenshots/pp-01-dashboard.png)

![密钥管理 — 加密存储，只写不可读](screenshots/pp-02-secrets.png)

![项目管理 — 多项目隔离](screenshots/pp-03-projects.png)

![绑定关系 — 服务名 → Secret 映射](screenshots/pp-04-bindings.png)

![测试中心 — API 连通性与 Binding 探针](screenshots/pp-05-test-center.png)

![审计日志 — 脱敏后的操作记录](screenshots/pp-06-logs.png)

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
├── frontend/src/
│   ├── pages/                      # Dashboard / Secrets / Bindings / Logs …
│   └── components/                 # OnboardingWizard / UnlockModal / Sidebar
├── sdk/                            # Python SDK
├── sdk-ts/                         # TypeScript SDK
├── docs/                           # architecture / security-model / api-reference
├── capabilities.json               # SOTAgent 能力发现声明
├── polaris.json                    # Polarisor 生态 SSOT
└── screenshots/                    # Web UI 截图
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

```bash
# 1. 启动后端
cd backend
privportal init-db      # 首次
privportal start        # → http://127.0.0.1:12790

# 2. 启动前端
cd frontend
npm run dev             # → http://localhost:5170
```

浏览器打开 `http://localhost:5170`，按 Onboarding 向导设置 **Master Password**，在 Secrets 页录入 API Key，在 Bindings 页创建 `llm.*` 绑定。

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
| [PolarPort](https://github.com/beichenO2/PolarPort) | 端口分配与管理（12790 / 5170） | 推荐 |
| [Agent_core](https://github.com/beichenO2/Agent_core) | 安全协议与 Polarisor 集成规范 | 推荐 |
| [PolarCopilot](https://github.com/beichenO2/PolarCopilot) | Agent 默认经 PolarPrivate 路由 LLM | 生态内推荐 |
| [KnowLever](https://github.com/beichenO2/KnowLever) | 超长 Prompt 自动压缩（>120K tokens） | 可选 |

**被依赖方**（来自 `polaris.json`）：PolarCopilot、KnowLever、PolarClaw、digist、tqsdk 等。

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
