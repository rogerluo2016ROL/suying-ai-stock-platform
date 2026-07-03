# QA Engineer Progress — 测试覆盖债务审计

- **Date**: 2026-06-12
- **Tester**: qa-engineer (deepseek-v4-pro)
- **Status**: 审计完成 — 产出未覆盖清单

---

## 一、现有 E2E/UAT 覆盖汇总

| Feature | E2E 通过 | UAT 通过 | 关联服务 | Verdict |
|---------|:---:|:---:|------|-----|
| auth-rbac | 12/12 | 8/8 (4 P0 pass^2) | backend :9001, frontend :3000 | Promote → Approve |
| auto-trading | 10/10 | 7/7 | strategy-service :8003 | Promote → Approve |
| diagnosis | 6/6 | 8/8 | diagnosis-service :8009 | Promote → Approve |
| live-trading | 10/10 | 8/8 | trade-service :8006 | Promote → Approve |
| model-training | 5/7 + 1 cond | 8/8 | training-service :8008 | Promote → Approve |

**已覆盖服务**：backend (auth)、strategy-service、diagnosis-service、trade-service、training-service（5/12）

---

## 二、缺少 E2E/UAT 的服务

| 服务 | 端口 | 功能 | 风险等级 | 说明 |
|------|:---:|------|:---:|------|
| **screener-service** | 8001 | 6 模式选股 + 多因子排序 | **HIGH** | 全角色使用的核心功能（选股/排序），无任何 E2E/UAT。PRD auth-rbac 权限矩阵中选股是所有 4 角色共用入口 |
| **prediction-service** | 8002 | Kronos 30 日 K 线预测 | **HIGH** | 全角色使用，AI 核心能力。无独立 E2E/UAT（diagnosis 测试中仅作为下游依赖被间接覆盖，未测预测服务本身的端点） |
| **signal-service** | 8004 | 50 维综合交易信号 | **MEDIUM** | 被 strategy-service 依赖（Mock），无独立 E2E/UAT。自动交易 E2E 使用 Mock 代替真实信号服务 |
| **backtest-service** | 8007 | 历史回测 + IC/ICIR 分析 | **MEDIUM** | 3 角色使用（admin/internal/external），无 E2E/UAT。选股→回测链路未端到端验证 |
| **alert-service** | 8005 | 预警规则 + 实时提醒 | **MEDIUM** | 全角色使用，无 E2E/UAT |
| **data-service** | N/A | 数据管道（采集/同步/物化视图） | **CRITICAL** | **当前 active feature** — PRD `data-pipeline-refactor-2026-06-12.md` 刚 Approved，8 AC 全未测试 |
| **api-gateway** | 8080 | 统一 API 网关 | LOW | 纯代理层，通过各服务测试间接覆盖 |

---

## 三、data-pipeline-refactor AC 未覆盖清单（当前 active feature）

> PRD: `docs/prd/data-pipeline-refactor-2026-06-12.md`，ADR: `docs/adr/006-data-pipeline.md`（6 项决策已落盘）
> 8 AC，0/8 通过。E2E 和 UAT 均尚未执行。

| AC | Priority | 描述 | 状态 |
|----|:---:|------|:---:|
| AC-1 | P0 | `POST /api/v1/data/sync/post_market?date=` 返回后 30s 内 PG daily_kline 有数据 | 未测试 |
| AC-2 | P0 | PG 写入失败不影响 SQLite，scheduler status 含失败计数 | 未测试 |
| AC-3 | P0 | 移除 pg_sync 任务，status jobs 不含 pg_sync | 未测试 |
| AC-4 | P1 | `POST /api/v1/data/sync/stocks` 后 PG stocks >= 4000 行 | 未测试 |
| AC-5 | P1 | 物化视图刷新失败时 status 含失败 view 名 + 原因 | 未测试 |
| AC-6 | P1 | 盘中 rt_min 执行后 PG stk_mins 60s 内可查最新 trade_time | 未测试 |
| AC-7 | P2 | `sync_daily_to_pg()` 函数从 pg_writer.py 移除（subprocess 链路废弃） | 未测试 |
| AC-8 | P2 | status 每个 job 含 pg_write_status 字段（ok/partial/fail/skipped） | 未测试 |

**ADR-006 决策覆盖缺口**：

