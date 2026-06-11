---
name: dual-db-phase-a
description: Phase A 双库并存（SQLite 46旧表 + PostgreSQL 5新表），Phase B 全量迁 PG
metadata:
  type: project
---

ADR-005 D1/D6 决策：Phase A 新表（schemes/scheme_positions/scheme_daily_snapshots/alert_rules/alerts）走 PostgreSQL + Alembic，旧 46 表保持 SQLite + Flask webui。Phase B 一次性全量迁移到 PG+TimescaleDB。

**Why:** PRD §6 要求 FastAPI + PostgreSQL，但全量迁移 46 表 + 12GB 数据预估 3-5 天，会阻塞 Phase A 交付。双库并存隔离风险，不影响现有选股/回测功能。

**How to apply:** backend-dev 新路由走 FastAPI + PG，旧路由保持 Flask + SQLite 只读。Phase B 触发条件：Phase A 交付后，product-lead 发起迁移专项。

See also: [[d3-shadcn-deferred]]
