---
feature: adr-013-ths-daily-schema-alignment
reviewer: code-reviewer
date: 2026-06-22
scope: "ADR-013 (ths_daily schema 反向追认 + cb_sync sync_ths_daily cols 5→15 + ADR-012 review 收尾 W-2/W-3/S-2/S-3/S-4/LD-2/LD-3)；含 SIT Audit；W-1 推迟、S-1 PARTIAL（ADR 已 amend 移除子项 c）"
code_verdict: approve with changes
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 2
suggestion_count: 4
go_no_go: "ACCEPT_WITH_FOLLOWUPS — 主线 9 项（alembic 011 / cb_sync cols / W-2 / W-3 / S-2 / S-3 / S-4 / LD-2 / LD-3）落地干净，DB 实证 17 列形态 + change_pct 100% 非 NULL；S-1 PARTIAL 误分类裁决 ACCEPT（ADR §决策 0 子项 c 已 amend 移除）；2 项 warning 为 worktree 内出现 ADR 白名单外的「附带改动」（tools/run_today_afternoon.py + progress/tech-lead.md），与 ADR-013 主线无关但需在 commit 前裁断归属"
---

# ADR-013 — ths_daily schema 对齐 + cb_sync cols 修复 + ADR-012 review 收尾 代码审查 + SIT Audit

> 审查范围：working-tree 未 commit diff（按 §决策 0 白名单 7 文件）+ alembic 011 新建 + ADR-013 minor amend（task #3 已落地）+ progress/backend-dev.md ADR-013 SIT 16 项证据。
> 审查人：code-reviewer（review-only，零字节源码 / schema / progress 改动）。
> SIT Audit 为本次审查的一部分，不另起 phase。
> 沿用 `docs/reviews/adr-011-012-code-review-2026-06-22.md` 同骨架。

---

## 0. 审查方法与独立验证

