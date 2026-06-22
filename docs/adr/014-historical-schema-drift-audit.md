# ADR-014: 历史 schema drift 一次性 audit + 索引登记

- 状态：**Proposed**（待 backend-dev 实施 SIT + reviewer audit 通过后升 Accepted）
- 日期：2026-06-22
- 决策者：tech-lead 起草；product-lead 排期实施
- 影响范围：审计性 ADR，**不直接做 schema 迁移**；产出审计报告 + 索引登记清单 + ADR-014.X 子 ADR 建议清单

## 上下文

ADR-008~013 完成 sw_daily / pledge_detail / rt_sw_k / top_list / cyq_chips / top_inst / ths_daily 共 7 表的 schema 对齐。memory `data-pipeline-write-debt` 与 ADR-011/012 review 揭示剩余至少 8+ 表（hk_holdings / repurchase / share_float / cyq_perf / stock_news_tushare / research_reports_tushare / stk_factor_pro / index_daily 等）的 init_sql DDL 与 DB 实际列集**对账状态未知**。

ADR-013 实测 ths_daily 一表 init_postgres.sql 声明 8 列、DB 实际 17 列 —— **9 列偏差**；ADR-011 review §1.3 / S-5 标记 `idx_cyq_chips_date`、`idx_top_inst_date`（init_sql 未声明、DB 实存）等 legacy 索引未登记，是同型「历史 schema drift」的另一种形态。

**核心问题**：剩余表是否每张都有类似偏差？哪些表偏差 ≥ ADR-013 同级（≥ 3 列差异、PK 不一致或类型不一致）需要单立 ADR-014.X 子 ADR 修复？哪些可以判定为「DB 现状即权威，只补 init_sql」就行？目前没有数据回答这个问题，**任何"下一张表先修哪一张"的决策都缺基础**。

### ADR-010 F-1 合并背景

ADR-010 backlog 留有 F-1：「`idx_cyq_chips_date` schema drift（init_sql 未声明，DB 实存）」—— ADR-011 review §1.3 S-5 把 F-1 升级为「历史 schema drift 索引登记/清理」task 并建议合并到本 ADR。本 ADR 把 F-1 + S-5 一并纳入 audit 范围。

### 不做此决策的后果

1. **下一张 schema 对齐 ADR（ADR-014.X / ADR-016 系列）盲选**：tech-lead 没有 diff 数据，只能凭直觉挑表，可能漏掉「丢列每天造成 fallback」的高危表（如 ths_daily 是因 ADR-012 review SIT 5 偶然暴露才发现）
2. **运维侧 schema drift 累积无可见性**：DB 实存但 init_sql 未声明的列 / 索引会无人维护，新环境 init + 老环境 alembic 走出两套形态
3. **ADR-013 后期会被反复打开**：每次 reviewer 在另一表上发现同型偏差就要拆新 ADR 单独修，ADR 模板瘦身（ADR-012 后续工作 #3）的 ROI 被稀释

## 决策

### 决策 0：本 ADR 的范围（audit only，不做 schema 迁移）

⚠️ **本 ADR 是审计型 ADR**：产物是 **审计报告（schema diff 清单）+ 索引登记清单 + 子 ADR 建议清单**，**不修改任何 schema**。任何具体的 schema 迁移必须**拆出独立子 ADR-014.X**（参考 ADR-008/009/010/011/013 同型骨架）由 tech-lead 起草、PL 排期、backend-dev 实施。

**Decision 0 范围声明**：
- ✅ 允许产出：`docs/reviews/schema-drift-audit-YYYY-MM-DD.md` 审计报告 + 本 ADR 末尾的「子 ADR 建议清单」+ 索引登记表
- ✅ 允许产出：一次性 Python 脚本（不进生产 service code）`tools/schema_audit.py`（可放 `scripts/` 或 `services/sql/audit/`，本 ADR 推荐 `services/sql/audit/schema_audit.py`，与 `data_quality_check.sql` 同目录）
- ❌ 禁产出：alembic 迁移（含新建任何 alembic 版本）
- ❌ 禁产出：init_postgres.sql 改动
- ❌ 禁产出：任何 sync 函数改动
- ❌ 禁产出：CLAUDE.md Tech Stack 表改动（本 ADR 不引新依赖）

