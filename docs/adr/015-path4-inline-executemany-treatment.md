# ADR-015: 路径 #4 inline executemany 模块治理（SQLite/PG dual-target 盘点 + 选型）

- 状态：**Accepted**（2026-06-22 盘点报告产出 + tech-lead 选型对齐方案 A + ADR-015.0 前置完成）
- 日期：2026-06-22
- 决策者：tech-lead 起草；product-lead 排期实施
- 影响范围：盘点性 + 选型性 ADR，**不直接做模块改造**；产物是盘点报告 + 候选方案对比 + 推荐方案 + 子 ADR-015.X 实施清单

## 子 ADR-015.X 跟踪表

| 子 ADR | 优先级 | 范围 | 状态 |
|---|:---:|---|:---:|
| [ADR-015.0](015.0-pg-write-upsert-extension.md) | P0 前置 | `_pg_write` UPSERT 扩展 (conflict_action 参数) | ✅ Accepted (2026-06-22) |
| [ADR-015.1](015.1-stocks-pg-write-migration.md) | P1 | `stocks.py` (高风险 + 高频写入, 需 UPSERT) | ✅ Accepted (2026-06-22) |
| [ADR-015.2](015.2-tushare-pg-path-audit.md) | P1 | `tushare.py` (audit-only: PG 已在 ADR-012 收口, SQLite 保留) | ✅ Accepted (2026-06-22, no-op) |
| ADR-015.3 | P2 | `announcements.py / cctv_news.py / mp_report.py / policy_law.py` (合并) | ⏳ Pending |
| [ADR-015.4](015.4-stock-profiles-pg-write-migration.md) | P1 (015.2 重排) | `stock_profiles.py` (16 列 inline-execute_values, UPSERT) | ✅ Accepted (2026-06-22) |
| ADR-015.4a | P2 | `fina_mainbz.py / fina_audit.py` (原 015.4 拆出, SQLite-only 清理) | ⏳ Pending |
| [ADR-015.5](015.5-namechange-pg-write-migration.md) | P3 | `namechange.py` (PG-only inline, 需 UPSERT; `_upsert_st_history` 收口, `_fallback_snapshot` 保留 INSERT...SELECT) | ✅ Accepted (2026-06-22) |
| ADR-015.6 | P3 | `rt_k.py` 相关 (dual-target) | ⏳ Pending |
| 不立 ADR | — | `interact.py / rt_min.py` (SQLite-only, 无 PG 表) | ❌ Excluded |

## 上下文

ADR-012 方案 A §决策 0 范围声明明确：**路径 #4 inline `executemany` 8+ 模块暂留不动**，因为 (i) 改造涉及 SQLite/PG dual-target 适配，工作量超出方案 A 的 2-3 day 边界；(ii) 这些模块当前未暴露列错位故障；(iii) 留位 ADR-015 治理。

本 ADR 是 ADR-012 §不覆盖 段的兑现。grep 实证 2026-06-22：

**路径 #4 inline executemany 模块清单**（与 ADR-012 §决策 0 范围声明同源）：

| # | 模块 | inline executemany 位置 | PG 表存在 | SQLite-only / Dual-target | 风险级别 |
|---|---|---|---|---|---|
| 1 | `announcements.py` | L89 `db.executemany(INSERT OR REPLACE)` | ✅ | **Dual**（L75 `_pg_write` + L89 SQLite executemany） | 中 |
| 2 | `cctv_news.py` | L85 | ✅ | 未确认（需 grep）— 推断 Dual | 中 |
| 3 | `mp_report.py` | L84 | ✅ | 未确认 — 推断 Dual | 中 |
| 4 | `interact.py` | L133 | ❌（PG 表不存在） | **SQLite-only** | 低 |
| 5 | `policy_law.py` | L147 | ✅ | 未确认 — 推断 Dual | 中 |
| 6 | `fina_mainbz.py` | L106 | ✅ | 未确认 — 推断 Dual | 中 |
| 7 | `fina_audit.py` | L148 | ✅ | 未确认 — 推断 Dual | 中 |
| 8 | `stock_profiles.py` | L105 | ✅ | 未确认 — 推断 Dual | 中 |
| 9 | `namechange.py` | L123 `cur.executemany` (PG 路径) | ❌ | **PG-only**（PG inline，无 SQLite 路径） | 中 |
| 10 | `stocks.py` | L85（SQLite executemany）+ L66 PG inline `cur.execute` 单条循环 | ✅ | **Dual + 反模式**（PG 单条 cur.execute 循环 + SQLite executemany 批量） | 高 |
| 11 | `rt_min.py` | L91 | ❌（PG 表不存在） | **SQLite-only** | 低 |
| 12 | `rt_k`（在 tushare.py / etl.py 等）| 多处 | ✅ | Dual | 中 |
| 13 | `tushare.py` | L66/L186/L194/L265/L299 多处 | ✅ | **Dual + 混合**（部分走 _pg_write，部分 inline） | 高 |

