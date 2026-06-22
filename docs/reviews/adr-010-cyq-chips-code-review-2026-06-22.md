---
feature: adr-010-cyq-chips-schema-alignment
reviewer: code-reviewer
date: 2026-06-22
scope: "ADR-010 cyq_chips schema 对齐 — alembic 009 + init_postgres.sql DDL 对齐 + TRUNCATE+upgrade+回补 SIT 证据 audit"
code_verdict: approve
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 0
suggestion_count: 2
go_no_go: "GO with follow-ups (本次实施落地干净；2 个 suggestion 不阻断主线，需由 PL 派 follow-up task)"
---

# ADR-010 cyq_chips schema 对齐 — 代码审查 + SIT Audit

> 审查范围：commit `8e18637` (tech-lead 落 ADR + 009 迁移 + init_sql) + working-tree 仅 `progress/backend-dev.md` 追加 SIT 证据段（backend-dev 实施执行）。
> 审查人：code-reviewer（review-only，未改一行源码）。SIT Audit 为本次审查的一部分，不另起 phase。
> 价值取向：ADR-010 是"修筹码因子永久 fallback 之死"（不是加新功能），所以本次审查的核心是 **白名单合规 + 迁移幂等 + 数据真实落盘**，而非 verdict 体收益。

---

## 0. 审查方法与独立验证

| 验证项 | 命令 / 检查 | 结果 |
|---|---|---|
| working-tree 改动清单 | `git status` | ✅ 仅 `progress/backend-dev.md` 追加（+ vitest cache 无关），代码侧零改动 |
| 白名单越界检查 | `git diff HEAD -- packages/ services/ docker/ backend/ \| head -50` | ✅ **零字节**（backend-dev 未碰 etl.py / advanced_factors / pg_adapter / scheduler / 任何旧 alembic） |
| commit 8e18637 落点（tech-lead） | `git show 8e18637 --stat` | ✅ 3 文件：`backend/alembic/versions/009_cyq_chips_align.py` (新建 78 行) / `docs/adr/010-cyq-chips-schema-alignment.md` (+212/-31) / `services/sql/init_postgres.sql` (+5/-3 仅 cyq_chips 段) — **严格落在白名单内** |
| 009 迁移 AST 解析 | `python3 -c "import ast; ast.parse(open('backend/alembic/versions/009_cyq_chips_align.py').read())"` | ✅ Pass |
| DB alembic_version | `psql -c "SELECT version_num FROM alembic_version"` | ✅ `009` |
| DB cyq_chips schema | `psql -c "\d cyq_chips"` | ✅ 4 列 (code text NN / trade_date date NN / price numeric NN / percent numeric) + PK `(code, trade_date, price)` |
| ADR §决策5 验证 SQL 1 | `SELECT COUNT(*) FROM cyq_chips` | ✅ 36,142（与 dev 报告一致） |
| ADR §决策5 验证 SQL 2 | `SELECT COUNT(DISTINCT code) FROM cyq_chips WHERE trade_date >= CURRENT_DATE - 7` | ✅ 300（top-300 全覆盖） |
| ADR §决策5 验证 SQL 3 | `SELECT code, trade_date, COUNT(*) FROM cyq_chips WHERE trade_date=MAX GROUP BY 1,2 LIMIT 5` | ✅ 000001=104 / 000063=139 / 000100=83 / 000166=101 / 000301=196 档位（per-stock 浮动正常） |
| percent 真正归口 0-100 | `SELECT code, SUM(percent), MIN, MAX FROM cyq_chips GROUP BY code LIMIT 5` | ✅ `SUM ≈ 100.02-100.05`（每股各档位百分比累和 ≈ 100，**确认 0-100 scale 体系**，dev 报告中"单档 max=39.87"是单档峰值非和，无归一化问题） |
| 工作树未触 `etl.py` / `advanced_factors.py` | `git diff HEAD -- packages/` | ✅ 零字节，与 ADR §决策3 "零代码改动" 承诺一致 |
| `sync_cyq_chips` cols 字面与新 schema 一致 | `grep cols /Users/rogerluo/...etl.py:1156` | ✅ `["code","trade_date","price","percent"]` 4 列匹配新表 |
| `advanced_factors.py:1076` 字面命中 | `sed -n 1076p .../advanced_factors.py` | ✅ `SELECT price, percent FROM cyq_chips ... ORDER BY price`，PG 列名直接命中（无需 `_COLUMN_MAP`） |
| init_sql 与 009 终态一致性 | `grep -A6 "cyq_chips" services/sql/init_postgres.sql` | ✅ 4 列 + 三列 PK，与 009 upgrade 后形态字面一致 |