| 决策 | 验证项 | QA 覆盖 |
|------|------|:---:|
| 决策 1: PG-first 写入顺序 | PG 先写成功 → SQLite 后写（失败仅 WARN） | 未覆盖 |
| 决策 2: 全 P0+P1 表 upsert 直写 | 8 张表幂等写入验证 | 未覆盖 |
| 决策 3: 消除 subprocess 桥 | pg_sync job 移除 + sync_to_pg.py LEGACY 标记 | AC-3/AC-7 部分覆盖 |
| 决策 4: stocks 同步 | stock_basic → PG + SQLite 双写 | AC-4 部分覆盖 |
| 决策 5: 物化视图 | 3 现存 + 1 新增 mv_daily_composite_ranking | 未覆盖 |
| 决策 6: 错误处理 | 3 次退避重试 + 数据量门禁 + PG 连接失败降级 | 未覆盖 |

---

## 四、整体测试债务评估

### 4.1 按服务统计

| 类别 | 数量 |
|------|:---:|
| 总微服务数 | 12 |
| 有完整 E2E+UAT | 5 |
| 部分覆盖（仅策略框架） | 0 |
| 完全无覆盖 | 7 |
| E2E/UAT 覆盖率 | **42%** (5/12) |

### 4.2 按 PRD 统计

| PRD | E2E | UAT | 状态 |
|-----|:---:|:---:|------|
| auth-rbac | Y | Y | 完成 |
| auto-trading | Y | Y | 完成 |
| live-trading | Y | Y | 完成 |
| model-training | Y | Y | 完成 |
| diagnosis | Y | Y | 完成 |
| **data-pipeline-refactor** | **N** | **N** | **当前 active，待 E2E+UAT** |

### 4.3 风险排序

1. **CRITICAL — data-pipeline-refactor**: 当前 active feature，8 AC 未测。数据管道是所有下游服务的基石，失败影响面全平台。
2. **HIGH — screener-service + prediction-service**: 选股和预测是用户核心功能，无独立 E2E/UAT 意味着回归靠手工。
3. **MEDIUM — signal-service + backtest-service + alert-service**: 被其他 feature 间接引用但未独立验证。

---

## 五、推荐的测试执行顺序

1. **data-pipeline-refactor** E2E + UAT（当前 active feature，最高优先）
2. **screener-service** E2E + UAT（全角色高频使用）
3. **prediction-service** E2E + UAT（AI 核心能力，独立端点未验证）
4. **signal-service** E2E + UAT（被 auto-trading 依赖，Mock 无法替代真实集成）
5. **backtest-service** E2E + UAT（回测→选股→交易闭环关键节点）
6. **alert-service** E2E + UAT（实时通知链路未验证）

---

## 六、下一阶段

- data-pipeline-refactor 需 code-review (含 SIT Audit) 通过后进入 E2E
- E2E 通过后进入 UAT
- 其他未覆盖服务建议按风险排序逐步补齐，至少完成 HIGH 级别服务的 E2E

---

## 质量门

- [x] 所有 QA 报告已审核
- [x] 服务覆盖率统计完整
- [x] PRD AC 逐条对账
- [x] ADR 决策覆盖评估
- [x] 风险排序清晰
- [x] 未覆盖清单可操作

---

## ADR-013 E2E + UAT — 2026-06-22

- **Stage**: E2E + UAT 合段（含 deploy-engineer 冒烟尾部）
- **Branch / commit**: feature/suying-ai-stock-platform @ 0ba2a3e
- **Environment**: UAT 隔离栈 `uat-adr013` (PG 16432 / API-GW 18080 / 10 services 18001-18009/19001/18080)
- **Report**: `docs/reviews/adr-013-e2e-uat-report-2026-06-22.md`

### AC 总览 (10 项)

| AC | Priority | Verdict | 备注 |
|----|----------|---------|------|
| AC-1 health × 10 | P0 | ❌ Fail | backend 19001 restart-loop (exit 3) |
| AC-2 data-service 宿主进程 | P1 | ✅ Pass | UAT 端口 18010 启动成功 |
| AC-3 cb_sync + change_pct 100% 非 NULL | P0 | ✅ Pass^2 (2/2) | 3015 行，change_pct fill rate 100.00% |
| AC-4 登录链路 | P0 | ⚠️ Blocked | backend 不可达 |
| AC-5 端到端 happy path | P0 | ⚠️ Blocked | 依赖 AC-4 + 缺基础数据 |
| AC-6 ths_daily fallback 消除 | P1 | ✅ Pass | signal/screener 日志无 fallback 警告 |
| AC-7 抽 3-5 股 | P1 | ⚠️ Blocked | 依赖 AC-4 |
| AC-8 validator warnings=0 | P0 | ✅ Pass^2 (2/2) | checked 47 tables, 0 warn / 0 err |
| AC-9 合并报告输出 | P1 | ✅ Pass | 本报告 |
| AC-10 verdict 判定 | P0 | ❌ Block | 决策树推出 |

