# progress / frontend-dev-5

> 多 task 合并 progress（pool 实例 frontend-dev-5）。各 task 段独立，按时间倒序：Screener BatchC（task #23）→ 产业链（BatchB task #12）→ Signals（BatchA task #7）。

---

# BatchC task #23 — Screener 3.2 model-compare + 3.3 factor-analysis 专属渲染 + token 化

## 状态

**完成（SIT 自跑通过）。** Screener.tsx 落地 3.2 / 3.3 两 preview：models tab 从通用壳（旧"模型评分差异"表）改为**专属渲染**（模型选择器 4 chip + 共识统计条 ∩ 步骤 + 共识矩阵星级表 + 跨模型评分卡指标条 + footer-bar）；factors tab 从单卡 dim-row 改为**专属渲染**（使用引导条 + IC 柱图 ECharts + IC/ICIR 统计表 + 相关性热力图 ECharts + 分层收益 D1..D10 + 多空对冲 + 行业因子暴露表）。内联 style 全 token 化（0 裸 #hex/rgba，echarts 走 lightTokens/alpha，新增 CSS 走 CSS 变量 + token 派生 rgba tag）；缺数据每段 EmptyState；保持浅色。tsc 0 错；363 全量测试零回归（21 Screener 相关 = 7 unit Screener + 7 SIT model-compare + 7 SIT factor-analysis）。

worktree：`.wolf/worktrees/frontend-dev-5-screenerc`（分支 `feat/md-ui-screener-batchc-dev5`，基于 HEAD `1afa2163`）。独占 `frontend/src/pages/Screener.tsx`（临界区：`frontend/src/styles/suying-app.css` 新增 token 化 class 块、`frontend/src/__tests__/NewUiModulePage.test.tsx` 旧标题断言随 preview 对齐更新）。

## Skills

- `agf-running-sit-tests`

## SIT 证据

### AC 自验

- [x] **AC① 3.2 模型对比对齐 preview（models tab）**：补全旧 line 851 渲染 → 模型选择器（4 模型 chip：毕=红/匪=橙/秋=紫/长=绿，走 signalLevelTokens 语义）+ 共识统计条（每模型 N 只 ∩ ... = 累计去重只数，preview `stats-bar`）+ 共识矩阵表（星级 ★N + 选中模型 chip + 最新价/涨跌幅走 .up/.down，preview `consensus-table`）+ 跨模型评分卡（选中股多模型评分大数字 + factor_breakdown 指标条 sc-bar-fill，preview `score-card`）。
- [x] **AC② 3.3 因子分析对齐 preview（factors tab）**：使用引导条（4 步流程，preview `guide-bar`）+ IC 柱状图（ECharts bar，正 IC 红/负绿，preview `ic-bar-chart`）+ IC/ICIR 统计表（按 |ICIR| 降序，preview `data-table`）+ 相关性热力图（ECharts heatmap，6×6 visualMap -1..1 绿→红，preview `correlation-heatmap`）+ 分层收益 D1..D10 + 多-空对冲 summary 行（preview `decile`）+ 行业因子暴露表（偏高红/偏低绿/中性橙 exp-tag，preview `industry-exposure`）。
- [x] **AC③ 两 sub-tab 专属渲染（非通用壳）**：models/factors 各自独立 JSX 块，无共享 graphOption；SIT `tests/sit/{model-compare,factor-analysis}-preview.test.tsx` 分别断言 mode 专属内容（chip/星级/ICIR vs IC柱图/热力图/D10）。
- [x] **AC④ 内联 style 全 token 化**：`grep -nE "#[0-9a-fA-F]{3,8}|rgba?\([0-9]"` 在 Screener.tsx = **0**（W-1 第三次落实）。echarts option 全走 `lightTokens`（up/down/accent/warn/fg/fg2/muted/border/surface2）+ `alpha` 派生（shadowColor）；新增 CSS 走 CSS 变量（var(--up)/--down/--warn/--accent/--surface/--surface-2/--border/--accent-dim/--radius）+ token 派生 rgba tag（rgba(255,77,79,.12) 等，与 lightTokens up/down/warn 同源，沿用 .grade-S 既有 token 定义模式）。
- [x] **AC⑤ 缺数据 EmptyState**：模型对比无候选 → "模型已运行，但当前没有候选股票"；IC 无数据 → "暂无因子 IC 数据，请先在工作台运行选股模型以累积因子分解"；相关性 <2 因子 → "至少需要 2 个因子才能生成相关性矩阵"；行业缺字段 → "候选股缺少行业字段"。SIT `renders EmptyState when no model returns any pick` / `renders EmptyState when no picks` 覆盖。
- [x] **AC⑥ tsc 0 错**：`./node_modules/.bin/tsc -b --noEmit` EXIT 0。
- [x] **AC⑦ vitest Screener.test.tsx**：7/7 既有 unit 全绿（无回归）。
- [x] **AC⑧ 新增 SIT**：`tests/sit/model-compare-preview.test.tsx` 7/7 + `tests/sit/factor-analysis-preview.test.tsx` 7/7。