---

## 1. Code Review（按 ADR 决策 0 白名单逐条核）

### 1.1 白名单合规 — ✅ 严格合规

| ADR 决策 0 白名单 | 实际改动 | 越界？ |
|---|---|---|
| `backend/alembic/versions/009_cyq_chips_align.py`（新建） | 8e18637 新建 78 行 | ❌ 无越界 |
| `services/sql/init_postgres.sql` 仅 cyq_chips 段 | 8e18637 改动仅 L296-303（+5/-3）严格 cyq_chips | ❌ 无越界 |
| `packages/kronos-data/kronos_data/etl.py` **零改动** | `git log -1 -- packages/kronos-data/kronos_data/etl.py` 最后 commit = `6280997`（ADR-009 落地，先于本次） | ❌ 无越界 |
| `packages/kronos-factors/.../advanced_factors.py` **零改动** | 同上 | ❌ 无越界 |
| 禁改 `alembic/versions/001-008_*` / `pg_adapter.py` / `scheduler.py` | 全无命中 | ❌ 无越界 |

✅ **backend-dev 完全在白名单内执行**（实际上 backend-dev 本次仅运行迁移 + sync，没改一行源码，最严格）。

### 1.2 Alembic 009 迁移 — ✅ approve

逐条核对 ADR §决策4：

| 检查点 | 实测 | 结论 |
|---|---|---|
| `revision='009'` / `down_revision='008'` | L31-32 字面一致 | ✅ |
| upgrade 三步顺序：DROP 旧 PK → 单条 ALTER（DROP 3 死列 + ADD price/percent）→ ADD 新 PK | L37-61 严格三步 | ✅ |
| 全部 `op.execute` 原生 SQL，禁 `op.add_column`/`op.drop_column`/`op.create_primary_key` (ADR-008 教训) | L41/46/58 三处 `op.execute`，无 `op.add_column` 调用 | ✅ |
| 幂等保护：`DROP CONSTRAINT IF EXISTS` + `DROP COLUMN IF EXISTS` + `ADD COLUMN IF NOT EXISTS` | L41 / L48-50 / L51-52 全覆盖 | ✅ |
| ADD 新 PK 无 `IF NOT EXISTS`（PG 不支持，正确） | L58-61 无 `IF NOT EXISTS`，但前置 DROP 旧 PK 已保护重复 | ✅ |
| downgrade 完整反向：DROP 新 PK → DROP price/percent + ADD 3 死列（DOUBLE PRECISION）→ ADD 旧 PK | L64-78 严格逆序 | ✅ |
| downgrade 死列类型与原 init_sql 一致 (DOUBLE PRECISION) | L71-73 `DOUBLE PRECISION` 与历史 init_sql 字面一致 | ✅ |

> 说明：本迁移的"破坏性"是表数据损失（TRUNCATE），但 ADR §决策5 已明确"3 死列从无数据 + DROP 自动清旧 PK + price 列 NOT NULL 强制要求"——TRUNCATE 是技术必需。执行顺序合规（dev 已先 TRUNCATE 再 upgrade）。

### 1.3 init_postgres.sql cyq_chips 段 — ✅ approve

```sql
-- 实测 L296-303
CREATE TABLE IF NOT EXISTS cyq_chips (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    price NUMERIC NOT NULL,
    percent NUMERIC,
    PRIMARY KEY(code, trade_date, price)
);
```

字面与 009 upgrade 后形态一致。备注：新增 ADR-010 引用注释，可读性 +1。✅

