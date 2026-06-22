# deploy-engineer 状态

**Task**: #5 — 起 ADR-013 UAT 隔离栈
**Status**: ✅ COMPLETED（PL 已签字 Conditional Promote, ADR-013 merged @ 2180fa7）
**Commit**: 0ba2a3e → 2180fa7
**Model**: deepseek-v4-pro

## 已完成

- [x] 拆除旧 suying-uat 栈（alembic 007 pre-ADR-013，含 pgdata 卷）
- [x] `.env.uat` 创建（端口偏移 +10000，PG 16432 / Redis 17379 / API 18080 / backend 19001 / 8001-8009→18001-18009）— **未入库**（gitignore `docker/.env.*`，host shell 注入 TUSHARE_TOKEN）
- [x] Postgres (16432) + Redis (17379) up & healthy
- [x] ths_daily 17 列 + BIGSERIAL PK + UNIQUE(code,trade_date) + idx_ths_daily_code_date — AC #2
- [x] **Retag 旧 suying-uat 镜像 → uat-adr013**（10 服务节省 30-60min build）
- [x] **`docker compose -p uat-adr013 --env-file .env.uat up -d` 起栈**
- [x] **冒烟各服务 `/health`**（PL 主导 round 2，10/10 health pass）
- [x] **data-service 宿主进程启动 → cb_sync 实跑** → ths_daily 3015 行 change_pct 100% 非 NULL
- [x] **`docker/uat-adr013-deploy.sh` 入库**（commit 2180fa7，复用脚本）
- [x] **部署报告**：QA round 2 报告 `docs/reviews/adr-013-e2e-uat-report-2026-06-22.md` 含部署证据

## 双轨部署教训（→ tech-lead memory）

- **Root cause 1**: retag 旧镜像导致 backend Alembic 008-011 缺失 → exit 3 restart loop
- **Root cause 2**: rebuild 后 init_postgres.sql 已含 post-011 schema, alembic 从 001 跑会 `multiple primary keys for table pledge_detail`
- **修复（4 步）**：(1) rebuild backend, (2) 手动跑 alembic 001→007（建 auth tables, init_sql 无）, (3) `alembic stamp 011`, (4) restart backend → lifespan no-op → seed_roles OK
- **永久教训**：`.claude/agent-memory/tech-lead/data-pipeline-dual-track-deployment.md`

## 已知风险（pre-existing, 不阻断 ADR-013）

- **DEF-3 Medium**: api-gateway:18080 路由到 `localhost:9001` 错（容器内寻址）→ follow-up issue
- **DEF-4 Medium**: docker-compose.yml 业务微服务缺 `JWT_SECRET_KEY` env → follow-up issue
- data-service 不在 docker-compose.yml，需宿主进程启动（按 ADR-006 设计）

## 质量门

- [x] UAT 栈 up & healthy（10/10 health pass round 2）
- [x] ADR-013 核心 AC pass^2 (AC-1/3/4/8 P0)
- [x] PL 签字 Conditional Promote (2026-06-22)
- [x] 部署证据落 progress/qa-engineer.md + docs/reviews/adr-013-e2e-uat-report-2026-06-22.md