**Summary**: 4 pass / 0 fail / 6 blocked (其中 1 P0 Fail, 3 P0 Blocked)

### 关键发现

1. **ADR-013 主线核心验证 PASS**：`ths_daily.change_pct` 列 100% 非 NULL（3015/3015 rows），sync_ths_daily 写入成功，validator 0 warnings，下游 fallback 警告消除。**ADR-013 schema 对齐目标本身已达成**。

2. **P0 阻塞 (DEF-1 Critical)**：UAT backend Docker 镜像缺少 Alembic 008-011 migrations。`uat-adr013-deploy.sh` retag 了旧的 `suying-uat-backend:latest` 镜像而非从当前代码 rebuild，导致 backend 容器启动时执行 `alembic upgrade head` 报 `Can't locate revision '011'`，exit 3 后被 compose `restart: unless-stopped` 持续拉起。

3. **DEF-2 High**：UAT PG 基础数据未填充（stocks=0, daily_kline=0），导致下游业务接口（选股/诊断/信号）即使有 auth 也不可用。

### Hand-off

立即升 PL，**不自行 hack 修复**（遵守 task §7 + iron rule #7）。


---

## ADR-013 E2E + UAT — Re-run Round 2 — 2026-06-22

**Trigger**: deploy-engineer + dev 修复 P0 阻塞后（rebuild backend + alembic 001-007 + stamp 011 + restart）PL 重派 Task #6。

### Round 2 AC 总览

| AC | P | Round 1 | Round 2 | pass^2 |
|----|---|---------|---------|--------|
| AC-1 health × 10 | P0 | ❌ Fail | ✅ Pass | 2/2 |
| AC-3 change_pct | P0 | ✅ | ✅ | 2/2 |
| AC-4 登录 | P0 | ⚠️ Blocked | ✅ Pass | 2/2 |
| AC-5 happy path | P0 | ⚠️ Blocked | ⚠️ Conditional | — |
| AC-8 validator | P0 | ✅ | ✅ | 2/2 |
| AC-10 verdict | P0 | ❌ | ⚠️ Conditional | — |

**Round 2 final**: 8 Pass / 0 Fail / 2 Conditional, P0 pass^2 = 4/4

### Verdict

⚠️ **Conditional Promote** — ADR-013 schema 对齐主线完整达成，可 merge。

### 新发现 (round 2 only)

- **DEF-3 Medium**: api-gateway:18080 路由到 `localhost:9001` 错（容器内寻址），auth 走 gateway 失败；绕过直连 backend 19001 OK
- **DEF-4 Medium**: docker-compose.yml 业务微服务缺 `JWT_SECRET_KEY` env，跨服务 JWT 验签用 default secret 失败

两者均 **pre-existing 配置 bug, 与 ADR-013 无关**，建议单开 follow-up issue。

---

## 行情决策板块 E2E/UAT 策略准备 — 2026-07-02

**状态**: 策略就绪（待执行） — 等 deploy + backend + frontend SendMessage 通知修完后开测
**Skills（执行阶段）**: agf-writing-qa-report（写 E2E/UAT 报告）, agf-writing-github-issue（P0/P1 建 issue）
**Tester**: qa-engineer
**Scope**: 行情决策板块 6 主路由 + 23 sub-tab preview（用户明确四点要求 → 25 条 AC）

### 1. 任务背景（PL 审计结论）

前端"无法使用"根因 = 运行时环境混乱 + 部分 API 故障，非代码逻辑本身：
- 三套 docker 残留 + vite 残留实例并发，端口/proxy 指向错
- 数据停昨天（freshness 不达标）
- 部分 API 502 / 404 / timeout

deploy / backend / frontend 三个角色正在修。本阶段**只准备策略框架 + AC 清单，不执行**；修完后用 chrome-devtools MCP 真机点遍执行。

### 2. 测试目标与入口