### 1.4 安全审计（OWASP Top 10 简核）

| OWASP 类别 | 适用？ | 结论 |
|---|---|---|
| Injection（SQL/NoSQL/LDAP） | ✅ 适用（迁移含原生 SQL） | 迁移 SQL 是固定字面字符串无参数，零拼接，零注入面 |
| Broken Authentication | ❌ N/A | 本 ADR 不涉及认证 |
| Sensitive Data Exposure | ✅ | cyq_chips 是公开市场数据，无 PII；存储无加密需求 |
| XML External Entities | ❌ N/A | 无 XML |
| Broken Access Control | ❌ N/A | 表无 RBAC 字段 |
| Security Misconfiguration | ✅ | NUMERIC 未限精度，理论上不限位浮点会消耗存储；Tushare 实际返回小数位 <= 4，无风险 |
| XSS / Deserialization / Vuln Components / Insufficient Logging | ❌ N/A | 不适用 |

无安全风险。

### 1.5 前后端对接审查 — N/A

本 ADR 是 DB schema 迁移，无 frontend / API contract 改动，跳过强制覆盖项。

---

## 2. SIT Audit（按 §SIT Audit 4 项检查）

> dev 在 `progress/backend-dev.md` §"ADR-010 — cyq_chips schema 对齐"（L313-411）追加完整证据段，本节做独立第三方审计（**未重跑 SIT**，仅审证据可信度 + 自跑独立验证 SQL 比对）。

### 2.1 progress 完整性 — ✅ Pass

`progress/backend-dev.md` L313-411 含本次 task 完整 SIT 证据段（标题"## ADR-010 — cyq_chips schema 对齐"，5 段格式齐：状态 / Skills / SIT 证据 / 质量门 / 下一步）。

### 2.2 AC 覆盖（ADR §决策 0/4/5 验收点）— ✅ Pass

| ADR 验收点 | progress 证据段 | 覆盖？ |
|---|---|---|
| 决策 0：仅审 009 迁移 + 跑 sync，不改源 | "Step 1 — Review 009"（L319-324） + "未动 etl.py/advanced_factors.py/pg_adapter.py" 显式声明（L407） | ✅ |
| 决策 4：alembic upgrade 应用成功，alembic_version=009 | "Step 2 — TRUNCATE + upgrade head"（L327-352）含真实 alembic 日志 + version_num 查询输出 | ✅ |
| 决策 5 验证 SQL 1：总行数非空 | L367-373 实测 36142 | ✅ |
| 决策 5 验证 SQL 2：近 7 天股票数 | L376-382 实测 300 | ✅ |
| 决策 5 验证 SQL 3：per-price 多档 | L385-396 实测 5 股各 83-196 档 | ✅ |

### 2.3 证据可信度 — ✅ Pass

- alembic 日志格式真实（`INFO  [alembic.runtime.migration] Running upgrade 008 -> 009, ...`）；
- `\d cyq_chips` 输出含中文表头"数据表 / 栏位 / 校对规则 / 可空的 / 预设"——确凿来自实际 `psql` 中文 locale，非伪造；
- 三条验证 SQL 的真实 count 与我**独立 psql 复跑**结果字面一致（36142 / 300 / 各股档位数 104/139/83/101/196）；
- sync 输出 `cyq_chips: 36142 fetched, 36142 written (300 stocks)` 与 `etl.py:1171` `print` 语句字面一致，且 fetched==written 证明 `_insert_rows` 未丢列（**ADR-010 修复目标的最关键证据**，过去 sync 数千行写入但物理列缺失被静默吞——本次写入率 100% 证明止血生效）。

### 2.4 失败 / 阻塞标记真实性 — ✅ Pass（无 fail 用例）

本次 5 个 step 全部 `[x]` 通过，与独立验证完全吻合，无虚假 pass。dev 主动暴露 2 处 ADR 假设偏差（不掩盖）：

