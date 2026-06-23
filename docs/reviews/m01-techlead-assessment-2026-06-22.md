# M01 walk_forward 时序泄露 — tech-lead 方案评估

- 评估日期: 2026-06-22
- 评估人: tech-lead（只读评估，未改任何代码）
- 触发: code-reviewer-ml 在 `docs/reviews/ml-p0-review-2026-06-22.md` M01 专项明确 flag 升级
- 评估对象: M01（audit §3 根因 A — `walk_forward.py` 用 HEAD 版本策略测过去 = 参数时序泄露）的强化方案 A/B/C/D 取舍
- 上游证据: `docs/reviews/audit-model-2026-06-22.md` §3 根因 A + §4 修复优先级 + `docs/reviews/ml-p0-review-2026-06-22.md` §2 M01 / C-1 / §6 架构升级建议
- 关联 memory: `phase1-sample-out-conclusion`（bi_trend 三重印证样本外确定性亏，需根本重设）、`bi-trend-net-backtest-finding`
- **状态更新（2026-06-22）**: 推荐方案 A + C 已由 ml-engineer 实施并 commit：
  - `92a4d39` `feat(ml): M01-A/C walk_forward 时序泄露护栏 — strict-timeline flag + dirty 始终 exit(2)` —— `tools/walk_forward.py` (+116 行) + `services/training-service/tests/test_walk_forward_timeline.py` (+172 行，8 个行为级单测，直接回应 code-reviewer-ml W-2)。
  - `8bb195f` progress 条目。
  - 实现与本文 §3 AC 对齐：`--strict-timeline` flag 控制 commit 日期阻断；dirty 工作区**始终 exit(2) 不受 flag 控制**（符合本文"dirty 跑样本外任何情况不可信，无兼容必要"）；代码注释显式引用 memory `phase1-sample-out-conclusion` How-to-apply #4。
  - tech-lead 复核：commit 真实存在 + walk_forward.py 实际含 strict-timeline / dirty raise 逻辑 + 单测文件真实，状态核实通过。

---

## 0. 问题复述（一句话）

`tools/walk_forward.py` 对 2024-01~2025-24 个样本外月循环跑回测，但循环里 `run_backtest_day` → `from kronos_factors.engine.bi_trend_launch import run_bi_screening` import 的是**当前工作区 HEAD 版本**的策略模块——HEAD 是 2026-06 用 216 网格调参后才冻结的 V13。用 2026-06 的参数测 2024-2025 = 参数从未来泄漏到过去，"样本外"名不副实。这是 audit 定性的 bi_trend 样本外 -1.157%/月 Sharpe -3.178 的**最致命根因**。

ml-engineer 的 M01 修复（`_git_strategy_commit()`）只**记录 commit + 打印警告**，不阻断。code-reviewer-ml 判 AC-1 字面满足但实质要求（阻止时序泄露）未达，flag 升级 tech-lead。

---

## 1. 方案对照

### 方案 A — strict exit

`--strict-timeline` flag：commit 日期 > OOS 起始月，或工作区 dirty → `sys.exit(2)`。CI 跑 walk_forward 必须传此 flag 才算有效样本外。

- **彻底性**：中。**能阻断"用调参后参数测调参前"**（commit 日期晚于 OOS 起始 → exit），但**不能让 walk_forward 自动用对时点参数**——它只是拒绝跑，跑的人仍需手工 `git checkout <commit-at-oos>` 后再跑。对"24 个 OOS 月用同一时点参数"的伪样本外，A 只是逼操作者承认"我用的是 X commit 的参数"。
- **实施成本**：低。纯增量，只动 `walk_forward.py:main()` 开头 `_git_strategy_commit` 后那段（现 line 215-218 的 print 警告改成 sys.exit），不碰循环、不碰 import、不碰 `run_backtest_day` 契约。约 15 行代码 + 1-2 个单测。
- **风险**：低。exit code 2 是标准 CI 失败信号，无副作用。

### 方案 B — per-oos-month checkout

每个 OOS 月循环内 `git show <commit-at-oos-month>:path/to/bi_trend_launch.py` 取该时点版本，动态加载跑该月（audit §3 根因 A 明示此方案）。