| 项 | 值 | 来源 |
|---|---|---|
| 主路径 | 共享 UAT 栈 | deploy 报告 `docs/deploy/<feature>-uat-2026-07-02.md`（待 deploy 提供 URL） |
| 前端入口 | `http://localhost:3000` | 与 deploy/frontend 协调确认的唯一实例（铁律：开测前先确认无 vite/docker 残留实例抢端口） |
| 浏览器自动化 | chrome-devtools MCP | navigate_page / take_snapshot / click / take_screenshot |
| 证据 SSOT | 用例文档 + 报告 | E2E: `docs/qa/market-decision-e2e-2026-07-02.md`；UAT: `docs/qa/market-decision-uat-2026-07-02.md` |

### 3. 范围矩阵（6 主路由 × 23 sub-tab）

| # | 主路由 | 路径 | 组件 | sub-tab preview（23） | 数据/API owner |
|---|---|---|---|---|---|
| 1 | 智能看板 | `/` | `Dashboard` | 情绪(1.1)/竞价(1.2)/信号总览(1.3)/自选(1.4) = 4 | signal-service + screener `/screener/market/index-quotes` |
| 2 | 开盘决策 | `/open-decision` | `OpenDecision` | 决策总览/竞价分析/信号扫描/候选池/执行监控 = 5 | screener + signal + strategy + trade |
| 3 | 智能选股 | `/screener` | `Screener` | 工作台/模型对比/因子分析 = 3 | screener-service `/screener/run`、`/screener/modes` |
| 4 | 产业链拆解 | `/supply-chain-bom` | `SupplyChainBom` | 政策/产业链解构/多维度 = 3 | screener `/screener/chain/deconstruct`、`/screener/policy/interpret` |
| 5 | K线预测 | `/predictions` | `Predictions` | 预测总览/单股/多股对比/准确率回测 = 4 | prediction-service |
| 6 | 交易信号 | `/signals` | `Signals` | 信号详情/总览/历史/风险扫描 = 4 | signal-service |

路由配置实证：`frontend/src/App.tsx:132-202`（protectedRoutes，6 主路由 + 各 sub-tab 均已注册）。
选股模式实证：`services/screener-service/app/config.py:35-39`（leader_scalp / leader_afternoon / leader_afternoon_trend_full 等），`/screener/modes` 列表在 `routers/screener.py:5493`。

### 4. AC 清单（4 维度 × 25 条）

> 格式按 `.claude/standards/ac-lifecycle.md`：每条 AC = 触发条件（"当…时"）+ 可观察结果 + 优先级 + 对应 E2E 步骤。交互类写成可点击因果链（控件 → API → UI 后果）。实际结果 + 证据留执行时回填。

#### 维度 A — 数据及时性（用户要求①：各页数据非空且日期最新，非昨天/非 EmptyState 兜底）

| AC | P | 触发条件 + 可观察结果 | E2E 步骤 |
|----|---|---|---|
| AC-A1 | P0 | 当登录后访问 `/` 时 → 行情带上证/深成/创业板/北证50 数值非 `--`/`待同步`（`marketApi.getIndexQuotes` 200 且 `diff` 非空），情绪卡片数据非 EmptyState，数据日期 ≥ 最近交易日 | navigate `/` → snapshot → 断言 `.tk .val` 非 `--` → list_network_requests 断言 `/screener/market/index-quotes` 200 → screenshot |
| AC-A2 | P0 | 当访问 `/open-decision` 时 → 决策总览候选/信号区非空，日期 = 今日或最近交易日（非昨天） | navigate → snapshot → 断言候选区有行 → curl `/open-decision` BFF（或下游 screener/signal）验日期字段 → screenshot |
| AC-A3 | P0 | 当访问 `/screener` 时 → 模式列表加载（`GET /screener/modes` 200 + `modes[]` 非空），工作台显示最新交易日 | navigate → snapshot → list_network 断言 `/screener/modes` 200 → 断言模式下拉 ≥ 3 项 → screenshot |
| AC-A4 | P0 | 当访问 `/supply-chain-bom` 时 → 产业链解构图谱/节点非空（非 EmptyState） | navigate → snapshot → 断言节点/图表渲染 → screenshot |
| AC-A5 | P0 | 当访问 `/predictions` 时 → 预测总览显示 model_version / as_of 非空，as_of ≥ 最近交易日 | navigate → snapshot → curl prediction API 验 `as_of` / `data_freshness` → screenshot |
| AC-A6 | P0 | 当访问 `/signals` 时 → 信号列表非空，信号时间 ≥ 今日/最近交易日 | navigate → snapshot → curl signal API 验时间字段 → screenshot |

#### 维度 B — 所有按钮可用性（用户要求②：按钮非 disabled 误锁，点击有响应）

