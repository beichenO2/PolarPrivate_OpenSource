# PolarPrivate 灵魂

> 本地 API Key 代理门户。Agent 修改本项目前，必须阅读并遵守以下核心特质。

---

## 核心特质

| 特质 | 与社区同类项目的差异 |
|------|----------------------|
| **密钥永不出内存** | 不像 Vault 等密钥管理工具会返回明文密钥，PolarPrivate 的密钥只在内存中解密，直接转发给上游服务器 |
| **代理转发模式** | 客户端不接触密钥，通过代理访问外部 API，代理自动注入认证头 |
| **本地优先** | 无云依赖，所有数据存储在本地 SQLite，加密密钥由用户 Master Password 派生 |

---

## 外部合作

### 依赖

- 无外部项目依赖（基础设施层）

### 被依赖

几乎所有 Polarisor 项目都依赖 PolarPrivate：
- [PolarClaw](../PolarClaw/PolarSoul.md)：LLM 调用代理
- [KnowLever](../KnowLever/PolarSoul.md)：LLM 编译代理
- [digist](../digist/PolarSoul.md)：LLM 摘要代理
- [AutoOffice](../AutoOffice/PolarSoul.md)：AI PPT 生成代理

### 接口契约

- `/v1`：统一 LLM 网关（OpenAI 兼容）
- `/proxy/{service_name}`：通用代理路径
- `/api/secrets`：Secret CRUD（需 Master Password）

---

## 设计决策

### 为什么密钥不出内存？

**问题**：传统密钥管理工具（Vault、AWS Secrets Manager）会返回明文密钥，客户端需要处理密钥。

**决策**：PolarPrivate 采用代理模式，密钥在内存中解密后直接转发给上游服务器，客户端永远不接触明文密钥。

**不可妥协**：任何情况下密钥不得以明文形式写入日志、返回给客户端、或存储到非加密存储。

### 为什么用 Master Password？

**问题**：需要一种方式让用户控制加密密钥，同时不需要记住复杂的密钥。

**决策**：用户设置一个 Master Password，通过 PBKDF2 派生 Fernet 密钥，用于加密存储的 Secret。

**不可妥协**：Master Password 永远不存储，只存在于用户记忆和运行时内存。

---

## 详情入口

- [SSoT](polaris.json)
- [使用指南](README.md)
- [安全模型](docs/security-model.md)
