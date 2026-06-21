# ADR-010: cyq_chips schema 对齐 — 存 per-price 明细

- 状态：Proposed（**大纲，业务方向已定，待 tech-lead 细化技术细节后 Accepted**）
- 日期：2026-06-22
- 决策者：product-lead（业务方向）+ tech-lead（待细化：迁移脚本/数据量/版本审计）
- 影响范围：services/sql/init_postgres.sql + backend/alembic/versions/009（待定）+ packages/kronos-data/kronos_data/etl.py（sync_cyq_chips）+ 下游因子消费方（packages/kronos-factors/）
- 编号说明：ADR-008 sw_daily / ADR-009 pledge+rt_sw+toplist 已 Accepted；本决策顺延 ADR-010

## 上下文

`cyq_chips`（筹码分布）当前 schema 与 Tushare 实际返回**完全错位**。探针实测（2026-06-22）：`pro.cyq_chips(ts_code='000001.SZ', trade_date='20260618')` 返回字段只有 `ts_code, trade_date, price, percent`，且是 **per-price-level 明细**（每股每日约 104 个价格档位，每个档位一条）。但 PG 表 `cyq_chips` 当前建的是 `code, trade_date, avg_cost, concentration_90, profit_ratio`（聚合指标）——**Tushare 根本不返回这 3 个字段，它们是建表时凭空想象的死列**，sync 从未写入过真实值。

下游 `packages/kronos-factors/kronos_factors/scorer/advanced_factors.py` 的筹码因子读 `price, percent`（按价格档算集中度/平均成本），但因为表物理列是聚合名，`_insert_rows` 静默吞掉 sync 的 price/percent（ADR-008 §上下文 问题 #2），因子长期 fallback。

不做此决策：筹码集中度因子永久失效（同 sw_daily 的 pe 因子、pledge 的 pledge_total_ratio 因子），50 维评分继续缺一项。

## 决策

**存 Tushare 原始 per-price 明细**（数据源为准），聚合指标由下游从明细算。

| 维度 | 选型 | 理由 |
|---|---|---|
| 目标列集 | `(code, trade_date, price, percent)` | 对齐 Tushare 唯一返回字段 + 下游读法 |
| 主键 | `(code, trade_date, price)` | 同股同日多 price 档，price 是天然区分维度 |
| 死列处理 | 删 `avg_cost / concentration_90 / profit_ratio` | Tushare 无此字段，从未有真实值，保留是噪音 |
| 聚合指标 | 不存表，下游算 | `avg_cost = Σ(price×percent)`、集中度从明细推导，符合"存原始、下游加工"原则（ADR-006 §决策2）|
| sync / 下游 | **零改动** | sync_cyq_chips 已用 `r.get("price")/r.get("percent")`，advanced_factors 已读 price/percent —— 是 6 表里改起来最轻的 |

**数据量约束**：sync_cyq_chips 当前只拉 top 300 股（by market cap）+ 近期（`days_back` 默认 5），明细 104 行/股/日 → 30 天 ≈ 93 万行，PG 15 单表可控。全市场/长期历史另议（见"不覆盖"）。

## 备选方案

- **A. 改 sync 反向算聚合写表（avg_cost/concentration_90）** — pros: 表不动；cons: Tushare 无这些字段，sync 要自己 Σ(price×percent) 算 avg_cost，且下游 advanced_factors 读的是 price/percent（不是 avg_cost），改了 sync 还得改下游；算两次。**否决理由**：违背"存原始、下游加工"，且 sync + 下游双改比单改表更重。
- **B. 明细 + 聚合双列都存** — pros: 下游想用哪个都行；cons: 聚合列冗余（可从明细算），双写易不一致。**否决理由**：违反单一来源原则。
- **C. 新建 cyq_chips_detail 表双写灰度** — pros: 零停机；cons: cyq_chips 是日级 ETL 非高频，TRUNCATE+重拉窗口 < 1 分钟，双表复杂度收益比不成立（同 ADR-008 备选 B 否决理由）。**否决**。

## 影响

- **对现有代码**（待 tech-lead 细化范围）：
  - `services/sql/init_postgres.sql`：cyq_chips DDL 改写（4 列 + 主键）
  - `backend/alembic/versions/009_cyq_chips_align.py`（待定编号）：DROP 3 死列 + ADD price/percent + 改主键 —— ⚠️ **改主键是破坏性**，需先 DROP CONSTRAINT 旧 PK（如有）再 ADD 新 PK
  - `etl.py sync_cyq_chips`：**零改动**（已用 price/percent）
  - 下游 `advanced_factors.py`：**零改动**（已读 price/percent）
- **对成本**：API 300 股 × days_back 次调用（同现状）；存储 ~93 万行 × 4 列 ≈ 可忽略
- **对运维**：回补前 TRUNCATE（改主键前表须无重复 (code,trade_date,price)）；监控 `COUNT(*) FILTER(WHERE price IS NOT NULL) > 0`

## 本 ADR 不覆盖的决策

- **cyq_chips 全市场扩展**（从 top 300 → 全市场 5000 股）：数据量 5×，需评估是否分区，另开 ADR
- **cyq_chips 长期历史回补**（> 30 天 / 年级）：单表超 1000 万行考虑按年分区
- **聚合指标的下游实现**（avg_cost/集中度从明细算的具体公式）：属因子实现细节，非 schema 决策

## 后续工作

- [ ] **tech-lead**：细化本 ADR 到可实施——Alembic 009 迁移脚本（改主键的破坏性处理）、数据量/分区评估、`## 版本与查证` 回填（PG/Alembic/psycopg2/Tushare cyq_chips 接口版本），状态升 Accepted
- [ ] **backend-dev**（限额重置后 / 新会话）：按 Accepted ADR-010 实现 + SIT（TRUNCATE → 改主键迁移 → sync_cyq_chips 回补 → 验证 price 非空 → detect OK）

## 版本与查证

> 待 tech-lead 细化时回填。基线参考 ADR-008/009（PG 15 / Alembic 1.18.4 / psycopg2 2.9.12 / Tushare 1.4.29）。Tushare cyq_chips 接口需 6000 积分（现有 latest=06-04 数据证明 token 可拉）。