| AC | P | 触发条件 + 可观察结果 | E2E 步骤 |
|----|---|---|---|
| AC-B1 | P1 | 当点击智能看板情绪/竞价/信号/自选 tab 时 → tab 切换 + 对应数据刷新（非 disabled） | snapshot → 逐 tab click → 断言 active tab 变化 + 网络请求发出 → screenshot |
| AC-B2 | P1 | 当点击开盘决策执行监控页主要按钮时 → 按钮非 disabled，点击有 toast/跳转/数据响应 | snapshot → 遍历按钮断言无 `disabled` 属性 → click → 断言可观测后果 → screenshot |
| AC-B3 | P1 | 当在选股工作台选模式 + 点"执行选股"时 → 按钮非 disabled，点击发出 `POST /screener/run`，候选表格刷新出非空行 | snapshot → 选 leader_scalp → click 执行 → list_network 断言 `/screener/run` 200 → 断言表格行出现 → screenshot |
| AC-B4 | P1 | 当在产业链拆解切换模式（上下游/价值链/竞争格局）+ 点 LLM 抽取时 → 按钮可点，点击有响应 | snapshot → 切模式 click → 断言 UI 变化 → click 抽取 → 断言请求发出 → screenshot |
| AC-B5 | P1 | 当在 K线预测单股页点查询 + 切 horizon tab 时 → 按钮可点，点击有数据/图表响应 | snapshot → 输入代码 → click 查询 → 切 horizon → 断言图表刷新 → screenshot |
| AC-B6 | P1 | 当在交易信号页点筛选/订阅时 → 按钮可点，点击有响应 | snapshot → 遍历可交互控件 click → 断言可观测后果 → screenshot |

#### 维度 C — 交互跳转可用性（用户要求③：tab 切换/路由跳转/详情跳转通）

| AC | P | 触发条件 + 可观察结果 | E2E 步骤 |
|----|---|---|---|
| AC-C1 | P0 | 当点击左侧导航 6 个行情决策菜单项时 → 每项 URL 变更 + 页面渲染 + 无 404/白屏 | 逐项 click → 断言 URL + 页面标题 + 无 ErrorBoundary 兜底 → screenshot |
| AC-C2 | P1 | 智能看板 4 sub-tab（`/`、`/dashboard/auction`、`/dashboard/signals`、`/dashboard/watchlist`）切换通 | 逐路径 navigate → 断言渲染 → screenshot |
| AC-C3 | P1 | 开盘决策 5 sub-tab（`/open-decision` + `/auction`、`/signals`、`/candidates`、`/execution`）切换通 | 同上 |
| AC-C4 | P1 | 智能选股 3 sub-tab（`/screener`、`/screener/models`、`/screener/factors`）切换通 | 同上 |
| AC-C5 | P1 | 产业链 3 sub-tab（`/supply-chain-bom`、`/policy`、`/company`）切换通 | 同上 |
| AC-C6 | P1 | K线预测 4 sub-tab（`/predictions` + `/single`、`/compare`、`/backtest`）切换通 | 同上 |
| AC-C7 | P1 | 交易信号 4 sub-tab（`/signals` + `/overview`、`/history`、`/risk`）切换通 | 同上 |
| AC-C8 | P2 | 当点击候选表格行时 → 打开详情抽屉/页面（行可点击有反馈） | snapshot → click 行 → 断言抽屉/路由 → screenshot |

#### 维度 D — 选股模型可用性（用户要求④：screener/run 各模式返回非空候选）

| AC | P | 触发条件 + 可观察结果 | E2E 步骤 |
|----|---|---|---|
| AC-D1 | P0 | 当 `POST /screener/run?mode=leader_scalp` 时 → 200 + `candidates[]` 非空 | curl / chrome 执行 → 断言状态码 + 候选行数 ≥ 1 → 落 curl 输出 |
| AC-D2 | P0 | 当 `mode=leader_afternoon` 时 → 200 + 非空 | 同上 |
| AC-D3 | P0 | 当 `mode=leader_afternoon_trend_full` 时 → 200 + 非空 | 同上 |
| AC-D4 | P1 | 当 `GET /screener/modes` 时 → 200 + 模式列表含上述 3 模式 | curl → 断言 `modes[]` 含 3 个 id → 落输出 |
| AC-D5 | P0 | 当前端选股工作台选模式 + 点"执行选股"时 → 候选表格显示非空候选行（端到端，非仅 API） | chrome：选模式 → click 执行 → snapshot 断言表格行 ≥ 1 → screenshot |