- **彻底性**：高（理论上）。每 OOS 月用该月对应时点的策略参数，"样本外"定义真正成立。但——
- **实施成本**：**高，且有硬架构冲突**。读代码：
  1. `walk_forward.py:41-43` 在**进程启动时**（模块加载）`from backtest_bi_trend import run_backtest_day, simulate_pick`；
  2. `run_backtest_day`（`tools/backtest_bi_trend.py:367-389`）**函数体内** `from kronos_factors.engine.bi_trend_launch import run_bi_screening`；
  3. Python module cache 一旦 import 进 `sys.modules` 就固定，同进程内第二次 import 返回 cached 对象。
  
  要让每个 OOS 月用不同 commit 的 bi_trend_launch，必须 `importlib.reload()` 整个 bi_trend_launch 模块链（含它 import 的 calc_obv / calc_wr / 市场环境 / 仓位管理全部子依赖）——reload 不会级联，需手工逐个 reload，且 bi_trend_launch 还引用了 `setup_db` 注入的 DB adapter（`_db_stub` 全局态），reload 顺序错会丢 DB 句柄。另一条路是**每 OOS 月 spawn 一个 subprocess** 跑 `run_month`，把结果 marshal 回主进程——干净隔离，但破坏现有"主进程 `setup_db()` 一次、`_get_db()` 进出 context 复用 PG 连接池"的性能模型，24 月变 24 次冷启动（每次重连 PG + 重建因子 cache），跑一轮从数小时变可能半天以上。audit §4 自己也说"当前性能开销使回测一轮要数小时，阻碍 walk-forward 多次验证"——B 会放大这个问题。
- **风险**：高。subprocess 路径涉及 commit 解析（要算"OOS 月 = oos_month 对应的 git 历史上的最新 commit"）、临时文件清理、异常传播、dirty 工作区交互（checkout 期间工作区状态污染）。任一环节错就静默用错版本，比当前的"警告"更隐蔽。

### 方案 C — dirty raise

工作区 dirty → raise，强制 clean commit 才能跑 walk_forward。

- **彻底性**：低。只防"本地未提交修改"，不防"用调参后 HEAD 测调参前数据"（HEAD 即使 clean commit，日期仍晚于 OOS 起始）。是 A 的子集。
- **实施成本**：极低（`_git_strategy_commit` 已算出 dirty flag，加一行 `raise`）。
- **风险**：低。

### 方案 D — 保持现状（记录 + 警告）

接受 ml-engineer 现实现，列 follow-up。

- **彻底性**：无实质阻断。audit §3 根因 A 的实质要求（阻止泄露）未达。

---

## 2. 评估维度

### 2.1 防时序泄露彻底性

**B > A > C > D**。但这是纯机制维度的排序，**忽略了"防什么"的语义**。

### 2.2 与 bi_trend 根本重设的关系（决定性维度）

memory `phase1-sample-out-conclusion` 三重印证：

| 参数版本 | 样本外 Sharpe | 加权 net/月 |
|---|---|---|
| V13（调参后 HEAD） | -3.178 | -1.157% |
| V5.9（调参前 frozen） | -2.993 | -1.263% |
| V13 + ST 过滤 | -3.305 | -1.175% |

**三个版本样本外全部确定性亏**。memory 结论原文："排除'调参把策略调坏'假设，确认亏损是**策略逻辑本身（OBV+WR+ADX 规则）问题**，非调参失误"→ "bi_trend 需根本性策略重设（非调参/微调）"。

这条结论对 M01 是**釜底抽薪**：

- **方案 B 的核心价值是"让 walk-forward 真的样本外"**——前提是策略本身有 alpha、值得用真样本外验证其泛化性。bi_trend 已经被证伪有 alpha，**花高工程代价把它从"伪样本外"修成"真样本外"，结论不会变**（V5.9 调参前版本已经是某种意义上的"早时点参数"，照样 -2.993）。B 修的是一个**注定要被推倒重来**的框架里的一根梁。
- **方案 A 的价值不同**：它不是为了让 bi_trend 的回测更可信，而是给**未来任何新策略**走 walk-forward 时立一道**流程护栏**——commit 日期晚于 OOS 起始就拒绝跑。这道护栏在 bi_trend 重设后**仍然有效且必要**（重设后的新策略迭代也要 walk-forward 先行，memory How-to-apply 第 4 条明示"后续策略迭代必须先用 walk-forward 样本外验证才谈上线"）。A 是**跨策略复用的基础设施**，B 是**bi_trend 专用的一次性深度修复**。

