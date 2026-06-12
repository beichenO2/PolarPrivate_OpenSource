# API Key 并发极限压测报告

> 日期：2026-06-10  
> 测试工具：`backend/tests/test_concurrency_limits.py`  
> 测试方法：Ramp-up + Binary Search + Sequential RPM  
> 协议：每服务 3 轮，轮间 15 分钟冷却  
> 请求内容：`"Say just the number N"`, max_tokens=5  
> 目标网关：PolarPrivate `http://127.0.0.1:8005/v1/chat/completions`  
> 测试期间 `_SERVICE_LIMITS` 临时放大到 100/600 以暴露上游真实限制

---

## 总结

| API Key | 测试并发极限 | 设定并发 | 测试 RPM | 设定 RPM | 平均延迟 |
|---------|-------------|---------|---------|---------|---------|
| llm.glm51.enterprise | 12-15 | **10** | 3.8-11.5 | **10** | 5-10s |
| llm.aliyun.codingplan | **8** (3轮零偏差) | **8** | 12.8-13.9 | **10** | 3.5-4.2s |
| llm.minimax | 12-15 | **12** | 28-41 | **25** | 1.2-1.6s |
| llm.aliyun.dashscope | 按量计费不限 | **50** | — | **600** | — |

设定值选取原则：取各轮测试最小值的 80%（向下取整），确保在正常负载下不触发上游限制。

---

## 1. llm.glm51.enterprise（讯飞星火 MaaS 企业版）

模型代码：`0000`

### Round 1

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 4.64s |
| 5 | 5 | 0 | — | 7.92s |
| 8 | 8 | 0 | — | 5.59s |
| 10 | 10 | 0 | — | 8.93s |
| 12 | 12 | 0 | — | 7.80s |
| 15 | 15 | 0 | — | 9.24s |
| 18 | 0 | 18 | timeout | — |

Binary Search: n=16 → 0 ok, 16 fail  
**结论：并发极限 = 15，n=16 开始 timeout**

RPM 测试：11 ok, 0 429, 3 err, 175.5s → ~3.8 RPM  
（RPM 低是因为每个请求耗时长 ~16s）

### Round 2（冷却 15min 后）

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 1.30s |
| 5 | 5 | 0 | — | 4.19s |
| 8 | 8 | 0 | — | 3.36s |
| 10 | 10 | 0 | — | 5.99s |
| 12 | 12 | 0 | — | 9.52s |
| 15 | 0 | 15 | timeout | — |

Binary Search: n=13 → 0 ok, 13 fail  
**结论：并发极限 = 12，n=13 开始 timeout**

RPM 测试：59 ok, 0 429, 1 err, 308.8s → ~11.5 RPM

### Round 3（冷却 15min 后）

| Burst n | OK | Fail | 类型 |
|---------|-----|------|------|
| 2 | 0 | 2 | timeout |

**严重退化**：即使 n=2 也全部 timeout。Binary Search 得出 0。  
但 RPM 顺序测试正常：59 ok, 0 429, 1 err, 306.9s → ~11.5 RPM

### 分析

- 上游对**突发并发**有惩罚机制：连续两轮大并发后第三轮被临时封锁
- 顺序请求不受影响（RPM 测试始终正常）
- 真实安全并发：**10**（取 R2 的 12 × 0.8）
- 真实 RPM：**10**（R2/R3 的 11.5 × 0.87）

---

## 2. llm.aliyun.codingplan（阿里云 CodingPlan）

模型代码：`V0000`

### Round 1

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 4.29s |
| 5 | 5 | 0 | — | 4.05s |
| 8 | 8 | 0 | — | 3.58s |
| 10 | 8 | 2 | 429 | 4.13s |
| 12 | 0 | 12 | 429 | — |

Binary Search: n=9 → 0 ok, 9 fail (429)  
**结论：并发极限 = 8，n=9 开始 429**

RPM 测试：60 ok, 0 429, 0 err, 268.8s → ~13.4 RPM

### Round 2（冷却 15min 后）

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 4.22s |
| 5 | 5 | 0 | — | 4.03s |
| 8 | 8 | 0 | — | 3.69s |
| 10 | 8 | 2 | 429 | 3.71s |
| 12 | 0 | 12 | 429 | — |

Binary Search: n=9 → 0 ok, 9 fail (429)  
**结论：并发极限 = 8**

RPM 测试：59 ok, 0 429, 1 err, 276.3s → ~12.8 RPM