**AC 汇总**：25 条 = P0×11（A1-A6, C1, D1, D2, D3, D5）+ P1×13（B1-B6, C2-C7, D4）+ P2×1（C8）

### 5. E2E 执行框架（chrome-devtools MCP）

每条 AC 按 5 段写（Setup / Action / Expected / Actual / Verdict，铁律 #1），执行模板：

```
1. navigate_page → 目标 URL（确认是 :3000 唯一实例）
2. take_snapshot → 获取控件 uid（最新快照）
3. click / fill → 操作控件
4. list_network_requests → 断言 API 调用 + 状态码（治"按钮点击无反应"）
5. take_screenshot → 证据落盘 docs/qa/screenshots/market-decision-<AC>-<step>.png
6. （UAT 阶段强制）Read 截图 → 读图四查（导航在不在 / 有没有裁切 / 控件能不能点 / 视觉达不达标）
```

**证据要求（铁律 #2）**：每个 Pass 必有可验证 evidence — curl 输出 / 截图 / DB 行 diff，纯文字 "Passed" = Fail。
**P0 pass^2（铁律 #3）**：11 条 P0 case 每条连续跑 2 次都过才升 Pass（`p0_pass2_ok` / `p0_pass2_total` 记数）。

### 6. 执行前门槛 checklist（任一未满足不开测，回报 team-lead）

- [ ] deploy SendMessage 通知：共享 UAT 栈已部署 + 冒烟通过，URL 写入 `docs/deploy/<feature>-uat-2026-07-02.md`
- [ ] backend SendMessage 通知：API 修复，502/404/timeout 清零（screener/prediction/signal/market 端点健康）
- [ ] frontend SendMessage 通知：vite/proxy 收敛，`http://localhost:3000` 是唯一前端实例，无残留 docker 抢端口
- [ ] 数据新鲜：PG 最新交易日 = 今日或最近交易日（非昨天）— curl `/screener/modes` 看 `latest_trade_date` 验证
- [ ] 登录链路通：admin@suying.ai / Admin123! 能登录拿 token（AC 前置）

### 7. Verdict 决策树（铁律 #3）

- P0 case pass^2 = 2/2 连续两次都过 → 升 Pass
- 任一 P0 = Fail → **Block**（回派 dev 修，qa 只报告 + 提证据 + 建 issue）
- P0 + P1 全 Pass → **Promote**
- P1 部分 Fail → **Conditional**（附 fail 清单，PL 判定）

### 8. 失败处理

- E2E/UAT 发现 P0/P1 → 用 skill `agf-writing-github-issue` 建 issue（标签锁定）
- test-only 硬边界：不修源码，失败用例由 team-lead 重派执行层修复
- 不自行 hack 修复环境（遵守 task §7 + iron rule #7）

### 9. 下一步

等 deploy + backend + frontend 三方 SendMessage 通知修完 → 跑 §6 checklist → 通过则按 §4 AC 清单逐条执行 E2E → E2E 过 → 生成 UAT 用例文档 `docs/qa/market-decision-uat-cases-2026-07-02.md` 走用户审核（`status: Approved`）→ 执行 UAT → skill `agf-writing-qa-report` 出报告 → SendMessage team-lead。

---

## 行情决策板块 E2E 执行（进行中）— 2026-07-03

**入口**: `http://localhost:3000`（node PID 60809，唯一实例，proxy 指 UAT 89xx 栈：backend:8900 / screener:8901 / prediction:8902 等）

### 门槛 checklist 结果

| 项 | 结果 | 证据 |
|---|---|---|
| 栈可达 | ✅ Pass | UAT 8 服务全活（backend:8900 / screener:8901 / prediction:8902 / signal:8904 / alert:8905 / trade:8906 / backtest:8907 / diagnosis:8909 / data:8910 / gateway:8980） |
| API 无 5xx | ✅ Pass | `GET /screener/modes`（UAT 8901）HTTP 200 |
| :3000 唯一实例 | ✅ Pass | `lsof :3000` → node PID 60809 单实例，无 vite/docker 抢端口 |
| 数据非昨天 | ✅ Pass | `daily_kline` max=2026-07-02（昨日 EOD，预期）/ `stk_mins` max=2026-07-03 11:30（今日实时，4997 codes）/ `data_freshness.status=fresh quality=96` |
| **登录通** | ✅ Pass | team-lead 指引 `docker exec suying-uat-backend-1 printenv ADMIN_PASSWORD` 拿到 `Admin-UAT-ADR013-9b2f0c`，admin@suying.ai 登录 200，进 `/` Dashboard |