**关键观察**：
1. **不是简单的 8 模块**：实际涉及 13+ 模块（grep `executemany|db\.execute\(` 命中），且每个模块 SQLite-only / PG-only / Dual / 混合 路径**各不相同**
2. **已有部分模块半改造**：`announcements.py` / `stocks.py` 已经做了 dual-write（PG via `_pg_write` 已生效，SQLite executemany 是 fallback）—— **inline executemany 不全是无防御**，部分模块的 PG 路径已经收口到 ADR-012 主干 `_pg_write`，只剩 SQLite 侧是 inline
3. **SQLite-only 模块**：`interact / rt_min / (namechange?)` 等 PG 表不存在，path #4 治理对它们意义不大（SQLite 是本地文件无 IO 抖动 / 列错位风险，inline executemany 实际无风险）
4. **PG-only 模块**：`namechange.py` 走 PG inline cursor，没有 SQLite 路径 —— 直接改 `_pg_write` 即可，工作量最小

**ADR-012 SIT 5 (cb_sync.sync_ths_daily) 给的启示**：thin wrapper 化让长期静默的列错位首次可见（[WARN] 输出）。如果 path #4 模块也有同型潜在问题（列名 ts_code vs code、字段命名不一致等），改造后会暴露 —— **暴露 = 修复机会，不是新问题**。

### 不做此决策的后果

1. **新模块复制 path #4 写法扩散**：早期野生代码（inline executemany + try except pass）会被新人当模板复制（已有先例：cb_sync.py 复制 pg_writer.py 95%），技术债复利
2. **path #4 模块的列错位静默故障无法被发现**：如果未来 path #4 某个模块的 PG 列名错位（如新加列时 sync cols 拼错），整批 UndefinedColumn 然后 `except: pass` 吞掉 —— pledge_detail / rt_sw_k / top_list / ths_daily 的剧本会在 path #4 重演（ADR-009 / ADR-013 教训）
3. **ADR-016 方案 B 升级时增量重构面更大**：方案 B 注册中心要求所有 sync 都走 SyncSpec 注册，path #4 模块到时也要被强制改造，本 ADR 现在做盘点 + 选型可以让 ADR-016 实施时心里有数

## 决策

### 决策 0：本 ADR 的范围（盘点 + 选型，不做模块改造）

⚠️ **本 ADR 是盘点 + 选型型 ADR**：产物是 **盘点报告 + 候选方案对比 + 推荐方案 + 子 ADR-015.X 实施清单**，**不修改任何 sync 模块**。具体模块改造必须**拆出独立子 ADR-015.X**（参考 ADR-008/009/010/011/013 同型骨架）由 tech-lead 起草、PL 排期、backend-dev 实施。

**Decision 0 范围声明**：
- ✅ 允许产出：`docs/reviews/path4-inline-executemany-survey-YYYY-MM-DD.md` 盘点报告 + 本 ADR 末尾的「候选方案对比」+ 「推荐方案」+ 「子 ADR-015.X 实施清单」
- ✅ 允许产出：一次性 grep 脚本（不进生产 service code）`tools/path4_survey.py` 或 `services/sql/audit/path4_survey.py`，建议复用 ADR-014 同目录
- ❌ 禁产出：任何 sync 模块改动（即使是 dead code cleanup）
- ❌ 禁产出：alembic 迁移 / init_sql 改动
- ❌ 禁产出：`pg_writer.py` / `_insert_rows` 等主干改动
- ❌ 禁产出：CLAUDE.md Tech Stack 表改动（本 ADR 不引新依赖）

### 决策 1：盘点维度（survey schema）

每个 path #4 模块按以下维度详细盘点：

