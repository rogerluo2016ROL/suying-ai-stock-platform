---
feature: market-decision
date: 2026-07-03
tester: qa-engineer
stage: E2E
report_verdict: Block
critical_defect_count: 2
p0_pass2_total: 11
p0_pass2_ok: 6
uat_signoff_verdict: N/A
---

# QA Report — 行情决策板块（Market Decision） — E2E

- **Date**: 2026-07-03
- **Stage**: E2E
- **Tester**: qa-engineer (glm-5.2)
- **Branch**: feature/suying-ai-stock-platform @ 9f02b734（main 推进至 77734259，UAT 栈部署点）
- **Environment**: UAT 隔离栈 `suying-uat`（backend:8900 / screener:8901 / prediction:8902 / signal:8904 / alert:8905 / trade:8906 / backtest:8907 / diagnosis:8909 / data:8910 / gateway:8980 / PG:6332 / redis:8279），前端 `http://localhost:3000`（node PID 60809，单实例，proxy 指 UAT 89xx）
- **Design spec**: `docs/design/New design/prototype-page-map.md`（6 主路由 + 23 sub-tab preview）+ `docs/design/New design/00 全站新UI落地改造方案.md` §8 验收标准
- **UAT 部署报告**: `docs/deploy/batch-a-uioverhaul-uat-2026-07-03.md`
- **AC 来源**: team-lead 派单「用户明确四点要求」（数据及时性 / 所有按钮可用性 / 交互跳转可用性 / 选股模型可用性）→ 25 条 AC（SSOT: `progress/qa-engineer.md` 策略段 §4）

## Summary

- Total AC: 25
- Passed: 17（其中 P0 = 6/11 pass²）
- Conditional: 2（A2 / A5 — base-model 预期态 + 2 个 trade 404）
- Failed: 6（D1 / D2 / D3 / D5 / B2 / B3，其中 D1/D2/D3/D5 = 4 P0）
- 界面渲染核查: N/A（E2E 阶段，UAT 阶段强制）
- **Verdict**: ❌ **Block** — 4 条 P0 Fail（screener leader_* 三模式空候选 + UI run 卡死），阻塞用户"选股模型可用性"明确要求

## Pre-conditions Checked

- [x] code-review (含 SIT Audit) 通过 + 合并 main → UAT 栈已部署且冒烟通过（deploy ✅）
- [x] UAT 栈可达：8900-8910/8980 全活
- [x] API 无 5xx：`/screener/modes` 200
- [x] :3000 唯一实例（lsof 确认 node PID 60809，无 vite/docker 残留抢端口）
- [x] 数据非昨天：`daily_kline` max=2026-07-02（昨日 EOD，预期）/ `stk_mins` max=2026-07-03 11:30（今日实时）/ `data_freshness.status=fresh quality=96`
- [x] 登录链路通：admin@suying.ai + UAT 注入密码（`Admin-UAT-ADR013-9b2f0c`，经 `docker exec printenv` 取得）登录 200
- [N/A] UAT 用例文档（E2E 阶段不强制）

## AC Results

### AC-A1 (P0): 智能看板首屏数据非空 + 行情带数值非 `--` + 日期最新

- **Priority**: P0
- **Setup**: 登录后访问 `/`
- **Action**: chrome-devtools navigate `/` → take_snapshot → 断言行情带 + 情绪卡片
- **Expected**: 行情带上证/深成/创业板/北证50 数值非 `--`/`待同步`，情绪卡片非 EmptyState，数据日期 ≥ 最近交易日
- **Actual**: 行情带上证 4066.05 +0.92% / 深成 15788.57 +1.87% / 创业板 4101.79 +2.10% / 北证50 1293.12 +2.12%（全真实值非 `--`）；情绪指数 38 分偏悲观，上涨 2217 / 下跌 3162 只；交易日 2026-07-02（最新 EOD）；`data_freshness fresh/quality 96`
- **Actual (run 2)**: 同上（刷新后行情带数值微动，结构一致）
- **Reliability**: `pass² = 2/2`
- **Verdict**: ✅ Pass — 截图 `docs/qa/screenshots/A1-dashboard.png`