### 维度 D 选股模型（API 直测 + UI）

| AC | P | 命令 | 结果 | Verdict |
|----|---|---|---|---|
| D4 | P1 | `GET /screener/modes` | HTTP 200，17 模式，含 leader_scalp / leader_afternoon / leader_afternoon_trend_full | ✅ Pass |
| D1 | P0 | `POST /screener/run?mode=leader_scalp` | HTTP 200，`total_picks=0`，trade_date=2026-07-02 | ❌ Fail |
| D2 | P0 | `mode=leader_afternoon` | HTTP 200，`total_picks=0` | ❌ Fail |
| D3 | P0 | `mode=leader_afternoon_trend_full` | HTTP 200，`total_picks=0` | ❌ Fail |

**D1/D2/D3 根因诊断**（已排除"无数据/无涨停"假象）：
- 07-02 有 **114 只涨停股**（change_pct≥9.8%）+ 11 只 20cm 涨停，`leader_scalp`（盘后龙头战法）本应筛出部分，却返回 0 → **非"市场无信号"，是模型/数据拼接缺陷**
- `trade_date` 参数（POST body 与 `?date=` query）**均被忽略**——传 07-01 / 06-30 / 06-26 都强制返回 latest(07-02)，无法回测历史日
- 今日盘中数据存在（`stk_mins` 07-03 11:30），但盘后模型不消费
- `data_freshness` 正常（fresh / quality 96），排除数据问题
- 结论：**screener run 端点对 leader_* 模式产出空候选，是 P0 defect**，需 backend-dev 修

### 维度 A 数据及时性（chrome-devtools 真渲染）

| AC | P | 路由 | 结果 | 证据 |
|----|---|---|---|---|
| A1 | P0 | `/` Dashboard | ✅ Pass | 行情带真实值(上证4066.05+0.92%等4指数非--)、情绪指数38分偏悲观、上涨2217/下跌3162只、交易日2026-07-02(最新EOD)、fresh。截图 A1-dashboard |
| A2 | P0 | `/open-decision` | ⚠️ Conditional | 交易日07-03对+行情带ok，但决策总览多区空(情绪指数-/候选池0只)；熔断2接口：`/trade/risk-verdicts` 404 + `/trade/decision-contexts` 404（trade-service 缺这两个路由）。截图 A2-open-decision |
| A3 | P0 | `/screener` | ✅ Pass(渲染) | 模式分类16模型+日期07-03+开始选股按钮非disabled；但点运行后卡死(见D5)。截图 A3-D5-screener-run-hang |
| A4 | P0 | `/supply-chain-bom` | ✅ Pass | 上游观察池35真实公司(雅运股份+9.99%/百合花+7.82%等, 07-02)、BOM节点11、主题3、3模式radio。状态可用 |
| A5 | P0 | `/predictions` | ⚠️ Conditional | Kronos-mini"模型未加载"=base predictor(CLAUDE.md记录的预期状态)；候选池空(依赖选股模型)；状态"缺少交易日"。非数据停昨天 |
| A6 | P0 | `/signals` | ✅ Pass | 今日信号20条真实实时(易实精密Bullish/珂玛科技Bearish等)、13:12更新、候选联动抽屉(DC-920221/CAND-920221/RiskVerdict待预检) |

**A 维结论**：4/6 PASS + 2/6 Conditional，主路径无"数据停昨天/EmptyState兜底"违规；Conditional 项是 base model 预期态 + 2 个 trade 404。

### 维度 B 全板块死按钮扫描（chrome-devtools 逐个 click + 断言 network/toast/modal/计数变化）

| AC | 路由 | 结果 | 死按钮清单 |
|----|---|---|---|
| B1 | `/` Dashboard | ✅ Pass | filter chips(过热/冰点/急转)有 className 切换；sub-tab 跳转通 |
| B2 | `/open-decision/*` | ❌ **9 死按钮** | 信号扫描tab: 批量确认买入信号 / 一键排除风险标的 / 一键推送已确认->候选池 / 查看候选池-> ；执行监控tab: 一键启动自动交易 / 去交易中心手动下单 / 删除 ；候选池tab: 生成方案 / 保存为手动方案 |
| B3 | `/screener` | ❌ Fail | "开始选股"按钮 click 后永久 disabled 锁死，`/signal/trigger-sync` ERR_ABORTED + `/screener/run` 永久 pending(>40s)（见 D5）|
| B4 | `/supply-chain-bom` | ✅ Pass | 3模式radio + 主题按钮 + 导出清单/刷新图表 可点；解读政策 disabled 因文本空=正常 |
| B5 | `/predictions` | ✅ Pass | 查看单股预测/进入多股对比/打开准确率回测 跳转通 |
| B6 | `/signals/*` | ✅ Pass | 风险通过 chip 切换响应；RiskVerdict 面板渲染 |