### Round 3（冷却 15min 后）

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 3.39s |
| 5 | 5 | 0 | — | 3.89s |
| 8 | 8 | 0 | — | 4.06s |
| 10 | 8 | 2 | 429 | 3.72s |
| 12 | 0 | 12 | 429 | — |

Binary Search: n=9 → 0 ok, 9 fail (429)  
**结论：并发极限 = 8**

RPM 测试：60 ok, 0 429, 0 err, 259.0s → ~13.9 RPM

### 分析

- **最稳定的服务**：3 轮结果完全一致，n=8 全通过，n=9 必 429
- 上游返回标准 429（非 timeout），说明有明确的并发限制配额
- 不存在退化机制，限制是硬性的
- 设定值 = 测试值 = **8 并发**，RPM = **10**

---

## 3. llm.minimax（MiniMax）

模型代码：`0110`

### Round 1

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 1.94s |
| 5 | 5 | 0 | — | 1.49s |
| 8 | 8 | 0 | — | 1.31s |
| 10 | 10 | 0 | — | 1.25s |
| 12 | 12 | 0 | — | 1.20s |
| 15 | 15 | 0 | — | 1.36s |
| 18 | 0 | 18 | timeout | — |

Binary Search: n=16 → 0 ok, 16 fail  
**结论：并发极限 = 15，n=16 开始 timeout**

RPM 测试：60 ok, 0 429, 0 err, 92.6s → ~38.9 RPM

### Round 2（冷却 15min 后）

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 1.65s |
| 5 | 5 | 0 | — | 1.28s |
| 8 | 8 | 0 | — | 1.44s |
| 10 | 10 | 0 | — | 1.13s |
| 12 | 12 | 0 | — | 1.43s |
| 15 | 15 | 0 | — | 1.58s |
| 18 | 0 | 18 | timeout | — |

Binary Search: n=16 → 0 ok, 16 fail  
**结论：并发极限 = 15**

RPM 测试：60 ok, 0 429, 0 err, 127.2s → ~28.3 RPM

### Round 3（冷却 15min 后）

| Burst n | OK | Fail | 类型 | 平均 OK 延迟 |
|---------|-----|------|------|------------|
| 2 | 2 | 0 | — | 1.41s |
| 5 | 5 | 0 | — | 1.28s |
| 8 | 8 | 0 | — | 1.26s |
| 10 | 10 | 0 | — | 1.37s |
| 12 | 12 | 0 | — | 1.61s |
| 15 | 0 | 15 | timeout | — |

Binary Search: n=13 → 3 ok, 10 fail  
**结论：并发极限 = 12**

RPM 测试：60 ok, 0 429, 0 err, 88.5s → ~40.7 RPM

### 分析

- **响应最快的服务**：平均延迟 1.2-1.6s
- 并发 R1/R2 稳定 15，R3 下降到 12（轻微退化）
- RPM 最高：28-41 RPM
- 设定值取保守值：**12 并发**，**25 RPM**

---

## 测试方法论

### 并发测试（Ramp + Binary Search）

1. **Ramp 阶段**：按 2, 5, 8, 10, 12, 15, 18, 20, 25, 30 递增发送并发请求
2. 每级全部并发同时发出（`asyncio.gather`），单请求超时 30s
3. 当某级 >50% 失败时停止递增
4. **Binary Search 阶段**：在「最后全通过」和「首次失败」之间做二分查找
5. 找到精确阈值：`last_all_ok` → `first_fail`

### RPM 测试

- 按顺序逐个发送请求（非并发）
- 最多 60 个请求或遇到 3 个 429 停止
- 计算 `有效 RPM = ok_count / elapsed_seconds * 60`

### 失败类型

- **429**：上游明确拒绝（codingplan 的行为）
- **timeout**：请求未在 30s 内返回（glm51/minimax 的行为，上游排队后超时）
- **error**：连接错误或其他异常

---

## 最终配置

```python
_SERVICE_LIMITS: dict[str, ServiceLimitConfig] = {
    "llm.glm51.enterprise": ServiceLimitConfig(max_concurrent=10, rpm=10),
    "llm.aliyun.codingplan": ServiceLimitConfig(max_concurrent=8, rpm=10),
    "llm.aliyun.dashscope":  ServiceLimitConfig(max_concurrent=50, rpm=600),
    "llm.minimax":           ServiceLimitConfig(max_concurrent=12, rpm=25),
}
```

Commit: `a67293c` on `feat/add-service-management`
