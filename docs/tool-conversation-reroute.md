# 工具对话兼容改路由（tool_convo_reroute）

> 适用于 `/v1/chat/completions` 统一 LLM 网关。  
> 源码：`backend/app/api/v1_gateway.py`（`_request_has_tool_messages`、`_TOOL_CONVO_REROUTE`）  
> 与跨订阅负载均衡的关系见 [rate-limiting-algorithm.md](./rate-limiting-algorithm.md)。

## 背景

PolarClaw 等多轮 Agent 在 ReAct 循环中，会在同一对话里交替出现：

- `assistant` 消息携带 `tool_calls`
- `role: "tool"` 的工具结果

实测发现：当请求被路由到讯飞企业订阅 **`llm.glm51.enterprise`** 且 payload **已含上述 tool 消息** 时，上游偶发返回 **HTTP 200 但 body 为空**（`content` 与 `tool_calls` 皆无）。Agent 侧表现为 `toolCalls=0, contentLen=0`，循环空转、最终「暂无文本回复」。

**这不是「讯飞不支持 tool calling」。** 单轮 tool call、简单多轮、非流式/流式在多数场景下均正常；问题集中在 **follow-up 轮次 + 含 tool 历史的上下文** 与特定上游组合的兼容性。

`llm.glm51.enterprise` 是**订阅网关**，托管 GLM-5.1、DeepSeek V4 Flash/Pro、Kimi-K2.6 等多个模型，并非单指 GLM-5.1。

## 策略

在 **跨订阅权重选源之后**、**转发上游之前**，插入一层兼容改路由：

```
resolve_model + LOAD_BALANCE 选源
        │
        ▼
  service == llm.glm51.enterprise
  且 messages 含 tool_call / tool 消息？
        │
   是 ──┴── 否 → 按原 (service, model) 转发
        │
        ▼
改路由 → qwen3.7-plus @ llm.aliyun.codingplan
        │
        ▼
转发上游
```

### 触发条件（同时满足）

| 条件 | 说明 |
|------|------|
| 目标 service 为 `llm.glm51.enterprise` | 含 LOAD_BALANCE 选中的 DS-Flash/Pro、GLM-5.1 等 |
| `messages` 中存在 `role: "tool"` | 已有工具结果 |
| 或 `messages` 中 assistant 带 `tool_calls` | 历史中已有工具调用 |

检测函数：`_request_has_tool_messages(obj)`。

### 改路由目标

```python
_TOOL_CONVO_REROUTE = ("qwen3.7-plus", "llm.aliyun.codingplan")
```

选用 Qwen3.7-Plus 因其在多轮 tool 对话、流式聚合场景下稳定。

###  deliberately 不改路由的情况

| 场景 | 原因 |
|------|------|
| Round 0（尚无 tool 消息） | 首轮 tool 决策仍可使用原权重选中的 glm51 订阅模型（如 DS-Flash） |
| 已选源为 `llm.minimax` / `llm.aliyun.codingplan` | 非 glm51 订阅，无此兼容问题 |
| 请求头 `x-pp-no-reroute: 1` | 诊断开关，强制走原始路由以复现/对比上游行为 |

## 与跨订阅引流的关系

两者正交、顺序固定：

1. **`LOAD_BALANCE_GROUPS`**：按权重在多个订阅间分流；某订阅 429 冷却后跳过。
2. **`tool_convo_reroute`**：若最终仍落在 glm51 且含 tool 历史，**强制**切到 codingplan Qwen。

reroute 不是限速，而是 **Agent 多轮工具对话的兼容性兜底**；与「上游 429 等待重试 / 冷却引流」并列存在于 `v1_gateway.py`。

## 日志

改路由时写入 structlog 事件：

```
tool_convo_reroute  reason=glm51_empty_on_tool_messages
                  to_service=llm.aliyun.codingplan  to_model=qwen3.7-plus
```

Agent 成功 follow-up 后，PolarClaw 日志中可见 `model=qwen3.7-plus` 而非 opaque code `0001`。

## 诊断与复现

### 绕过改路由（直打 glm51 订阅）

```bash
curl -s http://127.0.0.1:12790/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'x-pp-no-reroute: 1' \
  -d '{
    "model": "0001",
    "stream": true,
    "messages": [
      {"role":"user","content":"查天气"},
      {"role":"assistant","content":"","tool_calls":[{"id":"c1","type":"function","function":{"name":"get_weather","arguments":"{\"city\":\"北京\"}"}}]},
      {"role":"tool","tool_call_id":"c1","content":"{\"temp\":\"15C\"}"}
    ],
    "tools": [{"type":"function","function":{"name":"get_weather","parameters":{"type":"object","properties":{"city":{"type":"string"}}}}}]
  }'
```

注意：即使带 `x-pp-no-reroute`，**LOAD_BALANCE 仍可能**把请求分到 MiniMax 或 codingplan；要固定 glm51 上游需结合 capability 权重或多次采样观察 `model` 字段。

### 验证改路由生效

同上 payload **不加** `x-pp-no-reroute`；响应 SSE/JSON 中 `model` 应为 `qwen3.7-plus`。

## 后续可调

- **改路由目标**：替换 `_TOOL_CONVO_REROUTE` 元组即可切换备用 provider。
- **扩大/缩小触发面**：若上游修复，可改为仅对特定 full_model（如 `xopglm51`）reroute，而非整个 glm51 订阅。
- **配置化**：当前为代码常量；如需运维可调，可迁入 `PRIVPORTAL_*` 环境变量。