**子 ADR 拆分规则**（决策 4 详化）：每张 audit 出的 drift 表若满足以下任一条件，必须拆独立 ADR-014.X（或顺延 ADR-016+ 编号）：
- 列差异 ≥ 3 列
- PK / UNIQUE 约束不一致
- 类型不一致（`text` vs `date`、`integer` vs `bigint` 等）
- 涉及业务下游因子读侧故障（grep 因子代码命中该表）

不满足上述任一条件的「DB 现状即权威，只补 init_sql」的轻量对齐 → 在本 ADR 末尾「轻量对齐清单」列出，由 backend-dev 在下一次 schema 类 ADR 实施时**顺手批量提交**（不单立 ADR，工作量 < 30 分钟）。

### 决策 1：审计范围 — 候选表清单

从以下 4 个来源汇总候选表：

1. **memory `data-pipeline-write-debt` 5 表未查清单**：`stk_factor_pro / ths_daily / stock_news_tushare / research_reports_tushare / cyq_perf / hk_holdings / repurchase / share_float`（含 cyq_perf 双写 cyq_chips 已在 ADR-010 修但 cyq_perf 未修）
2. **PG introspect 全表清单**：`SELECT table_name FROM information_schema.tables WHERE table_schema='public'`，与 init_postgres.sql 中 `CREATE TABLE` 字面解析后的表集做对账，差集列出
3. **ADR-008~013 已修过的表**：sw_daily / pledge_detail / rt_sw_k / top_list / cyq_chips / top_inst / ths_daily 共 7 表 —— **排除**（本 ADR 不重复审计）
4. **scheduler.MONITORED_TABLES 48 表**：列入候选（虽然不全是 drift 表，但 MONITORED 表 schema 一致性是 P0 监控价值前提）

去重后，初步候选表清单（待审计脚本实跑 + DB introspect 确认）：

| # | 表 | 来源 | drift 嫌疑级别 | 备注 |
|---|---|---|---|---|
| 1 | `hk_holdings` | memory | 高 | DB introspect 仅 4 列，init_sql DDL 不详；港股通持股数据，下游因子可能用 |
| 2 | `repurchase` | memory | 高 | DB introspect 4 列；股票回购数据 |
| 3 | `share_float` | memory | 高 | DB introspect 4 列；解禁数据 |
| 4 | `cyq_perf` | memory | 高 | 与 cyq_chips 同源 sync 但 ADR-010 只修了 cyq_chips；筹码绩效数据 |
| 5 | `stock_news_tushare` | memory | 中 | 5 列；股票新闻数据 |
| 6 | `research_reports_tushare` | memory | 中 | 6 列；研报数据 |
| 7 | `stk_factor_pro` | memory | 高 | DB 21 列；ADR-012 已修 backfill handler 未修 schema；高频因子表 |
| 8 | `index_daily` | memory | 高 | DB 9 列；指数日线，下游因子常用 |
| 9 | `index_basic` | ADR-012 LD-2 | 低 | 已确认 `updated_at` 缺失，ADR-013 移除监控；本 ADR 顺便审计列集 |
| 10 | `stk_factor` | scheduler MONITORED | 中 | DB introspect 待确认 |
| 11 | `rt_k` | scheduler MONITORED | 低 | 实时数据，schema 多变；audit 仅登记不强求对齐 |
| 12 | `rt_sw_k` | scheduler MONITORED | 中 | 同上 |
| 13 | `cb_basic` | data-pipeline-write-debt 隐含 | 中 | DB 38 列；可转债基础 |
| 14 | `cb_daily` | data-pipeline-write-debt 隐含 | 中 | DB 16 列；可转债日线 |
| 15 | `cb_price_chg` | data-pipeline-write-debt 隐含 | 中 | DB 8 列；可转债转股价变动 |
| 16 | `ths_concept_map` | data-pipeline-write-debt 隐含 | 低 | DB 4 列；同花顺概念映射 |
| 17 | 其他 PG 实存表 vs init_sql 差集 | audit 脚本实跑发现 | 待定 | 含可能的孤儿表 / 临时表 |

