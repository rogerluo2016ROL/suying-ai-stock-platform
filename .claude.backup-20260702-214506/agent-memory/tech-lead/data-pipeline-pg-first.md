---
name: data-pipeline-pg-first
description: ADR-006 决策：数据管道 PG 为主存储、SQLite fallback 的写入策略
metadata:
  type: project
---

数据管道写入顺序：先 PG 后 SQLite。PG 是主存储（服务层 screener/backtest/signal/prediction 均读 PG），SQLite 是 Kronos 训练管线的 legacy fallback。写入时 PG 失败应 ERROR，SQLite 失败仅 WARN。

**Why:** 当前 post_market sync 只写 SQLite，再通过 subprocess 桥到 PG，PG 数据完整性依赖脆弱的进程调用链路。ADR-006 决策 1+2 统一为 PG-first 直写，覆盖全部 P0+P1 表。

**How to apply:** 在 data-service sync 函数中，每个表写完 SQLite 后立即调用 `pg_writer.write_table()` 写 PG。使用 `INSERT ... ON CONFLICT DO UPDATE` (upsert) 实现幂等写入。不可先写 SQLite 再异步桥接 PG。
