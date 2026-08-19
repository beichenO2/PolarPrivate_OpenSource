# QCSA 能力码速查（Agent）

完整 SSOT：`backend/app/core/CAPABILITY_CODES.md`。此处只列**在册**高频码。

调用：

```
POST http://127.0.0.1:12790/v1/chat/completions
{"model":"<CODE>","messages":[...]}
```

## 文本 / Agent

| 码 | 场景 | 上游 Binding |
|---|---|---|
| `0000` | 默认均衡对话 | MiniMax-M3 |
| `0001` | **Agent 杂活首选**（tool call） | MiniMax-M3 |
| `0010` | 要快 | MiniMax-M3 |
| `0110` | 快速 + 长上下文 | MiniMax-M3 |
| `0100` | 长上下文 / 更强推理 | lant `deepseek-v4-pro` |
| `1000` | 质量优先对话 | MiniMax-M3 |
| `1001` | Agent 旗舰多步 | lant `deepseek-v4-pro` |
| `1110` | 深度推理（会出 thinking） | MiniMax-M3-Thinking |

## 视觉（MiniMax-M3 多模态）

| 码 | 场景 | 上游 |
|---|---|---|
| `V0000` | 默认看图 | MiniMax-M3 |
| `V0010` | **视觉首选**（快） | MiniMax-M3 |
| `V1000` | 深度看图 | MiniMax-M3-Thinking |
| `V0001` | 看图 + tool | MiniMax-M3 |
| `V0101` | 多图 / 长材料 + tool | MiniMax-M3 |

显式 `qwen3-vl-flash` 仍可走 DashScope。显式 `gpt-5.6-sol`（别名 `gpt-5.6`）走 RightAPI Codex（`llm.rightapi`）。已退役：`1100` `qwen3.7-plus`、全部 xfyun/`xop*`、`L0000`/`L0001`。

## 嵌入

| 码 | 场景 |
|---|---|
| `E000` | 云端 embedding（DashScope `qwen3.7-text-embedding`） |

## 生图 / 生音频 / 生视频（MiniMax）

| 码 | 入口 | 上游 |
|---|---|---|
| `I000` | `POST /v1/images/generations` | MiniMax `image-01` |
| `A000` | `POST /v1/audio/speech` | MiniMax `speech-2.8-turbo` |
| `D000` | `POST /v1/videos/generations` | MiniMax-Hailuo-2.3 |

查询视频：`GET /v1/videos/generations/{task_id}`。不要把这些码发到 `/v1/chat/completions`。

## 规则

- **只传码**，不传 `gpt-4o` / `qwen-...` 等上游名（`/v1` 网关）
- 换供应商改 PolarPrivate 路由，不改 Agent 业务配置里的 model 字符串
- 代理路径 `/proxy/{service}/…` 仍可能使用上游 model 名——那是 Binding 通道；生态新代码优先 QCSA `/v1`
- MiniMax 官方备线：`llm.minimax` 先打，`402/429/5xx` 溢到 `llm.minimax_1`（`secret.minimax.minimax_1`）