**初步评估行数：~20 张待审计表**（含 audit 脚本可能发现的额外孤儿表 5-10 张）。

### 决策 2：审计方法

#### 2.1 一次性脚本 `services/sql/audit/schema_audit.py`

输入：PG 连接 + `services/sql/init_postgres.sql` 路径
输出：`docs/reviews/schema-drift-audit-YYYY-MM-DD.md`

骨架（伪代码）：

```python
"""ADR-014 一次性 schema audit 脚本.

用法: python services/sql/audit/schema_audit.py

输出: docs/reviews/schema-drift-audit-YYYY-MM-DD.md
"""
import os, re, sys
from datetime import date
import psycopg2

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
INIT_SQL = "services/sql/init_postgres.sql"
EXCLUDED = {  # ADR-008~013 已修, 不重复审计
    "sw_daily", "pledge_detail", "rt_sw_k", "top_list",
    "cyq_chips", "top_inst", "ths_daily",
}

def parse_init_sql(path):
    """正则解析 CREATE TABLE 段, 返回 {table: [cols], pk: [...], unique: [...]}"""
    # 正则 r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)\s*;'  ── DOTALL
    # 逐表解析列名 + PRIMARY KEY (..) + UNIQUE(..)
    ...

def introspect_db(conn):
    """PG introspect 全 public schema 表: {table: [(col, type, nullable)], pk_cols, unique_cols, indexes}"""
    cur = conn.cursor()
    # information_schema.columns + information_schema.table_constraints + pg_indexes
    ...

def diff_table(db_meta, init_meta):
    """对比单表 DB vs init_sql, 返回 diff dict:
       {
         "only_in_db": [cols], "only_in_init": [cols],
         "type_mismatch": [(col, db_type, init_type)],
         "pk_diff": (db_pk, init_pk),
         "unique_diff": (db_uniques, init_uniques),
         "indexes_legacy": [idx_name],  # DB 实存但 init_sql 未声明
         "severity": "high|medium|low",  # 决策 4 规则判定
       }
    """
    ...

def render_md_report(diffs, output_path):
    """渲染 markdown 报告, 含 §候选清单 §严重度分类 §子 ADR 建议 §轻量对齐清单 §索引登记"""
    ...

if __name__ == "__main__":
    conn = psycopg2.connect(PG_URL)
    init_meta = parse_init_sql(INIT_SQL)
    db_meta = introspect_db(conn)

    all_tables = set(db_meta.keys()) | set(init_meta.keys())
    diffs = {}
    for t in sorted(all_tables - EXCLUDED):
        diffs[t] = diff_table(db_meta.get(t, {}), init_meta.get(t, {}))

    out = f"docs/reviews/schema-drift-audit-{date.today().isoformat()}.md"
    render_md_report(diffs, out)
    print(f"Audit complete: {out}")
    print(f"Tables audited: {len(diffs)}")
    print(f"High severity: {sum(1 for d in diffs.values() if d['severity']=='high')}")
```

**关键设计**：
- 脚本可重复跑（幂等）—— 每次跑生成带日期后缀的报告，便于跨时间对比
- `parse_init_sql` 正则解析比导入 sqlglot 等第三方库更轻量（init_postgres.sql 是手写 SQL，结构稳定）；若正则无法 robust 解析，可降级到 `sqlparse`（已在 Python 生态广泛，pure-python）—— 备选见 §决策 3
- `introspect_db` 用 `information_schema` 标准 SQL，PG 15 原生
- `diff_table` 输出严格 dict 结构，便于后续脚本读取（如生成子 ADR 模板）
- **不写入数据库**（read-only），不修改任何 schema

#### 2.2 索引登记

audit 脚本同时输出「索引登记表」，覆盖：

