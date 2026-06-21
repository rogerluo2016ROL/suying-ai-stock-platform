# PRD — 阶段 1 回测可信度重建（Phase 1 Backtest Credibility）

- **Date**: 2026-06-22
- **Owner**: product-lead
- **Status**: Draft
- **Estimated effort tier**: Large（多日持有回测引擎 + walk-forward + 幸存者偏差 + 样本外重跑，模型域深度工作）
- **依据**: `docs/reviews/audit-model-2026-06-21.md` §4 + `docs/reviews/platform-audit-2026-06-21.md` §4 阶段 1 + 阶段 0 Q-1 结论（`outputs/backtest_bi_trend_6m_cost14_summary.json`）

## 1. Background

阶段 0 的 Q-1 结论（扣 14bp 成本后聚合净均值 +0.0526%/trade，但净**中位数 -0.22%**、去掉 6 月调参期后 1-5 月净 sum **-34.18 为负**）证明：**当前 bi_trend 回测指标不可信**，不能作为策略迭代或对外承诺的基础。审计 model 报告 §4 列了 5 类回测偏差（隐式前视、幸存者偏差、零成本[阶段0已修]、样本内调参、持有期未实现）。

在动任何"提升收益"的事（阶段 2 接 Kronos/LLM）之前，必须先让回测指标值得相信。本 PRD 收口阶段 1——重建回测可信度：实现多日持有回测引擎（对齐策略声明）、消除幸存者偏差、用 walk-forward 验证样本外、冻结参数跑 2024-2025。

业务驱动：平台宣称"AI 驱动量化投资"，若策略到底赚不赚钱无法用可信回测回答，后续所有产品决策（接 Kronos、上实盘）都建立在沙地上。

## 2. Goal & Non-Goals

**目标**: 让 bi_trend 回测在「扣成本 + 多日持有 + 无幸存者偏差 + 样本外 walk-forward」口径下，产出**可对外陈述**的净收益符号 + Sharpe-like 指标；并据此判定策略是否值得继续（阶段 2 接 Kronos/LLM）或需重设计。

**KPI（上线后用什么判定成功）**:
1. bi_trend 回测实现策略声明的 hold_days 3/5/7/10 + TP 20/25% + trailing stop（当前只算 T+1，审计 §4.1）
2. 幸存者偏差消除：按 `trade_date` 关联 ST/退市标记，剔除历史曾戴帽股（审计 §4.3）
3. walk-forward 样本外：T-3 月调参 → T 月验证，滚动推进 2024-01~2025-12，输出样本外净 Sharpe-like
4. 冻结参数（6 月调参前版本）跑 2024-2025，净符号可对外陈述
5. 隐式前视消除：T 日信号 → T+1 开盘买入（非 T 日收盘同日成交，审计 §4.2）

**Non-Goals**（明确不做，留给后续）:
- **不调任何 bi_trend 策略参数**（OBV/WR/TP/stop_loss 等）——纪律，调参是 Q-1 符号明确后的决策（见 [[bi-trend-net-backtest-finding]]）
- 不接 Kronos 预测 / 不接 LLM（阶段 2）
- 不改前端回测页（阶段 3）
- 不补全量单元测试（阶段 3）
- 不接 xtquant 实盘（阶段 2，且依赖阶段 1 结论）
- 不合并 bi_trend_launch / full_market 两份重复代码（阶段 3）

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 量化研究员 | 回测实现策略声明的多日持有+止盈+移动止损 | 回测指标反映策略真实行为，而非 T+1 近似 |
| US-2 | 量化研究员 | 回测剔除历史曾 ST/退市的股 | 不被幸存者偏差系统性高估 |
| US-3 | 量化研究员 | walk-forward 样本外验证 | 知道策略在未见数据上是否有效，而非样本内调参假象 |
| US-4 | 产品负责人 | 冻结参数跑 2024-2025 的净符号 | 决定阶段 2 是否接 Kronos/LLM |
| US-5 | 量化研究员 | 回测消除"同日信号+收盘成交"隐式前视 | 决策时刻数据就绪，收益不掺未来信息 |

## 4. Acceptance Criteria

