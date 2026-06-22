# ADR-013: ths_daily schema 对齐 + cb_sync cols 修复 + ADR-012 W/S/LD 收尾

- 状态：**Proposed**（待 backend-dev 实施 SIT + reviewer audit 通过后升 Accepted）
- 日期：2026-06-22
- 决策者：tech-lead 起草；product-lead 排期实施
- 影响范围：单表 schema（ths_daily）+ cb_sync 单文件 cols 修复 + ADR-012 review follow-up 收尾（W-1 / W-2 / W-3 / S-1~S-4 / LD-1~LD-3）

## 上下文

ADR-012 方案 A 已 Accepted + 实施落地（commits 617793b / 06b14c7），三套写入路径合并到 `_insert_rows`、补 5 表 backfill、`validate_pipeline_consistency()` 启动期自检。SIT 实跑过程意外暴露多项 latent debt（详 `docs/reviews/adr-011-012-code-review-2026-06-22.md` §9）：

1. **LD-1（P1，本 ADR 主线）**：`cb_sync.sync_ths_daily` cols 含 `pct_change`，但 PG 表实际列是 `change_pct` —— thin wrapper 化后 `_insert_rows` 自动列过滤每次同步打印 `[WARN] _insert_rows ths_daily: 丢弃表不存在的列 ['pct_change']`，**每天 ths_daily 同步永远丢失 pct_change 列**，下游因子 `packages/kronos-factors/kronos_factors/engine/leader_intraday.py:318/327/417` 查 `SELECT pct_change FROM ths_daily` 经 `pg_adapter._COLUMN_MAP["pct_change":"change_pct"]` 翻译到 PG 物理列 `change_pct`，但 `change_pct` 长期无写入 → fallback。
2. **整张表是历史 schema drift**：`init_postgres.sql:551-561` DDL 8 列（`ts_code/trade_date/name/close/pct_change/avg_price/total_mv/float_mv` + PK(ts_code, trade_date)）vs PG 实际 17 列（`id integer / trade_date text / code text / name / open / high / low / close / pre_close / avg_price / change_pct / change / total_mv / float_mv / updated_at / vol / turnover_rate` + UNIQUE(code, trade_date)），列名 `ts_code → code`、`pct_change → change_pct`，主键从 PK 退化为 UNIQUE + 隐式自增 `id`，**DDL 与 DB 完全不一致**。从 grep 实证（`pct_change` vs `change_pct` 全 repo 出现）看，pg_adapter 在读侧用 `_COLUMN_MAP` 做了运行时 patch，但写侧无人 patch → 写入端永远丢列。

ADR-012 review 还转给本 ADR 收尾的 follow-up 包：
- **W-1（P1）**：`_pg_write` thin wrapper 在 `finally: db.close()` 关闭模块级缓存连接 `_pg_conn`，废除连接复用（每批写付 5-15ms 重连开销）
- **W-2（P2）**：`<3000 WARN` 分级被新 `data_volume_floor` 单档替代（1500-2999 区间温和告警吃掉）
- **W-3（P1）**：`sync_stk_factor_pro_backfill` 返回 `written = fetched 累计` 而非 `pg_written`（监控误导 ~10x）
- **S-1~S-4（P3）**：cb_sync.py dead 全局 / pg_writer.`_check_data_volume` dead / scheduler.py `pg_w if 'pg_w' in dir() else 0` 反模式 / `_register_backfill_handlers_late` 失效注释
- **LD-2（P3）**：`MONITORED_TABLES["index_basic"].date_col="updated_at"` 但表无此列
- **LD-3（P3）**：`_BACKFILL_MAP["rt_k"] = sync_rt_k` 签名缺 `days_back`

### 不做此决策的后果

1. ths_daily 每天同步丢列 `change_pct` 永远 NULL → leader_intraday 因子（`packages/kronos-factors/kronos_factors/engine/leader_intraday.py`）查 ths_daily.change_pct 长期 fallback、概念板块龙头识别失效（本 review 实证 SIT 5 [WARN] 输出）
2. cb_sync.sync_ths_daily 缺 name / total_mv / float_mv 6 列（API 返回 12 列但 sync 只拉 5 列），DDL 也缺这些 → 后续即使 schema 对齐也只能用 5 列子集
3. W-1 连接每批重连放弃 ADR-012 改造潜在性能收益（虽未导致功能 bug，但是改造目的之一）
4. W-3 监控字段语义错位让 `detect_data_gaps` / 后续 SRE dashboard 持续读到误导值

## 决策

### 决策 0：文件改动白名单（对 backend-dev 的硬约束）

⚠️ **本 ADR 升 Accepted 后明确列出允许修改的文件清单。backend-dev 不得修改清单外的任何文件。越界改动 = 违约，PL 直接回退。**（沿用 ADR-010/011/012 决策 0 风格。）

