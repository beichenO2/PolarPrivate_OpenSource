# PolarPrivate 第一性原理

> 本文回答一个问题：**这个项目为什么存在，以及它为什么长成现在这个样子。**
> 结论先行：PolarPrivate 是 Polarisor 生态的「供给平面」（supply plane）——密钥托管、模型供给、路由、配额与用量口径收敛于此的唯一权威。它存在的理由是让两句话同时为真：**Agent 拥有你的全部能力；Agent 不知道你的任何秘密。**
>
> 依据 2026-08-11 的代码、文档与生态证据写成，证据锚点以 `路径` 标注。

---

## 1. 一句话定义

**localhost 单向阀：能力进，秘密不出。**

调用方送入的只是能力的名字——QCSA 能力码（如 `0001`）、Secret 槽位 key 名（如 `secret.aliyun.dashscope`）；明文凭证只在 `127.0.0.1:12790` 进程内瞬时出现（解密 → 注入 → 丢弃），永不进入 Agent 可达边界。

## 2. 两条公理与一个矛盾

**公理 A：Agent 要有用，必须能行动。**
行动需要两种燃料：第三方凭证（API key / token）与智能（LLM）。没有凭证的 Agent 只能建议，不能执行。

**公理 B：Agent 的信息流不可控。**
上下文会进入云端 LLM、日志、Shell 历史、IDE 配置、git 提交（`README.md`「设计思考」：环境变量会进入 Agent 进程、Shell 历史、IDE 配置和日志栈）。因此必须假设：**任何进入 Agent 可达边界的明文，等价于已经泄露。**

**矛盾：能力需要秘密，安全要求秘密不可见。**

这个矛盾只有一个稳定解：**把「使用秘密」与「看见秘密」分离**——使用权在受控进程内兑现，知情权永不外发。以下所有设计都是这个解的推论。

## 3. 由解推导出的七条设计

### 3.1 进入上下文的只有引用

Secret 的 key 名、QCSA 码都是「能力的名字」而非能力本身。`backend/app/api/v1_gateway.py` 在进程内完成 码 → 上游模型/Binding 解析 → Vault 解密 → 注入 `Authorization`；响应再经模型名改写，把上游真实模型名擦掉、原样回显调用方传入的能力码。调用方全程零密钥接触，也不知道真正服务它的是哪个厂商。

### 3.2 A / B / D 三通道：对协议形态的完备枚举

「使用秘密」在现实协议里只有三种形态，每种一条封闭通道：

| 通道 | 场景 | 机制 | 锚点 |
|---|---|---|---|
| A 类 | 上游只需要带凭证的 Header | 反向代理注入；响应体把疑似明文替换为 `[REDACTED]`；429/5xx 走 fallback 链并对失败源冷却 | `backend/app/api/proxy.py` |
| B 类 | 协议要求用密钥做运算（签名） | 进程内算 HMAC，只返回 headers 字典，密钥不出进程 | `backend/app/api/sign.py`、`backend/app/services/sign_providers/`（weex / feishu-webhook / aliyun-sigv1） |
| D 类 | 第三方 SDK 必须持有明文 | 按 `service_name + 调用方可执行文件 SHA256` 白名单授予，命中与拒绝均写审计日志；AI Agent（Cursor/Codex/Claude Code）被明确排除 | `backend/app/api/d_class.py` |

### 3.3 R9 明文外发禁令：从「不该」到「不能」

R9 删除了 `POST /api/secrets/{secret_id}/reveal` 与 service-token 取值路径，GUI 对 Secret 只写不可读。意义在于把安全原则从「Agent 不应该调 reveal」升级为「系统里不存在 reveal」——**结构上不可能，胜过纪律上不允许**。

### 3.4 信任根必须一人掌控 → 本地化

- Master Password + 16 字节 salt 经 PBKDF2-HMAC-SHA256（480,000 轮）派生密钥，先验 sentinel，再解开加密存储的 fernet keys，组成 MultiFernet **只驻内存**，`lock()` 即丢弃（`backend/app/services/vault.py`）。
- 密文落 SQLite 单文件，离线、零云依赖；MultiFernet 支持密钥轮换，改密时全量 re-encrypt。
- 服务仅监听 localhost，不对外暴露。

不用云端 Secret Manager 的理由是第一性的：**云方案把信任根交给别人，并引入网络暴露面**；本地单用户场景下，Master Password + OS 文件权限（+ 可选的 macOS Keychain 自动解锁）是最小信任面。

### 3.5 QCSA 能力码：把需求表达为能力，把供应商降格为实现

调用方真正需要的不是「某厂商的某模型」，而是某种**能力组合**——QCSA 四维（Quality / Context / Speed / Agentic）+ `V` 视觉前缀 + `L`/`E` 本地与嵌入码（SSOT：`backend/app/core/CAPABILITY_CODES.md`）。把需求编码为能力向量之后：

- 路由、负载均衡（跨订阅加权引流）、降级链、冷却重试收敛在 `backend/app/core/model_routing.py`；
- 并发 Semaphore + RPM 令牌桶收敛在 `backend/app/core/rate_limiter.py`；
- 用量与计费口径收敛在代理这一个采集点（生态计费模型以「经代理转发的请求」为一次消费）。

换供应商时，十几个消费方一行配置不用改，只改代理一处。这是依赖倒置原则应用在模型供应上。

### 3.6 失败语义的不对称：fail-closed