> 逐条独立可验证。ml-engineer 自跑 + code-reviewer audit 证据。

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | `tools/backtest_bi_trend.py` 实现 hold_days 3/5/7/10 多日持有 + TP 20%/25% 止盈 + trailing stop 移动止损逐日检查（当前只算 T+1 单日），回测产物 JSON 含 `hold_days`/`exit_reason`/`exit_price` 字段 | grep 回测引擎含 hold loop + TP/trailing 判断；重跑产物含新字段 |
| AC-2 | P0 | 幸存者偏差修复：选股池过滤按 `trade_date` 关联 ST/退市标记（Tushare namechange 或 st_history），剔除回测时点**已戴帽或已退市**的股；对比修复前后样本数 + 净收益 | 对比修复前后 n_trades + net_return；grep ST 关联逻辑 |
| AC-3 | P0 | walk-forward 实现：T-3 月窗口调参（或用冻结参数）→ T 月样本外验证，滚动推进；输出 2024-01~2025-12 样本外逐月净收益 + 聚合 Sharpe-like（非样本内 6 月数据） | 跑 walk-forward 脚本，产物含样本外逐月表 + Sharpe-like |
| AC-4 | P1 | 隐式前视消除：入场改 T+1 开盘价买入（非 T 日收盘同日成交）；T 日 breadth 等盘后特征用于 T+1 决策（非 T 日盘中） | grep 入场价用 next_day open；回测产物 entry_price = open[T+1] |
| AC-5 | P1 | 冻结参数（6 月调参前 git 版本的 bi_trend 参数）跑 2024-01~2025-12 样本外，输出扣成本净符号 + Sharpe-like + 逐月表 | git checkout 调参前参数 + 跑回测，产物含 net 符号 + Sharpe |
| AC-6 | P1 | 加权逻辑进 JSON 产物：`weighted_return`（S 级 weight=0.6 等已应用），summary 用加权 sum（当前只进 stdout） | 产物 JSON 含 weighted_return 字段；summary 加权 |

## 5. Design

- **UI**: 无新 UI（阶段 1 纯回测引擎 + 脚本，不改前端）。
- **回测引擎**（`tools/backtest_bi_trend.py` 核心重构）：
  - `get_next_day_return` → `simulate_position(code, entry_date, hold_days, tp_pct, trailing_stop_pct)` 逐日循环：检查 TP/trailing/stop 触发，记录 exit_reason/exit_price/hold_days
  - 入场价：T+1 open（AC-4，消除前视）
  - ST 关联：选股池 SQL JOIN st_history（按 trade_date）
- **walk-forward 脚本**（`tools/walk_forward.py` 新增）：rolling window 调参/验证循环，输出样本外表
- **数据**：复用 PG daily_kline + 新需 ST 历史（namechange 或 st_history 表）

## 6. Technical Constraints

- **回测纪律**（铁律，承袭阶段 0）：AC-1/2/3/4/5/6 只重建回测口径，**禁止调 bi_trend 策略参数**。调参是阶段 1 结论后的决策。
- 扣成本沿用阶段 0 AC-11（`--cost-bps 14`，往返 0.14%）
- 不引入新重依赖（numpy/pandas/psycopg2 已在栈）；walk-forward 用现有 PG 数据
- 遵守 `.claude/standards/coding.md`「Verify before assert」
- 复权处理（AC 前提）：确认 PG daily_kline.close 是前复权（审计 §8.1 未确认）—— Q-4

## 7. Cost Estimate

- **LLM token / 月**：阶段 1 无 LLM（回测引擎 + 脚本），0
- **Agent Team 开发 token**：ml-engineer（主，回测引擎重构 + walk-forward + 幸存者偏差 + 样本外）+ code-reviewer（audit）+ 可能 backend-dev（ST 数据管道）。预估 ml-engineer 深 work ~150-250K + review。落 cost-budget **Large 档**
- **数据依赖**：ST 历史（Tushare namechange，需 token；或现有 st_history 表）

## 8. Out of Scope / Future Work

- 阶段 2（接通真东西）：Kronos 接入选股 / LLM 方案 / 实盘 / 4 store 迁 PG
- 阶段 3（质量性能）：bi_trend_launch/full_market 合并 / 全量单测 / 前端回测页改
- 策略参数调优（TP/stop_loss 网格搜索）：阶段 1 结论（净符号）后，若为正才做
- 复权方案升级（如果 Q-4 确认非前复权）：留阶段 1 内解决

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-2 | walk-forward 窗口设计：3 月调参 + 1 月验证 rolling？或固定 train/test split？ | ml-engineer | 2026-06-24 | 影响 AC-3 实现与样本外显著性 |
| Q-3 | ST 历史数据源：Tushare `namechange`（按 trade_date 拉 ST 戴帽/摘帽）？还是现有 st_history 表？数据完整性？ | ml-engineer | 2026-06-24 | AC-2 前提；Tushare namechange 需 token + 积分 |
| Q-4 | PG `daily_kline.close` 是否前复权？若否，回测绝对收益 + 多日持有 exit_price 都失真 | ml-engineer | 2026-06-23 | 审计 §8.1 未确认；影响所有 AC 的真实性，必须先答 |

## 10. Sign-offs

- [x] product-lead: 初稿（本文件）
- [ ] tech-lead: 技术可行性 review（回测引擎重构涉及数据管道，**建议**但不强制——若 Q-3/Q-4 涉及 schema/数据源新 ADR 则强制）
- [ ] ml-engineer: 实现可行性确认（AC-1~6 全部，主执行）
- [ ] backend-dev: ST 数据管道可行性（若 Q-3 需新 sync 任务）
- [ ] qa-engineer: N/A（阶段 1 纯回测脚本，无 E2E/UAT 业务签字；可信度由 ml-engineer 自跑 + code-reviewer audit）

## Changelog

- 2026-06-22: 初稿（基于阶段 0 Q-1 结论 + 审计 model §4）
