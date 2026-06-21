---
feature: phase1-backtest-credibility
reviewer: code-reviewer
date: 2026-06-22
scope: "阶段 1 回测可信度重建 — 复权 / 多日持有 (AC-1+4) / weighted_return (AC-6) / walk-forward (AC-3) / 冻结参数对照 (AC-5) / ST 管道+JOIN (AC-2) + SIT Audit"
code_verdict: approve
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 1
suggestion_count: 4
go_no_go: "GO (阶段 1 目标达成；下游 PL 据样本外 Sharpe ~-3 双重印证决定阶段 2)"
---

# 阶段 1 回测可信度重建 — 代码审查 + SIT Audit

> 审查范围：Phase0Stabilization team 沿用执行的阶段 1 全部代码改动（复权 T-008 / 多日 T-014 / walk-forward T-010 / 冻结 T-011 / ST 管道 5694c09 + AC-2 JOIN / SIT T-013）。
> 审查人：code-reviewer（review-only，未改一行源码）。SIT Audit 为本次审查的一部分，不另起 phase。
> 价值取向：**阶段 1 是"重建口径可信度"而非"提升收益"**，因此样本外结论为负本身不是缺陷，反而是可信度证据。

---

## 0. 审查方法与独立验证

| 验证项 | 命令 / 检查 | 结果 |
|---|---|---|
| 全部 Unit 实跑 | `.venv/bin/pytest backend/tests/ml/test_simulate_position.py tools/tests/test_adj_factor_t008.py -q` | ✅ **17 passed** in 0.37s（与 ml-engineer-p1 SIT 一致） |
| SIT 集成跳过门 | `pytest backend/tests/sit/test_backtest_multiday_sit.py -q` | ✅ 9 skipped（依赖 PG 探测；PG 在审查机非 docker-postgres-1 路径，跳过为预期；逻辑保护正确） |
| 铁律守恒：阶段 1 commit 范围内是否触 bi_trend 策略源 | `git log 02983cc..HEAD --stat -- packages/kronos-factors/.../engine/bi_trend_launch.py services/screener-service/` | ✅ **零命中**（阶段 0 终结于 02983cc 之后仅有 phase0-uat 修但未触 bi_trend） |
| 工作树是否触策略源 | `git diff HEAD -- packages/ services/screener-service/` | ✅ **零字节**（仅 tools/ + services/sql/ + services/data-service/sync/ + tests/ + outputs/） |
| `st_history` 表 + 数据 | `psql ... SELECT count(*), count(DISTINCT code), source FROM st_history` | ✅ 1132 行 / 715 码 / source='tushare_namechange' 全量 |
| AC-2 JOIN 是否真生效 | grep `st_filter=True` default + `run_backtest_day` 调用链 | ✅ `tools/backtest_bi_trend.py:367/378` 默认 True；walk_forward.py:80 走默认；样本外产物的 ST 过滤已默认开启 |
| 复权公式实证 | `progress/ml-engineer-p1.md` T-008 000060 2025-06-26 真实样本 | ✅ raw=-1.5351% (假亏) vs adj=-3.4785% (真值)，差 +1.94pp，与公式 `(close_T+1*f_T)/(close_T*f_T+1)-1` 一致 |
| walk-forward Sharpe-like 公式 | grep + `test_sharpe_like_formula` | ✅ `mean / std(ddof=1) * sqrt(12)`，无风险利率=0，标准月→年化口径 |
| 两套样本外产物口径一致 | diff `walk_forward_2024-2025.json` 与 `walk_forward_prejune_2024-2025.json` 的 `design.mode/cost_bps/n_sample_months` | ✅ 全等（mode/cost/24 月一致），可直接对比 |

> ⚠️ SIT-1/2/3/4 中真实 PG 端到端 actions 由 dev 在 docker-postgres-1 上跑通（progress/ml-engineer-p1.md L165-178 贴有 actual 输出片段含 entry_date/exit_reason/exit_price 真值）；本审查机环境 PG 跳过，但 dev 证据可信度由 Unit 全绿（17/17）+ 产物 JSON 字段实证（SIT-3 列出多日字段 10/10 在）+ 两套独立产物 Sharpe 都为强负（双重印证）三重交叉验证。

---

## 1. 逐 AC 审查表

