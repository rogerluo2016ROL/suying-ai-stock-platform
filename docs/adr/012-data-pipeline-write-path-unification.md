# ADR-012: 数据管道写入路径统一化 — 方法论 ADR

- 状态：**Accepted**（方案 A 渐进收口，PL 2026-06-22 决策签字）
- 日期：2026-06-22
- 决策者：tech-lead 起草；product-lead 2026-06-22 决策方案 A
- 影响范围：4 个文件（见决策 0 白名单）—— `packages/kronos-data/kronos_data/etl.py` + `services/data-service/app/sync/pg_writer.py` + `services/data-service/app/sync/cb_sync.py` + `services/data-service/app/scheduler.py`
- 编号说明：ADR-008/009/010/011 为单表 schema 对齐 ADR；本 ADR 升级到**方法论层面**，定写入路径统一化策略，下一批 ADR-013+ 按本 ADR 方法论实施单表

## PL 决策记录（2026-06-22）

product-lead 选**方案 A（渐进收口）**，理由对照 tech-lead §决策 4 给出的「选 B 触发信号」：
1. ❌ 剩余表 = 5-8 张（不超 10）
2. ❌ `detect_data_gaps` OK 21→32 已改善，无运维告警压力
3. ❌ 单 agent 团队，无新人错配场景
4. ✅ 可逆性优先（§决策 4 第 3 条），保留方案 B 升级通道——未来若新数据源接入 > 10 张表再走 ADR-016 升级评估

本 ADR §决策 0 / §决策 5 / §决策 6 / §不覆盖 / Hand-off 段按方案 A 写实，方案 B 内容保留在 §决策 2 / §备选方案 / §影响 作为决策史与未来升级参考。

## 上下文

ADR-008~011 完成 sw_daily / pledge_detail / rt_sw_k / top_list / cyq_chips / top_inst 共 6 表的 schema 对齐，验证了「改表加列对齐 sync + TRUNCATE 重拉」模式，但每张表都重写了一遍**几乎相同的修复流程**：决策 0 白名单 → 决策 N schema → Alembic 迁移 → 验证 SQL。memory `data-pipeline-write-debt` 列出剩余至少 5 表待修：`stk_factor_pro / ths_daily / stock_news_tushare / research_reports_tushare / cyq_perf / hk_holdings / repurchase / share_float` 等。

更严重的是：**数据管道的写入路径本身已分裂成 4 套**（grep `psycopg2.connect` / `_insert_rows` / `_pg_write` / `_pg_bulk_insert` 实证 2026-06-22），互不知晓彼此存在，每加一表都要选一套路径，路径间能力不一致——**根因不修，schema 对齐 ADR 会无限繁殖**。

### 现状盘点 1：四套写入路径并存

| # | 路径入口 | 位置 | 调用方数量 | 自动列过滤 | 重试 | 写失败可见 | 数据量门禁 | ON CONFLICT 策略 |
|---|---|---|---|---|---|---|---|---|
| 1 | `etl._insert_rows` | `packages/kronos-data/kronos_data/etl.py:167-200` | 32+ sync 函数（grep 45 次） | ✅（commit 2d311fa 止血） | ❌ | ✅（commit 2d311fa） | ❌ | `ON CONFLICT DO NOTHING`（PK 强约束） |
| 2 | `pg_writer._pg_write` | `services/data-service/app/sync/pg_writer.py:13-51` | scheduler.py:604/702（stk_factor_pro/rt_k）+ pg_writer 内 8 个 write_* helper | ❌ | ✅（3 次指数退避 1/4/16s） | ✅ | ✅（daily_kline/stk_mins <1000 ERROR / <3000 WARN） | `ON CONFLICT(conflict_cols) DO NOTHING`（需调用方传 PK） |
| 3 | `cb_sync._pg_bulk_insert` | `services/data-service/app/sync/cb_sync.py:58-90` | sync_ths_daily / sync_cb_price_chg_all / sync_ths_concept_map 3 个 | ❌ | ✅（同 #2，复制粘贴） | ❌（`except: pass`） | ❌ | 同 #2 |
| 4 | inline `db.executemany` | `services/data-service/app/sync/{announcements,cctv_news,mp_report,interact,policy_law,fina_mainbz,fina_audit,stock_profiles}.py` 等 8+ 个 | 8 个 sync 函数主路径走 SQLite + 偶发回弹 `_pg_write` | ❌ | ❌ | ❌ | ❌ | SQLite `INSERT OR REPLACE`；PG 写法不统一 |

**关键发现**：
- #1 `_insert_rows` 是**唯一带自动列过滤**的路径——schema ⊊ sync cols 错位时它能"丢弃表不存在的列"+ WARN 日志（commit 2d311fa）；其他三套路径列名错位 → 整批 `psycopg2.errors.UndefinedColumn` 失败（路径 #2/#3 retry 3 次后吞，#4 直接静默）。
- 但 #1 **缺重试 + 数据量门禁**，#2/#3 **有重试但缺自动列过滤**——两条主路径各缺一块拼图。
- #3 `_pg_bulk_insert` 与 #2 `_pg_write` 在 cb_sync.py 是**复制粘贴**（几乎逐行一致，仅 logger / 错误处理细节差异），是历史包袱而非设计。
- #4 inline 写法是**早期野生代码**，每个 sync 函数自己开 conn / 拼 SQL / executemany，零防御。

### 现状盘点 2：scheduler 监控与 backfill 失配

`services/data-service/app/scheduler.py:59-167` 实证：

- `MONITORED_TABLES`：**48 个表**（grep python 解析）
- `_BACKFILL_MAP`：**43 个 handler**
- **5 个 monitored 表无 backfill handler**：`['index_daily', 'stk_factor_pro', 'stocks', 'ths_daily', 'trade_cal']`

逐个诊断：

| 表 | 监控状态 | 实际 sync 函数 | 为何不在 _BACKFILL_MAP | 后果 |
|---|---|---|---|---|
| `stk_factor_pro` | gap_threshold=2 监控中 | `scheduler.py:531-631 sync_stk_factor_pro_daily()` | sync 签名是**无参数**（只拉 `trade_date=today`），与 `_BACKFILL_MAP` 期望的 `fn(days_back=int)` 不兼容 | gap > 2 天时 `trigger_data_backfill` 返回 `{status: "no_handler"}` 静默跳过，数据真空持续 |
| `ths_daily` | gap_threshold=1 监控中 | `services/data-service/app/sync/cb_sync.py:95 sync_ths_daily(days_back=30)` | 签名兼容但**遗漏注册**（cb_sync.py 是后加的，注册时忘了） | 同上 |
| `index_daily` | gap_threshold=1 监控中 | `etl.py:593 sync_index_daily(days_back=30)` | 签名兼容但**遗漏注册** | 同上 |
| `stocks` | gap_threshold=7 监控中 | `services/data-service/app/sync/stocks.py sync_stock_list / sync_stocks_incremental` | 函数签名不是 `days_back=int`（stocks 是全量列表非时序数据） | 监控规则错配（stocks 不该按 days_back 回补） |
| `trade_cal` | gap_threshold=1 监控中 | 无专门 sync 函数（trade_cal 由其他流程维护） | 设计上无 handler 是正确的 | 监控规则与 backfill 设计错配 |