**B2 死按钮特征**：全 `disabled:false`（未误锁），但 click 后**无 network 请求 / 无 toast / 无 modal / 无导航 / 计数不变**（已确认0/20 不动）。截图 `B-signalscan-deadbuttons.png` + `B-execmon-deadbuttons.png`。资金风险按钮"一键启动自动交易"无响应=不会误触发（安全），但仍是 defect（用户期望跳转/弹窗确认）。

### 维度 C 交互跳转（navigate + 断言 URL 变更 + 渲染）

C1 主导航6主路由 ✅ / C2 Dashboard 4 sub-tab ✅(信号总览有行业矩阵10股) / C3 OpenDecision 5 sub-tab ✅ / C4 Screener 3 sub-tab ✅ / C5 SupplyChain 3 sub-tab ✅ / C6 Predictions 4 sub-tab ✅ / C7 Signals 4 sub-tab ✅(history 渲染结构完整) / C8 候选行点击→详情 ✅(候选联动抽屉 + 选中股票侧栏)。**跳转维度全 PASS，无断链。**（10 个未逐个 click 的 sub-tab URL 经 fetch 批量校验全 200 + 抽样 signals/history 渲染核查）

### E2E AC 汇总（25 条）

| 维度 | PASS | Conditional | FAIL | 小计 |
|---|:---:|:---:|:---:|:---:|
| A 数据及时性 | 4 | 2 | 0 | 6 |
| B 按钮可用性 | 4 | 0 | 2 (B2×9死按钮 / B3 run卡死) | 6 |
| C 交互跳转 | 8 | 0 | 0 | 8 |
| D 选股模型 | 1 (D4) | 0 | 4 (D1/D2/D3空候选 + D5 UI卡死) | 5 |
| **合计** | **17** | **2** | **6** | **25** |

**P0 状态**：11 条 P0 中 D1/D2/D3/D5 = Fail（4 P0），A1/A2/A3/A4/A5/A6/C1 = Pass/Conditional。任一 P0 Fail → **Verdict: Block**（铁律 #3）。

### E2E Verdict: ❌ **Block**

按决策树（铁律 #3）：11 P0 中 D1/D2/D3/D5 = Fail → **Block**。主路径选股模型空候选 + UI run 卡死 + OpenDecision 9 死按钮，阻塞"选股模型可用性"和"所有按钮可用性"两个用户明确要求。

### Defect 分级（建议建 issue）

| ID | 级别 | defect | 建议处置 | 责任 |
|---|:---:|---|---|---|
| DEF-1 | P0 | screener `/run` leader_* 三模式 `total_picks=0`（07-02 有 114 涨停却筛 0；trade_date 参数被忽略） | 本 task 修 | backend-dev（PL 已派） |
| DEF-2 | P0 | screener UI"开始选股"click 后永久 disabled 锁死，`/screener/run` pending >40s，`/signal/trigger-sync` ERR_ABORTED | 本 task 修 | backend-dev + frontend-dev |
| DEF-3 | P1 | OpenDecision 9 死按钮（信号扫描×4 / 执行监控×3 / 候选池×2），disabled:false 但 click 无响应 | 本 task 修（简单：补 onClick）或 follow-up | frontend-dev |
| DEF-4 | P1 | `/trade/risk-verdicts` + `/trade/decision-contexts` 404（App.tsx 路由配了但 trade-service 缺端点）→ 熔断器常驻 | follow-up issue | backend-dev |

### 下一步

1. 等 backend-dev 修 DEF-1/DEF-2 → 重测 D1/D2/D3/D5 + B3
2. 等 frontend-dev 修 DEF-3 → 重测 B2
3. 全 P0 pass^2 → 出 UAT 用例文档 `docs/qa/market-decision-uat-cases-2026-07-03.md` 走用户审核 → UAT
4. 本 E2E 报告 `docs/qa/market-decision-e2e-2026-07-03.md`（skill agf-writing-qa-report，待出）
5. DEF-1/DEF-3/DEF-4 用 skill agf-writing-github-issue 建 issue（P0/P1）