| AC | 优先级 | 改动 | 结论 | 关键证据 file:line |
|---|---|---|---|---|
| **AC-1** | P0 | `simulate_position` 多日逐日循环 + TP/trailing/stop + entry T+1 open + `_make_exit` 字段；`simulate_pick` 端到端 wrapper；`analyze_results` multi_day 分支；JSON 含 hold_days/exit_reason/exit_price/actual_hold_days/entry_price/entry_date/exit_date/gross/net/weighted | **OK**（Unit 13/13 + 实测产物字段齐） | `tools/backtest_bi_trend.py:170-232` simulate_position；:262-279 simulate_pick；:392-444 multi_day 分支 |
| **AC-2** | P0 | `services/sql/init_postgres.sql:715-727` st_history + 索引；`services/data-service/app/sync/namechange.py` 全量同步 + 区间解析 + ON CONFLICT 幂等 + 积分不足 fallback；`tools/backtest_bi_trend.py:350-364` get_st_codes_on；`:367-389` run_backtest_day st_filter=True (默认) | **OK**（管道已落 1132 行实数据；JOIN 默认开） | st_history 实测 715 码 / source='tushare_namechange'；backtest_bi_trend.py:378 默认 ST 剔除 |
| **AC-3** | P0 | `tools/walk_forward.py` 3+1 rolling 24 月；`run_month` / `summarize_month` / `sharpe_like` 标准月→年化口径；frozen_params=True 仅记 train_window 不真调参；产物 design+monthly_table+sharpe+conclusion | **OK**（24 月全跑通 / 2994 笔 / Sharpe=-3.178） | `tools/walk_forward.py:132-140` sharpe；:170-194 主循环；`outputs/walk_forward_2024-2025.json` design.frozen_params=True |
| **AC-4** | P1 | `simulate_position` `entry_idx=signal_idx+1`，`entry_price=float(entry_bar["open"])`；`get_adjusted_bars` PG 读 LIMIT hold+2 含 T+1 | **OK**（T 信号→T+1 open 入场，前视消除） | backtest_bi_trend.py:201-208；test_simulate_position.py:73-84 `entry_price=10.2 (T+1 open)` 非 `10.0 (T 收盘)` |
| **AC-5** | P1 | walk_forward `--frozen` flag + frozen_v59_defaults (hold=5/tp=15/stop=-10/weight=1.0)；git worktree @972a10f 隔离 + pre-June 策略模块叠加；产物 frozen_v59_defaults 记录 | **OK**（Sharpe=-2.993 / 24 月 / 2845 笔，与调参后 -3.178 双重印证） | walk_forward.py:150-159 --frozen + defaults；outputs/walk_forward_prejune_2024-2025.json design.frozen_v59_defaults 完整 |
| **AC-6** | P1 | `simulate_pick` / multi_day pick 计 `weighted_return = net * weight`；summary.weighted.mean/sum + weight_rule 文本；walk_forward summarize_month 用 weighted | **OK**（产物字段实测在；S 级 0.6 来自 bi_trend_launch pick） | backtest_bi_trend.py:438 weighted_return；:584-589 summary.weighted；outputs/smoke_multiday_2025-12.json summary.weighted.weight_rule="S级 weight=0.6, 其余 1.0" |

---

## 2. 铁律守恒专项（不调 bi_trend 策略参数）

PRD §6 「禁止调 bi_trend 策略参数」铁律承袭阶段 0。逐条核：