| # | 文件 | 允许改动 |
|---|---|---|
| 1 | `backend/alembic/versions/011_ths_daily_align.py`（新建） | 新建迁移：根据 DB 现状 introspect 出权威 17 列 DDL 形态（无破坏性变更，纯把 init_postgres.sql 拉齐到 DB 实际），同时把表「id integer 隐式自增」升级为 `id BIGSERIAL PRIMARY KEY` + 保留 UNIQUE(code, trade_date)；冗余索引清理一并在此 |
| 2 | `services/sql/init_postgres.sql:551-561` | 仅 ths_daily 段（8 行 → 17 行 + UNIQUE/索引声明），与 011 upgrade 后形态字面一致 |
| 3 | `services/data-service/app/sync/cb_sync.py` | (a) `sync_ths_daily` cols 列表 `pct_change` → `change_pct`、`ts_code` → `code`；(b) 扩展 cols 与 rows 拼装到 12 列（含 name / open / high / low / pre_close / change / total_mv / float_mv / vol / turnover_rate）对齐 Tushare `pro.ths_daily` 实际返回字段。**~~(c) S-1 cleanup~~ 已撤销，依据见 §决策修订 minor amend 2026-06-22** |
| 4 | `packages/kronos-data/kronos_data/etl.py` | 仅 `_insert_rows`（ADR-012 已扩展段）：W-2 增 `data_volume_warn: int \| None = None` 二档参数；W-1 修共享连接关闭（择一方案见 §决策 5.3）；其他 32+ sync 函数零碰 |
| 5 | `services/data-service/app/sync/pg_writer.py` | (a) `_pg_write` thin wrapper 配合 W-1 修复（不再 `finally: db.close()` 关闭模块级共享连接，或显式拿 `borrow=True` 临时连接，见 §决策 5.3）；(b) S-2 删 dead 函数 `_check_data_volume`（与 W-2 联动转移到 `_insert_rows`） |
| 6 | `services/data-service/app/scheduler.py` | (a) W-3 修复：`sync_stk_factor_pro_backfill` return 字段 `"written"` 改为 `total_pg`（PG 实际新增行数），保留 `"fetched": total_written`；S-3 修复 `pg_w if 'pg_w' in dir() else 0` 改为标准 try/except + 显式初始化；S-4 修复 L172-173 失效注释；(b) LD-2 收尾：`MONITORED_TABLES["index_basic"].date_col` 改为表实际存在的列（grep `index_basic` 实际列，建议 `list_date` 或 `update_flag`，或在 `_DESIGN_SKIP_MONITORING` 列入 index_basic 标记非时序数据）；(c) LD-3 收尾：把 `rt_k` / `rt_sw_k` 加入 `_DESIGN_SKIP_BACKFILL`（与 stocks/trade_cal 同档），sync_rt_k / sync_rt_sw_k 不改签名 |
| 7 | `progress/backend-dev.md` | W-3 注解：SIT 7 段补一行 `written=22037 实际为 fetched 累计；PG 新增 2037 行；ADR-013 已修返回字段语义`（dev 自己写 SIT 时一并落） |

**不在白名单内的常见误改项**（明确禁止）：
- 路径 #4 inline executemany 8+ 模块（announcements / cctv_news / mp_report / interact / policy_law / fina_mainbz / fina_audit / stock_profiles / namechange / stocks / rt_min / tushare）—— 留 ADR-015 治理
- 其他历史 drift 表（hk_holdings / repurchase / share_float / cyq_perf / stock_news_tushare / research_reports_tushare / stk_factor_pro / index_daily 等）的 schema 对齐 —— 留 ADR-014 audit 拆出
- 下游因子代码（`packages/kronos-factors/`）—— 整套 read 路径经 `pg_adapter._COLUMN_MAP` 翻译，写侧对齐后自动复活，不需要因子改动
- `pg_adapter._COLUMN_MAP` —— 保留 `pct_change → change_pct` 兼容映射（防回归 + 兼容历史 SQL）
- 其他 alembic 迁移（001-010）—— 仅追加 011
- CLAUDE.md Tech Stack 表 —— 不引新依赖

**Decision 0 范围声明**：本 ADR **只对齐 ths_daily 一表 schema + 修 cb_sync.sync_ths_daily cols + 收尾 ADR-012 review W-1/W-2/W-3 + S-1~S-4 + LD-1~LD-3**。其他历史 drift 表 audit 由 ADR-014 处理；路径 #4 治理由 ADR-015 处理；方案 B 注册中心由 ADR-016 留位。

### 决策 1：ths_daily DDL 以 DB 现状为权威

DB 实测 17 列已是事实标准（pg_adapter 读侧通过 `_COLUMN_MAP` patch 适配，下游因子能正常读出 NULL 然后走 fallback），本 ADR 的 init_postgres.sql + alembic 011 必须**反向追认 DB 现状**而非另立基线。理由：