| 表 | 索引名 | 列 | 来源（init_sql / DB 实存 / alembic 文件 N） | drift 状态 |
|---|---|---|---|---|
| top_inst | idx_top_inst_date | (trade_date) | DB 实存（legacy, init_sql 未声明） | drift |
| top_inst | idx_top_inst_code_date | (code, trade_date) | init_sql + alembic 010 | 同步 |
| cyq_chips | idx_cyq_chips_date | (trade_date) | DB 实存（legacy） | drift |
| ... | ... | ... | ... | ... |

drift 状态可选 `synced` / `drift-init-missing`（DB 有但 init_sql 无）/ `drift-db-missing`（init_sql 有但 DB 无）/ `legacy-redundant`（DB 有但被 alembic 后续 superseded 的索引）。

### 决策 3：审计脚本备选方案

- **A. 选 sqlparse 替代正则**：pros: 健壮；cons: 多一个依赖。**否决理由**：init_postgres.sql 是手写 SQL（仅 `CREATE TABLE IF NOT EXISTS` 风格统一），正则 + 行级状态机够用；若正则失败再降级 sqlparse（已 pure-python，pip install 即可，不进生产代码）
- **B. 用 alembic autogenerate 反向生成 diff**：pros: 复用 alembic 既有能力；cons: alembic autogenerate 依赖 SQLAlchemy MetaData 声明（项目无 ORM 层），从 init_postgres.sql 反推 MetaData 工作量超出脚本本身。**否决理由**：增加抽象层与 ADR-006 「不引 ORM」一致性背离
- **C. 手工逐表跑 `psql \d table` + 人脑对比 init_sql**：pros: 零脚本；cons: 20 张表 × 平均 10 列 = 200 行手工对比，错误率高 + 不可重复跑。**否决理由**：典型「应该自动化的工作」
- **D. 升级方案 B 注册中心（ADR-016）跳过本 ADR**：pros: 一次到位；cons: 与 ADR-012 决策一致性破坏（PL 选方案 A 渐进收口理由含「剩余表 < 10 张」，本 ADR audit 可能发现更多 drift 但不立即升级方案 B 是契约）。**否决**

### 决策 4：子 ADR 拆分规则（重申）

audit 脚本输出 `severity` 字段，按以下规则判定：

| 严重度 | 判定条件 | 处置 |
|---|---|---|
| **high** | 列差异 ≥ 3 列 / PK 类型不一致 / 涉及业务下游因子读侧故障 | 必须拆独立 ADR-014.X（或 015.X / 016.X，编号顺延）由 tech-lead 起草 |
| **medium** | 1-2 列差异 / UNIQUE 约束差 / 类型不一致 | 单立 ADR 还是合并到下次 schema ADR 顺手处理由 tech-lead 评估；**默认推荐合并** |
| **low** | 仅注释 / 索引差 / 默认值差 | 轻量对齐清单，backend-dev 在下次 schema 类 ADR 实施时顺手批量提交（init_sql 补齐 + alembic optional） |

**业务下游影响判定**：audit 脚本不自动判定（涉及 grep `packages/kronos-factors/` 因子代码），而是输出「该表是否在 `pg_adapter._COLUMN_MAP` 翻译表内」与「该表是否在 scheduler.MONITORED_TABLES 内」两项作为参考；tech-lead 在 review audit 报告时人工判定。

### 决策 5：本 ADR 完成定义（DoD）

backend-dev 实施完本 ADR，应交付：

1. `services/sql/audit/schema_audit.py` 一次性脚本（< 200 行，含 docstring）
2. `docs/reviews/schema-drift-audit-2026-06-22.md`（或实施当天日期）—— 含以下段：
   - §1 审计范围（实际跑出来的表清单 + 排除 ADR-008~013 已修 7 表）
   - §2 严重度分类（high / medium / low 三档）
   - §3 子 ADR 建议清单（每张 high 严重度表附「建议 ADR-014.X，关键 diff 摘要 3-5 行」）
   - §4 轻量对齐清单（low 严重度表的 init_sql 补齐 patch，直接可用）
   - §5 索引登记表（与决策 2.2 格式一致）
   - §6 ADR-010 F-1 收尾（合并 idx_cyq_chips_date 处置 + idx_top_inst_date 处置）
