# Opaque model codes

调用方在 `model` 字段里只传**码**，不传厂商名、不传 Ollama 标签、不传端口号。  
每个码 = **接口类型 + 模型槽位**；PolarPrivate 在服务端解析成真实模型并转发。

**零兼容**：只认下表中的码。

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
| `0000` | 0000 | 默认均衡 | GLM-5.1 (200K) | llm.glm51.enterprise | 通用首选 |
| `0010` | 0010 | 快速 | DS V4 Flash (1M) | llm.glm51.enterprise | 超长上下文+快 |
| `0100` | 0100 | 长上下文 | DS V4 Pro (1M) | llm.glm51.enterprise | 旗舰推理 |
| `0110` | 0110 | 快速+长上下文 | MiniMax-M3 | llm.minimax | 综合性价比 |
| `1000` | 1000 | 旗舰（质量优先） | GLM-5.1 (200K) | llm.glm51.enterprise | 有质量要求的对话 |
| `1110` | 1110 | 旗舰+深度推理 | MiniMax-M3-Thinking | llm.minimax | 长思考链 |

### Agent 模型（A=1）

| 码 | QCSA | 槽位含义 | 默认上游模型 | Binding | 备注 |
|----|------|----------|--------------|---------|------|
| `0001` | 0001 | Agent 均衡 | DS V4 Flash (1M) | llm.glm51.enterprise | Agentic 杂活，tool call 最快最准 |
| `0011` | 0011 | Agent 快速 | DS V4 Flash (1M) | llm.glm51.enterprise | 同上 |
| `1001` | 1001 | Agent 旗舰 | DS V4 Pro (1M) | llm.glm51.enterprise | 复杂多步推理 |

### 视觉/多模态模型（V 前缀）

| 码 | 含义 | 默认上游模型 | Binding | 备注 |
|----|------|--------------|---------|------|
| `V0000` | 默认视觉 | qwen3.7-plus | llm.aliyun.codingplan | **效果最好最详细** |
| `V0010` | 视觉快速 | qwen3-vl-flash | llm.aliyun.dashscope | 大量图片（44p/30s），需请示用户 |
| `V1000` | 单页视觉旗舰 | Kimi-K2.6 (256K) | llm.glm51.enterprise | **单图最强**，xfyun 限 3-4 张 |
| `V0001` | 视觉 Agent 单图 | Kimi-K2.6 (256K) | llm.glm51.enterprise | K2.6 + tool call |
| `V0101` | 视觉 Agent 多图 | qwen3.7-plus | llm.aliyun.codingplan | C=1 长上下文处理多图 + tool call |

---

## VLM 使用策略

| 场景 | 推荐码 | 模型 | 理由 |
|------|--------|------|------|
| 聊天中 1 张图片 | `V1000` | Kimi-K2.6 | 单图理解最强 |
| **默认**视觉任务 | `V0000` | qwen3.7-plus | 效果最好最详细 |
| 大量图片（>5 张） | `V0010` | qwen3-vl-flash | 最快；Agent 使用前须请示用户 |
| 视觉 Agent 单图 | `V0001` | Kimi-K2.6 | 单图+tool call |
| 视觉 Agent 多图 | `V0101` | qwen3.7-plus | C=1 长上下文 + tool call |

⚠️ Kimi-K2.6 多图限制：xfyun 代理对多图输入限 3-4 张，超出返回 500

---

## 本地 Ollama

| 码 | 槽位 | 默认 Ollama 模型 | 说明 |
|----|------|------------------|------|
| **`L0000`** | embedding | qwen3-embedding:8b | 本地向量化 |

环境变量：`OLLAMA_EMBED_MODEL` 或 `OLLAMA_MODEL_L0000`。


---

## 本地嵌入 `POST /v1/embeddings`

| 码 | 默认 Ollama 模型 |
|----|------------------|
| **`E000`** | `qwen3-embedding:8b` |

环境变量：`OLLAMA_EMBED_MODEL_E000` 或 `OLLAMA_EMBED_MODEL`。

---

## Fallback 链

| 码 | 主路由失败时降级到 |
|----|-------------------|
| `V1000` (K2.6 多图/500) | qwen3-vl-flash |
| `0010` (DS Flash 不可用) | qwen3.7-plus |
| `1000` (GLM 不可用) | DS V4 Pro |
| `0001` (Agent Flash 不可用) | DS V4 Pro |

---

## 响应里的 `model` 字段

API 回显调用方传入的码（如 `V0000`、`0001`、`L0000`），不回显上游/Ollama 真实模型名。
