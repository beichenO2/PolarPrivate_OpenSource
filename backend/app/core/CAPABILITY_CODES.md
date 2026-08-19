# Opaque model codes

调用方在 `model` 字段里只传**码**，不传厂商名、不传 Ollama 标签、不传端口号。  
每个码 = **接口类型 + 模型槽位**；PolarPrivate 在服务端解析成真实模型并转发。

**零兼容**：只认下表中的码。已退役（无 Binding、不要再调用）：讯飞 xfyun / `llm.glm51.enterprise`、`llm.aliyun.codingplan`（`1100` `qwen3.7-plus`）、本地 Ollama（`L0000` `L0001`）。

---

## QCSA 四位含义（云端 `0000`–`1111`）

从左到右：**Q**uality · **C**ontext · **S**peed · **A**gentic（每位 `0` 或 `1`）。

- Q=0 标准模型 / Q=1 旗舰模型
- C=0 标准上下文 / C=1 长上下文
- S=0 均衡 / S=1 快速
- A=0 对话模式 / A=1 Agent 模式（优先 tool calling + 快速响应）

---

## 云端对话 `POST /v1/chat/completions`

### 文本模型（4 位 QCSA）

| 码 | QCSA | 槽位含义 | 默认上游模型 | Binding | 备注 |
|----|------|----------|--------------|---------|------|
| `0000` | 0000 | 默认均衡 | MiniMax-M3 | llm.minimax | 通用首选 |
| `0010` | 0010 | 快速 | MiniMax-M3 | llm.minimax | |
| `0100` | 0100 | 长上下文 | deepseek-v4-pro | llm.lant | |
| `0110` | 0110 | 快速+长上下文 | MiniMax-M3 | llm.minimax | |
| `1000` | 1000 | 旗舰（质量优先） | MiniMax-M3 | llm.minimax | |
| `1110` | 1110 | 旗舰+深度推理 | MiniMax-M3-Thinking | llm.minimax | 长思考链 |

### Agent 模型（A=1）

| 码 | QCSA | 槽位含义 | 默认上游模型 | Binding | 备注 |
|----|------|----------|--------------|---------|------|
| `0001` | 0001 | Agent 均衡 | MiniMax-M3 | llm.minimax | Agentic 杂活；402/限流溢到 `llm.minimax_1` |
| `0011` | 0011 | Agent 快速 | MiniMax-M3 | llm.minimax | |
| `0101` | 0101 | Agent 长上下文 | deepseek-v4-pro | llm.lant | |
| `1001` | 1001 | Agent 旗舰 | deepseek-v4-pro | llm.lant | 复杂多步 |

### 视觉/多模态模型（V 前缀）

MiniMax-M3 原生多模态（图 / 视频输入）。调用方仍只传 V 码；显式 `qwen3-vl-flash` 可走 DashScope。

| 码 | QCSA | 槽位含义 | 默认上游模型 | Binding | 备注 |
|----|------|----------|--------------|---------|------|
| `V0000` | 0000 | 默认视觉 | MiniMax-M3 | llm.minimax | 通用看图 |
| `V0010` | 0010 | 视觉快速 | MiniMax-M3 | llm.minimax | AutoOffice Designer |
| `V1000` | 1000 | 视觉旗舰 | MiniMax-M3-Thinking | llm.minimax | 深度看图 |
| `V0001` | 0001 | 视觉 Agent | MiniMax-M3 | llm.minimax | 看图 + tool |
| `V0101` | 0101 | 视觉 Agent 长上下文 | MiniMax-M3 | llm.minimax | 多图 / 长材料 |

---

## 云端嵌入 `POST /v1/embeddings`

| 码 | 默认上游 | Binding |
|----|----------|---------|
| **`E000`** | DashScope `qwen3.7-text-embedding` | llm.aliyun.dashscope |

环境变量：`CLOUD_EMBED_MODEL` 或 `CLOUD_EMBED_MODEL_E000`。

---

## 生图 / 生音频 / 生视频（MiniMax）

调用方只传能力码，不传 `image-01` / `speech-2.8-turbo` / `MiniMax-Hailuo-2.3`。上游路径与模型由 PolarPrivate 解析。Binding 默认 `llm.minimax`（`secret.minimax.api_key`）；该 Binding 的 `fallback_chain` 指向官方备线 `llm.minimax_1`（`secret.minimax.minimax_1`）。所有 MiniMax 请求先打原版，402 / 429 / 5xx 再切备线。

| 码 | 入口 | 默认上游 | 备注 |
|----|------|----------|------|
| **`I000`** | `POST /v1/images/generations` | `image-01` | 接受 OpenAI 字段 `prompt`/`size`/`n`/`response_format` |
| **`A000`** | `POST /v1/audio/speech` | `speech-2.8-turbo` | 接受 OpenAI 字段 `input`/`voice`；缺省音色 `male-qn-qingse` |
| **`D000`** | `POST /v1/videos/generations` | `MiniMax-Hailuo-2.3` | 异步任务；`GET /v1/videos/generations/{task_id}` 查询 |

环境变量：`POLARPRIVATE_IMAGE_MODEL` / `POLARPRIVATE_AUDIO_MODEL` / `POLARPRIVATE_VIDEO_MODEL` / `POLARPRIVATE_AUDIO_VOICE`。

Token Plan 当前不支持 MiniMax-H3；H3 请走按量 Key 后用 `/proxy/llm.minimax/v2/video_generation`。

---

## 显式模型别名（非 QCSA）

QCSA 码之外，`/v1` 仍接受下列在册上游名（与 glm-5.2 同类）。业务代码优先传 QCSA；需要钉死某条付费线路时再用显式 id。

| 调用方 model | 上游 | Binding | 备注 |
|--------------|------|---------|------|
| `gpt-5.6-sol` | gpt-5.6-sol | llm.rightapi | RightAPI Codex 号池；Secret `secret.rightapi.api_key` |
| `gpt-5.6` | gpt-5.6-sol | llm.rightapi | 别名，与 OpenAI `gpt-5.6` → Sol 一致 |
| `glm-5.2` | glm-5.2 | llm.glm2 | 独立 glm2 线 |

---

## 响应里的 `model` 字段

API 回显调用方传入的码（如 `V0010`、`0001`），不回显上游真实模型名。
