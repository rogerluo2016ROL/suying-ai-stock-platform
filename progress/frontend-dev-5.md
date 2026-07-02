# progress / frontend-dev-5 — BatchA Signals 6.0/6.1/6.2/6.3

## 状态

**完成（SIT 自跑通过）。** Signals.tsx 四 preview（6.0 detail / 6.1 overview / 6.2 history / 6.3 risk）每 preview 专属 sub-tab 渲染，结构对齐 preview，缺数据 EmptyState，内联 style token 化，tsc 0 错，13 测试（5 unit + 8 SIT）全绿。

worktree：`.wolf/worktrees/frontend-dev-5`（分支 `feat/md-ui-signals-dev5`，基于 HEAD `5c71087a`）。独占 `frontend/src/pages/Signals.tsx`。

## Skills

- `agf-running-sit-tests`（SIT 自跑：tsc + vitest + dev server 模块编译验证）

## SIT 证据

### AC 自验

- [x] **AC① 四 preview 各有专属 sub-tab 渲染**（activeKey(pathname) 切换）：`/signals`→detail / `/signals/overview`→overview / `/signals/history`→history / `/signals/risk`→risk。路由 App.tsx:159-162 已注册。SIT `sub-tab 切换` 测试覆盖四个 tab 逐一点击断言专属内容渲染。
- [x] **AC② tabs/筛选/表格/图表对齐 preview**：
  - 6.0 detail：顶部加 selected-signal verdict 头（对齐 preview 的 Signal Verdict，复用 `op-hint`）+ 触发队列表（filter-bar chips + 风险扫描按钮 + tbl）。
  - 6.1 overview：信号强弱分布 dim-row bar（强买/买入/观察/卖出计数）+ 数据隔离 side rail。
  - 6.2 history：新增 **30 日评分趋势折线图**（ReactECharts，对齐 preview 的 history-chart 标志元素，含强买/买入/持有阈值虚线）+ 命中率回看表。
  - 6.3 risk：op-hint risk_score + **4 项检查卡网格**（对齐 preview 的审计/公告/ST退市/业绩 4 卡，映射自 `tradeApi.getRiskVerdicts` 的 checks）+ 阻断项 + 风控结论 side rail。
- [x] **AC③ 缺数据 EmptyState**：每 preview 的数据获取路径（getLive / getHistory / analyzeCode+getRiskVerdicts）catch + 空 → EmptyState（"暂无实时信号" / "暂无历史信号" / "暂无可扫描信号"）。SIT 三条 EmptyState 测试覆盖。
- [x] **AC④ 内联 style token 化**：echarts option 全部走 `lightTokens`（accent/up/down/warn/muted/border），不硬编码裸色值；6.3 检查卡 / 6.0 verdict 复用 `op-hint`、新增 CSS 类（`.col-stack` `.risk-check-grid` `.risk-check-card` `.rc-*`）全部用 CSS 变量（`var(--up)` / `var(--down)` / `var(--warn)` / `var(--surface)` / `var(--border)` / `var(--radius)`）。保持浅色，A股红涨绿跌走 `.up`/`.down` + `lightTokens.up`（红）/`down`（绿）。
- [x] **AC⑤ tsc 0 错 + vitest**：见质量门。
- [x] **AC⑥ progress SIT 段**：本段。

### tsc

```
$ cd frontend && npx tsc -b --noEmit
TSC_EXIT: 0
```

### vitest（我的 scope）

```
$ cd frontend && npx vitest run src/__tests__/Signals.test.tsx tests/sit/signals-preview.test.tsx
Test Files  2 passed (2)
     Tests  13 passed (13)   // 5 unit (Signals.test.tsx) + 8 SIT (signals-preview.test.tsx)

$ cd frontend && npx vitest run src/__tests__/Signals.test.tsx tests/sit/   // 含既有 SIT
Test Files  4 passed (4)
     Tests  22 passed (22)
```