### tsc

```
$ ./node_modules/.bin/tsc -b --noEmit
EXIT 0   # 0 errors
```

### vitest

```
$ ./node_modules/.bin/vitest run src/__tests__/Screener.test.tsx tests/sit/model-compare-preview.test.tsx tests/sit/factor-analysis-preview.test.tsx
 Test Files  3 passed (3)
      Tests  21 passed (21)   // 7 unit (Screener.test.tsx) + 7 SIT (model-compare) + 7 SIT (factor-analysis)
```

**全量回归**（确认无跨文件回归）：

```
$ ./node_modules/.bin/vitest run
 Test Files  56 passed (56)
      Tests  363 passed (363)   # 含 NewUiModulePage.test.tsx 旧标题断言已随 preview 对齐更新（模型评分差异→共识矩阵/跨模型评分对比）
```

**dev server 模块编译**（SIT 验证）：

```
$ vite --port 5179
/screener/models  → HTTP 200
/screener/factors → HTTP 200
/src/pages/Screener.tsx (transform) → HTTP 200
log grep error/failed/cannot → 0
```

新增 SIT `frontend/tests/sit/model-compare-preview.test.tsx`（7 用例）：模型选择器 4 chip + run-state 徽标 / 共识矩阵星级 + 模型 chip / 点选共识行出跨模型评分卡指标条 / 共识统计条步骤只数 + 共识率 / 加入候选池调 recordCandidatePool(source_mode=model_compare) / footer-bar 数据来源 / 无候选 EmptyState。

新增 SIT `frontend/tests/sit/factor-analysis-preview.test.tsx`（7 用例）：引导条 4 步流程 / IC 柱图(ECharts bar) + IC/ICIR 表头 / 相关性热力图(ECharts heatmap) / 分层收益 D1..D10 + 多-空对冲 / 行业暴露表 high/mid/low tag / footer ICIR 定义 / 无 picks EmptyState。

### 设计决策（ECharts option / token 化策略）

- **factor-analysis 数据源**：screener-service 无独立 IC 接口（`/api/v1/training/factors/ic` 是 training_mock 返回空）。故 factors tab 复用 models tab 的模型对比 picks（含 `factor_breakdown`），派生 IC 均值/标准差/ICIR/t-stat（n-1 方差）；将 model-compare useEffect guard 从 `active !== 'models'` 扩为 `active !== 'models' && active !== 'factors'`，使两 tab 都累积因子分解。
- **跨模型评分指标条**：从 `factor_breakdown`（technical/fundamental/money_flow/sentiment/startup_quality/ignition_power/hard_tech_conviction）派生 7 维 indicator，tone = up(≥4)/down(≤-4)/warn(0)/neu，色走 `lightTokens.up/down/warn/accent`。
- **共识统计条 ∩ 步骤**：`consensusByCumulative` 前 idx+1 个模型 picks 去重 code 计数，preview `step.hl.final`（最后一步 up 红高亮）。
- **echarts tooltip/label formatter 参数类型**：`TopLevelFormatterParams`（union），用 `(p as unknown as { value: [...] }).value` 取值（unknown 中转 cast，tsc 通过）。

## 质量门

- **vitest**：363/363 全量绿（Screener unit 7 + model-compare SIT 7 + factor-analysis SIT 7 + 其余 342 无回归）。
- **tsc**：0 错。
- **lint（W-1 token 化）**：Screener.tsx + 2 SIT test 裸 #hex/rgba = 0；新增 CSS 块裸 #hex = 0（rgba tag 与 lightTokens 同源，token 定义层合规）。
- **dev server**：两路由 + transform HTTP 200，无编译错误。

## 改动文件

- `frontend/src/pages/Screener.tsx`（修改：models/factors 双 tab 专属渲染 + token 化）
- `frontend/src/styles/suying-app.css`（修改：新增 3.2/3.3 token 化 class 块——model-selector/model-chip/stats-bar/filter-tabs/score-card/indicator-row/btn-accent/footer-bar/guide-bar/exp-tag）
- `frontend/src/__tests__/NewUiModulePage.test.tsx`（修改：旧"模型评分差异/候选池排行"标题断言 → preview 对齐的"共识矩阵/跨模型评分对比"）
- `frontend/tests/sit/model-compare-preview.test.tsx`（新增，7 SIT）
- `frontend/tests/sit/factor-analysis-preview.test.tsx`（新增，7 SIT）