**核心病灶**：monitored / backfill / sync_fn 三者**没有单一来源**——MONITORED_TABLES 是手写字典、_BACKFILL_MAP 是手写字典、sync_fn 是各自 import 的散件，三方对账靠人脑记忆。每加一表要**同时改 3 处**，漏一处就埋雷（stk_factor_pro 漏 backfill 已埋了 N 个月）。

### 现状盘点 3：cols 与 schema 的真相分裂

每个 sync 函数自己维护一份 `cols = [...]` 字面量（grep `cols = \[` 在 etl.py 出现 30+ 次），与表的 `CREATE TABLE` 字面无关联：

- `_insert_rows` 通过 introspect `information_schema` 自动**过滤**不匹配的列（运行时止血），但 sync 函数自己写错列名时**没有任何静态检查**——只能等 sync 跑完看 WARN 日志。
- `_pg_write` / `_pg_bulk_insert` 完全相信调用方传入的 cols，列名错位时整批 `UndefinedColumn`，路径 #2 retry 3 次后吞掉返回 0，路径 #3 `except: pass` 静默——表面 0 写入实则灾难（这正是 ADR-009 pledge / rt_sw_k 长期失效的机制）。
- alembic 迁移 + `init_postgres.sql` + sync cols 三处独立维护，**任何一处偏移都不会编译期报错**，全靠运行时数据缺失才暴露。

### 不做此决策的后果

1. **schema 对齐 ADR 无限繁殖**：剩余 5+ 表（stk_factor_pro / ths_daily / cyq_perf / hk_holdings / repurchase / share_float 等）每张都要重走 ADR-008~011 模板（白名单 + 决策 N + Alembic + 验证），ADR 数量预计涨到 17+，每个 ADR ~6 KB 模板冗余。
2. **新表接入零防御**：未来加表（如 sw_concept / cb_call_calendar）仍要选一套路径手填三处字典，新坑还会埋。
3. **静默故障率不变**：路径 #3/#4 的"列名错位 → 整批吞 → 0 写入"模式只要还有调用方在用，下一个 pledge / rt_sw_k 必然出现。
4. **监控规则与 backfill 失配**：当前已知 5 表缺 handler（其中 stk_factor_pro 是高优先级 60-day lookback 表），P0 监控价值打折。

## 决策

### 决策 0：文件改动白名单（对 backend-dev 的硬约束 — 方案 A 落地版）

⚠️ **本 ADR 升 Accepted 后明确列出允许修改的文件清单。backend-dev 不得修改清单外的任何文件。越界改动 = 违约，PL 直接回退。**（沿用 ADR-010/011 决策 0 风格。）

| # | 文件 | 允许改动 |
|---|---|---|
| 1 | `packages/kronos-data/kronos_data/etl.py` | 仅 `_insert_rows`（L167-200）增 `retries`（默认 0 = 关）+ `data_volume_floor`（默认 None = 关）两个可选参数 + 内部 retry/门禁实现；**不得动 32+ 个 sync 函数签名、不得改各 sync 函数内 cols 字面量、不得动 _get_pg_columns / clean_before_write / _Db 类** |
| 2 | `services/data-service/app/sync/pg_writer.py` | `_pg_write`（L13-51）改为 thin wrapper，内部经 `kronos_data.etl._insert_rows(retries=3, data_volume_floor=...)` 写入；保留 8 个 `write_*` helper 外部入口名 + 现有 column mapping 逻辑（write_moneyflow / write_daily_basic / write_index_daily 等的字段重排是业务必需，不得删）；`refresh_materialized_views` **零改动** |
| 3 | `services/data-service/app/sync/cb_sync.py` | `_pg_bulk_insert`（L58-90）改为 thin wrapper 调用 `_insert_rows`，或保留独立函数体但内部 delegate；**不得动 3 个 sync 函数（sync_ths_daily / sync_cb_price_chg_all / sync_ths_concept_map）的业务逻辑**（_get_pro / _get_trade_dates / _safe_val helper 保持不变） |
| 4 | `services/data-service/app/scheduler.py` | (a) 补 5 表 `_BACKFILL_MAP` handler（其中 stk_factor_pro 需新增 `sync_stk_factor_pro_backfill(days_back=int)` 双轨入口在同文件内）；(b) 新增 `validate_pipeline_consistency()` 启动期自检函数 + 在 scheduler 启动 lifespan 调用一次（WARN 模式，不 raise）；(c) 调整 stocks / trade_cal 监控配置（移除 MONITORED_TABLES 或显式标注 `"backfill": None`）；**不得动 MONITORED_TABLES 既有 43 表的 date_col / lookback / gap_threshold 字段、不得动 cron job 配置、不得动 detect_data_gaps / trigger_data_backfill / run_data_integrity_check / run_data_quality_report 核心逻辑** |

**不在白名单内的常见误改项**（明确禁止）：
- `services/data-service/app/sync/{announcements,cctv_news,mp_report,interact,policy_law,fina_mainbz,fina_audit,stock_profiles,namechange,stocks,rt_min,tushare}.py` — 8+ 个 sync 模块的 inline executemany 暂**不在本 ADR 范围**（缺陷 A 路径 #4 留待 ADR-015 治理；本 ADR 先收口 #1-#3 路径）
- 任何 alembic migration（001-009）
- `services/signal-service/app/routes.py:1006-1014` `_DATE_COL_MAP`（方案 A 不动 signal-service）
- `packages/kronos-factors/` 任何文件（下游因子零改动）
- `init_postgres.sql`（本 ADR 不涉及 schema 改动）
- CLAUDE.md Tech Stack 表（不引新依赖）

**Decision 0 范围声明**：方案 A 选定后，路径 #4 inline executemany 8 模块**暂留不动**——理由：(i) 这 8 个模块的写入对象多是 SQLite legacy + 偶发 PG 回弹路径（announcements / cctv_news / mp_report 等是 SQLite 主路径，stocks / namechange 是 PG 主路径），改造涉及 SQLite/PG dual-target 适配，工作量超出方案 A 的 2-3 day 边界；(ii) 这 8 模块当前未暴露列错位故障（缺陷 A 实际危害集中在路径 #2/#3 的 stk_factor_pro / ths_daily 等），可继续观察；(iii) ADR-015 留位治理（在 §不覆盖 段记录）。

### 决策 1：核心病灶根因诊断

**根因不是"哪个表缺修"，而是"写入路径分裂 + 真相源分裂"两类结构性缺陷**：

#### 缺陷 A：写入路径分裂（4 套，能力不互通）

- `_insert_rows`（路径 #1）：唯一有自动列过滤——**新表必经路径**；但缺重试 + 数据量门禁。
- `_pg_write`（路径 #2）：有重试 + 数据量门禁——**容错路径**；但缺自动列过滤，列错位时静默归零。
- `_pg_bulk_insert`（路径 #3）：与路径 #2 复制粘贴——**纯历史包袱**，无独立价值。
- inline executemany（路径 #4）：早期野生代码——零防御，**新人易复制扩散**。

历史成因：路径 #1 在 `packages/kronos-data`（独立 Python 包，给 Kronos 训练侧用），路径 #2/#3 在 `services/data-service`（FastAPI 服务），两个团队各自演进时无契约同步；路径 #4 是把 SQLite legacy 写法生搬到 PG 没改造。

#### 缺陷 B：真相源分裂（4 处独立维护，对账靠人脑）

每张表的"5 个事实"散落在 4 处：