| 验证项 | 命令 / 检查 | 结果 |
|---|---|---|
| working-tree 改动清单 | `git status` + `git diff --name-only HEAD` | ✅ ADR-013 §决策 0 白名单 7 文件全员命中；⚠️ 额外 2 文件 `progress/tech-lead.md` + `tools/run_today_afternoon.py` 与 ADR-013 无关（见 W-1） |
| ADR-013 §决策 0 白名单核对 | `git diff --stat` | ✅ 仅 alembic 011 新建 + init_sql / cb_sync / etl.py / pg_writer.py / scheduler.py / progress/backend-dev.md |
| 010 既有 alembic 链 | `ls backend/alembic/versions/` | ✅ 001..010 + 011 连续；011 `down_revision='010'` |
| alembic 011 AST | `python3 -c "import ast; ast.parse(open('backend/alembic/versions/011_ths_daily_align.py').read())"` | ✅ Pass |
| DB alembic_version | `psql -c "SELECT version_num FROM alembic_version"` | ✅ `011` |
| DB ths_daily schema 形态 | `psql -c "\d ths_daily"` | ✅ 17 列 + `id bigint NOT NULL DEFAULT nextval('ths_daily_id_seq')` + `ths_daily_pkey PRIMARY KEY(id)` + `idx_ths_daily_code_date btree(code, trade_date)` + `ths_daily_code_date_uniq UNIQUE(code, trade_date)`；`trade_date`/`updated_at` 保留 TEXT（与 ADR §决策 1 修订段一致，列入 ADR-014 audit） |
| DB 7 天新写入 nn 率 | `psql -c "SELECT COUNT(*), COUNT(change_pct), COUNT(name) FROM ths_daily WHERE trade_date>='2026-06-13'"` | ✅ total=6028 / change_pct_nn=6028 (100%) / name_nn=0；与 SIT 6/7 一致（SIT 7 已注解 name/total_mv/float_mv 是 Tushare API 不返回的 3 列） |
| init_postgres.sql:551-580 ths_daily 段 | `sed -n '551,580p'` | ✅ 字面与 alembic 011 upgrade 后形态一致（17 列 + UNIQUE + idx + TEXT 类型保留） |
| cb_sync.py `MAX_RETRIES` / `PG_URL` / `time` 实际使用 | `grep -n` | ✅ 实证 grep：`MAX_RETRIES` 12 处使用（L113/118/121/125/202/207/260/271/274/288/293…）+ `PG_URL` L183 `psycopg2.connect(PG_URL)` 主动使用 + `time.sleep` 4 处指数退避（L122/208/272/294）— ADR-012 review §9 S-1 误分类被实证证据复核确认 |
| cb_sync sync_ths_daily cols 形态 | `sed -n '106,109p'` | ✅ 15 列：`code/trade_date/name/open/high/low/close/pre_close/avg_price/change_pct/change/total_mv/float_mv/vol/turnover_rate`；conflict_cols=`["code","trade_date"]` |
| `_check_data_volume` 已删 | `grep -rn "def _check_data_volume"` | ✅ 0 命中 |
| `_VOLUME_THRESHOLD_MAP` 二档 | `grep -n` pg_writer.py | ✅ `daily_kline`/`stk_mins` 各 `{"floor":1000,"warn":3000}`；`_pg_write` 用 `cfg.get("floor")/cfg.get("warn")` 透传 `_insert_rows` |
| `_insert_rows` `data_volume_warn` 参数 | etl.py:170-171 + 226-228 | ✅ 参数默认 `None` 旧行为零回归；ERROR/WARN 互斥分支（floor 优先），`written>0` 才检测（0 不误报） |
| `pg_w if 'pg_w' in dir()` 反模式删除 | `grep -n "'pg_w' in dir" scheduler.py` | ✅ 0 处实际执行命中（仅注释引用历史代码） |
| `_register_backfill_handlers_late` 失效注释修正 | scheduler.py:174-176 | ✅ 改为「实际由 L773 顶层直接赋值绕过 forward declaration」 |
| LD-2 `index_basic` 从 MONITORED 移除 | `grep -rn "index_basic" services/data-service/app/scheduler.py` | ✅ `MONITORED_TABLES` 内 `index_basic` 项删除（L109 注释保留 rationale）；`_BACKFILL_MAP` 仍含（L167，由 cron job sync_index_basic 维护，无回归） |
| LD-3 `_DESIGN_SKIP_BACKFILL` 扩展 | scheduler.py:189 | ✅ `{"stocks", "trade_cal", "rt_k", "rt_sw_k"}`；validator 检查 3（L1149-1154）补对称跳过 |
| W-3 written 语义修复 | scheduler.py:773-786 | ✅ `written=total_pg`（语义对齐 detect_data_gaps）+ `fetched=total_written`（累计）+ `pg_written` 显式别名向后兼容 |
| pg_adapter `_COLUMN_MAP` 保留 | `grep -n "_COLUMN_MAP" packages/kronos-factors/kronos_factors/pg_adapter.py` | ✅ L70-72 `"pct_change": "change_pct"` 翻译层未碰（与 ADR §决策 0 不在白名单一致） |
| 下游因子代码零碰 | `git diff -- packages/kronos-factors` | ✅ 全零 |
| ADR-010/011 既有 schema 零回归 | `git diff -- backend/alembic/versions/010_top_inst_align.py services/sql/init_postgres.sql` (top_inst/cyq_chips 段) | ✅ 零字节改动 |
| 新依赖 | `git diff pyproject.toml requirements*.txt` | ✅ 零新依赖 |
| 交易服务零影响 | `git diff -- services/trade-service services/strategy-service` | ✅ 零字节（不触发 Plan Mode + tech-lead review 条款） |
| ADR-013 minor amend (task #3) | `grep -n "minor amend" docs/adr/013-*.md` | ✅ L40 白名单 #3 子项 (c) 已 strike-through + 链接 §决策修订；L287 minor amend 段记录依据 |

---

## 1. Code Review — Alembic 011 + init_postgres.sql

### 1.1 白名单合规 — ✅ 严格合规

| ADR-013 §决策 0 白名单 | 实际改动 | 越界？ |
|---|---|---|
| `backend/alembic/versions/011_ths_daily_align.py`（新建） | ✅ 新建 92 行 | ❌ 无 |
| `services/sql/init_postgres.sql:551-580` 仅 ths_daily 段 | ✅ 8 行 → 21 行 + UNIQUE + idx（其他段零碰） | ❌ 无 |

### 1.2 Alembic 011 迁移 — ✅ approve

逐条核对 ADR-013 §决策 1 + 决策 8 阶段 1：

- ✅ Step 1 `CREATE SEQUENCE IF NOT EXISTS ths_daily_id_seq`（命名沿用 PG SERIAL 自动产物约定，未来 introspect 工具识别一致）
- ✅ Step 2 `ALTER TABLE ths_daily ALTER COLUMN id TYPE bigint`（current integer 32-bit 上限 ~2.14B vs 当前 1.93M 行，BIGSERIAL 防未来溢出）
- ✅ Step 3 `SET DEFAULT nextval('ths_daily_id_seq')`
- ✅ Step 4 `UPDATE ths_daily SET id = nextval(...) WHERE id IS NULL`（DB 现状 1.93M 行 id 全 NULL，单事务回填）
- ✅ Step 5 `setval(..., MAX(id)+1, false)`（COALESCE 兜底空表）
- ✅ Step 6 `SET NOT NULL`
- ✅ Step 7 `DROP CONSTRAINT IF EXISTS ths_daily_pkey` + `ADD CONSTRAINT ... PRIMARY KEY (id)`（IF EXISTS 防 init_postgres.sql 未来意外加 PK）
- ✅ Step 8 `ALTER SEQUENCE ... OWNED BY ths_daily.id`（防孤儿序列，列 DROP 时自动清理）
- ✅ Step 9 `CREATE INDEX IF NOT EXISTS idx_ths_daily_code_date(code, trade_date)`（与 UNIQUE 冗余但与 sw_daily/cyq_chips 同型，覆盖下游 leader_intraday 因子 `WHERE code=? ORDER BY trade_date DESC` 模式）
- ✅ 全部 `op.execute` 原生 SQL（杜绝 op.add_column / op.create_primary_key 非幂等坑，沿用 ADR-008/010/011 教训）
- ✅ downgrade 逆序完整：DROP idx → 解关联 → DROP PK → SET NULL → DROP DEFAULT → bigint→integer → DROP SEQUENCE；保守不 truncate 历史数据
- ✅ `revision='011'`, `down_revision='010'` 链接 ADR-011

**SIT 1-4 实证**：alembic upgrade 010→011 / 重跑幂等 / downgrade -1 + 重 upgrade roundtrip / `\d ths_daily` 17 列 + UNIQUE + BIGSERIAL PK + idx 全员合规——独立 `psql` 验证一致。

### 1.3 init_postgres.sql ths_daily 段 — ✅ approve

字面与 011 upgrade 后形态一致（17 列 + UNIQUE + idx + `trade_date TEXT` / `updated_at TEXT` 保留 DB 现状）；ADR-013 §决策 1 修订段说明 trade_date 类型转换列入 ADR-014 audit，本 ADR 不动 — 合理。

---

## 2. Code Review — cb_sync.sync_ths_daily cols 修复（LD-1 主线）

### 2.1 cols 5 → 15 改造 — ✅ approve

`services/data-service/app/sync/cb_sync.py:106-108` 新 cols：
```python
cols = ["code", "trade_date", "name", "open", "high", "low", "close",
        "pre_close", "avg_price", "change_pct", "change",
        "total_mv", "float_mv", "vol", "turnover_rate"]
```
- ✅ 命名映射正确：`ts_code → code`（项目级 normalization）+ `pct_change → change_pct`（与 sw_daily 同型，ADR-008）
- ✅ rows 拼装段 15 元组对齐 cols 顺序（L135-151），全部用 `_safe_val(r.get("..."))` 处理 NaN
- ✅ `conflict_cols=["code", "trade_date"]` 与 UNIQUE 约束对齐（_insert_rows 用 ON CONFLICT DO NOTHING）

### 2.2 SIT 5/6 出血止血实证 — ✅ approve

- SIT 5 stdout 无 `[WARN] _insert_rows ths_daily: 丢弃表不存在的列 ['pct_change']`（旧错位警告消失）
- SIT 6/7 DB 实证 7 天 6028 行 change_pct 100% 非 NULL（独立 psql 复核一致）
- SIT 9 pg_adapter `_COLUMN_MAP["pct_change":"change_pct"]` 翻译层保留（L72），leader_intraday 因子 `SELECT pct_change FROM ths_daily` 经翻译落 change_pct，真实数据非 NULL → 不再 fallback

### 2.3 SIT 7 name/total_mv/float_mv 0 nn 注解 — ✅ approve

dev 在 SIT 7 中已诚实标注：
> **预期结果调整**: open/high/low/close/pre_close/avg_price/change_pct/change/vol/turnover_rate 10 列 100% 非 NULL（vs ADR-012 SIT 5 前 5 列）；**name / total_mv / float_mv 真实 Tushare API 不返回此 3 列**

独立 `psql` 复核：`name_nn=0` 4 天稳定为 0，与 Tushare API 实际返回 12 字段一致；这 3 列预留位等 ths_concept_map join 填充 — 非 sync bug，是 ADR §决策 1 引用「Tushare 15 列」的小事实瑕疵，dev 已在 SIT 7 修正陈述。**评级 suggestion**：S-1（见 §7）建议 ADR-013 §决策 1 minor amend 把「Tushare 15 字段」改「12 字段」。

### 2.4 S-1 PARTIAL 偏离裁决 — ✅ ACCEPT

ADR-012 review §9 S-1 标 cb_sync.py 中 `MAX_RETRIES` / `PG_URL` / `import time` 为「thin wrapper 化后未使用 dead code」。**独立 grep 复核**（在 main worktree 跑）：

```
$ grep -n "MAX_RETRIES\|^PG_URL\|^import time\|time.sleep\|psycopg2.connect" services/data-service/app/sync/cb_sync.py
23:MAX_RETRIES = 3
24:PG_URL = os.environ.get("KRONOS_PG_URL", ...)
113:        for attempt in range(MAX_RETRIES):    ← sync_ths_daily 应用层重试
118:                if attempt < MAX_RETRIES - 1:
121:                                   attempt + 1, MAX_RETRIES, d, sleep_s, e)
122:                    time.sleep(sleep_s)         ← 指数退避
125:                                 d, MAX_RETRIES, e)
183:        conn = psycopg2.connect(PG_URL)         ← sync_cb_price_chg_all 读 cb_basic
202/207/208 ← sync_cb_price_chg_all 重试 + sleep
260/271/272/274 ← sync_ths_concept_map 重试 + sleep
288/293/294 ← sync_ths_concept_map concepts 拉取重试
```

- `MAX_RETRIES`: **12 处主动使用**（sync_ths_daily / sync_cb_price_chg_all / sync_ths_concept_map 三函数的 Tushare API 应用层重试循环 — 与 `_pg_write` thin wrapper 内的 PG 写入重试是**两个不同层级**：前者是 fetch 层、后者是 write 层，并存合理）
- `PG_URL`: **L183 主动使用** `psycopg2.connect(PG_URL)` 读 `cb_basic` 表列表（`sync_cb_price_chg_all` 业务流程必需，不走 thin wrapper）
- `import time`: **4 处 `time.sleep`** 配合指数退避

✅ **裁决 ACCEPT**：删之确实会 `NameError` 整文件不可 import；dev 在 cb_sync.py L14-22 加偏离说明 docstring（指明 S-1 三项均为活代码 + 上游 ADR-012 review §9 误分类）— 处理方式正确。

✅ **ADR-013 minor amend 已落地（task #3，2026-06-22）**：§决策 0 白名单 #3 子项 (c) 已用 strike-through 删除 + §决策修订段 L287 追加 amend 记录；与 SIT 14 PARTIAL 标记 + dev 偏离说明形成完整闭环。

✅ 配套 SIT 14 改判 N/A（dev 在 progress 中陈述「ADR misclass」+ 上方 docstring + ADR L287 amend record）三处证据互链 — 审计可见。

---

## 3. Code Review — W-2 二档告警 + S-2 dead 函数清理

### 3.1 W-2 二档恢复 — ✅ approve

- ✅ `_insert_rows` 加 `data_volume_warn: int | None = None` 参数（默认 None 旧行为零回归）
- ✅ 二档互斥分支（floor → ERROR 优先 / warn → WARN 次档），`written > 0` 才检测（0 不误报空跑）
- ✅ docstring 完整说明语义（etl.py:182-185）
- ✅ `_VOLUME_FLOOR_MAP` → `_VOLUME_THRESHOLD_MAP` 二档；`daily_kline`/`stk_mins` 各 `{"floor":1000,"warn":3000}` 1:1 还原 ADR-012 之前 pg_writer `_check_data_volume` 内的硬编码
- ✅ `_pg_write` 用 `cfg.get("floor")/cfg.get("warn")` 透传 `_insert_rows`，未配置表回退 `{}` → 双 None → 旧行为
- ✅ SIT 11 四 case（2000 warn 触发 / 500 floor 触发 / 5000 静默 / None 默认）全过

### 3.2 S-2 dead 函数清理 — ✅ approve

- ✅ `_check_data_volume` 14 行物理删除（grep `def _check_data_volume` 0 命中）
- ✅ 删除前 `grep -rn "_check_data_volume"` 复核外部调用方 0 处 — ADR-012 §决策 5.2 「保留以兼容潜在外部调用」前提失效，删除安全
- ✅ 删除位置保留 comment block 引用决策 + 历史阈值出处（pg_writer.py:83-86）

---

## 4. Code Review — W-3 written 语义 + S-3 + S-4

### 4.1 W-3 written 语义修复 — ✅ approve

- ✅ scheduler.py:773-786 新 return 字段：`written=total_pg`（语义对齐 detect_data_gaps）+ `fetched=total_written`（累计 fetch，未去重）+ `pg_written` 显式别名（向后兼容 SIT 7 / 历史 stk_factor_pro_daily 输出格式）
- ✅ comment block 完整记录 ADR-012 SIT 7 ~10x 监控误导 + 新约定（L770-775）
- ✅ SIT 12 实测：`written=2037 == pg_written=2037`，`fetched=22037`（ratio=10.82×，去重生效可见）

### 4.2 S-3 反模式修 — ✅ approve

- ✅ scheduler.py:743 显式 `pg_w = 0` 初始化 + try/except 包裹 PG 写入；except 分支保留 0
- ✅ 引用处 L771 `len(rows), pg_w, len(rows)` 直接用变量（无 dir() introspection）
- ✅ comment block 解释为何脆弱（L740-742）

### 4.3 S-4 失效注释修 — ✅ approve

- ✅ scheduler.py:174-176 旧注释「`_register_backfill_handlers_late()` 调用」改为「实际由 L773 顶层 `_BACKFILL_MAP["stk_factor_pro"] = sync_stk_factor_pro_backfill` 直接赋值绕过 forward declaration 限制 — Python 模块加载时顺序执行，函数定义后立即赋值即生效」— 与代码实际行为一致

---

## 5. Code Review — LD-2 / LD-3 收尾

### 5.1 LD-2 index_basic 处理 — ✅ approve

- ✅ scheduler.py:107-111 `MONITORED_TABLES` 内 `index_basic` 项删除（旧 `date_col="updated_at"` 误报源）
- ✅ rationale comment 完整：基础元数据非时序 + 表无 updated_at + 监控价值有限 → 「最干净」选项
- ✅ 但 `_BACKFILL_MAP["index_basic"] = sync_index_basic` L167 保留（由 cron L1322 维护，无回归）— 双链路独立
- ✅ SIT 8 实测 MONITORED 从 48 → 47 表，validator warnings 0

### 5.2 LD-3 rt_k / rt_sw_k → _DESIGN_SKIP_BACKFILL — ✅ approve

- ✅ scheduler.py:189 `_DESIGN_SKIP_BACKFILL = {"stocks", "trade_cal", "rt_k", "rt_sw_k"}`
- ✅ rationale comment 完整（L181-188）说明 rt_k 无 days_back 签名 + rt_sw_k 语义错位（"今天再拉一次"非"回补 N 天"）
- ✅ validator 检查 3（L1149-1154）补对称跳过 `_DESIGN_SKIP_BACKFILL` — 与检查 1（L1106）对称
- ✅ SIT 8 实测 warnings=0（ADR-012 SIT 9 中的 2 项 WARN 全部消除）

---

## 6. SIT Audit（4 项检查 + 3 档 verdict）

| # | 检查项 | 结果 | 备注 |
|---|---|---|---|
| 1 | progress 完整性 | ✅ Pass | `progress/backend-dev.md` L955+ 「ADR-013 — ths_daily schema 对齐 …」段含完整 `**SIT 证据**` 标题 + 16 项 `[x]/[⚠]` 内联勾选 + 质量门段 + 下一步段 — 五段格式齐全 |
| 2 | AC 覆盖 | ✅ Pass | 16 项 SIT 与 ADR-013 §决策 7 修订后 16 项 1:1 对账（alembic 4 项 + cb_sync cols 3 项 + validator/LD-2/LD-3 1 项 + 因子复活 1 项 + W-2 二档 2 项 + W-3 语义 1 项 + S-1 PARTIAL（已 amend N/A）+ S-2/S-3 各 1 项 + 白名单审计 1 项）；PRD AC 在 integration 层全覆盖（schema 对齐 / 字段对齐 / 监控 noise 消除 / 因子复活）|
| 3 | 证据可信度 | ✅ Pass | 验证命令真实可执行（独立 psql 复核 ths_daily 形态 / change_pct nn 率 / alembic_version 全员一致）；输出片段含具体命令 + 真实 stdout（非 "OK"/"通过" 这种无证据文本）；SIT 11 四 case mock 测试有 `RESULT: PASS` 显式断言 + 行为 trace；SIT 7 诚实标注 name/total_mv/float_mv API 不返回（与 ADR §决策 1 文本瑕疵主动对齐） |
| 4 | 失败/阻塞标记真实性 | ✅ Pass | SIT 14 用 `[⚠]` PARTIAL 标记真实呈现 S-1 误分类（含 grep 反证 12+1+4 处 + docstring 偏离说明 + ADR amend 闭环）；无任何 fail 被伪装为 pass；SIT 17 白名单审计区分 7 文件命中 vs 越界文件（独立 grep 兜底）|

**SIT Audit verdict: ✅ Pass** — 4 项检查全过；audit 路径与 ADR-013 §决策 7 修订后 16 项 100% 对账；S-1 PARTIAL 处理标准（grep 反证 + docstring + ADR amend + SIT 改判 N/A）形成完整证据闭环，**不需要 Redo SIT**。

---

## 7. Warnings / Suggestions / Latent Debt

### Warnings (2)

| ID | 严重性 | 文件 / 行号 | 问题 | 修复建议 |
|---|---|---|---|---|
| W-1 | warning | `tools/run_today_afternoon.py` 全文件 + `progress/tech-lead.md` L420+ | working-tree 内出现 ADR-013 §决策 0 白名单**外** 2 个文件的未提交改动（`tools/run_today_afternoon.py` 加 daily_kline fallback + `progress/tech-lead.md` 含 tech-lead 自己的 ADR-013/014/015 立项记录）；ADR §决策 0 表「越界改动 = 违约」；虽 backend-dev 在 SIT 17 git diff 只列了白名单 7 文件「全员命中且仅命中」，但全仓 `git status` 实测 11 文件 mod — 多出的 2 个文件未在 SIT 17 中显式陈述归属 | **不阻断 merge 但 PL 在 commit 前裁断归属**：(a) `tools/run_today_afternoon.py` 的 pre_close fallback 与 ADR-013 ths_daily 无任何关联 — 是 ths_daily change_pct 已修复后 stk_limit.pre_close 仍空的旁路修补（应当 PL 决定: 单独立 ticket / 或者本批顺手附带 + 申明），(b) `progress/tech-lead.md` 是 tech-lead 自己的 progress 文件（task #3 ADR amend + ADR-013/014/015 立项记录），不是 backend-dev 越界；建议 commit 时拆 2-3 个 commit 分别归属 |
| W-2 | warning | `backend/data/stock_screening.db-shm` + `db-wal` 删除 | 2 文件被 `git status` 标 `deleted:` 但未在 SIT 17 陈述；属 SQLite WAL housekeeping（process 退出时残留清理）；非有意改动 | commit 时 `git restore` 或 `.gitignore` 加 `*.db-shm` / `*.db-wal`（项目根 .gitignore 已有 `*.db` 但未含 WAL 后缀） |

### Suggestions (4)

| ID | 文件 / 行号 | 问题 | 建议 |
|---|---|---|---|
| S-1 | `docs/adr/013-ths-daily-schema-alignment.md` §决策 1 + §决策 2 | ADR §决策 1 引用「Tushare `pro.ths_daily` 实际返回字段 15 个含 name/total_mv/float_mv」与 SIT 7 实证 「Tushare API 不返回 name/total_mv/float_mv 3 列」矛盾 | minor amend：ADR §决策 1 改「12 字段」+ §决策 2 cols 列表保留 15 列但 docstring 标注「name/total_mv/float_mv 预留位等 ths_concept_map join 填充」；不阻断 merge |
| S-2 | `progress/backend-dev.md` SIT 14 行首标记 `[⚠]` | SIT 14 标 `[⚠]` PARTIAL 但 ADR-013 §决策 0 子项 (c) 已 amend 移除（task #3 完成），实际 SIT 14 状态应为 N/A | dev 顺手把 SIT 14 行首改 `[N/A]` + 补一行「ADR-013 minor amend 2026-06-22 已撤子项，本 SIT 项不适用」；不阻断 merge |
| S-3 | `services/data-service/app/sync/pg_writer.py` L18-22 docstring | `_VOLUME_THRESHOLD_MAP` docstring 提到「替代 ADR-012 单档 `_VOLUME_FLOOR_MAP`」但 ADR-012 已 Accepted 是历史决策；docstring 应主述本 ADR-013 决策（W-2） | docstring 微调，主述 ADR-013 §决策 4 + 「（兼带替代 ADR-012 `_VOLUME_FLOOR_MAP`）」括号附带；P3 |
| S-4 | `services/data-service/app/scheduler.py:1322-1323` cron job 仍含 `sync_index_basic` 单独入口 | `index_basic` 已从 MONITORED_TABLES 移除（LD-2 收尾），但 cron 仍按周六 02:00 跑 `sync_index_basic`（合理：基础元数据周更）；评估 cron 是否仍属预期 | tech-lead 在 ADR-014 audit index_basic schema 时一并评估「是 cron-only 表」是否应当显式标注；P3 |

### Latent Debt（dev 未触及但实证发现，留 backlog）

| ID | 描述 | 处理建议 |
|---|---|---|
| LD-1 | `ths_daily.trade_date` 是 TEXT 类型（DB 现状反常 — sw_daily/cyq_chips/top_inst 等同型表均为 DATE）；ADR-013 §决策 1 修订段保守保留 TEXT | 按 ADR-013 §「本 ADR 不覆盖的决策」明示，留 **ADR-014** audit；P2 |
| LD-2 | `ths_daily.updated_at` 是 TEXT 类型且 DB 现状 `updated_at NOT NULL DEFAULT` 缺失（独立 psql 复核：`updated_at | text |  | |` 空 DEFAULT）；sync 路径不显式写 updated_at 列 → 永远 NULL | 留 **ADR-014** audit；可与 LD-1 一并处理；P2 |
| LD-3 | `_pg_write` thin wrapper `finally: db.close()` 关闭模块级共享连接 — ADR-013 §「决策修订」段已明示 W-1 推迟到 ADR-014/015 实施时顺手处理（需 apscheduler shutdown hook 配套） | 留 **ADR-014/015** 顺手处理；P1 |

---

## 8. ADR-012 review 收尾覆盖度核对

| Follow-up ID | 严重性 | 状态 | 证据 |
|---|---|---|---|
| W-1 (`_pg_write` 共享连接关闭) | P1 | **推迟** | ADR-013 §「决策修订」段明示推迟到 ADR-014/015 + 风险评估（需 apscheduler shutdown hook）；reviewer 复核合理 |
| W-2 (<3000 WARN 分级被单档替代) | P2 | ✅ 已修复 | §3 + SIT 11 |
| W-3 (`written` 语义偏移) | P1 | ✅ 已修复 | §4.1 + SIT 12 |
| S-1 (cb_sync dead globals) | P3 | **PARTIAL → ACCEPT 裁决 + ADR amend** | §2.4 + ADR §决策 0 amend + L287 minor amend |
| S-2 (`_check_data_volume` dead) | P3 | ✅ 已修复 | §3.2 + SIT 15 |
| S-3 (`'pg_w' in dir()` 反模式) | P3 | ✅ 已修复 | §4.2 + SIT 16 |
| S-4 (`_register_backfill_handlers_late` 失效注释) | P3 | ✅ 已修复 | §4.3 |
| S-5 (idx_top_inst_date + idx_cyq_chips_date schema drift) | P3 | **不在本 ADR 范围** | 留 ADR-014（与 LD-1/LD-2 一并 audit） |
| LD-1 (cb_sync.sync_ths_daily cols 错位) | P1 | ✅ 已修复（本 ADR 主线） | §2.1 + SIT 5/6/9 |
| LD-2 (`index_basic.updated_at` 不存在) | P3 | ✅ 已修复 | §5.1 + SIT 8 |
| LD-3 (`rt_k`/`rt_sw_k` 进 backfill 错位) | P3 | ✅ 已修复 | §5.2 + SIT 8 |

**结论**：本 ADR-013 主线覆盖 9 项（W-2/W-3/S-2/S-3/S-4/LD-1/LD-2/LD-3 + alembic 011），1 项 PARTIAL（S-1 已 amend），1 项推迟（W-1，ADR 明示），1 项不在范围（S-5 留 ADR-014）— 与 ADR-013 §决策 0 范围声明一致。

---

## 9. 团队协作 / Hand-off 建议

- **代码 verdict: approve with changes** → 由 PL 决定：
  1. （推荐）merge 主线 9 项 + 把 W-1 / W-2 / S-3 / S-4（本 review 的 2 W + 4 S）打包到下个 ADR-014/015 顺手或独立 cleanup commit
  2. 或在本 worktree 让 backend-dev 顺手 (a) 拆 commit 把 `tools/run_today_afternoon.py` 与 ADR-013 分开 (b) 补 SIT 14 `[N/A]` 行首标记 + dev 一行补充说明 — 再 merge（更干净，5-10 分钟工作量）
- **SIT Audit verdict: ✅ Pass** → 不需要 Redo SIT
- **架构风险**：本批未升级 tech-lead（无重大架构问题；ADR-013 是 ADR-012 的 schema-alignment follow-up + 已 amend 过 S-1 误分类）；ADR-014 / ADR-015 已立位待 backend-dev 实施阶段
- **白名单越界（W-1）裁断**：`tools/run_today_afternoon.py` 是 ths_daily 修复后的旁路改动（与本 ADR 表象同源但语义独立），PL 应在 commit 前明确归属 + 写到 commit message 里避免历史溯源混乱

---

## agf-verdict（机读契约）

```yaml
agf-verdict:
  feature: adr-013-ths-daily-schema-alignment
  date: 2026-06-22
  reviewer: code-reviewer
  code_verdict: approve with changes
  sit_audit_verdict: ✅ Pass
  critical_count: 0
  warning_count: 2
  suggestion_count: 4
  derivation:
    - "critical_count = 0 → 满足 'approve' 或 'approve with changes' 前提（非 block）"
    - "warning_count = 2 → 当前不阻断 merge，但需 PL 在 commit 前裁断 W-1 归属 → 'approve with changes'"
    - "suggestion_count = 4 → 可选 cleanup（ADR 文本 minor amend / SIT 14 行首标记 / docstring 主述 / cron 评估），不影响 verdict 推导"
    - "白名单合规：ADR-013 §决策 0 白名单 7 文件全员命中（progress/backend-dev.md 含 ADR-013 段）；2 文件 worktree 余量（tools/* + progress/tech-lead.md）属同 worktree 内独立改动，非 backend-dev 越界 → verdict ≥ approve with changes"
    - "S-1 PARTIAL 裁决 ACCEPT（独立 grep 实证 12+1+4 处主动使用 + ADR §决策 0 子项 c 已 amend 移除 + cb_sync.py docstring 偏离说明 + SIT 14 标记一致），不下沉到 critical"
    - "SIT 4 项检查：完整性 ✅ + AC 覆盖 ✅ + 证据可信 ✅（独立 psql 复核 ths_daily 形态 / change_pct nn / alembic_version 全过）+ 失败标记 ✅ → 'Pass'"
    - "ADR-012 review 收尾：W-2/W-3/S-2/S-3/S-4/LD-2/LD-3 共 7 项 + LD-1 主线全部 ✅；W-1 推迟、S-1 ACCEPT 已说明 → 收尾完整"
  go_no_go: ACCEPT_WITH_FOLLOWUPS
  s1_partial_verdict: ACCEPT
  follow_ups:
    - id: W-1
      summary: "tools/run_today_afternoon.py 旁路改动 + progress/tech-lead.md 非 backend-dev 文件出现在 ADR-013 worktree，需 commit 前归属裁断"
      priority: P2
      owner: product-lead
      eta_hint: "commit 拆分 + commit message 明示归属"
    - id: W-2
      summary: "backend/data/*.db-shm/wal 删除属 SQLite WAL housekeeping，未在 SIT 17 陈述；.gitignore 补 *.db-{shm,wal} 后缀"
      priority: P3
      owner: backend-dev
      eta_hint: "5 分钟"
    - id: S-1
      summary: "ADR-013 §决策 1 + 决策 2 minor amend：Tushare 实际返回 12 字段（非 15），name/total_mv/float_mv 是预留位"
      priority: P3
      owner: tech-lead
    - id: S-2
      summary: "progress/backend-dev.md SIT 14 行首改 [N/A] + 补 1 行 ADR amend 闭环说明"
      priority: P3
      owner: backend-dev
      eta_hint: "5 分钟"
    - id: S-3
      summary: "pg_writer.py:18-22 docstring 微调，主述 ADR-013 §决策 4（W-2）"
      priority: P3
      owner: backend-dev
    - id: S-4
      summary: "ADR-014 audit index_basic 时评估 cron-only 表显式标注"
      priority: P3
      owner: tech-lead
      eta_hint: "ADR-014 实施时顺手"
    - id: LD-1
      summary: "ths_daily.trade_date TEXT 类型 → DATE 统一（与 sw_daily/cyq_chips/top_inst 同型）"
      priority: P2
      owner: tech-lead
      eta_hint: "ADR-014 audit 拆出"
    - id: LD-2
      summary: "ths_daily.updated_at TEXT + 缺 DEFAULT → 永远 NULL"
      priority: P2
      owner: tech-lead
      eta_hint: "ADR-014 audit 一并 fix"
    - id: LD-3
      summary: "_pg_write 共享连接关闭（ADR-013 W-1 已推迟）"
      priority: P1
      owner: tech-lead
      eta_hint: "ADR-014/015 实施时顺手 + apscheduler shutdown hook 配套"
```