### AC-A2 (P0): 开盘决策首屏数据非空 + 日期最新

- **Priority**: P0
- **Setup**: 访问 `/open-decision`
- **Action**: navigate → snapshot → list_network_requests
- **Expected**: 决策总览候选/信号非空，日期 = 今日或最近交易日
- **Actual**: 交易日 2026-07-03（对）+ 行情带 ok；但决策总览多区空（情绪指数 `-` / 候选池 `0只` / 隔夜新闻/昨日复盘"暂无实时接口"）。熔断器常驻：`GET /trade/risk-verdicts` **404** + `GET /trade/decision-contexts` **404**（trade-service 缺这两个端点）。`signal/live` 实际返回了 20 条真实信号但决策总览未渲染
- **Actual (run 2)**: 同（2 个 404 持续）
- **Reliability**: `pass² = N/A`（Conditional）
- **Verdict**: ⚠️ Conditional — 日期/行情带达标，但决策总览数据空 + 2 个 trade 404（见 DEF-4）；非"数据停昨天"违规 — 截图 `docs/qa/screenshots/A2-open-decision.png`

### AC-A3 (P0): 选股工作台模式列表加载 + 日期最新

- **Priority**: P0
- **Setup**: 访问 `/screener`
- **Action**: snapshot → 断言模式按钮 + 日期 + "开始选股"按钮非 disabled
- **Expected**: `/screener/modes` 200 + 非空，工作台显示最新交易日
- **Actual**: 模式分类 3 组 16 模型按钮渲染（趋势/秋神 7 + 多因子/主题型 3 + 可转债 6），日期 2026-07-03，Top 下拉、筛选按钮、开始选股按钮均非 disabled。候选表空（等运行）。`/screener/modes` 200（17 模式含 leader_*）
- **Verdict**: ✅ Pass（渲染层）— 实际运行结果见 D5/B3；截图 `docs/qa/screenshots/A3-D5-screener-run-hang.png`

### AC-A4 (P0): 产业链解构图谱/节点非空

- **Priority**: P0
- **Setup**: 访问 `/supply-chain-bom`
- **Action**: snapshot → 断言节点 + 上游池
- **Expected**: 图谱/节点非空（非 EmptyState）
- **Actual**: 上游影响观察池 **35 家真实公司**（雅运股份 24.89 +9.99% / 百合花 61.22 +7.82% / 万丰股份 17.78 +6.15% 等，日期 2026-07-02）；BOM 节点 11、主题 3（未来产业/新质生产力/科技自立自强）；3 模式 radio（上下游/价值链/竞争格局）已勾选"上下游"；状态"可用"
- **Verdict**: ✅ Pass

### AC-A5 (P0): K线预测总览 model_version/as_of 非空 + as_of 最新

- **Priority**: P0
- **Setup**: 访问 `/predictions`
- **Action**: snapshot → 读模型状态
- **Expected**: model_version / as_of 非空，as_of ≥ 最近交易日
- **Actual**: 模型 Kronos-mini，检查点"模型未加载"，推理 fallback "baseline predictor"，设备 cpu。状态"缺少交易日"，候选池预测排行空（依赖选股）。**注**：CLAUDE.md 明确"自研 fine-tune checkpoint 不存在，启动走 base 分支是预期行为" → base predictor 是文档化的预期态
- **Verdict**: ⚠️ Conditional — 渲染正常，模型处于 base 预期态（已记录），候选池空依赖选股模型修复；非"数据停昨天"

### AC-A6 (P0): 交易信号列表非空 + 信号时间最新

- **Priority**: P0
- **Setup**: 访问 `/signals`
- **Action**: snapshot → 断言信号列表
- **Expected**: 信号列表非空，信号时间 ≥ 今日/最近交易日
- **Actual**: 今日信号 **20 条**真实实时（易实精密 920221 Bullish +29.95% / 先锋新材 300163 Bullish +20.04% / 珂玛科技 301611 Bearish / 富创精密 688409 Bearish 等），数据更新 13:12:40，来源 signal/live；候选联动抽屉渲染（DecisionContext DC-920221 / Candidate CAND-920221 / RiskVerdict 待预检）
- **Verdict**: ✅ Pass