| 事实 | 位置 | 维护方 | 同步机制 |
|---|---|---|---|
| 物理列集 | `init_postgres.sql` + alembic versions/NNN | tech-lead 起 ADR + backend-dev 落 migration | 手工 |
| sync cols 列表 | 各 `sync_*` 函数内 `cols = [...]` 字面量 | sync 编写者 | 与表 schema 无静态关联 |
| backfill 注册 | `scheduler.py:_BACKFILL_MAP` | 加表者手填 | 无校验 |
| 监控配置 | `scheduler.py:MONITORED_TABLES` | 加表者手填 | 无校验 |
| date_col | 散落在 `MONITORED_TABLES` + sync 函数 + `signal-service/routes.py:1006-1014` `_DATE_COL_MAP` | 三处独立 | 无校验（ADR-009 pledge_detail 改 ann_date 时漏改 scheduler 已是教训） |

**任何一处偏移都不会编译期 / 单测期发现**——只能等 sync 跑完看数据缺失或 grep 反查。

#### 两类缺陷的乘积效应

每加一表 → 4 套路径选 1 + 4 处真相填 4 处 → 4×4=16 种组合空间，错配概率随表数线性增加。ADR-008~011 修的是"已暴露错配"，根本不解决"未来加表仍会错配"。

### 决策 2：业务方向两选（PL 决策）

#### 方案 A — 渐进收口：统一到 `_insert_rows` + 完善 _BACKFILL_MAP + cols 反向 introspect

**核心动作**：
1. **路径合并**：`_pg_write` / `_pg_bulk_insert` / inline executemany 三套全部改造内部 fallback 调用 `_insert_rows`；保留三个外部入口名（向后兼容调用方），但函数体改为薄 wrapper，把列过滤能力带给所有路径。
2. **缺陷 B 局部解**：scheduler.py 加一个 `validate_pipeline_consistency()` 启动期自检——遍历 `MONITORED_TABLES` 与 `_BACKFILL_MAP`，缺 handler 的表启动期 WARN（而非运行时静默跳过）；同时校验 `MONITORED_TABLES.date_col` 是否在表实际列集内（PG introspect）。
3. **5 表缺 backfill 补齐**：
   - `stk_factor_pro`：sync 改造接 `days_back=int`，注册 _BACKFILL_MAP
   - `ths_daily`：注册 _BACKFILL_MAP（函数签名已兼容）
   - `index_daily`：注册 _BACKFILL_MAP
   - `stocks` / `trade_cal`：从 MONITORED_TABLES 移除（监控规则错配，不属于"按 days_back 回补"模型）或挂 N/A handler 显式表达"不回补"
4. **cols 反向 introspect**（可选增强）：sync 函数支持 `cols=None` 时从 schema 自动 introspect 全列集，避免手填 cols 与 schema 偏移；保留旧 `cols=[...]` 路径向后兼容。

**优点**：
- 改动面小（核心 4 文件：`etl.py` `pg_writer.py` `cb_sync.py` `scheduler.py`），可在 1 个 PR 内落地 + SIT
- 不引入新模块 / 新概念，新人零学习成本
- 路径 #1 `_insert_rows` 自动列过滤已生产验证（commit 2d311fa 后 ADR-008~011 实施 0 误伤）
- 风险可控：fallback 到 _insert_rows 时若失败，外部 wrapper 仍可保留原路径作为二级 fallback

**缺点**：
- **不解决缺陷 B 根因**：sync cols / backfill / monitored / date_col 仍是 4 处独立字典，需人脑对账；validate_pipeline_consistency 只能在启动期 catch 已经写错的情况，不能预防写错。
- ADR-013+ 单表 ADR 仍要继续写（schema 改动本身需要 ADR），只是模板更瘦——下游因子改造与 sync cols 改造的"两端对账"工作量不减。
- 路径 #2 `_pg_write` 的重试 + 数据量门禁能力要在 `_insert_rows` 同步实现（否则改造后路径能力反而退化），需小心 merge 三套路径的最佳特性。
- 路径 #4 inline executemany 8 个文件挨个改 wrapper，机械工作量不小（虽不复杂）。

**预估工作量**：backend-dev 2-3 day（核心合并 1d + 5 表 backfill 补齐 0.5d + scheduler validator 0.5d + SIT 0.5-1d）。

#### 方案 B — 重构：引入 SyncSpec 表注册中心，所有路径从注册中心读真相

**核心动作**：
1. **新建 `packages/kronos-data/kronos_data/sync_registry.py`**：每张表一份 `SyncSpec` dataclass：

   ```python
   @dataclass
   class SyncSpec:
       table: str                       # 表名
       sync_fn: Callable                # sync 入口 (lazy import, 避免循环依赖)
       backfill_fn: Callable | None     # backfill 入口 (=sync_fn / 或独立 fn / 或 None=不回补)
       cols: list[str]                  # 业务列集 (Tushare 原名)
       pk: list[str]                    # 主键列 (用于 ON CONFLICT)
       date_col: str                    # 监控日期列
       lookback: int                    # 监控回看窗口 (天)
       freq: str                        # L0-realtime / L1-intra / L2-daily / L3-weekly / L3-monthly
       gap_threshold: int               # 触发回补的滞后天数
       monitored: bool = True           # 是否纳入 MONITORED_TABLES (False=纯 cron 触发)
       writer: Literal["insert_rows", "pg_write"] = "insert_rows"  # 选写入路径
   ```

2. **改造**：MONITORED_TABLES / _BACKFILL_MAP / signal-service _DATE_COL_MAP 全删，改为从 sync_registry 动态构造（保留外部接口名向后兼容）。
3. **新 sync 函数遵循契约**：所有新表必须在 sync_registry 注册一份 SyncSpec；老 sync 函数迁移到注册中心（保留 import 入口）。
4. **路径合并**（同方案 A）：4 套路径收敛到 2 套（`_insert_rows` 默认 / `_pg_write` 容错），由 SyncSpec.writer 字段路由。
5. **静态检查**：注册中心启动期对所有 SyncSpec 做一致性扫描——`cols ⊆ PG schema` / `pk ⊆ cols` / `date_col ∈ cols` / `backfill_fn 签名为 (days_back: int) -> dict`；任一失败启动期 raise（非 WARN），强制开发者把脏注册改对再启动。
6. **生成 schema 对齐 ADR 模板**：可选——SyncSpec 完整后可半自动生成"schema vs sync cols vs pk 偏差"清单，把 ADR-013+ 模板写作变 90% 机械填表。

**优点**：
- **真正解决缺陷 B**：单一真相源（SyncSpec），4 处字典退化为视图（dynamic dict comprehension）
- **新表接入零失配可能**：注册 SyncSpec 时静态检查全跑，缺 backfill / 列错位 / date_col 漂移启动期 raise 而非运行时静默
- ADR-013+ 模板大幅瘦身：剩余 5+ 表 schema 对齐 ADR 可压缩到 ~50% 篇幅（只写"差异 diff + Alembic 模板"，不再重写决策 0/sync 改动/下游影响骨架——这些已被 SyncSpec 静态保证）
- 监控价值兑现：48 个 monitored 表的 backfill 缺口 5 表问题彻底消除——SyncSpec 强制 backfill 字段（None / fn 二选一），不能漏