### 2.3 实施成本 + 风险

A: ~15 行，低风险，纯增量，不碰 import 契约。
B: 高成本 + 高风险（见 §1.B 的 reload/subprocess 硬冲突）。
C: ~3 行，极低风险，但覆盖窄。
D: 0 行，0 风险。

### 2.4 memory 定性下的优先级

memory `phase1-sample-out-conclusion` How-to-apply 优先级：

1. 不接 Kronos/LLM（阶段 2 暂停）
2. **bi_trend 需根本性策略重设** ← 当前主线
3. 禁止任何"策略盈利"对外陈述
4. 后续策略迭代必须 walk-forward 样本外验证先行

M01 是"4"这条规则的**代码层强制**。在"2"（根本重设）完成之前，bi_trend 的任何 walk-forward 回测都是**为已证伪的策略算 PnL**——无论 A/B/C/D 怎么修，算出来的数都不可用。所以 M01 的正确价值定位是：**为重设后的新策略铺路，而非拯救 bi_trend**。

---

## 3. 推荐方案

### 推荐：A + C（组合），不取 B，D 列为 A/C 未实施期的过渡兜底

**一句话**：上 `--strict-timeline`（A）+ dirty 默认 raise（C），作为**跨策略复用的 walk-forward 流程护栏**；**不**做 per-oos-month checkout（B），因为 bi_trend 已被证伪不值得在它身上做框架级深度修复；A/C 实施前 D 作为临时兜底（当前 ml-engineer 实现保留）。

### 理由（按权重）

1. **memory 定性决定 B 不值得**。bi_trend 三重印证样本外确定性亏，根因是策略逻辑本身（OBV+WR+ADX），非参数时序泄露。B 的 per-month checkout 是**为有 alpha 的策略服务的机制**，对一个已证伪策略是沉没成本。audit §3 把 M01 列为"最致命根因"是在**尚未做 V5.9 冻结对照、尚未三重印证之前**的定性；memory 的后续三重印证已把"调参泄露"从"最致命根因"降级为"放大器"——真正的根因是策略逻辑。对 tech-lead 而言，**memory 的实测三重印证 > audit 的代码层推理**（实测是 ground truth，推理是 hypothesis）。

2. **A 是跨策略基础设施，价值延续到重设之后**。bi_trend 推倒重设后，新策略照样要走 walk-forward（memory How-to-apply #4）。`--strict-timeline` 这道护栏在重设后的新策略迭代里**继续生效**，不是 bi_trend 专用的一次性修复。这是"简单优于巧妙"+"记录权衡"——用最小代价（15 行）建一个永久护栏。

3. **A + C 的覆盖面对"bi_trend 重设前"也够用**。重设前任何对 bi_trend 的 walk-forward 回测，本就只是"确认亏损"的诊断性跑批（不是上线决策）——strict exit 逼操作者显式声明 commit，dirty raise 防脏工作区，足以保证诊断结果可追溯、不误导。不需要 B 那种"每月真样本外"的精度，因为重设前的回测结论（亏）已经定了。

4. **B 的工程风险在 bi_trend 当前形态下不可接受**。bi_trend_launch.py 2158 行单文件（audit M15）+ 进程内 DB adapter 全局态 + Python module cache 不级联 reload——在这上面做 per-month 动态加载，出错的概率 > 修对的概率，且错误会静默用错版本（比当前警告更糟）。audit 自己也说性能已是"数小时一轮"，B 的 subprocess 路径会进一步恶化。

### 实施路径

**派回 ml-engineer 实施 A + C**（不在 bi_trend 重设专项里做，理由：A/C 是 walk_forward 工具的护栏，属于"流程基础设施"，与"策略逻辑重设"是两个正交的工作流，分开派单更清晰）。

具体 AC 给 ml-engineer：

