# 大葱产业链 BOM V4 选股模型 UAT 报告

## 1. Summary

- **Feature**: 大葱产业链 BOM 级拆解选股模型 V4
- **Date**: 2026-06-24
- **Stage**: Self-UAT
- **Tester**: Codex qa-engineer
- **Branch / Commit**: `feature/suying-ai-stock-platform` / `44850ad`
- **Verdict**: Block

本轮 UAT 按 PRD 与设计文档逐项检查，并执行接口、前端组件、构建、真实浏览器走查。自动化测试全部通过，基础接口、评分、交易信号、图谱查询与 LLM 抽取入口具备可运行能力；但前端仍未完整达到 PRD 中的核心业务验收标准，尤其是板块矩阵、公司级财务指标、护城河证据、证据时间线、手工配置校准、外部专利/招投标/产能数据接入等能力。因此本轮不建议进入业务签字。

## 2. Pre-conditions

| Item | Status | Notes |
|---|---:|---|
| PRD | Pass | `docs/prd/supply-chain-bom-2026-06-23.md` 已检查 |
| API Design | Pass | `docs/design/supply-chain-bom-v4/api-contract.md` 已检查 |
| Implementation Plan | Pass | `docs/superpowers/plans/2026-06-23-supply-chain-bom-v4.md` 已检查 |
| Approved UAT Cases | Missing | 仓库中未发现已批准的 UAT case 文档，本报告按 PRD AC 自行派生 |
| Full Tushare Data | Not verified | 本轮未连接真实 Tushare 全量库，使用接口/单测/本地 mock 验证能力 |
| LLM Production Key | Not verified | 本轮未使用真实 DeepSeek key，使用 mock/单测验证抽取链路 |

## 3. Test Evidence

### 3.1 Automated Tests

| Scope | Command | Result |
|---|---|---:|
| screener-service supply-chain API / LLM / graph store | `../../.venv/bin/pytest tests/test_supply_chain_bom_api.py tests/test_llm_supply_chain.py tests/test_supply_chain_graph_store.py -v` | 12 passed |
| kronos-factors V4 scoring | `../../.venv/bin/pytest tests/test_supply_chain_bom_v4.py -v` | 3 passed |
| frontend component | `npx vitest run src/__tests__/SupplyChainBom.test.tsx` | 3 passed |
| frontend type check | `npx tsc -b --noEmit` | passed |
| frontend production build | `npm run build` | passed, chunk size warning only |

### 3.2 Browser UAT

| Screenshot | What Was Verified |
|---|---|
| `docs/qa/evidence/UAT-SCBOM-main.png` | 页面可登录进入；产业链拆解菜单可见；主题表、BOM 图、节点表、节点详情、LLM 抽取区域可渲染 |
| `docs/qa/evidence/UAT-SCBOM-company-drawer.png` | 公司抽屉可打开，并展示评级、排名、交易信号、BOM 路径、产品、材料 |
| `docs/qa/evidence/UAT-SCBOM-extraction.png` | LLM 抽取输入、写入图谱开关、抽取结果、映射数量、证据数量可展示 |

## 4. AC Results

| AC | PRD Expectation | Result | Evidence / Gap |
|---|---|---:|---|
| AC-1 | `mode=supply_chain` 返回政策主题、BOM 路径、产品/材料、公司映射、商业化、卡脖子、评分、评级、排序、交易信号、证据 | Pass | API 单测覆盖，V4 评分字段存在 |
| AC-2 | 图谱 API 返回主题、链条、节点、边、公司映射、证据来源 | Pass | `/themes`、`/bom`、`/node/{id}`、`/company/{code}` 单测通过 |
| AC-3 | 前端展示政策主题、板块矩阵、BOM 图，并支持点击主题刷新 | Fail | 页面有主题表与图谱，但未展示 high_growth / high_profit / high_moat 板块矩阵 |
| AC-4 | 点击节点展示上市公司列表、评分、评级、交易信号、证据数量 | Fail | 节点详情仅展示公司名称按钮与证据数量；列表未展示公司评分、评级、交易信号 |
| AC-5 | 公司抽屉展示 BOM 路径、产品/材料、财务指标、护城河证据、风险提示、证据时间线 | Fail | 抽屉仅显示评级、排序、信号、BOM 路径、产品、材料，缺财务、护城河、风险与时间线 |
| AC-6 | 评分模型覆盖政策、BOM、卡脖子、成长、利润、商业化、市场共振七类维度 | Pass | `test_score_company_v4_adds_required_fields` 通过 |
| AC-7 | LLM 自动阅读政策/公告并写入候选映射、证据、置信度、待审状态 | Conditional Pass | 抽取 API 与 UI 路径可用；真实生产 key 和真实公告源未验证 |
| AC-8 | 历史验证必须按 `trade_date` 截止，避免未来函数 | Partial | 代码中存在验证工具与 V4 字段；本轮未跑真实历史回测数据集 |
| AC-9 | 输出 V4 与 V3、卡脖子子策略的命中率/收益/回撤对比 | Not Run | 本轮未连接完整历史行情与选股结果，无法形成 OOS 对比报告 |
| AC-10 | 前端逐级下钻到上市公司、产品/材料、财务指标、护城河证据 | Fail | 下钻可到公司抽屉，但未下钻到财务指标与护城河证据 |
| AC-11 | 政策、主题、板块优先使用 Tushare 或国内券商分类 | Partial | PRD 与配置有方向，UAT 未证明真实 Tushare/券商分类已接入 |
| AC-12 | 交易信号是研究信号，不触发自动下单 | Pass | 交易信号限定为观察、关注、启动、强启动、风险回避；未发现自动下单调用 |
| AC-13 | 接入专利、招投标、产能投产公告等外部数据，并可降级 | Fail | 未验证到可用外部数据适配器或前端呈现 |
| AC-14 | LLM 自动抽取，同时可手工配置和覆盖 | Fail | 发现 manual override 表设计，但未验证到对应 API 或 UI 操作入口 |