| 维度 | 取值 | 来源 |
|---|---|---|
| `module` | 文件名 | 文件系统 |
| `executemany_locations` | 行号清单 | `grep -nE "executemany\|db\.execute\("` |
| `target` | `sqlite-only` / `pg-only` / `dual` / `mixed` | grep `psycopg2.connect` + `sqlite3.connect` |
| `pg_path` | `none` / `inline-cursor` / `_pg_write` / `mixed` | grep `_pg_write` 调用 |
| `sqlite_path` | `none` / `inline-executemany` / 其他 | grep `db.executemany` |
| `pg_table_exists` | `True` / `False` | PG introspect |
| `sync_function` | sync function name | AST 解析 |
| `cols_inline` | sync 函数内 cols 列表（前 5 个 + ...）| 静态读 |
| `pg_table_cols_count` | PG 表实际列数 | introspect |
| `caller` | 调用方（scheduler.py 哪个 job）| grep |
| `daily_volume_estimate` | 每日写入量量级（粗估） | 历史数据查询 |
| `column_misalignment_risk` | `low` / `medium` / `high` | 基于 cols 与 PG 表列对账（参 ADR-013 LD-1 模式） |
| `migration_priority` | `P0` / `P1` / `P2` / `P3` | 综合上述维度评估 |

### 决策 2：候选方案对比（path #4 治理的 3 条路径）

#### 方案 A — 逐个模块切换到 `_pg_write` thin wrapper（沿用 ADR-012 渐进收口）

**核心动作**：每个 dual-target 模块的 inline executemany 段改为：
- PG 路径：替换 inline cursor 为 `_pg_write(table, cols, conflict_cols, rows)` 调用
- SQLite 路径：保持 inline executemany（SQLite 无 IO 抖动 + 本地文件，列错位风险低）—— **不做改造**
- 改造目标：消除 PG 侧 inline，统一到 ADR-012 主干；SQLite 侧维持现状

**优点**：
- 与 ADR-012 §决策 5.2 一致，工作量最小
- 自动获得 ADR-012 的 4 项能力：自动列过滤、3 次重试、`data_volume_floor` 门禁、`ON CONFLICT DO NOTHING`
- 每个模块独立改造，可拆 ADR-015.X 子 ADR 并行
- 风险可控：失败可回退到 inline

**缺点**：
- **SQLite 侧仍是 inline executemany**，path #4 治理不完整 —— 但 SQLite 风险低，可接受
- 部分模块（如 `stocks.py` 当前用 inline `cur.execute` 循环 + `ON CONFLICT DO UPDATE`）的 UPDATE 语义与 `_pg_write` 的 `ON CONFLICT DO NOTHING` 不兼容 —— 需要扩展 `_pg_write` 接受 `conflict_action: Literal["nothing","update"] = "nothing"` 参数，**这是 ADR-012 主干扩展**，超出本 ADR §决策 0 范围
- 部分模块（如 `tushare.py` L186 `INSERT OR REPLACE`）SQLite 语义是 UPSERT，PG 侧若直接切 `_pg_write(DO NOTHING)` 会改变业务语义

**预估工作量**：每个 dual-target 模块 0.5-1d × 6-8 模块 = 3-8 day（拆 ADR-015.X 子 ADR）

#### 方案 B — 为 path #4 写一个 SQLite/PG dual-target 兜底 adapter

**核心动作**：新增 `services/data-service/app/sync/dual_writer.py`：

```python
def dual_write(
    table: str,
    columns: list[str],
    conflict_cols: list[str],
    rows: list[tuple],
    pg_action: Literal["nothing", "update"] = "nothing",
    sqlite_strategy: Literal["replace", "ignore"] = "replace",
) -> dict:
    """统一 SQLite + PG dual-target 写入.

    - PG: delegate _pg_write (ADR-012 主干)
    - SQLite: INSERT OR REPLACE / INSERT OR IGNORE 兜底, 仅当 PG 写入失败时启用
    """
    pg_written = _pg_write(...)
    sqlite_written = 0
    if pg_written == 0 and rows:  # PG 全失败才走 SQLite
        sqlite_written = _sqlite_fallback(table, columns, rows, sqlite_strategy)
    return {"pg_written": pg_written, "sqlite_written": sqlite_written}
```

**优点**：
- SQLite + PG **双路径统一封装**，path #4 真正退役
- 业务语义统一（UPSERT / DO NOTHING / IGNORE 等通过参数控制）
- 未来新 sync 模块只需调 `dual_write` 一行