1. **每股档位 21-196**（ADR 假设 ~104）：dev 在 progress 中明示"83-196 浮动属正常（活跃股 / 价格区间宽窄不同）"——经独立查询 `SUM(percent) GROUP BY code ≈ 100.02-100.05`，确认是 Tushare 按"实际成交价格区间宽度"返回的真实档位数，非 sync 错误。**这是 ADR 假设过于简化（统一 ~104）导致的认知差，不是实施 bug**。
2. **仅单日数据**（ADR §决策5 默认 days_back=5）：dev 解释"最近 5 个自然日内只有 2026-06-18 为有效交易日"（2026-06-19 周五但 Tushare 可能未发布；20-21 周末；22 当天非完整交易日）——符合 Tushare 行为，非 sync 偏差。`etl.py:1158-1162` 实际跑了 5 次循环，4 次返回空 df continue，1 次拿到数据 break——sync 函数行为正确，ADR 假设过乐观（默认 5 日窗口在月底 / 周末附近确实只能覆盖 1 个交易日）。

两个偏差 dev 都在 progress 中如实记录（未美化），audit 可见 + 可解释 → 真实性合规。

### 2.5 SIT Audit verdict — **✅ Pass**

4 项检查全过；无虚假 pass、无证据缺失、无 AC 漏覆盖。

---

## 3. Findings（按严重性分级）

### Critical — 0 个

### Warning — 0 个

### Suggestion — 2 个

#### S-1：`idx_cyq_chips_date` 索引存在于 DB 但 init_sql / 009 迁移均未声明（schema drift）

- **位置**：`services/sql/init_postgres.sql:299-303` (cyq_chips DDL 段) / `backend/alembic/versions/009_cyq_chips_align.py:37-61` (upgrade 主体)
- **实测**：`pg_indexes WHERE tablename='cyq_chips'` 返回两条索引——`cyq_chips_pkey` (PK) + `idx_cyq_chips_date` (btree on trade_date)；但 `grep idx_cyq_chips_date` 在全仓 `backend/alembic/versions/*` + `services/sql/init_postgres.sql` 均 **零命中**。
- **影响**：当前 DB 是 commit 8e18637 之前历史环境累积态，`idx_cyq_chips_date` 曾被手工或某个未追溯 migration 创建。当前不阻断（索引在，下游有人查 `WHERE trade_date >= ...` 时仍能加速），但 **新环境从 init_sql 起会缺这个索引**——一旦新部署或 disaster recovery，性能会回退到全表扫。
- **与 ADR §决策2 关系**：ADR 明确说"不新增其他索引...等出现 trade_date 跨股聚合再加"。但 DB 里事实上已有这个索引——这是 DB 状态早于 ADR 决策的历史遗留。ADR-010 升 Accepted 后应**让 DB 与文档归口一致**：要么删 idx（按 YAGNI 原则贴合 ADR），要么补登记到 init_sql + 新 migration（按"DB 是真理之源"原则贴合现实）。
- **修复建议**：让 PL 派 backend-dev 一个小 follow-up task——跑独立的"index audit"：`SELECT indexname FROM pg_indexes WHERE schemaname='public'` 与 init_sql 对比，把所有 schema drift 一次性补登或清理（非本 task 范围，不应阻断 ADR-010 通过）。
- **严重性理由**：suggestion 而非 warning——本次实施未引入此 drift（drift 是 commit 8e18637 之前的存量问题），且 dev 在 progress §"Step 2 \d cyq_chips" 已诚实显示该索引存在（透明披露，未隐瞒）。

#### S-2：单日数据足以让下游因子复活，但需 tech-lead 抽样实证

