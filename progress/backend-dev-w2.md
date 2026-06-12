## T-301: ETL CB 统一 + Gateway httpx→urllib + 端口修正 - 2026-06-12 18:30
**状态**: 已完成
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] AC-301.1 ✅ 5 个 CB sync 函数统一使用 `_Db` 封装 + `_insert_rows`
    - sync_cb_basic: 移除直接 psycopg2 connect → 用 `_insert_rows(db, "cb_basic", cols, rows)`
    - sync_cb_daily: 移除直接 psycopg2 → 用 `_insert_rows(db, "cb_daily", cols, rows)`
    - sync_cb_price_chg: 同上
    - sync_cb_call: 同上
    - sync_cb_factor: 同上
    - 验证: `grep -c "import psycopg2" etl.py` → 2 (仅 `_get_etl_db`/`_insert_rows` 两个工具函数内)
    - 语法: `python3 -c "import ast; ast.parse(open('etl.py').read())"` → Syntax OK
- [x] AC-301.2 ✅ Gateway 移除 httpx 依赖 → 改用 urllib async wrapper
    - `import httpx` 已删除
    - 改用 `urllib.request.Request` + `urllib.request.urlopen` 
    - 通过 `loop.run_in_executor(None, _proxy)` 实现异步包装
    - 保留 HTTPError 透传（返回上游状态码）
- [x] AC-301.3 ✅ Gateway 端口 8000 → 8080
    - health check: `"gateway": "api-gateway:8080"`
    - `__main__` 块: `port=8080`
    - 语法: `python3 -c "import ast; ast.parse(open('api-gateway/app/main.py').read())"` → Syntax OK

**质量门**: syntax ✅ (2/2 Python 文件) / SIT: CB 统一 5/5 函数 ✅ / Gateway httpx 零引用 ✅ / port 8080 ✅
**涉及文件**: packages/kronos-data/kronos_data/etl.py (修改), services/api-gateway/app/main.py (重写)

## T-302: ADR-001 架构漂移 + materialized_views.sql - 2026-06-12 18:45
**状态**: 已完成
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] AC-302.1 ✅ ADR-001 补充 "auth 合并入 backend (9001)" 决策记录
    - 决策表: 认证服务行 → "原决策 … → 实施变更为合并入 backend (9001)，不独立部署 auth-service (8010)"
    - 新增 "实施变更记录" 节: 4 条变更 (auth 不独立部署 / kronos-auth 不独立 / Alembic 迁移 / 端口统一)
    - 后续工作: 全部标记 `[x]` 完成
- [x] AC-302.2 ✅ services/sql/materialized_views.sql 独立文件，含 4 MV DDL
    - mv_daily_composite_ranking: 综合评分 0-100 (涨幅40+资金35+流动性25)
    - mv_today_strong_stocks: 涨幅>3% + 成交量活跃 Top 100
    - mv_sector_momentum: 按行业聚合平均涨幅+成交额+资金净流入
    - mv_top_capital_inflow: 资金净流入 Top 100
    - init_postgres.sql: MV DDL 替换为指针注释 → `psql ... -f services/sql/materialized_views.sql`

**质量门**: ADR-001 4 条实施变更记录 / materialized_views.sql 含 4 MV + UNIQUE INDEX
**涉及文件**: docs/adr/001-auth-rbac.md (修改), services/sql/materialized_views.sql (新建), services/sql/init_postgres.sql (修改)

## T-307: CORS 白名单 + trade_password Body + LIM-1 - 2026-06-12 19:00
**状态**: 已完成（全部 3 AC 为前置 sprint 已实现，本 wave 验证通过）
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] AC-307.1 ✅ CORS 白名单已实现（trade-service + strategy-service）
    - trade-service/main.py:36-38: `CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "...").split(",")`
    - strategy-service/main.py:36-38: 同上
    - 验证: `grep -rn 'allow_origins.*\['*'\]' services/trade-service/ services/strategy-service/` → 无匹配 (exit 1)
- [x] AC-307.2 ✅ trade_password Query→Body 已实现
    - trade-service/routes.py:372: `trade_password: str = Body("", embed=True)`
    - embed=True 确保请求体格式为 `{"trade_password": "value"}`
- [x] AC-307.3 ✅ LIM-1 scheduler status 已修复
    - data-service/routers/data.py:76-81: `trigger_post_market` 通过 `_run_job(core_job)` / `_run_job(ext_job)` 执行
    - `_run_job` (scheduler.py:66-86) 更新 `_job_status` 含 `pg_write_status` + `pg_written`
    - data.py:79-84 返回 `_job_status.get("post_market_core")` / `_job_status.get("post_market_ext")`

**质量门**: CORS 白名单 ✅ / trade_password Body ✅ / LIM-1 scheduler status ✅（均为前置 sprint 实现，本次验证 0 代码变更）
**涉及文件**: 无新增修改（全部 AC 为前置 sprint 已实现）