1. 改 DB 现状（如把 `id integer` 删了或把 `change_pct` 改回 `pct_change`）会破坏 leader_intraday 历史已落盘数据（虽然 NULL 但行数存在）+ 已生效的 pg_adapter 翻译层
2. Tushare `pro.ths_daily` 实际返回字段是 `ts_code, trade_date, name, open, high, low, close, pre_close, avg_price, change, pct_change, vol, turnover_rate, total_mv, float_mv` —— DB 现有 17 列除 `id` 和 `updated_at` 之外的 15 列与 Tushare 字段 1:1 对齐，命名仅 `ts_code → code`、`pct_change → change_pct` 两处 normalization（与项目级 `code` 而非 `ts_code` 的命名约定一致，是 ADR-006 PG-first 直写时定的）
3. 旧 DDL 的 PK(ts_code, trade_date) 是错的（DB 是 UNIQUE(code, trade_date) + 隐式 id 自增），改回 PK 反而破坏 cyq_perf / top_inst 同型的「BIGSERIAL surrogate + UNIQUE 业务键」标准（参 ADR-011 §决策 2）

权威 17 列形态（alembic 011 upgrade 后 / init_postgres.sql 同步段）：

```sql
CREATE TABLE IF NOT EXISTS ths_daily (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT NOT NULL,
    trade_date    DATE NOT NULL,
    name          TEXT,
    open          DOUBLE PRECISION,
    high          DOUBLE PRECISION,
    low           DOUBLE PRECISION,
    close         DOUBLE PRECISION,
    pre_close     DOUBLE PRECISION,
    avg_price     DOUBLE PRECISION,
    change_pct    DOUBLE PRECISION,         -- Tushare API: pct_change → 表 change_pct (sw_daily 同型, 见 ADR-008)
    change        DOUBLE PRECISION,
    total_mv      DOUBLE PRECISION,
    float_mv      DOUBLE PRECISION,
    vol           DOUBLE PRECISION,
    turnover_rate DOUBLE PRECISION,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 同步时间戳, 非 Tushare 字段
    UNIQUE(code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_ths_daily_code_date ON ths_daily(code, trade_date);
```

**改动相比 DB 现状的两处升级**：
- `id integer` → `id BIGSERIAL PRIMARY KEY`（DB 现状是 integer 隐式自增但未声明 PK，本迁移补 PK 让 alembic 与现状一致）—— SIT 时若发现 DB id 已有数据则 alembic 用 `SELECT setval` 续接序列
- `trade_date text` → `trade_date date`（DB 是 text 反常，但 SIT 验证 text vs date 是否会引发数据不一致前，**本 ADR 保持 DB 现状 text**，列入 ADR-014 audit；011 upgrade 不改 trade_date 类型）—— 修订：保守起见，alembic 011 **不动 trade_date 类型**

### 决策 2：cb_sync.sync_ths_daily cols 修复（LD-1 主线）

`services/data-service/app/sync/cb_sync.py:95` 当前 cols：

```python
cols = ["ts_code", "trade_date", "close", "pct_change", "avg_price"]
```

改造后（对齐 DB 17 列中可由 Tushare 直接返回的 12 列业务列，不含 `id`/`updated_at`/`pre_close`——`pre_close` 是 Tushare 返回但语义上同 daily_kline.pre_close 重复，本 sync 保留可选）：

```python
cols = ["code", "trade_date", "name", "open", "high", "low", "close",
        "pre_close", "avg_price", "change_pct", "change",
        "total_mv", "float_mv", "vol", "turnover_rate"]
```

**字段命名映射**（API → 表）：
- `ts_code` → `code`（项目级 normalization）
- `pct_change` → `change_pct`（与 sw_daily 一致，ADR-008 同型）
- 其他 12 列字面一致

`rows` 拼装段同步扩展（`for _, r in df.iterrows(): rows.append((...))` 元组从 5 元扩展到 15 元，对应 cols 顺序），全部用 `_safe_val(r.get("..."))` 处理 NaN。

`_pg_bulk_insert("ths_daily", cols, ["code", "trade_date"], rows)` 的 `conflict_cols` 也同步改为 `["code", "trade_date"]`（与 UNIQUE 约束对齐）；底层 `_insert_rows` 用 `ON CONFLICT DO NOTHING` 依赖 UNIQUE 约束跳重，行为等价（参 ADR-012 §决策 5.2.bis）。

### 决策 3：W-1 共享连接关闭修复

ADR-012 review §2.3 复现：`_pg_write` `finally: db.close()` 关闭的是 `etl._get_etl_db()` 返回的**模块级缓存连接** `_pg_conn`（`etl.py:149-158`）。本 ADR 选**方案 1（简单）**：

