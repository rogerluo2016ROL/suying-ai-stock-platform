# 数据治理一次性推进记录

> 日期: 2026-07-01  
> 范围: Tushare 接口目录、PG 表/字段、ETL 写入、后端数据状态、前端数据更新页契约  
> 原则: 只读审计优先；不调用 Tushare；不改历史数据；先把错误口径显性化。

## 已落地

1. 新增只读数据资产目录工具：`services/sql/audit/tushare_data_catalog.py`
   - 读取本地 Tushare 接口文档 `skills/tushare-data/references/数据接口.md`。
   - 读取 `services/signal-service/app/routes.py` 的前端数据源登记和同步映射。
   - 读取 `services/data-service/app/scheduler.py` 的监控表和日期列。
   - 解析 `packages/kronos-data/kronos_data/etl.py` 的 `_insert_rows` 写入目标。
   - 连接 PG 读取真实表字段、行数、最早日期、最新日期。
   - 输出当前目录：`docs/data-governance/data-catalog-current.md`。
   - 已把本地 Tushare 文档中的 224 个 API 全部纳入覆盖矩阵；未实现的 API 也必须在矩阵里有治理状态。

2. 修正前端/后端数据状态口径
   - `research_reports` 改为真实 Tushare 表 `research_reports_tushare`。
   - 外提 `DATA_STATUS_DATE_COLUMNS`，可测试、可审计。
   - 修正日期列：
     - `financial_balance`: `end_date`
     - `stock_news_tushare`: `pub_time`
     - `research_reports_tushare`: `pub_date`
     - `broker_recommend`: `month`
     - `dividend_data`: `ex_date`
   - 补齐 `_SYNC_MAP`：
     - `stocks`: 走 data-service `/sync/stocks`
     - `stk_factor_pro`: 走 data-service backfill

3. 新增测试
   - `services/sql/audit/test_tushare_data_catalog.py`
   - 扩展 `services/signal-service/tests/test_signal_contracts.py`

4. 推进 P0 低风险修复
   - `moneyflow_hsgt` 初始化建表从旧 3 列补齐为真实 PG 的 9 列，避免 fresh 部署和现有库结构分叉。
   - 新增测试锁定 `moneyflow_hsgt` 的初始化 SQL 字段契约。

5. 全量 Tushare 原始层接入
   - 对 191 个此前待分类/未实现 API 建立 `ts_raw_<api>` 原始表。
   - 字段来自真实 Tushare 返回，统一先按 TEXT 落原始层，避免猜字段类型。
   - 新增 `tushare_api_ingest_status` 状态表，记录每个 API 的采集结果、行数、字段数和错误原因。
   - 首轮采集结果：152 个 API 已采集入库，39 个 API 已建表但需要补参数或 Tushare 当前环境不支持。
   - 主目录 `data-catalog-current.md` 已回写原始层状态：未分类 API 为 0。

## 当前审计结果

以真实 PG 生成的 `data-catalog-current.md` 为准：

- 本地 Tushare 接口文档 API 数：224
- 前端/后端已登记数据源：34
- PG+ETL 双覆盖：33
- 10 年跨度达标：17
- 存在字段/覆盖问题的数据源：15
- 全量 API 目录行数：224
- 原始层已采集 API：152
- 原始层已建表但需补参数/API 支持的 API：39
- 尚未分类治理结论的 API：0
- 尚未正式纳入业务 ETL 的 API：191

这些数字不是说 224 个接口都已经可以直接服务模型，而是说明每个接口都进入同一张项目目录；其中原始层已落地，后续还要决定哪些进入正式业务 ETL 和前端页面。

## 剩余治理项

### P0：字段/表结构漂移

这些项直接影响“从正确表、正确字段取数”：

- `limit_list_d`: DB/init 约束和字段仍有差异，`limit`/`"limit"` 需要统一。
- `moneyflow_hsgt`: 已把 init_sql 从旧 3 列补齐为真实 9 列。
- `stk_mins`: `trade_time` 真实库为 text，init_sql 期望 timestamp。
- `ths_concept_map`: 真实库与 init_sql 设计不一致，影响概念/产业链映射。

处理方式：每张表单独出迁移，先锁定真实业务字段，再同步 `init_postgres.sql`、alembic、写入端、查询端、测试。

### P1：ETL 字段多于 PG 字段

目录中 `etl_cols_not_in_pg` 代表写入端拿到了字段，但 PG 当前没有承接。当前 `_insert_rows` 会过滤这些字段，能避免写入失败，但会造成“以为采了，实际没入库”的认知风险。

优先评审：

- `daily_basic`: `turnover_rate_f`, `pe_ttm`, `ps`, `ps_ttm`, `dv_ratio`
- `financial_income`
- `financial_balance`
- `financial_cashflow`
- `forecast_data`
- `dividend_data`
- `research_reports_tushare`

处理方式：逐表决定“保留字段并扩表”或“明确丢弃并从 ETL cols 删除”，不能长期依赖自动过滤。

### P1：历史跨度不足

以下表目前不是 10 年级覆盖：

- `stk_mins`: 2026-03-02 起。分钟线 10 年全量成本很高，应明确保留窗口，而不是默认为缺失。
- `index_daily`: 2021-01-04 起。
- `sw_daily`: 2016-07-06 起，接近 10 年但未满。
- `stk_auction_o`: 2021-01-04 起。
- `cyq_chips`, `top_list`, `top_inst`: 目前主要是近期数据。
- `stock_news_tushare`, `research_reports_tushare`: 接近 10 年但未满。

处理方式：在数据目录增加治理决策列，写清“要回补到 10 年”或“按业务只保留近 N 年/近 N 天”。

### P2：已入目录但未分类的 Tushare API

当前 224 个接口已经全部进入项目目录，其中 191 个此前未实现接口已全部建原始表。下一步不是继续盲目扩表，而是给这些原始表打业务标签：

- in_scope: 和 A 股选股/回测/风控直接相关
- optional: 有价值但不是当前模型依赖
- out_of_scope: ETF/期货/港美股/宏观等暂不纳入
- no_permission: 需要权限或积分
- replaced: 已有替代数据源

## 建议下一步

1. 先按 `docs/data-governance/p0-schema-drift-execution-plan-2026-07-01.md` 修 P0 四张漂移表，避免基础表结构继续分叉。
2. 再处理 P1 字段承接，决定扩表还是删 ETL cols。
3. 给 191 个原始层 API 打业务标签，决定哪些升级为正式业务 ETL。
4. 把 `tushare_data_catalog.py` 加入每日只读审计任务，输出差异并告警。
