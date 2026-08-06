# PolarPrivate · Agent 使用手册

面向 Cursor / Codex Agent：如何用 PolarPrivate 交付**可运行**集成，而不是把「配密钥」甩给用户。

配套 Skill（权威流程）：

`PolarPrivate/.cursor/skills/polarprivate/SKILL.md`

## 一句话原则

> Agent 做完一切可编程的接线；用户只做 Agent 物理上做不到的事（注册、人机验证、粘贴 Key、输 Master Password）。

## 推荐心智模型

```
需要凭证？
  → PolarPrivate 是否在线且 Vault 解锁？
      → 否：PolarProcess 拉起 / 请用户解锁（单步）
  → Secret + Binding 是否已存在？
      → 否：API 创建占位槽（__AWAITING_USER_FILL__ + enabled:false）+ Binding
  → 项目是否已指向 proxy 或 /v1？
      → 否：Agent 改代码与 Start 脚本
  → 交付：【用户必做·已开槽】+ 精确 key + UI 路径（≤3 步）
  → 用户填完：test-connectivity / 业务冒烟
```

## 文档地图

| 文档 | 读者 | 内容 |
|---|---|---|
| `SKILL.md`（本仓库 `.cursor/skills/polarprivate`） | Agent | 触发条件与铁律 |
| `references/slot-provisioning.md` | Agent | 开槽 API 配方 |
| `references/agent-ops.md` | Agent | 日常 curl / 代理 |
| `references/qcsa-quickref.md` | Agent | 能力码 |
| `api-reference.md` | 人+Agent | 完整 REST |
| `security-model.md` | 人+Agent | 明文禁令 / A·B·D 通道 |
| `usage.md` / `gui-workflows.md` | 人 | GUI 操作 |
| `AGENT_WORKSPACE.md` | Agent | 工作区明文禁令 |
| `runtime-governance.md` | Agent | PolarProcess 服务 id |

## 与「完整可用交付」注入规则的关系

Inject Studio 积木 `base:rule:最高原则-完整可用交付` 要求交付物开箱可跑。  
涉及密钥时：**开槽 + 单步粘贴** 是唯一合规的用户手工路径；多步「手动改配置 / 手动启服务」会被用户级 Hook `manual-handoff-guard` 打回重做。

## 示例：给新项目接 OpenAI 兼容接口

1. `GET /health` 确认 unlocked  
2. `POST /api/secrets` → `secret.myapp.openai` 占位  
3. `POST /api/bindings` → `llm.myapp.openai`  
4. 代码 `base_url = http://127.0.0.1:12790/proxy/llm.myapp.openai/v1`  
5. 交付 `【用户必做·已开槽】` 指向该 key  
6. 用户保存后 `POST /api/secrets/{id}/test-connectivity`

## 常见错误

| 错误交付 | 应改为 |
|---|---|
| 请手动配置环境变量 | 开槽 + UI 粘贴 |
| 请手动启动 PolarPrivate | PolarProcess start |
| 把 Key 发我，我帮你写进文件 | 用户只写 UI；Agent 不收明文 |
| 附 12 步手动清单 | Agent 执行其中可编程步骤 |