`services/data-service/app/sync/pg_writer.py:_pg_write` 删 `finally: db.close()`，连接生命周期交给 `etl._get_etl_db()` 模块级缓存（首次建、进程退出关闭）。

**否决方案 2（borrow=True）**：给 `_get_etl_db()` 加 `borrow: bool = False` 参数让 `_pg_write` 拿临时连接 —— 工作量大、要 etl.py 改签名、`_insert_rows` 内部也要识别 borrow 标记，违背决策 0 「不动 32+ sync 函数」约束。

风险评估：方案 1 在多线程并发时若两个 caller 同时拿 `_pg_conn` 可能 race（psycopg2 单连接非线程安全），但实际 data-service scheduler 是 asyncio 单线程（`apscheduler.AsyncIOScheduler`），sync 函数串行执行 —— 无 race。验证项见 §决策 6 SIT 4.

### 决策 4：W-2 数据量告警二档恢复

`_insert_rows` 增 `data_volume_warn: int | None = None` 参数（默认关，向后兼容）：

```python
def _insert_rows(db, table, columns, rows,
                 retries: int = 0,
                 data_volume_floor: int | None = None,
                 data_volume_warn: int | None = None) -> int:
    # ... 现有逻辑 ...
    if data_volume_floor and written < data_volume_floor:
        logger.error(f"_insert_rows {table}: 写入量 {written} 低于 floor {data_volume_floor}, ...")
    elif data_volume_warn and written < data_volume_warn:
        logger.warning(f"_insert_rows {table}: 写入量 {written} 低于 warn 阈值 {data_volume_warn}, 可能上半场断网")
    return written
```

`pg_writer._VOLUME_FLOOR_MAP` 改 `_VOLUME_THRESHOLD_MAP`，含两档：

```python
_VOLUME_THRESHOLD_MAP = {
    "daily_kline":  {"floor": 1000, "warn": 3000},
    "stk_mins":     {"floor": 1000, "warn": 3000},
}

def _pg_write(table, columns, conflict_cols, rows) -> int:
    cfg = _VOLUME_THRESHOLD_MAP.get(table, {})
    return _insert_rows(db, table, columns, rows,
                        retries=3,
                        data_volume_floor=cfg.get("floor"),
                        data_volume_warn=cfg.get("warn"))
```

**联动 S-2**：`pg_writer._check_data_volume` dead 函数同时删除（双档逻辑已迁移到 `_insert_rows`）。

### 决策 5：W-3 written 语义修复

`services/data-service/app/scheduler.py:766-769` 当前：

```python
return {"table": "stk_factor_pro", "written": total_written, ...}
```

改为：

```python
return {"table": "stk_factor_pro",
        "written": total_pg,           # 实际 PG 落库行数（与 detect_data_gaps 语义一致）
        "fetched": total_written,      # 累计 fetch 行数（监控用，未去重）
        "pg_written": total_pg,        # 显式别名（向后兼容现有 SIT 7 输出格式）
        "sqlite_written": total_sqlite,
        "days_processed": ...}
```

**联动 S-3**：`pg_w if 'pg_w' in dir() else 0` 改为标准模式 ——

```python
try:
    pg_w = _pg_write(...)
except Exception as e:
    logger.warning("stk_factor_pro pg_write failed: %s", e)
    pg_w = 0
total_pg += pg_w
```

**联动 S-4**：scheduler.py L172-173 注释改为"`_BACKFILL_MAP['stk_factor_pro']` 延后到 L773 模块顶层直接赋值（绕过 forward declaration 限制）"。

### 决策 6：LD-2 / LD-3 收尾

**LD-2**（`index_basic.updated_at` 不存在）：grep 实证 `init_postgres.sql` `index_basic` 段（若有）；若 DB 实存 `index_basic` 表且无 `updated_at` 列，则在 `_DESIGN_SKIP_BACKFILL` 同档新增 `_DESIGN_SKIP_MONITORING = {"index_basic"}` 并改 `validate_pipeline_consistency` 检查 2 跳过此集合；或者直接把 index_basic 从 `MONITORED_TABLES` 移除（index_basic 是基础元数据非时序，监控价值有限）。**建议**：直接从 `MONITORED_TABLES` 移除（最干净）。

**LD-3**（`rt_k` / `rt_sw_k` 实时数据不应进 backfill）：加入 `_DESIGN_SKIP_BACKFILL`：

```python
_DESIGN_SKIP_BACKFILL = {"stocks", "trade_cal", "rt_k", "rt_sw_k"}
```

`sync_rt_k` / `sync_rt_sw_k` 签名保持不变（实时数据按 cron 拉，不接受 days_back）；validator 检查 3 跳过 design-skip 集合内的 handler。

### 决策 7：SIT 验证清单（backend-dev 自跑 + 写入 progress/backend-dev.md）