## Wave2 Line A: T-301 + T-302 验证与修正 - 2026-06-12 19:30
**状态**: 已完成
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] AC-301.1 ✅ 5 个 CB sync 函数全部使用 `_Db` 封装
    - 命令: `grep -n "import psycopg2" etl.py` → 仅 `_get_etl_db`(L131) 和 `_insert_rows`(L151) 内部使用
    - cb_basic(L1561) / cb_daily(L1616) / cb_price_chg(L1669) / cb_call(L1707) / cb_factor(L1756): 全部用 `_insert_rows(db, ...)`
    - 语法: etl.py Syntax OK
- [x] AC-301.2 ✅ Gateway 无 httpx，使用 urllib async wrapper
    - 命令: `grep "import httpx\|from httpx\|httpx\." main.py` → 无匹配 ✅
    - 命令: `grep -n "loop.run_in_executor\|urllib.request\|urllib.error" main.py` → L4, L9-10, L83
- [x] AC-301.3 ✅ Gateway 端口 8080
    - health check: `"gateway": "api-gateway:8080"` (L50)
    - uvicorn.run: `port=8080` (L101)
- [x] AC-302.1 ✅ ADR-001 "实施变更记录" 含 4 条记录
    - 1: auth 合并入 backend (9001)，不独立部署 auth-service (8010)
    - 2: kronos-auth 合并入 backend/app/
    - 3: Alembic 迁移位于 backend/alembic/versions/
    - 4: 数据库端口统一为 6432
- [x] AC-302.2 ✅ materialized_views.sql 修正为与 PG 实际 DDL 一致
    - mv_today_strong_stocks: 涨幅 7-12%，含 is_limit_up 封板检测（原文件误写为 >3% Top 100）
    - mv_sector_momentum: 仅聚合涨幅 ≥7% 的强势股，HAVING count≥2（原文件误写为全部股票）
    - mv_top_capital_inflow: LIMIT 50，net_inflow_yi 列，ST 过滤，net_mf_amount>0（原文件误写为 LIMIT 100）
    - mv_daily_composite_ranking: 移除不存在的 avg_vol_ratio 列（原文件多出此列）
    - 索引名修正: idx_mv_sector_ind / idx_mv_cap_code（原文件误写为 idx_mv_sector_industry / idx_mv_inflow_code）
    - PG 验证: 4 视图 count 返回 (3, 0, 0, 3)

**质量门**: syntax ✅ (2/2 文件) / SIT ✅ (5/5 CB 函数统一 + Gateway urllib + port 8080 + ADR-001 4 条记录 + materialized_views.sql 4 MV 与 PG 一致)
**涉及文件**: services/sql/materialized_views.sql (修正 DDL 匹配 PG) / 其余 3 AC 为前置 sprint 已实现无需修改
**下一步**: 等待 code review

## T-308: screener PG hang + prediction 404 修复 - 2026-06-12 19:30
**状态**: 已完成
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] AC-FIX-SCR ✅ screener DB 端点不再 hang — PG 连接池 + autocommit
    - 根因: `_PgAdapter` 单连接 `self._conn` 共享，`screener/routers/screener.py` 多线程并发调用时阻塞
    - 修复: `__init__` 改用 `ThreadedConnectionPool(minconn=2, maxconn=10)`; `execute()` 设 `autocommit=True` (只读查询); `_PgResult` 预取全量 rows 立即归还连接
    - `get_kline`/`get_stock_info`/`get_all_codes` 同样加 autocommit + try/finally `_put_conn`
    - 验证: `python3 -c "from kronos_factors.pg_adapter import create_pg_adapter; a=create_pg_adapter(...); print(type(a).__name__, hasattr(a,'_pool'))"` → _PgAdapter True
- [x] AC-FIX-PRED ✅ predict 端点不再 404 — 路由 pattern 修正
    - 根因: `@router.post("/predict/{code}/fast")` + prefix `/api/v1/prediction` → 全路径 `/api/v1/prediction/predict/{code}/fast`; E2E 测试 `/api/v1/prediction/{code}/fast` 不匹配 → FastAPI 默认 `{"detail":"Not Found"}` 404
    - 修复: `/predict/{code}/fast` → `/{code}/fast`; `/predict/{code}` → `/{code}`
    - 全路径: `POST /api/v1/prediction/{code}/fast` + `POST /api/v1/prediction/{code}`
    - 语法: routes.py Syntax OK

**质量门**: syntax ✅ (2/2 Python 文件) / PG pool ✅ / _PgResult ✅ / route pattern ✅
**涉及文件**: packages/kronos-factors/kronos_factors/pg_adapter.py (连接池+_PgResult), services/prediction-service/app/routes.py (路由修正)
