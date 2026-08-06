# Agent workspace policy

## 明文禁令（硬）

Secret plaintext MUST NOT appear in:

- repository files intended for AI agents (`.planning/`, inbox/outbox, scratch notes)
- committed `.env`, example files with real keys, screenshots pasted into chat
- SubAgent task envelopes or tool logs

Programs MUST use binding references (e.g. `service.llm.chat` → `secret.openai.default`) or QCSA `/v1` codes, not raw secret values in workspace configuration.

## 正确接线

| 场景 | 工作区应出现的内容 | 不应出现 |
|---|---|---|
| LLM 调用 | `http://127.0.0.1:12790/v1` + model=`0001` | 厂商 API Key |
| 代理调用 | `/proxy/<service_name>/...` | `Authorization: Bearer sk-...` |
| 待用户填 Key | 文档写 `【用户必做·已开槽】` + secret key 名 | 让用户手写一整份 `.env` |

## Agent 必做 vs 用户可做

- **Agent**：PolarProcess 启停、创建 Project/Secret 占位槽/Binding、改业务代码指向 proxy、跑连通性测试、写清单步说明  
- **用户**：Vault Master Password、上网注册、人机验证、向已开槽位粘贴 Key  

详见 `docs/agent-playbook.md` 与 Skill `polarprivate`。