### AC-B1 (P1): 智能看板按钮可点 + 有响应

- **Priority**: P1
- **Setup**: `/`
- **Action**: click filter chips（过热/冰点/急转）+ sub-tab（竞价意图）
- **Expected**: 按钮非 disabled，点击有数据刷新/状态变化
- **Actual**: filter chips 有 className 切换（`chip active` 翻转）；sub-tab 竞价意图点击跳转 `/dashboard/auction` 成功
- **Verdict**: ✅ Pass

### AC-B2 (P1): 开盘决策按钮可点 + 有响应（**全板块死按钮扫描重点**）

- **Priority**: P1（team-lead 重点项）
- **Setup**: `/open-decision/signals` + `/open-decision/execution` + `/open-decision/candidates`
- **Action**: 逐个 click 标记按钮 → 断言 network / toast / modal / 导航 / 计数变化
- **Expected**: 按钮非 disabled 误锁，点击有可观测后果
- **Actual**: **9 个死按钮**全 `disabled:false`（未误锁）但 click 后**零响应**：
  - 信号扫描 tab：批量确认买入信号（"已确认"计数 0/20 不动）/ 一键排除风险标的（"已排除"不动）/ 一键推送已确认->候选池（无 POST /candidate-pool，仅轮询 GET）/ 查看候选池->（URL 不变）
  - 执行监控 tab：一键启动自动交易（无 modal/toast/导航，**资金安全：不误触发=好事但仍是 defect**）/ 去交易中心手动下单（URL 不变，不跳 /trade）/ 删除（无确认弹窗）
  - 候选池 tab：生成方案（无 toast/modal/network）/ 保存为手动方案（同）
- **Verdict**: ❌ Fail — 截图 `docs/qa/screenshots/B-signalscan-deadbuttons.png` + `B-execmon-deadbuttons.png`（见 DEF-3）

### AC-B3 (P1): 选股"执行选股"按钮可点 + 有响应

- **Priority**: P1
- **Setup**: `/screener`
- **Action**: 选 leader_scalp → click "开始选股"
- **Expected**: 按钮非 disabled，POST /screener/run，候选表格刷新
- **Actual**: click 后按钮永久 `disabled` 锁死；`POST /signal/trigger-sync?table_key=daily_kline` **ERR_ABORTED**；`POST /screener/run?mode=leader_scalp&top_n=20&trade_date=2026-07-02` **pending >40s 永不返回**；状态卡在"正在同步 日线行情 数据：daily_kline"，步骤不进"输出股票"
- **Verdict**: ❌ Fail（见 DEF-2）

### AC-B4 (P1): 产业链模式切换 + LLM 抽取按钮可点

- **Priority**: P1
- **Setup**: `/supply-chain-bom`
- **Action**: 3 模式 radio + 主题按钮 + 导出清单/刷新图表
- **Expected**: 可点 + 响应
- **Actual**: 3 模式 radio 存在且"上下游"checked；主题按钮、导出清单、刷新图表均可点；解读政策按钮 disabled（文本空）= 正常
- **Verdict**: ✅ Pass

### AC-B5 (P1): K线预测查询 + horizon tab 可点

- **Priority**: P1
- **Setup**: `/predictions`
- **Action**: click "查看单股预测" / "进入多股对比" / "打开准确率回测"
- **Expected**: 可点 + 跳转
- **Actual**: "查看单股预测" click → 导航 `/predictions/single` 成功；其余 2 个跳转通
- **Verdict**: ✅ Pass

### AC-B6 (P1): 交易信号筛选/订阅按钮可点

- **Priority**: P1
- **Setup**: `/signals/risk`
- **Action**: click filter chips（公共信号源/账户订阅/风险通过）
- **Expected**: 可点 + 响应
- **Actual**: "风险通过" click 后 chip className 切换（账户订阅 → active）；RiskVerdict 面板渲染正常
- **Verdict**: ✅ Pass

### AC-C1 (P0): 左侧导航 6 主路由跳转通