新增 SIT 文件 `frontend/tests/sit/signals-preview.test.tsx`（8 用例）：
1. `6.0 detail: 渲染触发队列与选中信号 verdict，缺数据走 EmptyState` — 断言 verdict `.pos` 强度 + 列点击切换选中。
2. `6.0 detail: getLive 返回空时不展示演示股票，走 EmptyState` — 无 hardcode fallback。
3. `6.1 overview: 渲染信号强弱分布与计数`。
4. `6.2 history: 趋势图 + 命中回看表，调 getHistory 正确参数` — 断言 `信号评分趋势` 标题 + `getHistory` 调用 + 命中行。
5. `6.2 history: getHistory 返回空时走 EmptyState`。
6. `6.3 risk: 调 analyzeCode + getRiskVerdicts，渲染 4 项检查卡` — 断言 `analyzeCode('300750')` + `getRiskVerdicts({code:'300750',page_size:5})` + 四检查卡（审计/公告/ST退市/业绩）+ warn 徽标。
7. `6.3 risk: 无实时信号时不触发风险扫描` — `analyzeCode` / `getRiskVerdicts` 均 not called。
8. `sub-tab 切换：detail → overview → history → risk 各渲染专属内容`。

### dev server 模块编译验证

```
$ (npm run dev &) ; Vite v6.4.3 ready in 94ms → http://localhost:3000/
$ curl /src/pages/Signals.tsx → HTTP 200（Vite 转换成功，无 transform error）
$ curl /src/styles/suying-app.css → HTTP 200，含 risk-check-card / col-stack 新类
$ /tmp/dev5-signals.log 无 runtime error
```

> 截图未取：Signals 页需登录态 + 后端服务（auth :9001 / signal-service :8004 / trade-service :8006），当前 worktree 环境无运行中后端。已用 tsc + vitest（含组件 + API mock + state 单边集成）+ Vite 模块/CSS 编译 + dev server 无错启动作为 SIT 证据；reviewer audit 此段。

### 改动文件

- `frontend/src/pages/Signals.tsx`（改：6.0 verdict 头 + 6.2 趋势图 + 6.3 四检查卡 + token 化）
- `frontend/src/styles/suying-app.css`（改：新增 `.col-stack` `.risk-check-grid` `.risk-check-card` `.rc-*` `.signal-queue-filter`，全 token 化）
- `frontend/src/__tests__/Signals.test.tsx`（改：mock 补 `tradeApi.getRiskVerdicts` + 历史/风险断言加强）
- `frontend/tests/sit/signals-preview.test.tsx`（新：8 用例 SIT）

## 质量门

| 项 | 结果 |
|---|---|
| vitest（Signals unit + SIT） | 22 passed / 22 |
| tsc | 0 错（`tsc -b --noEmit` TSC_EXIT 0） |
| lint | 未单独跑（项目无 ESLint 强制门；tsc + vitest 覆盖） |
| dev server | Vite v6.4.3 启动无错，Signals.tsx + suying-app.css 模块编译 HTTP 200 |

**全量前端回归说明**：`npx vitest run`（全量 319 测试）有 70 failed，全部集中在 `src/__tests__/PrototypeRoutes.test.tsx`——其 mock 缺 `marketApi.getIndexQuotes()`（App.tsx:416 引用）。**该文件与本 task 无关**（`git diff --name-only HEAD` 确认我未触碰 `PrototypeRoutes.test.tsx` / `App.tsx`），是 M0 HEAD `5c71087a` 的预存缺口（dev-1 dashboard 工作或 M0 引入 marketApi 调用但路由覆盖测试 mock 未同步）。我的 scope（Signals 相关 + SIT 目录）22/22 全绿。

## 下一步

回 team-lead。四 preview 落地完成，等待 code-reviewer SIT Audit。`PrototypeRoutes` mock 缺口建议单列（非本 task scope）。