| # | 验证项 | 命令 / SQL | 期望结果 |
|---|---|---|---|
| 1 | alembic 011 upgrade 跑通 | `cd backend && .venv/bin/alembic upgrade head` | `Running upgrade 010 -> 011`；alembic_version = 011 |
| 2 | upgrade 幂等 | 重跑 `alembic upgrade head` | 无错、no-op |
| 3 | downgrade 可行 | `alembic downgrade -1` + `alembic upgrade head` | 双向 OK，无数据丢失（保守迁移） |
| 4 | DB 17 列形态 | `psql -c "\d ths_daily"` | 17 列 + UNIQUE(code, trade_date) + BIGSERIAL PK + idx_ths_daily_code_date |
| 5 | cb_sync.sync_ths_daily 实跑 | `KRONOS_PG_URL=... python3 -c "from app.sync.cb_sync import sync_ths_daily; print(sync_ths_daily(days_back=2))"` | `status=ok`；**无 `[WARN] _insert_rows ths_daily: 丢弃表不存在的列` 警告**；written>0 |
| 6 | change_pct 非 NULL 验证 | `SELECT COUNT(*) FROM ths_daily WHERE change_pct IS NOT NULL AND trade_date >= CURRENT_DATE - 7` | > 0（写侧字段对齐后，新写入数据 change_pct 不再 NULL） |
| 7 | name / total_mv / vol 落盘 | `SELECT COUNT(*) FROM ths_daily WHERE name IS NOT NULL AND vol IS NOT NULL AND trade_date >= CURRENT_DATE - 7` | > 0（新增 6 列正确写入） |
| 8 | validator 不再 ths_daily 警告 | scheduler 启动日志 grep `Pipeline validate` | 无 ths_daily 相关 WARN |
| 9 | leader_intraday 因子读 ths_daily 复活 | grep `pg_adapter._COLUMN_MAP["pct_change"]` 仍存在 + leader_intraday 因子抽样 1 股 | pg_adapter 翻译 `pct_change → change_pct` 不变；因子读出非 NULL（脱离 fallback） |
| 10 | W-1 共享连接复用验证 | 跑 `data-service` 完整 cron 一轮，`SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE '%data-service%'` | 单进程内连接数稳定（不反复 connect/disconnect） |
| 11 | W-2 二档告警触发 | 单测 mock `_insert_rows` 写入 2000 行 + `data_volume_warn=3000` | logger.warning 命中"低于 warn 阈值"，无 ERROR |
| 12 | W-3 written 语义修复 | `python -c "from app.scheduler import sync_stk_factor_pro_backfill; r=sync_stk_factor_pro_backfill(days_back=7); print(r)"` | `r["written"] == r["pg_written"]`，`r["fetched"] > r["written"]`（去重生效可见） |
| 13 | LD-2/LD-3 validator 静默 | scheduler 启动日志 | 无 index_basic / rt_k / rt_sw_k 三项 WARN |
| 14 | S-1 dead code 已删 | grep cb_sync.py `MAX_RETRIES\|^PG_URL\|^import time` | 0 命中（thin wrapper 化后未使用） |
| 15 | S-2 dead 函数已删 | grep pg_writer.py `def _check_data_volume` | 0 命中 |
| 16 | S-3 反模式已修 | grep scheduler.py `if 'pg_w' in dir\(\)` | 0 命中 |
| 17 | git diff 白名单审计 | `git diff main --stat` | 仅命中决策 0 白名单 7 文件 |

### 决策 8：分阶段实施顺序

1. **阶段 1 — alembic 011 + init_postgres.sql 同步**（白名单 #1 + #2）：DB 现状 introspect → DDL → SIT 1-4。**回滚点 A**。
2. **阶段 2 — cb_sync.sync_ths_daily cols 修复 + S-1 cleanup**（白名单 #3）：cols 改造 + dead code 删除 + 实跑回补；SIT 5-7。**回滚点 B**。
3. **阶段 3 — W-1 共享连接修复**（白名单 #4 + #5）：删 `finally: db.close()`；SIT 10。**回滚点 C**。
4. **阶段 4 — W-2 二档告警 + S-2 dead 函数清理**（白名单 #4 + #5）：`_insert_rows` 加 `data_volume_warn` + `_VOLUME_THRESHOLD_MAP` 双档；SIT 11。**回滚点 D**。
5. **阶段 5 — W-3 written 语义 + S-3 + S-4**（白名单 #6）：scheduler 返回字段修 + 反模式修 + 注释修；SIT 12。**回滚点 E**。
6. **阶段 6 — LD-2 / LD-3 收尾**（白名单 #6）：`_DESIGN_SKIP_BACKFILL` 扩展 + index_basic 处理；SIT 13。**回滚点 F**。
7. **阶段 7 — progress/backend-dev.md SIT 7 注解 + git diff 白名单审计**（白名单 #7）：SIT 14-17。