**缺点**：
- 新增抽象层（与 ADR-006 「轻量 sync」哲学有张力，ADR-012 §决策 4 已论证过）
- ADR-006 决策 1 「PG-first 写入」已经把 SQLite 降级为 fallback，dual_writer 的设计可能让 SQLite 重新成为「平级路径」，反而违背 PG-first 原则
- ADR-006 决策 3 「消除 subprocess 桥」+ ADR-012 主干已收敛 PG 侧，再加一层 dual_writer 让架构层数变多
- 工作量大（新模块设计 + 13+ 模块迁移 + SIT 矩阵）

**预估工作量**：5-8 day（adapter 设计 1d + 模块迁移 3-5d + SIT 矩阵 1-2d）

#### 方案 C — SQLite 侧整体退役

**核心动作**：path #4 的 SQLite 路径全部删除，仅保留 PG 路径（统一走 `_pg_write`）

**优点**：
- 与 ADR-006 决策 1 「PG-first」原则一致到底
- 13+ 模块的 SQLite 路径全部退役，path #4 真正消亡
- 简化未来运维（只需运维 PG）

**缺点**：
- **打破 ADR-006 决策 1 字面**：「PG-first 直写，SQLite 作 fallback」—— 删 SQLite = 取消 fallback
- 实际 SQLite 数据库 (`Kronos/data/kronos.db`) 是 Kronos 模型训练的 legacy 路径，**还有下游消费者**（grep `kronos.db` 实证）—— 删 SQLite 路径会破坏训练数据流
- `interact / rt_min / namechange` 这类 SQLite-only 模块的 PG 表不存在，删 SQLite = 删数据存储（功能性破坏）
- 与 ADR-006 已有的 ADR 决策史不一致；需先立 ADR-016 评估「PG-only 升级」

**预估工作量**：超出当前评估边界（涉及 Kronos 训练数据流改造）

#### 决策 3：本 ADR 推荐方案

**tech-lead 推荐方案 A（逐个模块切换到 `_pg_write` thin wrapper）**，理由：

1. **与 ADR-012 决策一致**：PL 已 Accepted 方案 A 渐进收口，ADR-015 沿用相同哲学（不引入新抽象层，沿用既有 `_pg_write` 主干）
2. **风险可控**：每个模块独立拆 ADR-015.X 子 ADR，可灰度
3. **真实工作量最小**：盘点显示部分模块（announcements / stocks 等）的 PG 路径**已经走 `_pg_write`**，只需清理 inline 残余 + 处理 `conflict_action` 兼容性
4. **SQLite 侧保留 inline 是合理的**：SQLite 是本地文件无网络抖动、列错位风险低；强行抽象 SQLite 侧（方案 B）违背 YAGNI
5. **ADR-006 / ADR-012 哲学连贯**：「PG-first 直写 + SQLite fallback」+「`_pg_write` 是 PG 主干」—— 方案 A 是这两条决策的自然延伸

**前置条件（ADR-012 主干扩展，列入本 ADR §决策 4 子 ADR-015.0）**：
- `_pg_write` 增 `conflict_action: Literal["nothing","update"] = "nothing"` 参数 + 配套 `update_cols` 参数
- 或者新增 `_pg_upsert` 函数（与 `_pg_write` 同型，但用 `ON CONFLICT(...) DO UPDATE SET ...`）

这个主干扩展是方案 A 实施的必要前提（stocks.py 需要 UPSERT 语义），需先拆出 ADR-015.0「`_pg_write` UPSERT 扩展」由 backend-dev 在 path #4 第一个模块改造前完成。

### 决策 4：子 ADR-015.X 拆分规则

按盘点报告输出的 `migration_priority`（参 §决策 1 维度）排序：

