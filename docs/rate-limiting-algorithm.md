# PolarPrivate 限速与跨订阅路由 — 算法详解

> 适用于 `/v1/chat/completions` 统一 LLM 网关。
> 源码：`backend/app/core/rate_limiter.py`、`backend/app/core/model_routing.py`、`backend/app/api/v1_gateway.py`

## 关键决策（2026-06 · 软性跨订阅引流）

**限速绝不向调用方返回错误。** 限速只做两件事：

1. **本地软节流**——不预先把自己限速到订阅真实额度以下；只保留一个宽松的
   并发信号量（连接安全，避免对单一供应商瞬间开过多连接），**不做 RPM 自节流**。
2. **跨订阅引流**——同一档位由多个已付费订阅（讯飞 `glm51` / MiniMax /
   阿里 `codingplan`）共同承载；按权重分摊；某订阅被上游 429 后短暂"冷却"并被
   路由跳过，新流量自动引到**没限流的订阅**。

**上游限速（429）**：等待（尊重 `Retry-After`）后重试；同订阅重试耗尽再切到
未冷却的备选订阅；只有当所有订阅都真不可用时才返回错误——此时属上游故障，
不是本地限速。

> ⚠️ 本方案彻底**替换**了早期实现（本地连续补充令牌桶 + acquire 超时拒绝 +
> AIMD 自适应降速 + BurstAbsorber 排队后拒绝 + Layer 4 直接回 429）。那套设计会
> 把自身限速在订阅额度以下、让其它已付费订阅闲置，并在饱和时**直接对调用方报
> 429**，等于"自己限自己"。该实现已废弃，相关机制不再使用。

## 设计动机

PolarPrivate 是 Polarisor 生态中所有 LLM 请求的唯一网关。多个程序（PolarClaw、
PolarUI、AutoOffice、KnowLever、digist 等）同时通过它请求上游 API。生态拥有
**多个独立计费的订阅**，每个订阅各有并发/RPM 限制：

| 订阅 service | 可服务模型 |
|---|---|
| `llm.glm51.enterprise`（讯飞 MaaS 企业版） | GLM-5.1 / DeepSeek V4 Flash·Pro / Kimi-K2.6 |
| `llm.minimax` | MiniMax-M3 / M3-Thinking |
| `llm.aliyun.codingplan` | Qwen3.7-Plus |
| `llm.aliyun.dashscope` | Qwen3-VL-Flash（视觉） |

核心思路：与其在单一订阅上自我节流，不如把负载**分摊/引流**到多个订阅，并在
某个订阅被上游限流时把流量切到其它订阅。中心化网关天然适合做这种全局调度。

## 系统分层（现行）

```
请求到达 (/v1/chat/completions, X-Client-Id: polarclaw)
│
├─ ① 路由选源：resolve_model_and_service → get_load_balance_group
│     按权重在多个订阅间选一个「未冷却」的 (service, model)
│
├─ ② FairScheduler：接近满载(≥80%)时低优先级客户端略让行（只延迟，不拒绝）
│
├─ ③ ServiceBudget.acquire()：只等并发信号量（无 RPM 节流、无超时拒绝）
│
├─ ④ 转发上游
│     成功            → 返回（流式/非流式）
│     429/5xx 等瞬时错误 → 等待重试(同订阅) → 切换未冷却订阅 → 仍不行才报错
│
└─ ⑤ release：429 → 设置该订阅短暂冷却（路由信号）+ 唤醒等待者
```

## 本地节流：只有并发信号量

`ServiceBudget.acquire()` 只 `await semaphore.acquire()`——拿到并发位子即放行：

- **没有 RPM 令牌桶阻塞**：不再按配置 rpm 限制自己的发包速率（那会卡在订阅真实
  额度以下，并让其它订阅闲置）。
- **没有 acquire 超时**：不会因为"暂时没位子"对调用方返回 429。并发位子是
  *连接安全上限*，设得很宽松。
- **没有 AIMD 自适应降速**：`maybe_adjust()` 现为 no-op——遇到 429 不降自己的速，
  而是冷却该订阅并把流量引到别的订阅。

> 并发信号量属「连接管理」（避免对单一供应商瞬间开上千连接），不是「限速」。

## 跨订阅软路由（核心）