任一阶段失败可独立回滚不影响已合并阶段。

## 备选方案

- **A. 把 cb_sync.sync_ths_daily 整体合并到 etl.sync_ths_daily（packages/kronos-data）** —— pros: 消除 cb_sync.py 这层包袱；cons: 跨 service 边界（cb_sync 在 data-service，etl 在 kronos-data 包），违反 ADR-006 分层 + ADR-012 §决策 5.2.bis 「cb_sync 在 services/data-service 层，按 ADR-006 分层应通过 pg_writer 走业务侧入口」原则。**否决**。
- **B. 不修 cb_sync cols，只在 alembic 011 把 DB 列名 `change_pct → pct_change`，让 sync 不变** —— pros: sync 零改动；cons: (i) DB 现状 `change_pct` 是与 sw_daily（ADR-008 已 Accepted）一致的项目级命名约定，回退到 Tushare 原名破坏一致性；(ii) leader_intraday 因子 `SELECT pct_change FROM ths_daily` 经 pg_adapter 翻译能跑，但下游所有 `change_pct` 直接引用（grep `change_pct` 实证含 data_quality_check.sql / data_quality_fix.sql 等）都要改；(iii) 与 ADR-008 sw_daily 同型背离。**否决**。
- **C. 把 LD-2 / LD-3 拆独立 backlog 而非本 ADR 收尾** —— pros: 本 ADR 更聚焦 ths_daily；cons: LD-2 / LD-3 是 ADR-012 validator 实跑发现的低优先级误报，单立 ADR 不划算（< 10 行改动），合并到本 ADR 阶段 6 一次性处理更经济。**否决**。
- **D. W-3 改 monitor dashboard 解释 written 字段 instead of 改 sync 返回** —— pros: 不动 sync code；cons: 所有读 `result["written"]` 的下游（detect_data_gaps / trigger_data_backfill / 未来 SRE dashboard）都要文档化 caveat，违反「单一来源原则」。改 sync 返回是根因修复。**否决**。
- **E. W-1 选 borrow=True 方案** —— 见 §决策 3 论证，**否决**（工作量与改动面超出本 ADR 范围）。
- **F. 推迟整张 ths_daily schema 对齐到 ADR-014 audit 后** —— pros: 让 ADR-014 一次性规划；cons: ths_daily 每天丢列每天造成因子 fallback，是「正在出血」的故障，等不到 audit 完成。**否决**。

## 影响

- `backend/alembic/versions/011_ths_daily_align.py`（新建）：~100 行 op.execute 原生 SQL，含 upgrade（追认 DB 现状 + 补 BIGSERIAL PK + 索引）+ downgrade（逆序）
- `services/sql/init_postgres.sql:551-561`：8 行 DDL → 17 行 DDL（与 011 upgrade 后字面一致）
- `services/data-service/app/sync/cb_sync.py`：sync_ths_daily cols 5 → 15 + rows 拼装段 + S-1 删 3 行 dead code，约 -3 / +20 行
- `packages/kronos-data/kronos_data/etl.py`：`_insert_rows` 加 `data_volume_warn` 参数 + warn 分支，约 +6 行
- `services/data-service/app/sync/pg_writer.py`：删 `finally: db.close()`（-1 行）+ `_VOLUME_FLOOR_MAP` 改 `_VOLUME_THRESHOLD_MAP` 双档（+3 行）+ 删 `_check_data_volume` dead 函数（-14 行）
- `services/data-service/app/scheduler.py`：W-3 字段语义改 + S-3 反模式修 + S-4 注释修 + LD-2/LD-3 `_DESIGN_SKIP_BACKFILL` 扩展，约 +8 / -5 行
- `progress/backend-dev.md`：SIT 7 段补注解 +1 行
- 下游因子代码（`packages/kronos-factors/`）：**零改动**（pg_adapter 翻译层保留）
- CLAUDE.md Tech Stack：**无更新**（不引新依赖）

### 对成本

- 无 API / 算力 / 存储增量
- 工作量：backend-dev 2-3 day（alembic 0.5d + cb_sync cols 0.5d + W-1/W-2/W-3 0.5d + S-1~S-4 + LD-2/LD-3 0.5d + SIT 0.5-1d）

### 对运维

- ths_daily 每天同步从「丢列 5 列」恢复到「写入 15 列」，下游因子从 fallback 切到真实数据
- scheduler 启动日志从 2 项 WARN（index_basic + rt_k）降为 0 项
- 监控 dashboard 读 stk_factor_pro `written` 字段从误导值切换到真实 PG 落库行数

### 风险

