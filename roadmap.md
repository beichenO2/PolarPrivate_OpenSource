# PolarPrivate Roadmap

> 进度视图：当前阶段、最近完成、技术债与下一步。
> 事实源是 `polaris.json`，本文件只做进度/计划摘要。

## 当前状态

| 维度 | 状态 |
| --- | --- |
| 项目状态 | active |
| 角色 | Polarisor 生态唯一 LLM 网关 + 隐私脱敏门户 |

## 最近完成

- **限速逻辑重整（软性跨订阅引流，2026-06）**：移除本地令牌桶自节流与
  acquire 超时拒绝；限速不再向调用方报错；改为跨多订阅按权重分摊 +
  上游 429 时冷却该订阅并引流到未限流订阅。详见
  `docs/rate-limiting-algorithm.md`。

## 技术债 / 运维待办

| 项 | 说明 | 优先级 |
| --- | --- | --- |
| **日志轮转** | `backend/logs/launchd-stdout.log` 已膨胀到约 4.3GB（stderr 约 103MB）。需为 uvicorn/structlog 输出加按大小或天数的轮转，旧日志归档/清理，避免无限增长。 | 高 |
| **数据库瘦身** | `backend/privportal.db` 已膨胀到约 7.4GB。需排查异常增长来源（如 usage/log_buffer 等表）、按保留期清理并 `VACUUM`，必要时加写入限额与监控告警阈值。 | 高 |
| **进程僵尸防护** | 历史上出现过多份脱离 launchd 的 uvicorn/node 旧实例残留占端口/吃 CPU。`privportal start` 退出时应确保子 uvicorn 一并回收；重启脚本加“先清理同端口旧实例”步骤。 | 中 |

## 下一步

1. 安排日志轮转与数据库瘦身（上表「高」优先级两项）。
2. 评估限速软路由的权重/策略是否需按订阅额度微调（纯故障切换 vs 主动分摊）。