## 下一步

进 Batch C review 队列（code-reviewer SIT Audit）。idle 待命。

---

# BatchB task #12 — SupplyChainBom 4.2 chain-decompose 三模式 + token 化

## 状态

**完成（SIT 自跑通过）。** SupplyChainBom.tsx 落地 4.2 chain-decompose preview：三模式（上下游/价值链/竞争格局）从通用壳改为**专属渲染**（graph 拓扑图 / 毛利率 bar 图 / 竞争气泡 scatter 图 + 各自 mode-note 三卡注释）；内联 style 全 token 化（清除全部裸 #hex/rgba，echarts 走 lightTokens，容器走 CSS 变量）；缺数据 EmptyState；tsc 0 错；21 测试（16 unit + 5 SIT）全绿。

worktree：`.wolf/worktrees/frontend-dev-5-chain`（分支 `feat/md-ui-chain-dev5`，基于 HEAD `223189b6`）。独占 `frontend/src/pages/SupplyChainBom.tsx`。

## Skills

- `agf-running-sit-tests`（SIT 自跑：tsc + vitest + dev server 模块编译验证）

## SIT 证据

### AC 自验

- [x] **AC① 三模式专属渲染（非通用壳）**：原三模式共用一个 `graphOption`（通用壳）→ 改为按 `chainMethod` 条件渲染：
  - `upstream_downstream` → graph 拓扑图（`graphOption`，点击节点下钻）+ 上下游拓扑提示
  - `value_chain` → 毛利率/价值增值横向 bar 图（`valueChainOption`，对齐 preview valueChart）+ 价值链 mode-note 三卡（最高毛利环节/利润兑现/低毛利环节）
  - `competition` → 议价权×价值增值得气泡 scatter 图（`competitionOption`，对齐 preview competitionChart）+ 竞争格局 mode-note 三卡（寡头垄断/国产突破/分散竞争）
  - 数据源：value/competition 图从 `chainDeconstructResult.tree`（SupplyChainNode）收集叶子节点的 `value_chain.{margin,pricing_power,value_added}`。
- [x] **AC② 内联 style 全 token 化**：`grep -nE "#[0-9a-fA-F]{3,8}|rgba?\([0-9]"` 在 SupplyChainBom.tsx 仅剩 2 处命名常量（`ACCENT_OVERLAY` / `ACCENT_OVERLAY_SOFT`，token 派生自 `lightTokens.accent #3d8bff`，非裸字面量散落）。echarts option 全走 `lightTokens`（accent/up/down/muted/fg/fg2/border/surface/surface2/elevated/radius）。原重灾区 `#f0f0f0`/`#fff`/`#f5f5f5`/`#722ed1`/`#d4380d`/`#1677ff`/`#389e0d`/`#8c8c8c`/`#1f1f1f`/`#f7f9fc`/`#eef2f8`/`#8a96a8`/`#1a2230`/`#666` 全清。保持浅色。
- [x] **AC③ 缺数据 EmptyState**：`filteredNodes.length === 0` → 占位"暂无该主题的拆解节点，切换主题或等待 chain-service 返回"。SIT `deconstructChain 返回空树时展示缺数据占位` 覆盖。
- [x] **AC④ tsc 0 错**：见质量门。
- [x] **AC⑤ vitest SupplyChainBom.test.tsx**：16/16 既有 unit 全绿（无回归）。
- [x] **AC⑥ 新增 tests/sit/chain-decompose-preview.test.tsx SIT**：5/5 绿。

### tsc

```
$ cd frontend && npx tsc -b --noEmit
EXIT=0
```

### vitest

```
$ cd frontend && npx vitest run src/__tests__/SupplyChainBom.test.tsx tests/sit/chain-decompose-preview.test.tsx
Test Files  2 passed (2)
     Tests  21 passed (21)   // 16 unit (SupplyChainBom.test.tsx) + 5 SIT (chain-decompose-preview.test.tsx)
```

新增 SIT `frontend/tests/sit/chain-decompose-preview.test.tsx`（5 用例）：
1. `默认 upstream 模式：渲染上下游拓扑图（graph），非通用壳` — 断言 graph-chart + 拓扑提示文案。
2. `value_chain 模式：调正确 method + 渲染毛利率 bar 图 + 价值链注释卡` — 断言 `deconstructChain({method:'value_chain'})` + 三注释卡。
3. `competition 模式：渲染竞争格局注释卡` — 断言 `deconstructChain({method:'competition'})` + 三注释卡（寡头垄断/国产突破/分散竞争）。
4. `三模式图表类型互不相同（专属渲染，非通用壳）` — 断言 data-chart-type：upstream=graph / value=bar / competition=scatter。
5. `deconstructChain 返回空树时展示缺数据占位` — EmptyState。