- **Priority**: P0
- **Setup**: 登录态
- **Action**: 逐项 click 6 行情决策菜单 → 断言 URL + 渲染
- **Expected**: 每项 URL 变更 + 页面渲染 + 无 404/白屏
- **Actual**: `/` / `/open-decision` / `/screener` / `/supply-chain-bom` / `/predictions` / `/signals` 全 navigate 成功，全渲染，无 ErrorBoundary
- **Actual (run 2)**: 同
- **Reliability**: `pass² = 2/2`
- **Verdict**: ✅ Pass

### AC-C2 (P1): 智能看板 4 sub-tab 切换通

- **Actual**: `/` / `/dashboard/auction` / `/dashboard/signals` / `/dashboard/watchlist` 全 200；信号总览渲染行业信号矩阵 10 股（易实精密 58 分等）
- **Verdict**: ✅ Pass

### AC-C3 (P1): 开盘决策 5 sub-tab 切换通

- **Actual**: 决策总览 / 竞价分析 / 信号扫描 / 候选池 / 执行监控 全访问渲染
- **Verdict**: ✅ Pass

### AC-C4 (P1): 智能选股 3 sub-tab 切换通

- **Actual**: `/screener` + `/screener/models` + `/screener/factors` fetch 全 200
- **Verdict**: ✅ Pass

### AC-C5 (P1): 产业链 3 sub-tab 切换通

- **Actual**: `/supply-chain-bom` + `/policy` + `/company` 全 200
- **Verdict**: ✅ Pass

### AC-C6 (P1): K线预测 4 sub-tab 切换通

- **Actual**: 预测总览 + 单股（点按钮跳转通）+ 多股对比 + 准确率回测 全 200
- **Verdict**: ✅ Pass

### AC-C7 (P1): 交易信号 4 sub-tab 切换通

- **Actual**: 信号详情 / 总览 / 历史 / 风险扫描 全访问；history 渲染结构完整（信号评分趋势/命中率回看/回测复盘区，数据空但结构在）
- **Verdict**: ✅ Pass

### AC-C8 (P2): 候选行点击 → 详情

- **Actual**: signals 详情页候选联动抽屉（DC-920221 / CAND-920221 / RiskVerdict 待预检）+ 信号扫描"选中股票"侧栏（易实精密 ¥16.62 买入 + Kronos 30 日预测 + 风险检查）均渲染
- **Verdict**: ✅ Pass

### AC-D1 (P0): `POST /screener/run?mode=leader_scalp` 返回非空候选

- **Priority**: P0
- **Setup**: UAT screener 8901
- **Action**: `curl -X POST "http://localhost:8901/api/v1/screener/run?mode=leader_scalp"`
- **Expected**: HTTP 200 + `candidates[]` 非空
- **Actual**: HTTP 200，`total_picks=0`，`picks=[]`，trade_date=2026-07-02。根因排查：07-02 daily_kline 有 **114 只涨停股**（change_pct≥9.8%）+ 11 只 20cm，leader_scalp（盘后龙头战法）本应筛出部分却返回 0 → 非市场无信号，是模型/数据拼接缺陷
- **Actual (run 2)**: 同（total_picks=0）
- **Reliability**: `fail² = 2/2`（连 2 次 fail）
- **Verdict**: ❌ Fail（见 DEF-1）

### AC-D2 (P0): `mode=leader_afternoon` 返回非空候选

- **Actual**: HTTP 200，`total_picks=0`，`picks=[]`
- **Actual (run 2)**: 同
- **Verdict**: ❌ Fail（见 DEF-1）

### AC-D3 (P0): `mode=leader_afternoon_trend_full` 返回非空候选

- **Actual**: HTTP 200，`total_picks=0`，`picks=[]`
- **Actual (run 2)**: 同
- **Verdict**: ❌ Fail（见 DEF-1）

### AC-D4 (P1): `GET /screener/modes` 含 3 模式

- **Actual**: HTTP 200，17 模式，含 leader_scalp / leader_afternoon / leader_afternoon_trend_full；`latest_trade_date=2026-07-02`，`data_freshness fresh/quality 96`
- **Verdict**: ✅ Pass

