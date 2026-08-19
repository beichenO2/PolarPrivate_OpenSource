---
name: polarprivate
description: >-
  Use PolarPrivate (PrivPortal) as the sole local secret vault and LLM proxy.
  Trigger whenever an Agent needs API keys, tokens, Binding/proxy setup, QCSA
  model codes, vault unlock status, or must ask a user to provide a secret —
  especially before saying the user must "manually configure" credentials.
  Also use when creating placeholder secret slots, wiring /proxy/{service}/…,
  or calling POST /v1/chat/completions via 127.0.0.1:12790.
---

# PolarPrivate · Agent 密钥与 LLM 代理

**权威服务**：`http://127.0.0.1:12790`（后端）· UI `http://127.0.0.1:12795`  
**启停**：走 PolarProcess（`privportal-backend` / `privportal-frontend`），禁止裸 `kill` / 裸 `npm run dev`。  
**明文禁令**：Secret 明文不得进 Agent 工作区、`.env`、日志、截图说明、commit、SubAgent 信封。

## 何时必读本 Skill

- 需要任何第三方 API Key / Token / Webhook Secret
- 要把用户侧凭证接进项目（含「填写到 PolarPrivate」）
- 调 LLM：应走 PolarPrivate `/v1` + QCSA 码，而不是直连厂商
- 交付前发现「还差用户配密钥」——先开槽，再给**一步**用户动作

深入步骤见：

| 文件 | 内容 |
|---|---|
| [references/agent-ops.md](references/agent-ops.md) | 健康检查、项目、Binding、代理调用、QCSA |
| [references/slot-provisioning.md](references/slot-provisioning.md) | **先开槽再请用户填 Key**（硬流程） |
| [references/qcsa-quickref.md](references/qcsa-quickref.md) | 常用能力码速查 |
| 仓库文档 | `docs/api-reference.md` · `docs/security-model.md` · `docs/agent-playbook.md` |

## 铁律（冲突时以本节为准）

1. **密钥只住在 PolarPrivate**：禁止把 Key 写入项目 `.env` / 配置文件「让用户自己填」。应创建 Secret 槽 + Binding，让用户只在 UI 粘贴一次。
2. **先开槽，后请人**：任何「请把 Key 填进 PolarPrivate」之前，Agent **必须**已用 API 建好 Project（如需）/ Secret（placeholder）/ Binding，并在交付里给出**精确 key 名 + UI 路径**。
3. **Vault 锁定时**：只请用户做一件事——打开 UI 解锁 Master Password；不要展开多步「手动改库」。
4. **禁止调用** `POST /api/secrets/{id}/reveal` 把明文拉进对话（GUI 专用；Agent 工作流不走 reveal）。
5. **LLM 调用**：`model` 只传 QCSA 码（如 `0001`），`base_url=http://127.0.0.1:12790/v1`；或 `POST /proxy/{service_name}/…` 由 Binding 注头。

## 最小预检（只读）

```bash
curl -fsS --max-time 3 http://127.0.0.1:12790/health
# → {"status":"ok","vault_unlocked":true|false}
```

- 不可达 → 用 PolarProcess 查/启 `privportal-backend`；仍失败则标 blocker，**不要**改叫用户手搓一堆环境变量。
- `vault_unlocked:false` → 合法用户动作：打开 `http://127.0.0.1:12795` 输入 Master Password。Agent 不得猜测密码。

## 合法「用户必做」白名单（仅这些可甩给用户）

用固定前缀交付，便于 Hook 放行：

```
【用户必做·已开槽】
1. 打开 http://127.0.0.1:12795 → Secrets
2. 找到 key=`secret.<vendor>.<name>` → Rotate/编辑 → 粘贴 Key → 保存并 Enabled
```

允许的用户动作仅限：

- 上网注册账号 / 人机验证 / 付款 / 接受 ToS
- 解锁 Vault（Master Password）
- 向**已由 Agent 创建的** PolarPrivate 槽位粘贴密钥
- 物理设备、短信/邮箱 OTP、硬件密钥

除此之外（改配置文件、启停服务、装依赖、写 `.env`、多步「手动部署」）→ **Agent 自己做完**，不得交付甩锅。

## 完成前自检

- [ ] 需要的 Secret/Binding 是否已存在（或本轮已创建 placeholder）？
- [ ] 用户步骤是否 ≤ 3 步、且每步 Agent 做不到？
- [ ] 对话/文件中是否零明文 Key？
- [ ] 项目侧是否只引用 `service_name` / QCSA，而非厂商 Key？