Vault 锁定时，全生态 LLM 调用宁可失败，也不存在降级绕过；对比同生态的 PolarBudget 不可用时允许标注 `budget_unavailable` 继续干活。**可恢复的失败允许降级，不可逆的失败（泄密）禁止绕过。** 这条不对称是整个 Polarisor 生态里最深思熟虑的设计之一。

### 3.7 信任先于能力：生态依赖图的最底层

`polaris.json` 声明 `depends_on: []`、`depended_by: [SOTAgent, PolarCopilot, KnowLever, digist, PolarClaw, tqsdk]`；实测生态内 15 个目录在代码中引用 `:12790`。生态协议（Agent_core Proto-N）规定「模型选择权完全归 LLM Proxy」，调用方三不原则：不传模型名、不配 Base URL、不持 API Key。**Agent 自治的前提，是先把不可逆风险从 Agent 手里拿走。**

## 4. 演化：从隐私门户到供给平面

### 4.1 起点：PrivPortal 双域构想

最初定位（`CLAUDE.md` 中的 GSD 项目快照）是「本地隐私代理与脱敏门户」：文档类 identity（姓名、邮箱、学号）的脱敏与导出回填，加上运行时 secret 的加密注入——「隐私」被当作一个统一问题。

### 4.2 收敛：R9 时代，identity 线事实退役

代码证据显示 identity/文档脱敏这条产品线已经退役：

- `backend/app/db/models.py` 中已无 `Identity` 模型（仅 `alembic/versions/001、002、007` 残留建表与加列痕迹）；
- `/api/sanitize/mappings` 只返回 secret key 清单，不含 identity、不含任何 value；
- SDK 脱敏中间件（`sdk/src/privportal_sdk/middleware.py`、`sdk-ts/src/middleware.ts`）因拿不到 identities 数据而退化为恒等函数；
- `backend/app/services/template_render.py` 的 `decrypt` 参数已标注 deprecated，「导出回填真实值」不复存在；
- 仍然存活的是**无状态 PII 正则扫描/涂抹**（`backend/app/services/pii_scanner.py` + `/api/sanitize/scan|redact`，支持自定义 pattern），被 PolarClaw 实际消费。

同期 R9 把保险库从「可读」改成「只写」，A/B/D 三通道成型——系统重心用脚投票地移向了高频、高价值的 LLM 与密钥供给。

### 4.3 现在：供给质量管理

近期工作（lant.top 中转线路别名、Nebula 模型族、跨订阅加权引流、Test Center 只展示已配置 Binding、共享 HTTP 客户端按目标主机选择代理或直连）本质是**模型供应链管理**：多源采购、按线路健康度调度、测控只看已采购渠道。

### 4.4 git 佐证

837 个非 merge 提交中，721 个是每小时自动 vault backup、102 个是设备间 auto-sync，真实开发提交仅 14 个；可见历史的根提交（2026-06-11 open source release）就是一次成熟系统快照。**项目记忆主要存在于文档而非提交史——这正是本文需要存在的原因。**

## 5. 自我描述与实现的差距（2026-08-11 收口）

| # | 叙事债 | 2026-08-11 状态 |
|---|---|---|
| 1 | `CLAUDE.md` 的项目定义停留在 PrivPortal 双域时代 | 已改为供给平面权威口径 |
| 2 | `capabilities.json`（v0.5.0）未声明 `/v1` 网关主干 | 已升级声明 chat / embeddings / models |
| 3 | API 与架构文档把 R9 删除的 Reveal 写成可用能力 | 已统一标记为永久移除 |
| 4 | 安全文档把 fernet keys 明文存储当作现状 | 已按 schema v2 wrapped keys 与真实信任根修正 |
| 5 | SDK Identity/脱敏中间件仍有实现与测试残留 | 产品口径已宣布退役；代码清理由独立单元执行 |

## 6. 定位决策记录（2026-08-11）

**D1 — 定位收敛。** PolarPrivate 定义为 Polarisor 生态的供给平面（supply plane）：**本地密钥保险库 + 统一 LLM Proxy**，目标是「让 Agent 拥有全部能力，而不知道任何秘密」。PII 正则 scan/redact 作为附属能力保留；文档 Identity 脱敏与导出回填产品线正式退役，不再恢复双域叙事。

**D2 — 开源拓扑。** 沿用并加固单向发布链：**PolarPrivate 私仓真源 → sanitize 管道 → PolarPrivate_OpenSource 公镜像**。私仓承载真实运行配置与加密备份，公镜像只接收净化后的可发布内容，不改为 public-first 单仓。

**D3 — staging 位置。** sanitize staging 迁至 `~/Polarisor/_opensource`，与产品仓分离。该迁移动作由其他单元执行；本记录只确定目标位置与口径。

同步状态：`README.md` 与 `CLAUDE.md` 已于同日切换到上述定位；API、架构、安全与使用文档同步区分主产品线、PII 附属能力和已退役 Identity 产品线。

## 附：方法与证据

本文由四路并行调查综合而成：代码库架构盘点、文档意图与叙事漂移分析、Polarisor 生态定位考察、git 演化史重建；关键事实经异模型交叉核查。主要证据锚点：`backend/app/api/`（v1_gateway / proxy / sign / d_class / sanitize）、`backend/app/core/`（model_routing / rate_limiter / CAPABILITY_CODES.md）、`backend/app/services/`（vault / pii_scanner / template_render）、`backend/app/db/models.py`、`capabilities.json`、`polaris.json`、`README.md`、`CLAUDE.md`、`docs/security-model.md`。