3. `progress/backend-dev.md` SIT 段（含脚本可重复跑证据 + 报告 markdown 渲染样本）

**不需要交付**：alembic 迁移、init_sql 改动、sync 改动、CLAUDE.md 更新（参 §决策 0）。

### 决策 6：SIT 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | audit 脚本可执行 | `python services/sql/audit/schema_audit.py` | exit 0，stdout 含 `Audit complete: docs/reviews/schema-drift-audit-YYYY-MM-DD.md` |
| 2 | 脚本幂等 | 重跑一次 | 报告内容字面一致（除时间戳），diff 数据稳定 |
| 3 | 报告含 ths_daily 排除 | grep `ths_daily` 报告 | 仅在「§1 排除表清单」段命中（不在 diff 表中） |
| 4 | high severity 表 ≥ 1 | grep `严重度: high` 报告 | 至少 hk_holdings / repurchase / share_float / stk_factor_pro 等候选表中有命中（具体由实跑决定） |
| 5 | 索引登记表完整 | grep `idx_cyq_chips_date\|idx_top_inst_date` 报告 §5 索引登记表 | 两项均命中，drift 状态 = `drift-init-missing` |
| 6 | 子 ADR 建议清单可用 | 检查报告 §3 各 high 表附「关键 diff 摘要」段 | 摘要含「DB 列数 X vs init_sql Y / 差异列 [...]/ 涉及下游 [yes/no]」 |
| 7 | ADR-010 F-1 收尾 | 检查报告 §6 | 含 F-1 完成声明 + idx_cyq_chips_date 处置（建议入轻量对齐清单 init_sql 补齐） |
| 8 | 脚本无 schema 写操作 | grep `INSERT\|UPDATE\|DELETE\|ALTER\|CREATE\|DROP` services/sql/audit/schema_audit.py | 0 命中（仅 SELECT） |
| 9 | git diff 白名单审计 | `git diff main --stat` | 仅命中 `services/sql/audit/schema_audit.py`（新建）+ `docs/reviews/schema-drift-audit-*.md`（新建）+ `progress/backend-dev.md`；不命中 alembic / init_sql / sync / factors |

### 决策 7：脚本写完 + 报告产出后的下一步

**tech-lead 在 audit 报告产出后 1 周内**：
1. 阅读报告 §2 严重度分类 + §3 子 ADR 建议清单
2. 按严重度排序提议 ADR-014.1 / 014.2 / ... 的实施顺序（PL 排期）
3. 写 ADR-014 顶部「accepted」段 + 「子 ADR 拆分实施清单」段（含本 ADR 末尾的 §子 ADR 跟踪表）
4. 同步在 `progress/tech-lead.md` 末尾追加「ADR-014 audit 结论 + ADR-014.1+ 立项排期」段

**PL 排期**：按 high → medium → low 顺序派 backend-dev 实施子 ADR（独立 worktree），每个子 ADR 沿用 ADR-008~011/013 同型骨架（tech-lead 抽取 schema-alignment 子模板加入 `agf-writing-adr` skill 后，模板瘦身 ~20-30%，见 ADR-012 后续工作 #3）。

## 备选方案