| 优先级 | 模块 | 推荐 ADR |
|---|---|---|
| P0（前置） | `_pg_write` UPSERT 扩展 | **ADR-015.0**（必须先做） |
| P1 | `stocks.py`（高风险 + 高频写入） | ADR-015.1 |
| P1 | `tushare.py` 5 处 inline（高风险 + 大表 daily_kline / moneyflow / stk_limit / limit_list_d 影响下游） | ADR-015.2（可能拆 .2a/.2b） |
| P2 | `announcements.py / cctv_news.py / mp_report.py / policy_law.py`（dual-target 已半收口，只清理 SQLite 侧的可选项） | ADR-015.3 合并 |
| P2 | `fina_mainbz.py / fina_audit.py / stock_profiles.py`（dual-target，中频） | ADR-015.4 合并 |
| P3 | `namechange.py`（PG-only inline，最小改动） | ADR-015.5（可能合并到 015.3） |
| P3 | `rt_k.py` 相关（dual-target） | ADR-015.6 |
| 不做 | `interact / rt_min`（SQLite-only，无 PG 表） | 不立 ADR，盘点表标记 `excluded-sqlite-only` |

具体子 ADR 启动时机 + 数量由 tech-lead 在盘点报告产出后评估（参 §决策 7 「盘点写完 + 报告产出后的下一步」）。

### 决策 5：本 ADR 完成定义（DoD）

backend-dev 实施完本 ADR，应交付：

1. `services/sql/audit/path4_survey.py` 一次性脚本（≤ 250 行）—— 输入 path #4 候选模块清单（13 个），grep + AST 静态解析输出每个模块的 §决策 1 维度数据
2. `docs/reviews/path4-inline-executemany-survey-YYYY-MM-DD.md` —— 盘点报告含以下段：
   - §1 候选模块清单（13 + 实跑发现）
   - §2 维度盘点矩阵（按 §决策 1 维度列出每个模块）
   - §3 风险评估（每个模块的 column_misalignment_risk + caller + daily_volume_estimate）
   - §4 ADR-012 主干兼容性评估（每个模块切 `_pg_write` 是否需要扩展 conflict_action 等）
   - §5 子 ADR-015.X 推荐清单（按 P0/P1/P2/P3 排序，附改造工作量预估）
   - §6 SQLite-only 模块排除清单 + 排除理由
3. `progress/backend-dev.md` SIT 段（含脚本可重复跑证据 + 报告 markdown 渲染样本）

**不需要交付**：alembic / init_sql / sync / `_pg_write` 改动（参 §决策 0）。

### 决策 6：SIT 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | path4_survey.py 脚本可执行 | `python services/sql/audit/path4_survey.py` | exit 0，stdout 含 `Survey complete: docs/reviews/path4-inline-executemany-survey-YYYY-MM-DD.md` |
| 2 | 报告含 13 个候选模块 | grep `^### ` 报告 §2 | ≥ 13 条目（announcements / cctv_news / mp_report / interact / policy_law / fina_mainbz / fina_audit / stock_profiles / namechange / stocks / rt_min / tushare / rt_k） |
| 3 | SQLite-only 模块排除清单 | grep §6 | 含 interact / rt_min + 排除理由 |
| 4 | `_pg_write` 主干兼容性段 | 检查报告 §4 | 至少 stocks.py 标记「需 UPSERT 扩展（ADR-015.0 前置）」 |
| 5 | 子 ADR 推荐清单完整 | 检查报告 §5 | 含 P0-P3 4 档；至少 5 个候选 ADR-015.X 列出 |
| 6 | 脚本无 schema 写操作 | grep `INSERT\|UPDATE\|DELETE\|ALTER\|CREATE\|DROP` services/sql/audit/path4_survey.py | 0 命中（仅 SELECT + grep） |
| 7 | 与 ADR-012 §决策 0 一致性 | 检查报告引用 ADR-012 §不覆盖段 | 含引用 + 沿用方案 A 哲学声明 |
| 8 | git diff 白名单审计 | `git diff main --stat` | 仅命中 `services/sql/audit/path4_survey.py`（新建）+ `docs/reviews/path4-*.md`（新建）+ `progress/backend-dev.md`；不命中 sync / scheduler / pg_writer / etl |

### 决策 7：盘点写完 + 报告产出后的下一步

**tech-lead 在盘点报告产出后 1 周内**：
1. 阅读报告 §3 风险评估 + §5 子 ADR 推荐清单
2. 决定 ADR-015.0（_pg_write UPSERT 扩展）的具体规格 + 立项
3. 按 P0 → P1 → P2 → P3 顺序提议子 ADR-015.X 实施排期（PL 排期）
4. 写本 ADR 顶部「Accepted」段 + 「子 ADR-015.X 跟踪表」段
5. 同步在 `progress/tech-lead.md` 末尾追加「ADR-015 盘点结论 + ADR-015.0+ 立项排期」段