- **位置**：`packages/kronos-factors/kronos_factors/scorer/advanced_factors.py:1075-1100` (筹码因子 cyq 块)
- **实测**：下游因子用 `MAX(trade_date)` 取最新一日，**仅需 1 个交易日的多档明细即可**——不要求多日历史。当前 2026-06-18 单日 36142 行 / 300 股 / 平均 ~120 档 → 完全满足下游计算需求。
- **影响**：理论上 cyq 因子应从"稳定 5.0 fallback 中性"切换为"基于真实档位的动态分（accumulation / distribution / neutral）"。但本次仅做了 schema + 写入端验证，**未实证下游因子真的切换了**——若下游某层 cache 或 fallback 路径残留，可能仍是 fallback。
- **修复建议**：让 PL 派 tech-lead（按 ADR §后续工作 tech-lead 项）抽样 3-5 只 top-300 股，跑 `advanced_factors.tushare_chip_concentration(code='000001')` 直接对比"修前 / 修后"输出，确认 `scores["tushare_cyq"]` 从 `{"score": 5.0, "signal": "no_data"}` 切到真实分数。
- **不阻断本次 ADR-010 通过**：dev 的 progress §"下游影响（pending tech-lead 后续审查）"已主动暴露此为待办（非本 task 范围）。是 ADR §后续工作明示的事项。

---

## 4. 风险评估

| 风险 | 是否阻断 advanced_factors？ | 缓解 |
|---|---|---|
| 仅单日数据 (2026-06-18) | ❌ 不阻断（下游用 MAX(trade_date) 单日即可计算） | 等定时 sync 自然累积；月底跑 days_back=30 一次回补可拉宽窗口 |
| Tushare percent 取值范围 0-100 vs 0-1 假设 | ❌ 不阻断（独立验证 SUM(percent)≈100，确认 0-100 体系；下游 avg_cost = Σ(p×w)/Σ(w) 与 conc 都是 scale-invariant，0-100 vs 0-1 不影响结果） | 无需归一化；tech-lead 抽样确认即可 |
| schema drift（S-1 idx_cyq_chips_date） | ❌ 不阻断（索引在 DB 中已存在，查询不退化） | 见 S-1 follow-up |
| 下游 fallback 残留 | ⚠️ 可能（S-2 未实证） | tech-lead 抽样 |

---

## 5. Verdict

### 5.1 Code verdict — **approve**

理由：
- 白名单 100% 合规（backend-dev 仅运行已有迁移 + sync，**零代码改动**）；
- 009 迁移 7 项幂等检查全过；
- init_sql 与 009 终态字面一致；
- 安全审计零风险；
- 独立验证 12 项与 dev 证据 100% 吻合（含中文 locale 输出、SUM(percent)≈100 实证等不可伪造细节）。

### 5.2 SIT Audit verdict — **✅ Pass**

4 项检查全过；2 处 ADR 假设偏差 dev 已如实暴露 + 可解释（非证据缺陷）。

### 5.3 Follow-up tasks（给 product-lead 派给执行层，不阻断本 ADR 通过）

| # | Task | Owner（建议） | 优先级 |
|---|---|---|---|
| F-1 | `idx_cyq_chips_date` 等历史 schema drift 索引登记或清理（一次性 schema audit） | backend-dev | P3 (低) |
| F-2 | 抽样 `advanced_factors.py` cyq 因子 3-5 只 top-300 股的"修前 / 修后"对比，确认从 fallback 切到真实数据 | tech-lead（ADR §后续工作明示项） | P2 (中) |
| F-3 | 月底跑一次 `sync_cyq_chips(days_back=30)` 累积多日历史，便于回测期 cyq 因子（非阻断当前 screener，screener 用单日即可） | backend-dev（定时任务自然累积亦可，可放至下次 sprint） | P3 (低) |

### 5.4 Go/No-Go

**GO with follow-ups**：ADR-010 本次实施干净落地，下游筹码因子已具备从 fallback 切到真实数据的硬条件；2 个 suggestion 均不阻断主线。

---

## agf-verdict (machine-readable)

```yaml
critical: 0
warning: 0
suggestion: 2
code_verdict: approve
sit_audit_verdict: pass
go_no_go: go
followups:
  - id: F-1
    owner_hint: backend-dev
    priority: low
    summary: idx_cyq_chips_date schema drift 登记或清理
  - id: F-2
    owner_hint: tech-lead
    priority: medium
    summary: 抽样 advanced_factors cyq 因子确认从 fallback 切到真实数据
  - id: F-3
    owner_hint: backend-dev
    priority: low
    summary: 月底跑 days_back=30 累积多日历史
```