- **A. 不做 audit，按 grep + 人脑挑表继续单立 ADR-014** —— pros: 工作量 0；cons: 漏表风险高（ths_daily 就是偶然 SIT 5 发现，不 audit 不知道还有几张同型）；ADR-014 模板瘦身 ROI 被稀释；**否决**
- **B. 把 audit 范围扩展到 alembic 迁移历史（每版本对应表状态）** —— pros: 历史回溯完整；cons: alembic 001-010 已通过 reviewer audit 落盘且 DB alembic_version=010 已稳定，回溯审计 ROI 低；**否决**
- **C. 跳过本 ADR 直接立 ADR-016（方案 B 注册中心）一次性根治** —— pros: 不留中间态；cons: 与 ADR-012 决策 PL 选方案 A 「可逆性优先 + 剩余表 < 10 张」原则破裂；本 ADR audit 实跑可能验证「剩余 drift 表 < 10」从而坐实方案 A 决策；**否决**
- **D. 把 audit 脚本做成 service 长驻 + scheduler 启动自检** —— pros: 持续监控 drift；cons: 与 ADR-012 `validate_pipeline_consistency` 功能重叠（虽然 validate 仅校验 monitored 表 date_col 与 backfill handler 签名，未对账 init_sql vs DB 全 schema）；本 ADR 是一次性 audit，未来 drift 由 schema 类 ADR 本身的 SIT 兜底（每次新 schema 迁移都会 introspect DB）；**否决**
- **E. 用 GitHub Action / CI 定期跑 audit** —— pros: 持续可见；cons: 项目当前无 CI（CLAUDE.md 没有 GitHub Actions 集成）；与 §决策 0 「不改 service code」约束兼容但工作量超出本 ADR；**否决**（列入 ADR-015 / ADR-016 长期规划）

## 影响

- 新建 `services/sql/audit/schema_audit.py`（~200 行）
- 新建 `docs/reviews/schema-drift-audit-YYYY-MM-DD.md`（~5-15 KB，含 §1-§6 段）
- `progress/backend-dev.md` 追加本 task SIT 段
- 现有代码（service / alembic / init_sql / factors）：**零改动**
- CLAUDE.md Tech Stack：**无更新**（不引新依赖）

### 对成本

- 不增 API / 算力 / 存储（audit 脚本仅 read-only PG introspect，单次跑 < 5 秒）
- 工作量：backend-dev 1 day（脚本编写 0.5d + 报告渲染 + SIT 0.5d）
- tech-lead 后续 audit 报告评估：0.5 day

### 对运维

- audit 报告产出后，schema drift 全表清单首次落盘可读，运维 / SRE 可按清单做迁移排期
- 索引登记表为 PG DBA 提供「合法 vs legacy」索引清单（清理 redundant 索引可释放磁盘 + 加速 VACUUM）

### 风险

1. **audit 脚本正则解析 init_postgres.sql 失败**：手写 SQL 偶有非标准格式（缩进 / 注释嵌入）。**缓解**：先实跑一次 + 人工校对 5 张表的 diff，确认正则鲁棒；失败则降级 sqlparse
2. **audit 报告暴露 high severity 表过多（如 > 5 张）**：可能让 tech-lead 排期失衡。**缓解**：本 ADR §决策 4 提供严重度分级，PL 按 high → medium 优先级派单；同时若 high 表 > 8 张，触发 ADR-012 §决策 4 「方案 B 升级信号 1 (> 10 表)」评估 → 立 ADR-016 评估方案 B
3. **audit 报告与 ADR-012 `validate_pipeline_consistency` 重复**：validator 只校验 monitored 表 date_col + handler 签名，本 ADR audit 全 schema 列集 + 索引，**范围不重叠**；运行时定位由 validator 担，规划性 audit 由本 ADR 担

## 本 ADR 不覆盖的决策

- **具体 drift 表的 schema 迁移**：拆独立 ADR-014.X 子 ADR（或顺延 015.X / 016.X 编号），沿用 ADR-008~011/013 同型骨架
- **路径 #4 inline executemany 8+ 模块治理**：留 **ADR-015**
- **方案 B 注册中心升级**：留 **ADR-016**（PL 排期触发信号见 ADR-012 §决策 4）
- **CI / GitHub Action 集成 audit**：留 ADR-016 长期规划
- **alembic autogenerate 切换**：项目无 ORM，autogenerate 不适用；改造成 declarative ORM 是 ADR-016 评估范围
- **W-1 共享连接关闭修复**：ADR-013 §决策 修订段移出，本 ADR audit 时若 audit 脚本无意中复用 etl._get_etl_db() 可顺手处理一并暴露问题；具体修复方案推迟到下一个非 audit 性质的 schema ADR 实施