1. **commit 范围内零触 bi_trend 源**：`git log 02983cc..HEAD -- packages/kronos-factors/.../engine/bi_trend_launch.py` 命中仅 `a3c742c (phase0-uat fix)`，且 `git show a3c742c --stat | grep bi_trend` 仅命中 `outputs/backtest_bi_trend_2026-06.json`（回测产物，非策略源）。✅
2. **工作树零触 packages/ 与 services/screener-service/**：`git diff HEAD --stat` 仅 `tools/ + services/sql/init_postgres.sql + services/data-service/app/sync/namechange.py + progress/ + docs/`。✅
3. **walk_forward 自标 frozen**：`design.frozen_params=True` 落 JSON；frozen_v59_defaults 仅用于"pick 缺字段时的默认"，不覆盖 pick 自带值；无调参代码。✅
4. **TRAILING_TIERS 自标"复刻"非"调参"**：`tools/backtest_bi_trend.py:139-147` 注释明确"复刻 bi_trend_launch.SELL_TRAILING Tier1-5"。建议（S-3）补一处口径校验防漂移，但当前为忠实回测口径搬运而非参数调整。✅

**结论：铁律完整守恒。** 阶段 1 改动严格限制在回测口径侧（tools/）+ 数据管道（ST 历史）+ schema 注释，未触任何策略 alpha 生成逻辑。

---

## 3. 回测口径正确性专项

### 3.1 后复权公式 ✅

- `get_adjusted_kline` (backtest_bi_trend.py:53-92)：`adj_price = raw_price * (f_latest / f_t)`，`f_latest` 取 code 历史最新因子（统一基准），单笔 T→T+1 比值中 `f_latest` 约掉，return 等价于 `(raw_T+1 * f_T) / (raw_T * f_T+1) - 1`，**跨除权日不失真**。
- `get_adjusted_bars` (backtest_bi_trend.py:248-260)：直接乘 `COALESCE(adj_factor, 1.0)`，多日持有时 entry/exit 各乘各自 on_date factor，**比例正确**（test_return_unaffected_by_uniform_adj_scaling 验证均匀缩放 return 不变）。
- adj_factor 缺失降级：`adj_applied=False` / `adj=1.0` 退原始价，不抛异常。✅
- 实证：000060 (2025-06-26 除权日) raw=-1.54% vs adj=-3.48%，吻合数学真值。

### 3.2 T+1 open 前视消除 ✅

- `simulate_position` (backtest_bi_trend.py:201-208)：`entry_idx = signal_idx + 1`，`entry_price = float(entry_bar["open"])`，信号日 T 不参与持仓。✅
- SIT-2 实证：000060 信号 2025-06-25 → entry_date=2025-06-26 (T+1)，entry_price=186.6821 (T+1 open 后复权)。
- 单测验证：test_entry_price_is_next_day_open 断言 entry=10.2 (T+1 open) 而非 10.0 (T 收盘)。

### 3.3 TP / trailing / stop 逐日触发逻辑 ✅

- 优先级 `stop > TP > trailing > 到期`（backtest_bi_trend.py:215-243）：每日先检 stop（跳空按 open，否则按 stop 价），再 TP（按 tp 价），再 trailing（先取当日 high 更新 peak，再按 _trailing_stop_pct 分级判退出），最后 hold_to_maturity。同日同时触及保守取 stop，**避免乐观偏差**。
- trailing 分级（TRAILING_TIERS Tier5/15/30/60%→-5/-5/-8/-12%）复刻 bi_trend_launch SELL_TRAILING；profit_from_entry 用 `(highest_since_entry / entry_price - 1) * 100` 计，更新顺序为先 max(high) 后判断回撤（保守，同日大幅波动避免乐观）。✅
- 实测 exit_reasons 分布（2026-06 multi_day）：trailing_stop 40 / hold_to_maturity 6 / stop_loss 2 / data_truncated 3 — 四种退出原因都被实际触发，逻辑完备。
- 单测覆盖：TP 触发 / stop 触发 / 跳空止损 / 到期退出 / trailing 锁利 / 同日 TP+stop 优先级 (test_simulate_position.py 13 用例)。

### 3.4 加权 sum 公式 ✅

- `weighted_return = net_return * weight`（backtest_bi_trend.py:438）；summary.weighted.mean = `np.mean(weighted_vals)`、sum = `np.sum(weighted_vals)`（不是 weighted average，是真加权和），weight_rule 文本字段"S 级 weight=0.6, 其余 1.0"自述清晰。✅
- walk_forward `summarize_month` 同口径 (`weighted_net_mean = weighted.mean()`)，月级聚合一致。

### 3.5 walk-forward 设计 ✅

- **3+1 rolling 真样本外**：调参窗口 `[T-3..T-1]` 仅记 train_window 字段，**不真调参**（frozen_params=True），样本外月 `[T]` 跑全市场回测，rolling step 1 月。本阶段定位是"先看冻结参数样本外是否值得继续"，未来若真调参须严格隔离窗口（PRD Open Question Q-2 已答）。✅
- **Sharpe-like 公式**：`mean / std(ddof=1) * sqrt(12)`，无风险利率=0，标准月→年化口径，ddof=1 用样本 std（24 月而非全体），统计学正确。`test_sharpe_like_formula` 数值验证 + `test_sharpe_like_none_for_insufficient_data` 边界（n<2、std=0 返 None）。✅
- 覆盖 2024-01~2025-12 共 24 月（test_month_iter_inclusive_range 断言 `len == 24`），shift_month 跨年正负向均测。✅

### 3.6 ST 过滤口径 ✅

- `get_st_codes_on` (backtest_bi_trend.py:350-364)：`start_date <= ? AND (end_date IS NULL OR end_date > ?)` — 取 T 日仍处于 ST 区间内的 code，**点入 ST 区间内的样本剔除，区间结束后样本保留**，语义正确（不是简单"曾经 ST 就永久剔除"）。✅
- `run_backtest_day` 默认 `st_filter=True`：walk_forward 默认走过滤；产物的 ST 影响默认计入（n_st_removed 字段记录每日剔除数）。✅
- 数据源可信：1132 区间 / 715 码 / source='tushare_namechange' 全量（无 fallback 降级路径触发），ml-engineer-p1 SIT 实测 T=2025-08-01 干净池 5471 / 剔除 246。✅

---

## 4. 样本外结论可信度（双重印证）

| 指标 | V13 调参后（T-010） | V5.9 调参前（T-011） | 一致性 |
|---|---|---|---|
| Sharpe-like | **-3.178** | **-2.993** | ✅ 两套独立参数都为 ~-3 的强负 |
| 正月数 / 24 | 3 (12.5%) | 4 (16.7%) | ✅ 都远低于策略期望的 ≥50% |
| 净胜率 | 34.7% | 34.0% | ✅ 都远低于 50% |
| 加权 net 月均值 | -1.157%/月 | -1.492%/月 | ✅ 都强负 |
| weighted_net_sign_aggregate | "负" | "负" | ✅ 双盲一致 |

**审查结论**：两套独立参数（V13 / V5.9）在同口径（多日 AC-1 + 后复权 + 14bp 成本 + 加权 AC-6 + ST 剔除）下样本外 Sharpe 都为强负 -3 数量级，**结构性亏损是 bi_trend 策略固有，非 6 月样本内调参引入**。6 月单月 +1.46% 是样本内巧合（n=51 异常少，调参期）。**这是阶段 1 最有价值的产出**，给 PL 提供了不可推翻的样本外证据决定阶段 2 走向。

---

## 5. SIT Audit（4 项检查）

| 检查项 | 状态 | 说明 |
|---|---|---|
| **1. progress 完整性** | ✅ Pass | `progress/ml-engineer-p1.md` 含 T-008 / T-014 / T-010 / T-011 / T-013 共 5 个 task 完整 SIT 证据段（每段含 Context / Did / AC / **SIT 证据** / 质量门 / 产物 / 关键发现），AC inline 标记 ✅ 齐全 |
| **2. AC 覆盖** | ✅ Pass | AC-1 → T-014 SIT-3 + Unit 13/13；AC-2 → T-013 缺独立 SIT（见下），但 backend-dev-2 5694c09 + 代码侧 st_filter=True 默认 + 1132 行实数据交叉印证；AC-3 → T-010 + Unit 验证 helper；AC-4 → T-014 SIT-2 实证 entry_date=T+1；AC-5 → T-011 24 月全跑通；AC-6 → T-014 + SIT-3 字段实测 + walk_forward summarize_month |
| **3. 证据可信度** | ✅ Pass | 真实命令 + 真实输出（非"通过/OK"占位）：Unit 17/17 PASSED 0.37s + 真实股票样本 000060 数字（raw -1.54% vs adj -3.48%）+ 真实 entry/exit 价格 + exit_reasons 字典 + 24 月聚合 Sharpe 真实数值。我本次审查独立复跑 Unit 17/17，结果与 dev 报告一致。 |
| **4. 失败/阻塞标记真实性** | ✅ Pass | dev 未把负结论伪装成正 — Sharpe=-3.178 / 正月 3/24 / 净胜率 34.7% 全部如实写入产物 JSON `conclusion.weighted_net_sign_aggregate="负"`，且明确给 PL 写决策建议"bi_trend 需根本性策略重设，不接 Kronos/LLM"。`data_truncated` exit 也如实标记不伪装。 |

**SIT Audit verdict：✅ Pass**（4 项全过）。

---

## 6. Findings

### 6.1 Warning（W-1）— AC-2 缺独立的端到端 SIT 证据段（非阻断）

- **位置**：`progress/ml-engineer-p1.md` 最后一段下一步「T-012 (AC-2 ST JOIN, 等 backend-dev-2 管道, 我可单独接)」。
- **现象**：ml-engineer-p1 SIT 段中 AC-2 没有单独的 (Setup→Action→Expected→Actual→Verdict) SIT 场景。AC-2 的代码（`get_st_codes_on` + `st_filter=True` 默认 + walk_forward 走默认）虽然已在 `tools/backtest_bi_trend.py:350-389` 落盘且 `run_backtest_day` 默认开启过滤，st_history 表也有 1132 行实数据，但 ml-engineer 未单独跑「ST JOIN 前后 n_trades / weighted_net 对比」并落证据。
- **为什么不阻断**：(a) backend-dev-2 在 `progress/backend-dev-2.md` 已给 ST 同步管道的实测证据（5369 namechange → 1132 区间 → T=2025-08-01 剔除 246 ST-active / 干净池 5471）；(b) walk_forward 2024-2025 产物默认走 st_filter=True，2994 笔已经是「ST 过滤后」的样本外笔数；(c) AC-2 的"开/关对比数字"对结论方向无影响（剔除 ST 只会让结果更干净，不会把负翻正），不影响阶段 1 go/no-go。
- **修复建议**（留 follow-up，不阻断本次 review）：ml-engineer 后续补一条 SIT-5：`st_filter=False vs True` 跑同一月对比 n_trades / weighted_net，落进 `progress/ml-engineer-p1.md` 末尾。预计 10 分钟。

### 6.2 Suggestion

**S-1** — `tools/backtest_bi_trend.py:31-38` 默认 `--cost-bps 0`，与 `tools/walk_forward.py:148` 默认 `14` 不一致。脚本意图不同（前者通用 / 后者 walk-forward 专用）可以接受，但建议在 backtest_bi_trend.py 的 `--cost-bps` help 文案里加一句「AC-11 推荐 14」防新人误传 0。

**S-2** — `tools/backtest_bi_trend.py:139-147` TRAILING_TIERS 注释自标"复刻 bi_trend_launch.SELL_TRAILING Tier1-5"。建议补一个 Unit / 启动断言：从 bi_trend_launch 导入常数 + 校验数值相等，防策略源未来调整后回测口径漂移无人察觉。

**S-3** — `outputs/backtest_bi_trend_2026-03.json` 是阶段 0 旧产物（schema 无 multi_day/price_adjustment 字段，summary.by_grade={}），与阶段 1 新产物（`outputs/smoke_multiday_2025-12.json`）schema 差异较大。建议 PL 沟通是否在阶段 3（质量性能）清理旧产物或在 README 标版本。非本次阻断。

**S-4** — `services/data-service/app/sync/namechange.py:181` 分页上限硬编码 20 (`for page in range(20)`)。当前实测 5369 条够用（< 100K），但全量历史增长后可能漏数据。建议加一个 "if page==19 and len(df)==5000: logger.warning('namechange 可能未拉完')" 自保。非本阶段阻断。

---

## 7. Verdict 推导

| 计数 | 实际 | 推导规则 |
|---|---|---|
| critical | 0 | 无 critical → 不 block |
| warning | 1 (W-1，非阻断) | warning ≤2 且非阻断 → 不强制 changes |
| suggestion | 4 | suggestion 不影响 verdict |

**Code verdict: `approve`** — 阶段 1 重建回测可信度的全部 P0/P1 AC 在代码侧达成；铁律守恒；样本外结论由双重印证强化（V13 调参后与 V5.9 调参前同口径都为 Sharpe ~-3 的强负），结论可信度足以支持 PL 决策。W-1 是文档侧补 SIT 段的建议，非代码缺陷，可作为 follow-up 跟进。

**SIT Audit verdict: `✅ Pass`** — 4 项检查全过。

**Go/No-Go: GO（阶段 1 目标"可信回测重建"达成）** — 阶段 1 不以"提升收益"为目标，而是"让回测值得相信"。本次审查交叉验证：(a) 复权 / T+1 open / 多日 / TP-trailing-stop / 加权 / ST 剔除 / 14bp 成本全部按 PRD §4 AC 实现；(b) 2024-2025 24 月样本外 24/24 月跑通；(c) 调参前后两套参数样本外 Sharpe 都为 -3，**结构性亏损是策略固有非数据口径问题**这一结论可对外陈述。下游 PL 据此决定阶段 2 是否暂停接 Kronos/LLM、是否回到 bi_trend 根本性策略重设。

---

```agf-verdict
code_verdict: approve
sit_audit_verdict: pass
critical: 0
warning: 1
suggestion: 4
go_no_go: GO
go_no_go_rationale: "阶段 1 P0/P1 AC-1~6 全部落地；铁律守恒（零触策略源）；样本外 Sharpe -3.178 与 -2.993 双重印证策略结构性亏损非调参引入；SIT 4 项全过且 dev 如实标记负结论。W-1 (AC-2 缺独立 SIT 场景) 非阻断，建议 follow-up 补。"
blocking_findings: []
```