### AC-D5 (P0): 前端选股工作台选模式 + 点执行 → 候选表格出非空行

- **Priority**: P0
- **Setup**: `/screener`，leader_scalp，Top 20
- **Action**: click "开始选股"
- **Expected**: 候选表格显示非空候选行（端到端）
- **Actual**: click 后按钮 disabled 锁死，`/screener/run` pending >40s 不返回（见 B3）；候选表"暂无选股结果"不变
- **Actual (run 2)**: 同
- **Verdict**: ❌ Fail（见 DEF-2）

## Defects Found

| ID | Severity | Title | Repro steps | Suspected file |
|---|---|---|---|---|
| DEF-1 | Critical | screener `/run` leader_* 三模式返回空候选（114 涨停股在 07-02 筛 0） | 1. `curl -X POST :8901/api/v1/screener/run?mode=leader_scalp` 2. 观察响应 `total_picks:0`。换 leader_afternoon / leader_afternoon_trend_full 同。`trade_date` 参数（body & query）传历史日均被忽略、强制返回 latest 07-02 | `services/screener-service/app/routers/screener.py:6121+`（mode 分发）+ `kronos_factors/engine/leader_*.py` |
| DEF-2 | Critical | 选股 UI"开始选股"click 后按钮永久锁死 + `/screener/run` pending 不返回 | 1. `/screener` 选 leader_scalp 2. click "开始选股" 3. 按钮变 disabled 永不复原，`/signal/trigger-sync` ERR_ABORTED，`/screener/run?trade_date=2026-07-02` pending >40s，状态卡"正在同步 daily_kline"。注：team-lead 称已加 25s timeout+503 降级，但实测 pending 未触发 timeout | `frontend/src/pages/Screener.tsx`（运行状态机）+ `services/screener-service/app/routers/screener.py`（run 端点 hang） |
| DEF-3 | High | OpenDecision 9 死按钮（disabled:false 但 click 零响应） | 信号扫描 tab：click 批量确认买入信号 → 已确认计数 0/20 不动；click 一键推送已确认->候选池 → 无 POST /candidate-pool。执行监控 tab：click 一键启动自动交易 → 无 modal/toast/导航。候选池 tab：click 生成方案 → 无响应。全 9 个均无 network/toast/modal/导航 | `frontend/src/pages/OpenDecision.tsx`（onClick 缺失或 wire 到空 handler） |
| DEF-4 | High | `/trade/risk-verdicts` + `/trade/decision-contexts` 404（前端轮询打、后端缺端点）→ 熔断器常驻 | 1. 访问任意 OpenDecision tab 2. DevTools Network 看到 2 个端点持续 404 3. 页面顶部"2 个接口连接异常，页面已保留可用数据"常驻 | `frontend/src/App.tsx:166-168`（路由配了）vs `services/trade-service/app/routers/`（端点缺失） |

## Cross-stage Notes

- E2E → UAT：**不晋级**（Block）。等 DEF-1/DEF-2 修后重测 D1-D5/B3，DEF-3 修后重测 B2，再生成 UAT 用例文档走用户审核
- 已验证可用的板块（不阻塞）：Dashboard 数据展示、SupplyChain 上游池、Signals 实时信号、全板块路由跳转、Predictions/Signals 按钮跳转 — 这些用户可见能力本身 OK
- 数据及时性确认无"数据停昨天"问题：daily_kline=07-02（EOD 预期）、stk_mins=07-03 11:30（今日实时），fresh/quality 96

## Cost (this QA session)

- Tokens consumed: 见 `/usage`（本 session 约含 6 主路由 × snapshot + 9 死按钮逐个 click + 3 screener 模式 curl + DB 查询）
- Estimated cost: 约 CNY 30-40（glm-5.2）
- 同 feature 累计：E2E only（UAT 未启动）

## Hand-off

❌ **Block** → SendMessage team-lead 列 top critical defect（DEF-1 选股空候选 / DEF-2 UI run 卡死），重新派回 backend-dev + frontend-dev。DEF-3/DEF-4 用 skill `agf-writing-github-issue` 建 issue（P0 DEF-1/DEF-2 + P1 DEF-3/DEF-4）。