## 后续工作

- [ ] **product-lead**：派 backend-dev 实施本 ADR（与 ADR-013 / ADR-015 并行，但本 ADR 优先级 P2，ADR-013 P1 在前）
- [ ] **backend-dev**：实施 + SIT 9 项 + 证据落 `progress/backend-dev.md`
- [ ] **code-reviewer**：audit 脚本 read-only 验证 + 报告格式 review
- [ ] **tech-lead**（audit 报告产出后 1 周内）：评估 + 立 ADR-014.X 子 ADR 清单 + 在本 ADR 追加「子 ADR 跟踪表」段
- [ ] **product-lead**：按 tech-lead 提议的 ADR-014.X 顺序排期 backend-dev 实施

## 版本与查证

**查证基线日期**：2026-06-22（Proposed 起稿当日；与 ADR-013 同基线，无新查证）

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | `information_schema.tables / .columns / .table_constraints` + `pg_indexes` 系统视图均 PG 15 原生 |
| PostgreSQL | 15.x | 17.x | 2 major | Active 至 2027-11 | 与 ADR-001/006/008-013 一致 |
| Python `re` | stdlib | stdlib | 0 | Active | init_postgres.sql 解析用 `re.DOTALL` 正则 |
| Python `sqlparse`（备选） | 0.5.x | 0.5.x | 0 | Active（pure-python） | 仅在正则解析失败时引入，**本 ADR 默认不引入** |

**实证 grep 来源**（2026-06-22）：

| 实证项 | 命令 | 结果 |
|---|---|---|
| 候选 drift 表 DB col 数 | `psql -c "SELECT table_name, COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name IN (...) GROUP BY 1 ORDER BY 1"` | hk_holdings=4, repurchase=4, share_float=4, cyq_perf=未查, stock_news_tushare=5, research_reports_tushare=6, stk_factor_pro=21, index_daily=9（DB introspect 2026-06-22） |
| ADR-008~013 已修 7 表 | 静态读 ADR 文件 | sw_daily / pledge_detail / rt_sw_k / top_list / cyq_chips / top_inst / ths_daily（excluded set） |
| init_postgres.sql `CREATE TABLE` 数 | `grep -c "^CREATE TABLE" services/sql/init_postgres.sql` | 约 65（参 CLAUDE.md L100 「65 业务表」） |
| ADR-010 F-1 索引 drift | `psql -c "SELECT indexname FROM pg_indexes WHERE tablename='cyq_chips'"` + grep init_sql | DB 含 idx_cyq_chips_date 但 init_sql 未声明（drift）；ADR-011 review §1.3 / S-5 已标记 |
| pg_adapter._COLUMN_MAP 翻译表 | Read packages/kronos-factors/kronos_factors/pg_adapter.py | 含 `pct_change → change_pct` 等映射；audit 报告参考其判定下游影响 |

---

**Hand-off 给 backend-dev**（限额重置后 / 新会话）：

按 §决策 5 DoD 实施：

1. 起草 `services/sql/audit/schema_audit.py`（< 200 行）—— 参考 §决策 2.1 骨架
2. 实跑脚本生成 `docs/reviews/schema-drift-audit-YYYY-MM-DD.md`（含 §1-§6 全 6 段）
3. 跑 SIT 9 项（§决策 6）—— 含报告内容人工抽查 3 张 high severity 表的 diff 摘要准确性
4. 证据写 `progress/backend-dev.md` `**SIT 证据**` 段
5. 不交付 alembic / init_sql / sync 改动（参 §决策 0）

白名单边界（§决策 0）：
- ✅ 允许：新建 `services/sql/audit/schema_audit.py` + `docs/reviews/schema-drift-audit-*.md` + `progress/backend-dev.md` 追加
- ❌ 禁改：alembic / init_postgres.sql / sync / factors / CLAUDE.md / scheduler

越界 = 违约，PL 直接回退。
