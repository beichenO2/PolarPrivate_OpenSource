# PolarPrivate · Agent 日常操作

## 地址与权威

| 用途 | URL / ID |
|---|---|
| API + 代理 + `/v1` | `http://127.0.0.1:12790` |
| Web UI | `http://127.0.0.1:12795` |
| PolarProcess backend | `privportal-backend` |
| PolarProcess frontend | `privportal-frontend` |

启停示例（只读查 id 后）：

```bash
curl -fsS http://127.0.0.1:11055/api/services
curl -fsS -X POST http://127.0.0.1:11055/api/services/privportal-backend/start
curl -fsS -X POST http://127.0.0.1:11055/api/services/privportal-frontend/start
```

## 健康与 Vault

```bash
curl -fsS http://127.0.0.1:12790/health
curl -fsS http://127.0.0.1:12790/api/vault/status
```

| 状态 | Agent 动作 |
|---|---|
| health 失败 | PolarProcess start/restart；勿手写端口 |
| `locked:true` | 请用户解锁 UI；其余配置工作可先列计划 |
| `locked:false` / unlocked | 可 CRUD Secret / Binding（仍勿 reveal） |

## 列出已有资源（开槽前先查重）

```bash
curl -fsS 'http://127.0.0.1:12790/api/secrets?q=secret.openai'
curl -fsS 'http://127.0.0.1:12790/api/bindings?q=llm.openai'
curl -fsS http://127.0.0.1:12790/api/projects
```

响应**不含** Secret 明文。`has_value` 等元数据可用于判断槽位是否待填。

## 创建 Project（可选）

```bash
curl -fsS -X POST http://127.0.0.1:12790/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-app","description":"Agent provisioned"}'
```

记下返回的 `id`，后续 Secret/Binding 挂 `project_id`。

## Binding → 代理调用

创建 Binding 后，调用方**不带** Authorization：

```bash
curl -fsS -X POST \
  'http://127.0.0.1:12790/proxy/llm.openai/v1/chat/completions' \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
```

项目配置里只写：

- `POLARPRIVATE_BASE=http://127.0.0.1:12790`
- `POLARPRIVATE_SERVICE=llm.openai`（或 QCSA `/v1`）

**不要**写 `OPENAI_API_KEY=...`。

## QCSA 网关（生态首选）

```bash
curl -fsS -X POST http://127.0.0.1:12790/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"0001","messages":[{"role":"user","content":"hi"}]}'
```

`model` 只传能力码；上游真实模型名由服务端解析。码表见 `qcsa-quickref.md` 与 `backend/app/core/CAPABILITY_CODES.md`。

## 连通性自检（不读明文）

```bash
# 对已有 secret_id
curl -fsS -X POST \
  "http://127.0.0.1:12790/api/secrets/${SECRET_ID}/test-connectivity"
```

或 UI → Test Center 批量测 Binding。

## 禁止事项速查

| 禁止 | 正确 |
|---|---|
| 把 Key 写进仓库 / `.env` | Secret 槽 + Binding / QCSA |
| `POST .../reveal` 进对话 | 用户只在 UI 粘贴；Agent 用 proxy |
| 教用户「手动改 sqlite」 | API / UI |
| 服务挂了就 `pkill` | PolarProcess API |