`model_routing.LOAD_BALANCE_GROUPS` 为每个**文本档位**定义跨订阅候选
`(service, model, weight)`，由 `select_service_by_weight(skip_services=cooling)`
按权重选择并跳过冷却中的订阅。现行权重：

| 档位（caller code） | 候选：service / model / weight |
|---|---|
| 均衡·旗舰对话 `0000` `1000` | glm51 GLM-5.1 **60** · minimax M3 **20** · codingplan Qwen3.7 **20** |
| Agent·快速 `0001` `0010` `0011` | glm51 DS-Flash **70** · codingplan Qwen3.7 **20** · minimax M3 **10** |
| Agent旗舰·长文 `0100` `0101` `1001` | glm51 DS-Pro **75** · codingplan Qwen3.7 **25** |
| 快速长文 `0110` | minimax M3 **70** · glm51 DS-Flash **30** |
| 深度推理 `1110` | minimax M3-Thinking **70** · glm51 DS-Pro **30** |

- **视觉档（`V*`）保持单源**：各订阅图片能力/张数限制差异大，blending 会把图片
  请求错路由到非视觉模型，故不参与负载组。
- 响应对调用方按 opaque capability code 回显，跨订阅切换对调用方**透明**。

## 冷却 = 路由信号（不是等待/拒绝）

上游 429 → `set_cooldown(Retry-After 或默认 5s)`。冷却期间该订阅被
`select_service_by_weight` 跳过，新流量引到未冷却订阅。冷却**只影响路由选择**，
不阻塞 `acquire`、不拒绝调用方。

## 上游 429 / 5xx 处理（网关 v1_gateway）

```
同订阅：按 Retry-After（封顶 30s）/退避 等待重试，最多几次
  ↓ 仍失败
负载组内切到「未冷却」的其它订阅重试（= 引流到没限流的订阅）
  ↓ 仍失败
静态 CAPABILITY_FALLBACK 兜底
  ↓ 仍失败（所有订阅都真不可用）
才返回上游错误（属上游故障，非本地限速）
```

流式路径同样在**开流前**做等待重试（尚未转发任何字节，安全），避免把上游 429
当作客户端错误抛出。

## FairScheduler — 优先级公平调度（保留）

静态优先级表（数值越大优先级越高）：

```
polarclaw: 10   polarui: 8   autooffice: 5
knowlever: 3    digist: 3    sotagent: 2    unknown: 5
```

`should_defer`：仅当某订阅 in_flight ≥ max_concurrent×80% 且有更高优先级客户端
在竞争时，低优先级客户端 sleep 一小段再排队——**只让行、不拒绝、不饿死**。
平时（<80%）所有客户端平等。

> 客户端身份来自请求头 `X-Client-Id`（PolarClaw SDK 会带 `polarclaw`）。

## 配置

### 默认 Service 限制（仅并发被强制；rpm 仅用于统计展示，不再节流）

| Service | max_concurrent |
|---------|---------------|
| `llm.glm51.enterprise` | 10 |
| `llm.aliyun.codingplan` | 8 |
| `llm.aliyun.dashscope` | 50 |
| `llm.minimax` | 12 |
| 其他（默认） | 3 |

### 环境变量

```bash
# 并发/RPM 覆盖（rpm 字段保留兼容，但已不参与节流）
# 格式: PRIVPORTAL_RL_<SERVICE>=concurrent,rpm   service 里的 . 用 __ 代替
PRIVPORTAL_RL_LLM__GLM51__ENTERPRISE=12,0

# 冷却（路由信号）调参
PRIVPORTAL_RL_COOLDOWN_SEC=5        # 上游无 Retry-After 时的默认冷却秒数
PRIVPORTAL_RL_COOLDOWN_MAX_SEC=30   # 尊重 Retry-After 的封顶
```

### 监控端点

- `GET /api/rate-limits` — 基础统计（per-service snapshot）
- `GET /api/rate-limits/dashboard` — 全量面板（summary + utilization + clients）
- SOTAgent Console → "LLM 限速" 页面（10s 自动刷新）

## 可调旋钮

- **权重比例**：现为"主源占大头 + 自动分摊"。可改为纯故障切换（主源权重 100%，
  仅在主源冷却时才切），或按订阅额度重新定权重。
- **Agent 档是否主动分摊**：当前 Agent 也会有一小部分走 Qwen/M3（工具调用质量
  略有差异）；可改为 Agent 仅在 glm51 冷却时才切源。
