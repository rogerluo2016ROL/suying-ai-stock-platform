# ADR-011: top_inst schema 对齐 — 存 per-institution 明细 + 下游聚合改造

- 状态：Proposed（**大纲，业务方向已定，待 tech-lead 细化技术细节后 Accepted**）
- 日期：2026-06-22
- 决策者：product-lead（业务方向）+ tech-lead（待细化：主键策略/聚合方案/迁移/版本审计）
- 影响范围：services/sql/init_postgres.sql + backend/alembic/versions/010（待定）+ packages/kronos-data/kronos_data/etl.py（sync_top_inst）+ **下游因子消费方（advanced_factors.py / diagnosis_engine.py，需聚合改造）**
- 编号说明：顺延 ADR-010

## 上下文

`top_inst`（龙虎榜机构席位）当前 schema 是 **per-stock-per-day 聚合**，但 Tushare 实际返回 **per-institution 明细**。探针实测（2026-06-22）：`pro.top_inst(trade_date='20260618')` 返回 `trade_date, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, side, reason`，单日 1020 行、每股约 10 个机构席位。`exalter`（席位名）多为「机构专用」（匿名），但 `buy/sell/net_buy` 是真实席位数据。

PG 表 `top_inst` 当前是 `(code, trade_date, inst_name, buy_amount, sell_amount, net_amount)`（聚合到 stock/day，丢机构维度）。sync 写的 `exalter/buy/sell/net_buy` 列名与表的 `inst_name/buy_amount/...` 对不上，`_insert_rows` 静默吞，表里这些列恒 NULL。下游 `advanced_factors.py` / `diagnosis_engine.py` 读 `net_amount`（stock/day 聚合维度），目前因子勉强跑通是因为 net_amount 在"交集"里——但从未被 sync 写入真实值。

**两难**：Tushare 是明细（per-institution），下游消费是聚合（per-stock-per-day 的 net_amount）。存明细会丢聚合便利，存聚合会丢机构维度信息。

不做此决策：top_inst 表数据残缺（机构买卖额恒 NULL），龙虎榜机构因子实际拿不到真实数据。

## 决策

**存 Tushare 原始 per-institution 明细**（数据源为准），下游需要 stock/day 聚合的用 `SUM` 或物化视图。与 ADR-010 哲学一致（存原始、下游加工）。

| 维度 | 选型 | 理由 |
|---|---|---|
| 目标列集 | `(code, trade_date, exalter, side, buy, sell, net_buy, buy_rate, sell_rate, reason)` | 对齐 Tushare 返回字段（exalter=席位名，side=买/卖方向 0/1）|
| 主键 | **待 tech-lead 定**（见下方风险）| ⚠️ "机构专用"匿名导致 (code,trade_date,exalter,side) 可能重复 |
| 死列处理 | 删 `inst_name/buy_amount/sell_amount/net_amount`（聚合列）| 由 exalter/buy/sell/net_buy 取代；聚合下游算 |
| 下游聚合 | `SUM(net_buy)` 或物化视图 `mv_top_inst_daily` | 下游现读 net_amount（stock/day）需改为聚合 |
| sync 改动 | cols 改 `inst_name→exalter, buy_amount→buy, sell_amount→sell, net_amount→net_buy` | r.get 不变（Tushare 原字段名）|

### 主键风险（待 tech-lead 细化）

`exalter` 多为「机构专用」（匿名），同一 (code, trade_date, side) 可能有多个「机构专用」席位 → `(code, trade_date, exalter, side)` 不唯一。候选方案：
- **方案 i**：自增 `id` 主键 + `(code, trade_date, exalter, side)` 普通索引（放弃业务唯一约束，允许重复席位）
- **方案 ii**：`(code, trade_date, exalter, side, buy, sell)` 复合键（加买卖额区分，但极端情况仍可能重复）
- **方案 iii**：保留 ON CONFLICT DO NOTHING + 最小业务键，重复席位跳过（丢少量数据）

tech-lead 需在细化时定（实测"机构专用"重复频率）。

### 下游聚合改造（本 ADR 与 ADR-010 的关键差异）

下游 `advanced_factors.py` / `diagnosis_engine.py` 现读 `net_amount`（stock/day 聚合）。改 per-institution 明细后需聚合：
- **选项 A（推荐）**：建物化视图 `mv_top_inst_daily(code, trade_date, sum_buy, sum_sell, sum_net)`，下游读视图（零下游代码改动，仅改表名/列名映射）
- **选项 B**：下游 SQL 改 `SUM(net_buy) GROUP BY code, trade_date`（改 advanced_factors/diagnosis 代码，非白名单）

## 备选方案

- **A. 改 sync 反向聚合写表（保留 stock/day 聚合 schema）** — pros: 表/下游不动；cons: sync 要按 (code,trade_date) GROUP BY SUM，丢机构维度（最大买方席位等信息永久丢失），且 Tushare 明细才是原始数据。**否决理由**：信息损失，违背"存原始"。
- **B. 明细 + 聚合双表** — pros: 明细/聚合各取所需；cons: 双写复杂、物化视图已能解决聚合需求。**否决**（物化视图是更轻的聚合方案）。
- **C. 不动表，只让下游从 top_list（已对齐）读机构数据** — pros: 零改动；cons: top_list 是龙虎榜个股明细（含 l_buy/l_sell 营业部），top_inst 是机构席位，语义不同，不可替代。**否决**。

## 影响

- **对现有代码**（待 tech-lead 细化）：
  - `services/sql/init_postgres.sql`：top_inst DDL 改写（明细列 + 主键待定）+ 可能加 `mv_top_inst_daily` 物化视图 DDL
  - `backend/alembic/versions/010_top_inst_align.py`（待定）：DROP 聚合列 + ADD 明细列 + 改主键（破坏性）
  - `etl.py sync_top_inst`：cols 改映射（exalter/buy/sell/net_buy）
  - **下游 `advanced_factors.py` / `diagnosis_engine.py`**：改读 `mv_top_inst_daily`（选项 A）或 `SUM`（选项 B）—— ⚠️ 不在 schema ADR 白名单，需单独 task
- **对成本**：API 30 次（30 交易日）；存储 1020 行/日 × 30 ≈ 3 万行，可忽略
- **对运维**：物化视图刷新时机（盘后 sync 后 REFRESH）；监控 `COUNT(*) FILTER(WHERE net_buy IS NOT NULL) > 0`

## 本 ADR 不覆盖的决策

- **主键最终方案**（自增 id / 复合键 / ON CONFLICT 跳过）：tech-lead 实测"机构专用"重复频率后定
- **下游聚合改造的具体实现**（物化视图 vs SQL SUM）：tech-lead 细化，下游改动单独 task
- **top_inst 历史回补深度**（> 30 天）：当前因子用近期，扩展另议

## 后续工作

- [ ] **tech-lead**：细化本 ADR——主键方案（实测"机构专用"重复）、聚合方案（物化视图 vs SUM）、Alembic 010 迁移、`## 版本与查证` 回填，状态升 Accepted
- [ ] **backend-dev**（限额重置后 / 新会话）：按 Accepted ADR-011 实现 schema + sync 改造 + SIT
- [ ] **backend-dev / 下游 task**：advanced_factors.py / diagnosis_engine.py 的聚合改造（改读 mv_top_inst_daily 或 SUM）—— 独立于 schema ADR 的单独 task

## 版本与查证

> 待 tech-lead 细化时回填。基线参考 ADR-008/009/010（PG 15 / Alembic 1.18.4 / psycopg2 2.9.12 / Tushare 1.4.29）。Tushare top_inst 接口 2000 积分。