- **AC-M01-A**: `walk_forward.py` 加 `--strict-timeline` flag（默认 False 保持兼容）。启用时，`_git_strategy_commit` 返回的 commit 日期 > `args.start` → `sys.exit(2)` 并打印明确错误（"策略 commit 日期 X 晚于样本外起始 Y，参数时序泄露，拒绝跑；若确需用此 commit 回测，去掉 --strict-timeline 但结果不可作样本外结论"）。
- **AC-M01-C**: 工作区 dirty（`strategy_info["dirty"]` True）→ 默认 `sys.exit(2)`（**不需 flag，始终强制**），打印"本地有未提交策略修改，跑样本外无意义，先 commit 或 stash"。理由：dirty 工作区跑样本外在任何情况下都不可信，没有"兼容"的必要。
- **AC-M01-test**: 行为级单测——构造 fake git repo（或 mock subprocess.run 返回不同 commit/date/dirty 组合），验证 (a) clean + commit 日期 ≤ start + strict → 正常跑；(b) clean + commit 日期 > start + strict → exit 2；(c) dirty → exit 2（无论 strict）。**这是对 code-reviewer-ml W-2 的直接回应**（M01 当前只有契约字符串校验，无行为级测试）。
- **AC-M01-ci**: 若有 CI 跑 walk_forward 的入口，加 `--strict-timeline`。若当前无 CI 入口，列 follow-up。

**不派 ml-engineer 做 B**。B 的设计意图（真样本外）记入 bi_trend 重设专项的 follow-up：**仅当重设后的新策略在 V5.9-frozen-style strict 模式下样本外为正**，才考虑投入做 per-month checkout（届时策略值得用更高精度验证）。即在 bi_trend 重设专项 PRD 里列一条"walk-forward 精度升级触发条件"。

### 对 audit §3 根因 A 定性的 tech-lead 复核

audit 把 M01 列为"bi_trend 样本外亏损最致命根因"，tech-lead **部分下调**此定性：

- 在**代码层**，M01 确实是泄露机制（不否定 audit 的代码事实）。
- 在**业务结论层**，memory 的 V5.9 冻结对照（-2.993）证明**即使无 M01 时序泄露**（用调参前参数），bi_trend 样本外照样确定性亏。所以 M01 不是"亏损的决定性根因"，而是"放大亏损的机制 + 让样本外定义失真的流程缺陷"。
- 这一下调**不影响 A/C 的推荐**——A/C 的价值在"流程护栏"不在"拯救 bi_trend"。但下调**直接影响 B 的取舍**（B 不值得）。

---

## 4. 给 code-reviewer-ml 的回应

code-reviewer-ml C-1（critical）的判断 tech-lead **接受**：当前实现"记录了泄露但没阻止泄露"是事实，AC-1 字面满足但实质未达是公正判断。tech-lead 的处置不是"驳回 C-1"，而是"同意补阻断机制，但**选择 A/C 而非 B**，并明确 A/C 的价值定位是跨策略护栏而非 bi_trend 救命"——这与 code-reviewer-ml 在 §6"是否要求升级到方案 A/B 是 tech-lead 决策"的留白一致。

C-1 在 A/C 落地后可降为 warning（残留 follow-up：B 留待 bi_trend 重设后视情况）。

---

## 5. 不写 ADR 的说明

本评估**不**新开 ADR。理由：

- M01 是 walk_forward 工具的**实现层修复**（加 flag + 行为），不是系统级技术选型/架构决策。按 ADR 边界（`.claude/standards/` 与 skill `agf-writing-adr` 的"what NOT to ADR"），实现细节不进 ADR。
- 涉及的"walk-forward 样本外方法论"约束已记录在 `docs/prd/` 阶段 1 PRD + memory，无需 ADR 重复。
- 若 bi_trend 重设专项后续触发"walk-forward 精度升级（B）"且引入新的工具架构（如 subprocess 隔离框架），**届时**才评估是否开 ADR。

---

## 6. 结论速览

| 方案 | 取舍 | 理由 |
|---|---|---|
| A（strict exit） | **取**，派回 ml-engineer | 跨策略护栏，15 行低风险，价值延续到 bi_trend 重设之后 |
| B（per-month checkout） | **不取**，记入重设专项 follow-up | bi_trend 已证伪不值得，工程代价高 + reload/subprocess 风险 |
| C（dirty raise） | **取**，派回 ml-engineer（与 A 同批） | dirty 跑样本外任何情况不可信，~3 行 |
| D（维持现状） | **过渡兜底**，A/C 落地前保留 | A/C 未 merge 前的临时态 |

派回 ml-engineer，AC 见 §3 实施路径三 AC（A / C / 行为级测试）。**不**纳入 bi_trend 重设专项（A/C 是正交的流程基础设施）。

---

*评估结束。本文件只做方案评估与取舍，不改任何源码；A/C 实施由 ml-engineer 按 §3 AC 执行。*