1. **alembic 011 升 BIGSERIAL PK 风险**：DB 现状 `id integer` 已有数据但无 PK 约束。alembic 011 需先 `SELECT MAX(id)` → `setval('ths_daily_id_seq', max_id)`（若序列存在）→ 再 ADD CONSTRAINT PK。**缓解**：011 upgrade 内置 setval 续接 + IF NOT EXISTS 兜底。
2. **cb_sync cols 扩展后 Tushare API quota 不变但每次返回数据放大 3 倍**（5 列 → 15 列）—— 不影响 quota（按调用次数计），仅 PG 写入量 ↑ ~3x。**缓解**：data_volume_floor / warn 不变（floor 不针对 ths_daily）。
3. **W-1 删 `finally: db.close()` 后若 scheduler 进程异常退出（OOM / kill -9），共享连接不会被关闭** —— PG 端 max_connections 有上限，长期挂起连接会耗尽。**缓解**：apscheduler shutdown hook 注册 `_pg_conn.close()`；或保持现状不修 W-1，仅作为 ADR-016 升级时的优化项。**本 ADR 暂选保守方案：保留 `finally: db.close()`，把 W-1 改为「documentation only」**。修订决策 3 → **W-1 改为 backlog，不在本 ADR 实施**；阶段 3 删除，重编号。

### 决策修订（基于风险评估）

**W-1 实施移除本 ADR**：上述风险评估发现「删 `finally: db.close()`」要配套进程 shutdown hook 才能安全，工作量超出本 ADR 边界。W-1 改为 **ADR-014 / ADR-015 实施时顺手处理**或独立 backlog。本 ADR §决策 3 / §决策 8 阶段 3 / §决策 7 SIT 10 / §决策 0 白名单 #4-W-1 部分**移除**。

修订后白名单 #4（etl.py）：仅加 `data_volume_warn` 参数（W-2）；W-1 不动。
修订后阶段顺序：阶段 1（alembic） → 阶段 2（cb_sync cols + S-1） → 阶段 3（W-2 二档 + S-2） → 阶段 4（W-3 + S-3 + S-4） → 阶段 5（LD-2/LD-3） → 阶段 6（progress + git diff 审计）。SIT 10 删除，重编号 17 → 16 项。

**2026-06-22 minor amend — 删 §决策 0 白名单 #3 的 S-1 子项**：backend-dev 实施阶段 2 时实证 grep 发现 ADR-012 review §9 S-1 误分类——`cb_sync.py` 中 `MAX_RETRIES` 12 处主动引用（重试上限）、`PG_URL` L161 `psycopg2.connect(PG_URL)` 实际读取 `cb_basic` 表、`import time` 配套 `time.sleep` 4 处指数退避，三者均为活代码；若按 S-1 删除，整文件 `NameError` 不可 import。依据：实证证据落 `progress/backend-dev.md` L890-953「S-1 偏离说明」段；上游误分类落 `docs/reviews/adr-011-012-code-review-2026-06-22.md` §9 S-1 子项。本次 amend 仅撤白名单 #3 子项 (c)，**保留** sync_ths_daily cols 5 → 15 改造（子项 a/b 不变）；S-1 配套修订：本 ADR §决策 8 阶段 2 标题维持「cb_sync cols 修复 + S-1 cleanup」字面、但 S-1 已不实施，SIT 14「S-1 dead code 已删」改判为 N/A（dev 在 progress 文件留 grep 反证）。ADR 状态保持 **Proposed**（minor amend 不升 Accepted）。


## 本 ADR 不覆盖的决策

- **其他历史 drift 表的 schema 对齐**（hk_holdings / repurchase / share_float / cyq_perf / stock_news_tushare / research_reports_tushare / stk_factor_pro / index_daily 等）—— 留 **ADR-014**（一次性 audit + 索引登记）后按 diff 严重度拆 ADR-014.X 子 ADR
- **路径 #4 inline executemany 8+ 模块治理** —— 留 **ADR-015**
- **方案 B 注册中心升级** —— 留 **ADR-016**（ADR-012 已 Accepted 方案 A，升级触发信号见 ADR-012 §决策 4）
- **W-1 `_pg_write` 共享连接关闭** —— 本 ADR 风险评估后推迟到 ADR-014 / ADR-015 实施时顺手处理，配套 apscheduler shutdown hook
- **trade_date 类型 text vs date 统一** —— DB 现状 text 反常但下游已适配；列入 ADR-014 audit 评估，本 ADR 不动
- **pg_adapter._COLUMN_MAP 清理** —— `pct_change → change_pct` 翻译保留（兼容历史 SQL）；未来 `_COLUMN_MAP` 退役时机由 ADR-016 评估
- **leader_intraday 因子抽样验证** —— 本 ADR SIT 9 仅冒烟，深度抽样（多股 + 多日 + 与 fallback 对比）由 reviewer 在 audit 时随机抽 1-2 股复核