## 5. Defects

| ID | Severity | Area | Description | Suggested Fix |
|---|---:|---|---|---|
| UAT-SCBOM-001 | P0 | Frontend | 政策主题区域未展示高增长、高利润、高围墙板块矩阵，未达到 PRD 的矩阵视图要求 | 在主题表或独立矩阵区展示 `theme.matrix.high_growth/high_profit/high_moat/policy_weight`，支持按主题切换 |
| UAT-SCBOM-002 | P0 | Frontend | 节点公司列表缺少评分、评级、交易信号展示 | 节点详情中的公司列表补充 `score/rating/trade_signal/evidence_count` |
| UAT-SCBOM-003 | P0 | Frontend | 公司抽屉缺少财务指标、护城河证据、风险提示、证据时间线 | 将 company API 的 `financial_indicators`、`moat_evidence`、`risk_flags/evidence` 渲染为分区 |
| UAT-SCBOM-004 | P0 | Product/API | PRD 写 `POST /supply-chain/llm-refresh`，设计与实现为 `POST /supply-chain/extract` | 统一 PRD、API contract 与前端调用命名 |
| UAT-SCBOM-005 | P1 | Backend/Frontend | 手工配置和覆盖能力未形成可验收 API/UI | 增加 manual override 新增、审核、回滚接口和前端入口 |
| UAT-SCBOM-006 | P1 | Data | 专利、招投标、产能投产公告外部数据未完成可验收接入 | 增加外部数据 adapter、失败降级状态、证据来源字段与测试 |
| UAT-SCBOM-007 | P2 | Process | 缺少已批准 UAT case 文档 | 基于 PRD AC 生成正式 UAT case 并完成业务确认 |

## 6. Cross-stage Notes

- 自动化测试覆盖了接口契约、基础图谱、LLM JSON 解析、抽取记录构造、V4 评分字段和前端基础渲染，但测试没有覆盖完整业务页面的“逐级下钻信息完整性”。
- 前端真实页面可用，但目前更像 MVP 控制台，还不是 PRD 中要求的完整产业链研究工作台。
- 本轮使用本地 mock 认证与 mock screener 数据完成浏览器 UAT，因此不能替代真实 Tushare、真实公告、真实 LLM key、真实历史回测环境下的最终 UAT。
- 生产构建通过，但 Vite 提示 `antd`、`echarts` 相关 chunk 超过 500 kB，属于性能优化风险，不阻断本轮业务验收。

## 7. Cost

- Automated tests: local only
- Browser UAT: local only
- External paid APIs: not invoked
- LLM provider: not invoked with production key
- Codex token usage: not available in this desktop session

## 8. Hand-off

当前结论为 **Block**。建议先修复 P0 缺陷 UAT-SCBOM-001 至 UAT-SCBOM-004，再补齐手工覆盖、外部证据源、真实 Tushare/券商分类与 OOS 回测证据。修复后需要重新执行：

1. screener-service supply-chain API tests
2. kronos-factors V4 scoring tests
3. frontend SupplyChainBom component tests
4. frontend type check and build
5. browser UAT with real drill-down screenshots
6. connected-data UAT with Tushare, LLM,公告/专利/招投标/产能数据