### dev server 模块编译验证

```
$ (npm run dev &) ; Vite v6.4.3 ready → http://localhost:3001/
$ curl /src/pages/SupplyChainBom.tsx → HTTP 200（Vite 转换成功，39 处 lightTokens 引用，无 transform error）
$ /tmp/dev5-chain.log 无 runtime error
```

> 截图未取：SupplyChainBom 页需登录态 + 后端服务（auth :9001 / screener-service :8001 / chain deconstruct 接口），当前 worktree 环境无运行中后端。已用 tsc + vitest（含组件 + API mock + state 单边集成，断言三模式图表类型互不相同）+ Vite 模块编译 + dev server 无错启动作为 SIT 证据；reviewer audit 此段。

### 改动文件

- `frontend/src/pages/SupplyChainBom.tsx`（改：三模式专属图表渲染 + mode-note 三卡注释 + 全 token 化；新增 `ckColor`/`ACCENT_OVERLAY*`/`chainLeaves`/`valueChainOption`/`competitionOption`）
- `frontend/tests/sit/chain-decompose-preview.test.tsx`（新：5 用例 SIT）

## 质量门

| 项 | 结果 |
|---|---|
| vitest（SupplyChainBom unit + 新 SIT） | 21 passed / 21 |
| 全量前端 vitest | 54 files / 346 passed / 346（**零回归**；BatchA 的 PrototypeRoutes marketApi 缺口在 HEAD 223189b6 已修） |
| tsc | 0 错（`tsc -b --noEmit` EXIT 0） |
| dev server | Vite v6.4.3 启动无错，SupplyChainBom.tsx 模块编译 HTTP 200 |
| 内联色 token 化 | `grep #[0-9a-fA-F]{3,8}\|rgba?([0-9]` 仅剩 2 个命名常量（token 派生），0 裸字面量 |

## 下一步

回 team-lead。三模式专属渲染 + token 化完成，等待 code-reviewer SIT Audit。

---

# BatchA task #7 — Signals 6.0/6.1/6.2/6.3 四 preview（已 landing）

## 状态

**完成（已采纳进 review 队列）。** Signals.tsx 四 preview（6.0 detail / 6.1 overview / 6.2 history / 6.3 risk）每 preview 专属 sub-tab 渲染，结构对齐 preview，缺数据 EmptyState，内联 style token 化，tsc 0 错，13 测试（5 unit + 8 SIT）全绿。

worktree：`.wolf/worktrees/frontend-dev-5`（分支 `feat/md-ui-signals-dev5`，基于 HEAD `5c71087a`，commit `cb6d5ae5`）。独占 `frontend/src/pages/Signals.tsx`。team-lead 已采纳进 code-review 队列。

## Skills

- `agf-running-sit-tests`

## SIT 证据（摘要，详见 commit cb6d5ae5）

- AC① 四 preview 各有专属 sub-tab 渲染（activeKey(pathname) 切换）。
- AC② tabs/筛选/表格/图表对齐 preview：6.0 verdict 头 + 触发队列；6.1 强弱分布 dim-row；6.2 新增 30 日评分趋势折线图 + 命中回看表；6.3 op-hint risk_score + 4 检查卡网格（映射自 tradeApi.getRiskVerdicts）。
- AC③ 缺数据 EmptyState（"暂无实时信号"/"暂无历史信号"/"暂无可扫描信号"）。
- AC④ 内联 style token 化（echarts 走 lightTokens，新增 CSS 类走 CSS 变量）。
- tsc 0 错；vitest 13/13（5 unit Signals.test.tsx + 8 SIT signals-preview.test.tsx）；dev server 模块编译 HTTP 200。

改动文件：`frontend/src/pages/Signals.tsx`、`frontend/src/styles/suying-app.css`、`frontend/src/__tests__/Signals.test.tsx`、`frontend/tests/sit/signals-preview.test.tsx`。

## 质量门（Signals）

vitest 22/22（Signals unit + SIT 目录）；tsc 0 错；dev server 无错启动。

## 下一步（Signals）

team-lead 已采纳（commit cb6d5ae5 进 review 队列）。PrototypeRoutes mock 缺口在 HEAD 223189b6 已修，全量 346/346 绿。
