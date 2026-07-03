---
name: data-pipeline-dual-track-deployment
description: alembic + init_postgres.sql 双轨架构在 fresh DB / UAT 新栈部署时的正确顺序，避免 ALTER PK 冲突
metadata:
  type: project
---

# data-pipeline 双轨部署：fresh DB / UAT 新栈启动顺序

2026-06-22 ADR-013 实施 + SIT round 2 验证（backend-dev `progress/backend-dev.md`；ADR-013 Accepted）

**架构事实**：本项目 schema 存在双轨来源 —— `backend/alembic/versions/*` 系列 011 个迁移（auth/RBAC 表 + ths_daily 等业务表 schema 演进）+ `services/sql/init_postgres.sql`（业务表 DDL 兜底，docker entrypoint 灌入）。两轨内容**不完全等价**：alembic 008-011 含 ALTER PK / BIGSERIAL 升级等迁移步骤；init_postgres.sql 直接是「升级后形态」。

**fresh DB / UAT 新栈正确启动顺序**（必须严格按下表，否则启动失败）：

| 步 | 命令 | 作用 |
|---|---|---|
| 1 | `psql -f services/sql/init_postgres.sql` | docker entrypoint 自动跑；建业务表「升级后形态」（含 ths_daily 17 列 BIGSERIAL PK） |
| 2 | `cd backend && alembic upgrade 007` | 跑 alembic 001-007 建 auth/RBAC 表（init_postgres.sql 不含） |
| 3 | `cd backend && alembic stamp 011` | **跳过 008-011 ALTER 迁移**（业务表已是升级后形态，再跑 ALTER PK 会冲突报 already exists / column not found） |
| 4 | `uvicorn backend.app.main:app` | lifespan 内 `alembic upgrade head` no-op（已 stamp 到 head） |

**常见错误**：
- 直接 `alembic upgrade head` 不 stamp：008-011 ALTER 触发 `ths_daily.id` already BIGSERIAL / `cyq_perf` PK 已存在等错误，阻断启动
- 跳 stamp 直接起 backend：lifespan 自动 `alembic upgrade head`，同上失败
- 只跑 init_postgres.sql 不跑 alembic 001-007：auth 表缺失，登录接口 500

**触发场景**（必查本条）：
- 新人/CI/UAT 任何「全新 PG 实例」初始化
- docker-compose down -v 后重起
- 测试环境 PG 重置后

**何时无效**（即升级现有库）：
- 已有数据的库做迁移：照常 `alembic upgrade head`，stamp 仅用于 fresh

**实证锚点**：
- ADR-013 §决策 1（DB 现状即权威 17 列）
- backend-dev SIT round 2：alembic 011 + init_postgres.sql 同步段升 BIGSERIAL，回补 ths_daily change_pct 100% / NULL 0%
- 关联：[[data-pipeline-pg-first]]、[[phase0-uat-lessons]]（dev 必跑 docker compose up 自冒烟）