## 后续工作

- [ ] **product-lead**：派 backend-dev 按 §决策 8 阶段 1-6 实施（与 ADR-014 / ADR-015 互相独立，可并行排期但本 ADR 优先级 P1 高于 014/015）
- [ ] **backend-dev**：实施 + SIT 16 项 + 证据落 `progress/backend-dev.md`（含 W-3 SIT 7 注解修订）
- [ ] **code-reviewer**：audit alembic 011 不破坏既有数据 + cb_sync cols 与 Tushare API 字段对齐 + LD-2/LD-3 收尾真实生效
- [ ] **tech-lead**：实施 + UAT 通过后立 **ADR-014**

## 版本与查证

**查证基线日期**：2026-06-22（Proposed 起稿当日；与 ADR-008/009/010/011/012 同基线，无新查证）

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | 与 ADR-008~012 同基线；alembic 011 `op.execute` 原生 SQL + `information_schema` introspect 走 psycopg2 |
| PostgreSQL | 15.x | 17.x | 2 major | Active 至 2027-11 | 与 ADR-001/006/008-012 一致；`BIGSERIAL`、`UNIQUE`、`SELECT setval` 均 PG 15 原生 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | 与 ADR-008~012 同基线；本 ADR 011 迁移沿用 ADR-010/011 同型骨架 |
| Tushare | 1.4.29 | 1.4.29 | 0 | Active | `pro.ths_daily(trade_date)` 接口 15 字段（已在 cb_sync.py:92 注释列出）；与 ADR-008~011 同基线 |

**实证 grep 来源**（2026-06-22）：

| 实证项 | 命令 | 结果 |
|---|---|---|
| ths_daily DB 17 列 | `psql -c "\d ths_daily"` | id/trade_date(text)/code/name/open/high/low/close/pre_close/avg_price/change_pct/change/total_mv/float_mv/updated_at(text)/vol/turnover_rate；UNIQUE(code, trade_date) |
| init_postgres.sql 8 列 | Read services/sql/init_postgres.sql:551-561 | ts_code/trade_date/name/close/pct_change/avg_price/total_mv/float_mv + PK(ts_code, trade_date) |
| cb_sync.sync_ths_daily 当前 cols | grep `cols = \["ts_code"` services/data-service/app/sync/cb_sync.py:95 | 5 列只含 ts_code/trade_date/close/pct_change/avg_price |
| pg_adapter `_COLUMN_MAP` 翻译 | grep `"pct_change":` packages/kronos-factors/kronos_factors/pg_adapter.py:72 | `"pct_change": "change_pct"` — ths_daily/sw_daily Tushare API 字段名 |
| leader_intraday 读 ths_daily | grep `pct_change FROM ths_daily` packages/kronos-factors/kronos_factors/engine/leader_intraday.py | L318/L327/L417 三处查询经 pg_adapter 翻译落到 change_pct |
| data_quality_fix.sql 已知 drift | Read services/sql/data_quality_fix.sql:215-225 | 历史曾有 fix 脚本统一 `pct_change → change_pct`（运维侧已意识到分裂，本 ADR 在 schema 层根治） |

**与 CLAUDE.md "数据管道" 段一致性**：`## Tech Stack` 表 `数据管道` 行不变；本 ADR 是 ADR-012 方案 A 实施 follow-up + 单表 schema 对齐，不引新行。

---

**Hand-off 给 backend-dev**（限额重置后 / 新会话）：

按 §决策 8 修订后的 6 阶段顺序，严格不越白名单（§决策 0）：

1. 阶段 1：起草 `backend/alembic/versions/011_ths_daily_align.py`（含 BIGSERIAL setval 续接）+ 改 `init_postgres.sql:551-561` 字面与 upgrade 后一致
2. 阶段 2：改 `cb_sync.sync_ths_daily` cols 5 → 15 + rows 拼装 + 删 dead code（S-1）
3. 阶段 3：`etl._insert_rows` 加 `data_volume_warn` 参数 + `pg_writer._VOLUME_THRESHOLD_MAP` 双档 + 删 `_check_data_volume` dead 函数（S-2）
4. 阶段 4：`scheduler.sync_stk_factor_pro_backfill` 返回字段语义改 + S-3 反模式修 + S-4 注释修
5. 阶段 5：`_DESIGN_SKIP_BACKFILL` 扩 rt_k / rt_sw_k；index_basic 从 MONITORED_TABLES 移除（LD-2/LD-3）
6. 阶段 6：`progress/backend-dev.md` SIT 7 段补 written 语义注解 + git diff 白名单审计

SIT 验证 16 项（§决策 7 修订后清单），证据落 `progress/backend-dev.md` 的 `**SIT 证据**` 段；任一项 `[ ]` 未通过不得进 code-review。

白名单越界 = 违约，PL 直接回退。