**PL 排期**：ADR-015.0 必须先于其他子 ADR 实施（前置条件）；其后按 P1 → P2 → P3 顺序，每个子 ADR 独立 worktree。

## 备选方案

- **A. 不做盘点，按 grep 凭直觉挑模块改** —— pros: 工作量 0；cons: 13+ 模块特征各异（dual-target / SQLite-only / 反模式），无盘点直接改有遗漏风险；ADR-012 已经留位 ADR-015，本 ADR 是兑现；**否决**
- **B. 把 path #4 治理与 ADR-014 audit 合并** —— pros: 节省一个 audit-type ADR；cons: ADR-014 是 schema audit（数据维度），本 ADR 是 code path audit（代码维度），两者读 / 写 / 范围都不同 —— ADR-014 不读 sync 模块 code，本 ADR 不读 schema diff；强行合并会让两个产物互相干扰；**否决**
- **C. 直接立 ADR-016 方案 B 注册中心一次性根治** —— pros: 一次到位；cons: 与 ADR-012 决策一致性破坏（PL 选方案 A 「可逆性优先」+「剩余模块 ≤ 10」原则未变；本盘点 13 模块虽超 10 但 SQLite-only 排除后 10 个左右，依然 < ADR-012 §决策 4 「> 10 张新数据源接入」触发信号）；**否决**
- **D. 把方案 A / B / C 全部对比延迟到子 ADR-015.X 时再决定** —— pros: 本 ADR 更聚焦盘点；cons: 决策 PL 没有方案对比无法排期；**否决**
- **E. 在本 ADR 内立即开始 ADR-015.0 主干扩展** —— pros: 提前启动；cons: 违反 §决策 0 「不修改任何 sync 模块」（ADR-015.0 涉及 `_pg_write` 改动，属于 sync 模块）；ADR-015.0 必须拆独立 ADR；**否决**

## 影响

- 新建 `services/sql/audit/path4_survey.py`（~250 行）
- 新建 `docs/reviews/path4-inline-executemany-survey-YYYY-MM-DD.md`（~8-20 KB，含 §1-§6 段）
- `progress/backend-dev.md` 追加本 task SIT 段
- 现有代码（service / sync / scheduler / pg_writer / alembic / init_sql / factors）：**零改动**
- CLAUDE.md Tech Stack：**无更新**（不引新依赖）

### 对成本

- 不增 API / 算力 / 存储（脚本仅 read-only + grep 静态分析）
- 工作量：backend-dev 1 day（脚本 0.5d + 报告渲染 + SIT 0.5d）
- tech-lead 后续盘点报告评估：0.5 day
- 子 ADR-015.0 ~ 015.X 实施工作量：**本 ADR 不评估**（在子 ADR 内估算）

### 对运维

- 盘点报告首次落盘后，path #4 模块技术债清单可见，运维 / SRE 可按子 ADR-015.X 计划做模块改造排期
- ADR-006 决策 1 「PG-first」状态首次可量化（每个模块 PG/SQLite 路径状态明确）

### 风险

1. **path4_survey.py 脚本 AST 解析失败**：sync 模块代码结构多样（每个模块 ~100-200 行）。**缓解**：先实跑 + 人工校对 5 个模块，确认 AST 解析鲁棒；失败则降级为纯 grep
2. **盘点报告暴露 path #4 模块过多需要改造（如 > 10 个）**：可能让 tech-lead 排期失衡。**缓解**：§决策 4 提供 P0-P3 优先级，PL 按 P0 → P1 排期；同时若 dual-target 模块 > 10 个，触发 ADR-012 §决策 4 「方案 B 升级信号 1」评估
3. **本 ADR 与 ADR-014 重叠**：ADR-014 audit 全 schema diff，本 ADR audit 全 code path —— 实际范围不重叠，**两者并行实施**（ADR-013 → 014/015 都可以并行，建议 PL 排期 ADR-013 P1 在前，014/015 P2 同步排期）

## 本 ADR 不覆盖的决策