**缺点**：
- **改动面大**：核心 2 文件新建（sync_registry.py + adapters）+ 12+ 文件迁移（etl.py 32+ sync 函数迁移注册 + scheduler.py 大改 + cb_sync.py 迁移 + sync/*.py 8 个 inline 迁移 + signal-service routes.py 改读注册）
- **风险高**：sync 函数迁移过程中任何一个 cols / pk 写错都可能触发启动期 raise → 短期阻塞所有 sync；需分阶段灰度（先注册 + dual-source dict 共存，逐表迁移）
- **新概念引入**：SyncSpec dataclass + adapters，新人需学习注册中心模型；与 Python 社区 alembic / SQLAlchemy 的 declarative model 在概念上有重叠但又不复用——是否值得自建抽象层存争议
- 与 ADR-006「PG-first 直写」+ ADR-008~011「存原始」哲学一致性需评估——SyncSpec.cols 是否会强制路径 #1 引入 ORM 概念，违背"轻量 sync 函数"风格
- **预估工作量**：backend-dev 5-7 day（注册中心设计 1d + sync 函数迁移 2-3d + scheduler / signal-service 改造 1d + 静态检查 1d + SIT + 灰度 1-2d）；含 1-2 天潜在 bug 修复缓冲

**预估工作量**：5-7 day（约方案 A 的 2.5×）。

### 决策 3：方案对比矩阵（PL 决策辅助）

| 维度 | 方案 A 渐进收口 | 方案 B 注册中心 |
|---|---|---|
| 改动文件数 | 4 | 12+（含新增） |
| 工作量 | 2-3 day | 5-7 day |
| 路径分裂（缺陷 A）解决 | ✅ 三套 fallback 合并 | ✅ 三套合并 + 路由化 |
| 真相分裂（缺陷 B）解决 | ⚠️ 仅启动期 validator，不预防 | ✅ 单一真相源 + 静态 raise |
| 短期数据真空消除 | ✅ 5 表 backfill 补齐 | ✅ 强制契约 |
| ADR-013+ 模板瘦身 | ❌ 模板不变 | ✅ ~50% 篇幅压缩 |
| 新人学习成本 | 0 | 中（需学 SyncSpec） |
| 阻塞风险 | 低（旧路径保留 fallback） | 中（注册期 raise 可能短期阻塞所有 sync） |
| 与 ADR-006/008-011 哲学一致 | ✅（沿用 _insert_rows + 存原始） | ⚠️ 引入新抽象层，需评估 |
| **可逆性** | ✅ 任意时刻可回滚到分裂状态 | ⚠️ 注册中心一旦 adopt，回滚需重新拆 4 处字典 |

### 决策 4：本 ADR 选定推荐方向（tech-lead 建议）

**tech-lead 倾向方案 A（渐进收口），理由**：

1. **当前剩余表数量有限**（5-8 表），方案 B 的"零失配新表接入"红利在中短期内体现不充分——若未来新增表数量回到月级 1-2 张，方案 A 的 validator + backfill 补齐已足以兜底。
2. **方案 B 的核心红利「ADR 模板瘦身」可在 ADR-013+ 通过共享模板片段实现**——不必引入 SyncSpec 抽象层（在 `.claude/skills/agf-writing-adr/SKILL.md` 加一个 "schema-alignment" 子模板就够）。
3. **可逆性优先**：方案 A 任意时刻可回滚到当前状态（旧路径保留），方案 B 一旦注册中心生效，回滚需还原 4 处字典 + sync 函数旧签名——治理风险。
4. **ADR-006 既有路径已是「轻量 sync 函数」哲学**——引入 SyncSpec dataclass 与该哲学有张力，需先评估是否冲突。

**但 PL 若有以下信号，应选方案 B**：
- 剩余表数量预计 > 10 张（如计划接入加密货币 / 港股期权等新数据源 + 多张表）
- 监控告警频繁误报（5 表 `no_handler` 静默跳过已被 SRE / 运维投诉）
- 团队成员 > 3 人且新人加表错配率 > 30%（有人为缺陷 B 实际付出代价）

PL 在决策回执中需要明确：选 A 还是 B + 理由（若 PL 选 B，本 ADR §决策 0 白名单需重写，工作量翻倍是契约）。

**[PL 2026-06-22 决策结果]**：选方案 A，理由见本 ADR 顶部「PL 决策记录」段。下面 §决策 5 / §决策 6 / §决策 7 为方案 A 的实施细则。

### 决策 5：方案 A 实施细则（backend-dev 落地依据）

#### 5.1 `_insert_rows` 能力扩展（白名单 #1）

`packages/kronos-data/kronos_data/etl.py:167-200` 增 2 个可选参数，默认值保持现有行为兼容：

```python
def _insert_rows(db: _Db, table: str, columns: list[str],
                 rows: list[tuple],
                 retries: int = 0,                    # 新增：≥1 时启用指数退避 1s/4s/16s
                 data_volume_floor: int | None = None # 新增：写入量 < floor 时 logger.error
                 ) -> int:
    """INSERT with per-row error isolation. Uses PG or SQLite bulk insert.

    Args:
        retries: PG OperationalError 重试次数 (默认 0 = 不重试, 保持旧行为)。
                 路径 #2/#3 改造时传 3 (沿用 pg_writer 现有重试策略)。
        data_volume_floor: 写入行数低于此值时 logger.error (用于关键表如 daily_kline / stk_mins);
                           默认 None = 关闭门禁，保持旧行为。
    """
```

**实现要点**：
- `retries` 路径仅 catch `psycopg2.OperationalError`（与 `_pg_write` 现有逻辑一致），其他异常（如 UndefinedColumn）走原有 WARN + return 0 路径——retry 只解决"网络瞬时抖动"而非"列名错位"。
- `data_volume_floor` 触发 logger.error 但不 raise（保持 best-effort 哲学，与 `pg_writer._check_data_volume` 一致）。
- SQLite 路径（`else` 分支）不受新参数影响（SQLite 是本地文件无网络瞬时故障）。
- **不动**自动列过滤逻辑（commit 2d311fa 已生产验证）。

#### 5.2 `_pg_write` thin wrapper 化（白名单 #2）

`services/data-service/app/sync/pg_writer.py:13-51` 改写为薄 wrapper：

```python
def _pg_write(table: str, columns: list[str], conflict_cols: list[str],
              rows: list[tuple]) -> int:
    """通用 PG 批量写入 — delegate to kronos_data.etl._insert_rows.

    ADR-012 决策 5.2: 三套写入路径合并到 _insert_rows, 获得自动列过滤能力;
    保留 conflict_cols 参数语义 (虽 _insert_rows 用 ON CONFLICT DO NOTHING
    且依赖表 PK 约束, 不显式接 conflict_cols ——见 5.2.bis)。
    """
    from kronos_data.etl import _insert_rows, _get_etl_db

    db = _get_etl_db()
    try:
        written = _insert_rows(db, table, columns, rows,
                               retries=3,
                               data_volume_floor=_VOLUME_FLOOR_MAP.get(table))
        return written
    finally:
        db.close()


# 数据量门禁阈值 (从原 _check_data_volume 提取的策略表, 显式而非硬编码)
_VOLUME_FLOOR_MAP = {
    "daily_kline": 1000,
    "stk_mins": 1000,
}
```

**5.2.bis — `conflict_cols` 参数兼容性**：
- 现状 `_pg_write` 用 `ON CONFLICT(conflict_cols) DO NOTHING`，依赖调用方传准确的 PK 列；`_insert_rows` 用 `ON CONFLICT DO NOTHING`（不指定列，依赖表实际 PK 约束）——两者行为**仅在表有完整 PK 约束时等价**。
- 实证：所有 `_pg_write` 调用方传的 `conflict_cols` 与表实际 PK 一致（grep `_pg_write\|write_*\(` × `init_postgres.sql` 的 PRIMARY KEY 字面），所以收口到 `_insert_rows` 无行为变化。
- backend-dev 实施时**必须**先 grep 验证每个 `_pg_write` 调用方的 `conflict_cols` ⊆ 表 PK，遇例外（如 ths_daily 用 `(ts_code, trade_date)` 非裸 PK 而是 UNIQUE 约束）保留独立 wrapper 而非强转。

#### 5.3 `_pg_bulk_insert` thin wrapper 化（白名单 #3）

`services/data-service/app/sync/cb_sync.py:58-90` 改写：

```python
def _pg_bulk_insert(table: str, columns: list[str], conflict_cols: list[str],
                    rows: list[tuple]) -> int:
    """ADR-012 决策 5.3: 收口到 pg_writer._pg_write (再委托 _insert_rows),
    消除与 pg_writer._pg_write 95% 复制粘贴的历史包袱。
    """
    from app.sync.pg_writer import _pg_write
    return _pg_write(table, columns, conflict_cols, rows)
```

**注意**：不直接 import `_insert_rows`——`cb_sync` 是 `services/data-service` 层，按 ADR-006 分层应通过 `pg_writer` 走业务侧入口（含 `_VOLUME_FLOOR_MAP`），而非穿透到 `packages/kronos-data`。

#### 5.4 `_BACKFILL_MAP` 补齐 5 表（白名单 #4-a）

| 表 | 改造动作 | 工作量 |
|---|---|---|
| `stk_factor_pro` | 在 `scheduler.py` 同文件内新增 `sync_stk_factor_pro_backfill(days_back: int) -> dict`：把 `sync_stk_factor_pro_daily()` 的核心逻辑抽出，接受 `days_back` 参数后用 `_get_trade_dates(days_back)`（同 `etl._get_trade_dates`）循环每日调用 `pro.stk_factor_pro(trade_date=d)`；保留 `sync_stk_factor_pro_daily` 作为 cron 入口（内部调 `sync_stk_factor_pro_backfill(days_back=1)`）。注册 `_BACKFILL_MAP["stk_factor_pro"] = sync_stk_factor_pro_backfill` | 中（涉 sync 逻辑改造） |
| `ths_daily` | 直接注册 `_BACKFILL_MAP["ths_daily"] = sync_ths_daily`（cb_sync.py 已 import） | 极小 |
| `index_daily` | 直接注册 `_BACKFILL_MAP["index_daily"] = sync_index_daily`（etl.py 已 import） | 极小 |
| `stocks` | 从 `MONITORED_TABLES` 移除（非时序数据，gap_threshold 模型不适用）；改由 cron 直接调度 `sync_stocks_incremental` | 极小 |
| `trade_cal` | 在 `MONITORED_TABLES` 加注释 `# trade_cal: 由 trade_cal_sync 路径维护, 不进自动 backfill`；保留监控但 `_BACKFILL_MAP` 不挂 handler（让 `trigger_data_backfill` 的现有 `no_handler` 分支日志透出 `[INFO] trade_cal: skip auto-backfill by design`） | 极小 |

#### 5.5 `validate_pipeline_consistency()` 启动期自检（白名单 #4-b）

新增函数（建议放 `scheduler.py` 顶部，紧邻 `_BACKFILL_MAP` 定义），在 scheduler 启动 lifespan 调用一次：

```python
def validate_pipeline_consistency() -> dict:
    """ADR-012 决策 5.5: 启动期自检数据管道一致性, WARN 不 raise.

    检查项 (任一不一致仅 logger.warning, 不阻断启动):
      1. MONITORED_TABLES 中的每个表, _BACKFILL_MAP 是否注册了 handler
         (例外: stocks/trade_cal 显式标注 design-skip)
      2. MONITORED_TABLES.date_col 是否在表实际列集内 (PG introspect information_schema)
      3. _BACKFILL_MAP 的每个 handler 是否 callable + 签名含 days_back 参数 (inspect.signature)

    Returns:
        {"checked": N, "warnings": [{"table": ..., "issue": ..., "fix_hint": ...}, ...]}
    """
    import inspect
    from psycopg2.sql import SQL, Identifier
    warnings = []
    # ── 检查 1: 监控表缺 backfill (排除 design-skip) ──
    DESIGN_SKIP = {"stocks", "trade_cal"}  # 与 5.4 一致
    for table in MONITORED_TABLES:
        if table in DESIGN_SKIP:
            continue
        if table not in _BACKFILL_MAP:
            warnings.append({
                "table": table,
                "issue": "monitored but no backfill handler",
                "fix_hint": f"add _BACKFILL_MAP['{table}'] = sync_<fn> in scheduler.py",
            })
    # ── 检查 2: date_col 实际存在 ──
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_URL)
        cur = conn.cursor()
        for table, cfg in MONITORED_TABLES.items():
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                (table,)
            )
            actual_cols = {r[0] for r in cur.fetchall()}
            if not actual_cols:
                continue  # 表不存在另案 (probable pre-migration state)
            if cfg["date_col"] not in actual_cols:
                warnings.append({
                    "table": table,
                    "issue": f"date_col '{cfg['date_col']}' not in PG columns {sorted(actual_cols)[:5]}...",
                    "fix_hint": "update MONITORED_TABLES[{table}].date_col or run alembic upgrade",
                })
        conn.close()
    except Exception as e:
        logger.debug("validate_pipeline_consistency: PG introspect skipped (%s)", e)
    # ── 检查 3: handler 签名 ──
    for table, fn in _BACKFILL_MAP.items():
        try:
            sig = inspect.signature(fn)
            if "days_back" not in sig.parameters:
                warnings.append({
                    "table": table,
                    "issue": f"backfill handler {fn.__name__} missing days_back param",
                    "fix_hint": "add `days_back: int = N` to function signature",
                })
        except (TypeError, ValueError):
            warnings.append({"table": table, "issue": "handler not introspectable",
                             "fix_hint": "ensure it's a plain function not a partial/lambda"})
    # ── 输出 ──
    for w in warnings:
        logger.warning("Pipeline validate [%s]: %s | %s", w["table"], w["issue"], w["fix_hint"])
    logger.info("Pipeline validate: checked %d monitored tables, %d warnings",
                len(MONITORED_TABLES), len(warnings))
    return {"checked": len(MONITORED_TABLES), "warnings": warnings}
```

**调用点**：scheduler 启动 lifespan / app startup hook 处一次性调用；warning 不阻断启动（决策 4 第 1 条「可逆性优先」）。

#### 5.6 不在范围（明确给 backend-dev 守住）

- **不实施** cols 反向 introspect 重写 sync 函数（方案 A 不强求；validator 检查 5.5 检查 2 已覆盖 date_col 偏移，sync cols ⊆ schema 由 `_insert_rows` 自动列过滤运行时兜底）
- **不实施** path #4 inline executemany 8 模块迁移（见决策 0 范围声明 + 不覆盖段 → ADR-015）
- **不动** signal-service `_DATE_COL_MAP`（方案 A 不动）
- **不动** alembic / schema / 下游因子

### 决策 6：SIT 验证清单（backend-dev 自跑 + 写入 progress/backend-dev.md SIT 证据段）

| # | 验证项 | 验证命令 / SQL | 期望结果 |
|---|---|---|---|
| 1 | `_insert_rows` retries=0 默认行为不变 | 单测 mock psycopg2 OperationalError，断言 retries=0 时 1 次抛 | 1 次 attempt 后 return 0 |
| 2 | `_insert_rows` retries=3 重试 | 单测 mock 前 2 次 OperationalError 第 3 次成功 | 第 3 次成功 return N |
| 3 | `_insert_rows` data_volume_floor 触发 ERROR | 单测 mock 写入 800 行 + floor=1000 | logger.error 命中 + 不阻断 |
| 4 | `_pg_write` thin wrapper 等价性 | 真实跑一次 `sync_stk_factor_pro_daily()` 对比合并前后 PG 行数（差值 = 0） | 行数一致 |
| 5 | `_pg_bulk_insert` thin wrapper 等价性 | 真实跑一次 `sync_ths_daily(days_back=1)` 对比合并前后 PG 行数 | 行数一致 |
| 6 | `_BACKFILL_MAP` 5 表补齐 | `python -c "from app.scheduler import _BACKFILL_MAP; print(sorted(_BACKFILL_MAP.keys()))"` | 含 stk_factor_pro / ths_daily / index_daily（stocks / trade_cal 不含） |
| 7 | `stk_factor_pro` 7 day backfill 跑通 | `python -c "from app.scheduler import sync_stk_factor_pro_backfill; print(sync_stk_factor_pro_backfill(days_back=7))"` | `{"written": >5000, ...}` |
| 8 | `detect_data_gaps` 5 表 status 变化 | 跑 `detect_data_gaps()` 前 / 跑 backfill 后再跑 | 跑前 stk_factor_pro / ths_daily / index_daily 可能 status=gap；跑后 ok 数 ↑ ≥ 3 |
| 9 | `validate_pipeline_consistency` 启动输出 | scheduler 启动后查日志 | 至少 1 行 `Pipeline validate: checked 46 monitored tables, X warnings`（46 = 移除 stocks/trade_cal 后；X 应为 0 或仅 design-skip 偏差） |
| 10 | `validate` 检查 2 触发 | 手动改 `MONITORED_TABLES["daily_kline"]["date_col"] = "wrong_col"` 重启 | 日志 WARN `daily_kline: date_col 'wrong_col' not in PG columns [...]` |
| 11 | 32+ sync 函数行为不回归 | 跑一次 `sync_tushare_data(mode="all", days=3)`（etl.py:1928） | 各表 written 与改造前相对差 < 5% |
| 12 | grep 越界检测 | `git diff main --stat` | 仅命中决策 0 白名单内 4 文件，无 packages/kronos-factors / alembic / sync/{announcements,...} 等命中 |

### 决策 7：分阶段实施顺序（防回归）

按依赖顺序，每阶段独立可 commit + 可回滚：

1. **阶段 1 — `_insert_rows` 能力扩展**（白名单 #1）：加 retries / data_volume_floor 参数，默认关；SIT 验证项 1-3 跑通。**回滚点 A**。
2. **阶段 2 — `_pg_write` 改 thin wrapper**（白名单 #2）：跑 SIT 验证项 4 行数一致；触发数据量门禁的 daily_kline / stk_mins 用 `_VOLUME_FLOOR_MAP`。**回滚点 B**。
3. **阶段 3 — `_pg_bulk_insert` 改 thin wrapper**（白名单 #3）：跑 SIT 验证项 5 行数一致。**回滚点 C**。
4. **阶段 4 — `_BACKFILL_MAP` 5 表补齐**（白名单 #4-a）：跑 SIT 验证项 6-8。**回滚点 D**。
5. **阶段 5 — `validate_pipeline_consistency` 上线**（白名单 #4-b）：跑 SIT 验证项 9-10。**回滚点 E**。
6. **阶段 6 — 综合回归**（SIT 验证项 11-12 + git diff 白名单审计）。

**任一阶段失败可停在该阶段回滚点不影响已合并阶段**——这是方案 A「可逆性优先」的体现。


## 备选方案

- **C. 不做统一化，继续按 ADR-008~011 模板挨个修表** — pros: 零额外结构改动；cons: ADR 数量预计涨到 17+，每张表埋错配新坑的概率随表数线性增加，根因不修——监控失配 5 表持续静默。**否决理由**：technical debt 的复利成本超过一次性重构成本（grep 实证当前已有 5 表静默 + 4 套路径分裂，再增量爬只会更难修）。

- **D. 完全弃用 `services/data-service/app/sync/` 路径，全部迁回 `packages/kronos-data/kronos_data/etl.py`** — pros: 单一路径，缺陷 A 彻底消除；cons: data-service 是 FastAPI 服务，etl.py 是 standalone 包，架构上分层有意义（FastAPI 拿 cron + REST 触发 / etl 提供 pure functions）——合并破坏 ADR-006 的「PG-first 直写 + 消除 subprocess 桥」分层；且 services/data-service/app/sync/{announcements,cctv_news,...} 8 个 sync 已写了 inline executemany，迁移工作量 ≥ 方案 B 但红利不及。**否决理由**：违背 ADR-006 分层架构；工作量大于方案 B 而成果不显著。

- **E. 引入 SQLAlchemy ORM declarative model 替代 SyncSpec dataclass** — pros: 复用社区生态，少自建抽象；cons: SQLAlchemy ORM 模型与现有 alembic-only / 原生 SQL 风格的迁移不一致（ADR-006 决策明确不引 ORM），且 ORM 对 ETL bulk insert 性能优化点（execute_values）支持不如裸 psycopg2；ADR-008~011 已 6 个 alembic 迁移用原生 op.execute，转 ORM 是平行另一套基线。**否决理由**：与 ADR-006/008/009/010/011 既有基线冲突，转 ORM 须另立顶层 ADR 评估。

- **F. 不重构写入路径，只补 backfill + scheduler validator（方案 A 的子集）** — pros: 工作量更小（~1 day）；cons: 缺陷 A 仍存（路径 #2/#3/#4 列错位风险依旧），下个 pledge 必然出现；且方案 A 的核心红利「自动列过滤普及到三套路径」本身工作量不大，无需进一步缩减。**否决理由**：YAGNI 的反面——为减半天工作量放弃缺陷 A 的解，不划算。

- **G. 用 Tushare API schema 自动生成所有表 DDL + sync cols + SyncSpec**（终极方案）— pros: 100% 静态一致；cons: Tushare 接口字段命名不规范（同字段在不同接口名字不一致：`pct_chg` vs `pct_change` vs `change_pct`，见 ADR-009），无法机械生成；Tushare 返回字段会无通知变更（如 ADR-010 cyq_chips 历史曾返回更多字段然后缩减），自动生成会跟着漂移。**否决理由**：Tushare 接口稳定性不达标，自动化反而引入不可控漂移。

## 影响

### 方案 A 选定时的影响

- `packages/kronos-data/kronos_data/etl.py`：`_insert_rows` 增加可选重试 + 数据量门禁参数；不动 sync 函数签名（保留旧 cols 列表）
- `services/data-service/app/sync/pg_writer.py`：`_pg_write` 改 thin wrapper 调用 `_insert_rows`；保留 8 个 write_* helper 函数名向后兼容
- `services/data-service/app/sync/cb_sync.py`：`_pg_bulk_insert` 改 thin wrapper（或直接删，3 调用方迁移到 `_pg_write` 名义入口）
- `services/data-service/app/scheduler.py`：增 `validate_pipeline_consistency()` 启动期自检 + 补齐 5 表 backfill 注册（其中 stk_factor_pro sync 函数签名需改造接 `days_back=int`）
- 下游因子代码（`packages/kronos-factors/`）：**零改动**
- CLAUDE.md Tech Stack：**无更新**（不引新依赖）

### 方案 B 选定时的影响

- 新建 `packages/kronos-data/kronos_data/sync_registry.py`（核心，~300-500 行：SyncSpec dataclass + adapters + 启动期 validator）
- 改 `packages/kronos-data/kronos_data/etl.py`（32+ sync 函数 hand-off SyncSpec.cols；保留函数体）
- 改 `services/data-service/app/scheduler.py`（MONITORED_TABLES / _BACKFILL_MAP 退化为 SyncSpec 视图；validate 改 raise）
- 改 `services/data-service/app/sync/{cb_sync,pg_writer}.py`（路径 #2/#3 路由化）
- 改 `services/data-service/app/sync/{announcements,cctv_news,mp_report,interact,policy_law,fina_mainbz,fina_audit,stock_profiles}.py`（8 个 inline executemany 迁移注册中心 + 走 _insert_rows）
- 改 `services/signal-service/app/routes.py:1006-1014`（`_DATE_COL_MAP` 退化为 SyncSpec 视图）
- 下游因子代码（`packages/kronos-factors/`）：**零改动**
- 文档：新建 `.claude/standards/data-pipeline.md`（数据管道编写规范，含 SyncSpec 注册流程）
- CLAUDE.md Tech Stack：**无更新**（dataclass 是 stdlib，无新依赖）；CLAUDE.md "Project-Specific Rules" 段加一条「新表必须先注册 SyncSpec 再写 sync」

### 对成本（两方案共同）

- 不增 API 调用 / 存储 / 算力
- 工作量：方案 A 2-3 day / 方案 B 5-7 day（含 SIT + 灰度）
- 监控价值：5 表静默 backfill 消除（两方案都能解）

### 对运维（两方案共同）

- scheduler 启动期日志会多 1-2 行 validate 输出（方案 A WARN / 方案 B raise）
- 5 表回补恢复后，数据 freshness 监控会从"5 表静默 gap"切换到"按 cron 正常补齐"，告警噪音降低
- 任何 sync 失败现在路径 #2/#3/#4 都能可见（commit 2d311fa 风格扩散）——SRE 会短期内看到更多 WARN 日志（这是修复噪音而非新增故障）

### 风险

#### 方案 A 共同风险
1. **`_insert_rows` 加重试 + 数据量门禁可能改变现有 sync 函数行为**（如 retry 拉长 sync 时间，门禁 ERROR 让 cron 看似失败）。**缓解**：新参数默认关（向后兼容），新调用方主动启用；validator 仅 WARN 不 raise。
2. **scheduler validator 启动期延迟**：48 表全 introspect 约 1-2 秒 PG IO。**缓解**：缓存到模块级变量，每次启动跑一次。
3. **stk_factor_pro sync 签名改造从无参数 → days_back=int 需改 cron job**（scheduler.py:980-981 cron 调用方）。**缓解**：保留无参数旧入口名 + 新建 `sync_stk_factor_pro_backfill(days_back)` 双轨。

#### 方案 B 额外风险
1. **注册期 raise 短期阻塞 sync**：迁移过程中任何 cols / pk 写错都 raise。**缓解**：分阶段——P1 注册全表（仅注册不 raise）→ P2 启用静态检查（WARN）→ P3 启用 raise。三阶段各 1 周观察期。
2. **SyncSpec 抽象层与 alembic 迁移信息源重复**：alembic 已是 schema 真相源，SyncSpec.cols 是 sync 真相源——若 alembic 改了某列名而 SyncSpec.cols 未跟，validator 仍能 catch，但**两处独立维护本身就是一种新分裂**。**缓解**：SyncSpec.cols 是"sync 拉取列"，alembic 是"表物理列"，两者本就独立（如 ADR-009 stk_factor_pro 表 pe_ttm 字段被丢——sync 拉的列 ⊂ 表物理列是合法的）；validator 只校验 ⊆ 关系不要求等价，符合"轻量分层"。

## 本 ADR 不覆盖的决策

- **剩余表的 schema 对齐**（hk_holdings / repurchase / share_float / cyq_perf / stock_news_tushare / research_reports_tushare 等）：本 ADR 是**方法论 + 4 文件改动**，不动 schema；具体单表 schema 对齐另起 ADR-013/014/...，按 ADR-008~011 模板。剩余表清单见 memory `data-pipeline-write-debt`。
- **stk_factor_pro / ths_daily / index_daily 的 schema 对齐**：本 ADR 只补 backfill handler，不审查这 3 表的 schema vs sync cols vs 下游因子三方对账——若实施 SIT 时（决策 6 验证项 7）发现仍有列错位（依赖 `_insert_rows` 自动列过滤兜底），单独立 ADR-013。
- **路径 #4 inline executemany 8 模块治理**（announcements / cctv_news / mp_report / interact / policy_law / fina_mainbz / fina_audit / stock_profiles）：方案 A 范围内**暂不改造**，理由见决策 0 范围声明；留位 **ADR-015**（路径 #4 SQLite/PG dual-target 适配）。
- **signal-service `_DATE_COL_MAP` 与 scheduler.MONITORED_TABLES 对齐**：方案 A 不动 signal-service；若 SIT 验证项 10 catch 到 date_col 偏移涉及 signal-service 侧，另案。
- **方案 B 升级路径**：未来若新数据源接入 > 10 张表（PL 决策记录信号 1）/ 运维告警频繁误报（信号 2）/ 团队扩到多人新人加表错配率 > 30%（信号 3），由 tech-lead 立 **ADR-016 数据管道注册中心升级**（SyncSpec dataclass + 静态 raise，沿用本 ADR 方案 B 草稿）。
- **Tushare API SDK 版本升级 / fallback 数据源（akshare）方案**：与本 ADR 写入路径正交，不涉及。
- **scheduler cron 调度时间表的重排**：本 ADR 仅治理 backfill 链路，cron 时间表（17:03 / 16:05 等）由运维另议。
- **下游因子改造**：本 ADR 写入路径统一不影响下游因子 SQL；下游因子改造单独在 ADR-013+ schema 对齐 ADR 内处理（与 ADR-008~011 同型）。

## 后续工作

- [x] **product-lead**：决策方案 A vs B —— **2026-06-22 选定方案 A**（理由见顶部 PL 决策记录段）
- [x] **tech-lead**：按 PL 决策 A 升 Accepted + 写实 §决策 0 文件白名单 + 写实 §决策 5 实施细则 + §决策 6 SIT 清单 + §决策 7 分阶段顺序 —— **本次 commit 落盘**
- [ ] **backend-dev**（限额重置后 / 新会话，与 ADR-010 / ADR-011 follow-up 合并到同一 worktree）：按本 ADR 决策 5-7 实施方案 A：
  - 阶段 1: `_insert_rows` 加 retries / data_volume_floor 参数（白名单 #1）
  - 阶段 2: `_pg_write` 改 thin wrapper（白名单 #2）
  - 阶段 3: `_pg_bulk_insert` 改 thin wrapper（白名单 #3）
  - 阶段 4: `_BACKFILL_MAP` 补齐 5 表（含 stk_factor_pro 双轨 sync）（白名单 #4-a）
  - 阶段 5: `validate_pipeline_consistency()` 启动期自检（白名单 #4-b）
  - 阶段 6: SIT 12 项 + git diff 白名单审计；证据写入 `progress/backend-dev.md` SIT 段
- [ ] **tech-lead**（backend-dev 完成后）：抽取本 ADR 决策 0 + 决策 5/6 + 模板片段到 `.claude/skills/agf-writing-adr/SKILL.md` 新增 "schema-alignment subtemplate"，给 ADR-013+ 复用（瘦身预估 20-30%）
- [ ] **tech-lead**：ADR-012 实施完成 + UAT 通过后 1-2 周内立 **ADR-013**（建议从 hk_holdings 起，因其与 ADR-009 pledge_detail 在同一 alembic 008 内迁移过、调用方多、是验证瘦身模板效果的最佳样本——不再从 stk_factor_pro 起，因 stk_factor_pro 已被 ADR-012 阶段 4 修了 backfill handler）

## 版本与查证

**查证基线日期**：2026-06-22（Proposed → Accepted 同日，PL 决策当日；方案 A 全部基于既有依赖，无需新查证）

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `pip show psycopg2` 实测；与 ADR-008/009/010/011 同基线；`information_schema.columns` introspect（决策 5.5 检查 2）+ `psycopg2.OperationalError` retry catch（决策 5.1）均 PG 15 原生 |
| PostgreSQL | 15.x | 17.x | 2 major | Active 至 2027-11 | 与 ADR-001/006/008-011 一致 |
| Alembic | 1.18.4 | 1.18.4 | 0 | Active | 与 ADR-008-011 同基线；本 ADR 不引 Alembic 新功能 |
| Python `inspect.signature` | stdlib（Python ≥ 3.3） | stdlib | 0 | Active | 决策 5.5 检查 3 用 `inspect.signature(fn).parameters` 检测 days_back 参数；Python ≥ 3.10 基线已覆盖 |
| Python `dataclasses` | stdlib（保留方案 B 未来升级用） | stdlib | 0 | Active | PEP 557 自 Python 3.7 引入；ADR-012 方案 A 实施不依赖，但 ADR-016 升级（方案 B 备份）会用 |

**方案 A 不引入新依赖**：所有改造基于既有 psycopg2 / Python stdlib（inspect）/ alembic / 现有 logger；CLAUDE.md Tech Stack 表无需更新。

**实证 grep 来源**（2026-06-22）：

| 实证项 | 命令 | 结果 | 文件 |
|---|---|---|---|
| 4 套写入路径 | `grep -lE "psycopg2.connect"` + `grep -nE "_insert_rows\|_pg_write\|_pg_bulk_insert"` | etl.py / pg_writer.py / cb_sync.py / 8 个 sync 模块 inline executemany | 见现状盘点 1 |
| MONITORED_TABLES 48 表 | python ast 解析 scheduler.py:59-116 | 48 个 key | `scheduler.py:59-116` |
| _BACKFILL_MAP 43 handler | python ast 解析 scheduler.py:119-167 | 43 个 key | `scheduler.py:119-167` |
| 5 表缺 backfill | set 差集 | `[index_daily, stk_factor_pro, stocks, ths_daily, trade_cal]` | 见现状盘点 2 |
| stk_factor_pro 仅拉 today | grep `pro.stk_factor_pro(trade_date=today)` | scheduler.py:558（无 days_back 循环） | `services/data-service/app/scheduler.py:531-631` |
| `_insert_rows` 自动列过滤 | grep `valid_cols = ` | etl.py:180-188（commit 2d311fa） | `packages/kronos-data/kronos_data/etl.py:167-200` |
| `_pg_bulk_insert` 与 `_pg_write` 重复 | diff cb_sync.py:58-90 vs pg_writer.py:13-51 | 95% 重复 | 见两文件 |
| inline executemany 8 文件 | `grep "db.executemany\|INSERT INTO"` in services/data-service/app/sync/*.py | 8 文件命中（方案 A 不改） | 见现状盘点 1 路径 #4 |

**与 CLAUDE.md "数据管道" 段一致性**：当前 `## Tech Stack` 表 `数据管道 data-service (asyncio 调度 + PG-first 直写 + Tushare 1.4.29) + SQLite fallback ADR-006` 行不变；本 ADR 是该行的细化治理 ADR，不替换 ADR-006，也不引新行（方案 A 无新依赖）。

---

**Hand-off 给 backend-dev**（限额重置后 / 新会话，按 PL 协调与 ADR-010 + ADR-011 follow-up 合并到同一 worktree 执行）：

按 §决策 7 分阶段实施顺序，**严格不越白名单**（§决策 0）：

**前置准备**：
1. 拉新 worktree（PL 会指定 base ref，本 ADR + ADR-010 + ADR-011 follow-up 三家合并）
2. 读三份 ADR：本 ADR §决策 0 / 5 / 6 / 7、ADR-010 决策 0、ADR-011 Hand-off 段（三家白名单互不冲突，但叠加后总改动面应可一次 PR 内完成）

**实施顺序**：
1. ADR-011 实施（top_inst schema 对齐，独立——见 ADR-011 Hand-off 段）
2. ADR-010 follow-up 实施（依 ADR-010 code-review 结论而定，PL 在新派单时附说明）
3. **本 ADR 阶段 1-6**（见 §决策 7）：
   - 顺序严格按 1→2→3→4→5→6，每阶段独立可 commit
   - 任一阶段 SIT 失败可停在该阶段回滚点（如阶段 3 失败不影响阶段 1/2 已提交）
   - 阶段 4 stk_factor_pro 改造涉及 scheduler.py 同文件内函数抽取，是机械工作量最大的一步——不可越界改 cron 配置

**SIT 验证**：12 项清单（§决策 6），证据落 `progress/backend-dev.md` 的 `**SIT 证据**` 段；任一项 [ ] 未通过不得进 code-review。

**报告产出**：
- `progress/backend-dev.md`：5 段格式（状态 / Skills / SIT 证据 [含 12 项 AC `[x]/[ ]` 内联] / 质量门 / 下一步）；SIT 段必须含 `git diff main --stat` 输出证明仅命中白名单 4 文件
- 不写独立 SIT 报告（按 `.claude/standards/ac-lifecycle.md` "Self-Reporting Pattern"，由 code-reviewer 在 review 时 audit）

**白名单边界（再次强调）**：
- ✅ 允许：`packages/kronos-data/kronos_data/etl.py`（仅 `_insert_rows` 加参数）
- ✅ 允许：`services/data-service/app/sync/pg_writer.py`（_pg_write thin wrapper + _VOLUME_FLOOR_MAP）
- ✅ 允许：`services/data-service/app/sync/cb_sync.py`（_pg_bulk_insert thin wrapper）
- ✅ 允许：`services/data-service/app/scheduler.py`（_BACKFILL_MAP 补 5 表 + sync_stk_factor_pro_backfill + validate_pipeline_consistency）
- ❌ 禁改：路径 #4 inline 8 模块（announcements/cctv_news/mp_report/interact/policy_law/fina_mainbz/fina_audit/stock_profiles）
- ❌ 禁改：alembic / init_postgres.sql / packages/kronos-factors / signal-service / CLAUDE.md Tech Stack
- ❌ 禁改：32+ sync 函数签名 / 各 sync 函数内 cols 字面量 / cron 配置 / detect_data_gaps / trigger_data_backfill 核心逻辑

越界 = 违约，PL 直接回退到 ADR 边界。
