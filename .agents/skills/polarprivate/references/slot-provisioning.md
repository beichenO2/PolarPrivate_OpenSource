# 先开槽，再请用户填 Key

API 创建 Secret 时 `value` **必填**（`min_length=1`），且无「空槽」专用字段。Agent 约定用 **占位密文 + `enabled:false`** 表示「待用户填入」。

占位常量（可检索、绝非真实 Key）：

```
__AWAITING_USER_FILL__
```

## 标准流程（必须按序）

### 1) 查重

```bash
curl -fsS 'http://127.0.0.1:12790/api/secrets?q=secret.<vendor>'
curl -fsS 'http://127.0.0.1:12790/api/bindings?q=<service_name>'
```

已有同名且用户只需补值 → 不要重复创建；交付指向已有 key。

### 2) 创建 Secret 槽（Vault 须解锁）

```bash
curl -fsS -X POST http://127.0.0.1:12790/api/secrets \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "secret.openai.default",
    "value": "__AWAITING_USER_FILL__",
    "enabled": false,
    "base_url": "https://api.openai.com/v1",
    "category": "openai",
    "project_id": null
  }'
```

命名约定：`secret.<vendor>.<role>`，必须含 `.`。

### 3) 创建 Binding

```bash
curl -fsS -X POST http://127.0.0.1:12790/api/bindings \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "llm.openai",
    "secret_ref_key": "secret.openai.default",
    "auth_header": "Authorization",
    "project_id": null
  }'
```

`service_name` 即后续 `/proxy/{service_name}/...` 路径段。

### 4) 项目侧接线（Agent 做）

- 代码/配置只引用 `http://127.0.0.1:12790/proxy/llm.openai` 或 `/v1` + QCSA
- Start 脚本、健康检查、PolarProcess 注册一并就绪
- **不要**留下「请编辑 .env 填 KEY」的 README 作为主路径

### 5) 交付给用户的唯一手工步

使用固定头（Hook 白名单）：

```
【用户必做·已开槽】
请打开 http://127.0.0.1:12795 → Secrets，找到 key=`secret.openai.default`：
用 Rotate/编辑把真实 API Key 粘贴进去，勾选 Enabled 并保存。
完成后告诉我一声，我会跑连通性测试。
```

若还需注册账号：

```
【用户必做·已开槽】
1. 在 https://platform.openai.com 注册/登录并创建 API Key（Agent 无法代你做人机验证）
2. 粘贴到 PolarPrivate 槽位 secret.openai.default（路径同上）
```

## 用户填完后 Agent 验收

1. `test-connectivity` 或对 `/proxy/...` 发只读探测
2. 将 Secret `enabled` 保持 true（用户已开则勿反复折腾）
3. 交付写清：槽位 key、Binding service_name、验证命令与结果

## 失败与降级

| 情况 | 处理 |
|---|---|
| Vault 锁定 | 只请解锁；槽位创建延后，但项目侧代理 URL 可先写好 |
| 423 / 未解锁创建失败 | 如实 NOT RUN；不要改教用户写 `.env` |
| key 冲突 409 | 复用已有槽，改交付文案 |
| PolarPrivate 宕机 | PolarProcess 拉起；仍失败才标基础设施 blocker |

## 反模式

- ❌「请手动在项目根目录创建 `.env` 并填写 OPENAI_API_KEY」
- ❌「请手动到 PolarPrivate 新建 Secret」（未说明 Agent 已建好的 key）
- ❌ 把真实 Key 让用户粘贴到聊天里再由 Agent 写入（应直达 UI）
- ❌ 一次甩 8 步「手动部署清单」