- **ADR-015.0 `_pg_write` UPSERT 扩展**：作为子 ADR 独立立项（盘点报告 §4 输出推荐规格后由 tech-lead 起草）
- **具体模块改造**：拆独立 ADR-015.X 子 ADR
- **SQLite-only 模块退役评估**：ADR-006 决策 1 已定 SQLite 作 fallback；退役评估留 ADR-016 长期规划
- **方案 B 注册中心升级**：留 **ADR-016**（PL 排期触发信号见 ADR-012 §决策 4）
- **rt_min / rt_k 实时数据架构**：实时数据写入路径有其自己的特性（流式 vs 批量），ADR-015.X 改造时需单独评估，不在本 ADR 范围

## 后续工作

- [ ] **product-lead**：派 backend-dev 实施本 ADR（与 ADR-013 / ADR-014 并行排期，本 ADR 优先级 P2 与 ADR-014 同档）
- [ ] **backend-dev**：实施 + SIT 8 项 + 证据落 `progress/backend-dev.md`
- [ ] **code-reviewer**：path4_survey.py read-only 验证 + 报告格式 review
- [ ] **tech-lead**（盘点报告产出后 1 周内）：评估 + 立 ADR-015.0 + ADR-015.X 子 ADR 清单 + 在本 ADR 追加「子 ADR 跟踪表」段
- [ ] **product-lead**：按 tech-lead 提议的 ADR-015.0 → ADR-015.X 顺序排期 backend-dev 实施

## 版本与查证

**查证基线日期**：2026-06-22（Proposed 起稿当日；与 ADR-013/014 同基线，无新查证）

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| psycopg2 | 2.9.12 | 2.9.x | 0 | Active | path4_survey.py 用 `information_schema.tables` introspect 验证 PG 表存在性，与 ADR-013/014 同 PG 15 原生 |
| Python `ast` | stdlib | stdlib | 0 | Active | path4_survey.py 用 ast 解析 sync 模块函数体（提取 cols 列表 / inline executemany 行号） |
| Python `re` | stdlib | stdlib | 0 | Active | grep 模式匹配 `executemany\|db\.execute\(\|psycopg2.connect\|sqlite3.connect` |
| PostgreSQL | 15.x | 17.x | 2 major | Active 至 2027-11 | 与 ADR-001/006/008-014 一致 |

**实证 grep 来源**（2026-06-22）：

| 实证项 | 命令 | 结果 |
|---|---|---|
| path #4 模块清单（13 个） | `grep -nE "executemany\|db\.execute\(" services/data-service/app/sync/*.py` | 13 模块命中（含 announcements/cctv_news/mp_report/interact/policy_law/fina_mainbz/fina_audit/stock_profiles/namechange/stocks/rt_min/tushare/rt_k） |
| PG 表存在性 | `psql -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=X)"` | announcements/cctv_news/mp_report/policy_law/fina_mainbz/fina_audit/stock_profiles/stocks/rt_k 存在；interact/namechange/rt_min 不存在 |
| announcements 已半收口 | Read services/data-service/app/sync/announcements.py:75-95 | L75 `from app.sync.pg_writer import _pg_write` + L89 SQLite inline executemany —— dual-target 已切换 |
| stocks 反模式 | Read services/data-service/app/sync/stocks.py:60-90 | L66 PG `cur.execute` 单条循环 + L85 SQLite executemany 批量 —— 不一致 + 需 UPSERT 语义 |
| ADR-012 §不覆盖留位 | Read docs/adr/012-*.md:499 | "路径 #4 inline executemany 8 模块治理...留位 ADR-015" |

---

**Hand-off 给 backend-dev**（限额重置后 / 新会话）：

按 §决策 5 DoD 实施：

1. 起草 `services/sql/audit/path4_survey.py`（≤ 250 行）—— 参考 §决策 1 维度 + ast 解析骨架
2. 实跑脚本生成 `docs/reviews/path4-inline-executemany-survey-YYYY-MM-DD.md`（含 §1-§6 全 6 段）
3. 跑 SIT 8 项（§决策 6）—— 含报告 §3/§4/§5 段人工抽查 3 个模块的盘点准确性
4. 证据写 `progress/backend-dev.md` `**SIT 证据**` 段
5. 不交付任何 sync / scheduler / pg_writer / etl 改动（参 §决策 0）

白名单边界（§决策 0）：
- ✅ 允许：新建 `services/sql/audit/path4_survey.py` + `docs/reviews/path4-*.md` + `progress/backend-dev.md` 追加
- ❌ 禁改：sync 模块 / scheduler / pg_writer / etl / alembic / init_sql / factors / CLAUDE.md

越界 = 违约，PL 直接回退。
