# PRD — 平台五域可信度与可维护性治理

- **Date**: 2026-07-10
- **Owner**: product-lead
- **Status**: Draft
- **Estimated effort tier**: Large（前端、后端、架构、数据采集、算法模型五条工作流，含交易与模型可信度门禁）
- **Related audit**: `docs/reviews/`、`docs/data-governance/`、2026-07-10 本地代码与数据库审计
- **Detailed design**: `docs/superpowers/specs/2026-07-10-platform-five-domain-optimization-design.md`
- **Implementation plan**: `docs/superpowers/plans/2026-07-10-platform-five-domain-optimization.md`

## 1. Background

速赢 AI 已覆盖看板、选股、产业链、预测、信号、策略、交易、风控、回测、训练和模型管理。项目现在的主要风险来自五条链路之间缺少统一约束：前端手写接口契约，后端服务各自维护测试入口和健康状态，数据表在不同日期完成更新，模型使用不同回测口径，部分运行仍依赖脚本和文件产物。

2026-07-10 审计确认了以下基线：前端类型检查通过，但全量测试有 1 个文案漂移失败；trade-service、strategy-service、data-service 分别有 40、14、13 个测试通过，但仓库根目录合并运行会因同名 `app` 包发生收集冲突；`daily_kline` 已到 2026-07-10，`daily_basic` 只到 2026-07-08，`adj_factor` 只到 2026-07-07；`screener.py` 约 8,700 行，多个前端页面超过 1,300 行；通用 backtest API 仍用历史涨幅代理预测值和因子校准结果，不能作为策略有效性证据。

本 PRD 不继续扩充业务功能。团队先让每次运行可以回答四个问题：用了哪天的数据、运行了哪个版本、结果是否通过样本外验证、系统是否能用自动测试复现。

## 2. Goal & Non-Goals

**目标**：在保留 React + FastAPI + PostgreSQL 技术栈和现有 API 路径的前提下，建立统一的质量门、数据就绪门、模型准入门和运行证据链，并拆解最危险的巨型模块。

**KPI**：

1. 主分支质量门连续 10 次运行保持前端类型检查、前端单测、核心微服务测试、构建检查全部通过。
2. 生产模式模型运行中，100% 记录 `target_trade_date`、数据就绪快照、模型版本、代码 commit、参数哈希和产物地址。
3. P0 模型的必需数据源在运行前达到同一目标交易日；任一必需源落后时，系统阻断运行并返回具体缺口。
4. schema drift 审计中 high 级未豁免项降为 0，medium 级未豁免项降为 0。
5. 所有可执行模型都具备扣成本、复权、无时间泄漏的样本外结果；没有证据的模型在 UI 和 API 中标为 `research`。
6. `auth → screener → diagnosis → strategy → backtest → paper trade` 全链路 smoke 在 UAT 连续 3 次通过。
7. `screener.py` 拆分后单个路由模块不超过 2,500 行，外部 API path、请求和响应契约保持兼容。
8. 生产 API 和页面中由固定值、随机数或分数映射生成的伪统计数量降为 0。

**Non-Goals**：

- 不新增业务页面、选股策略、行情供应商或实盘券商。
- 不以本次治理为理由调整策略参数或宣称收益提升。
- 不重写整套前端，不替换 React、FastAPI、PostgreSQL 或现有网关。
- 不新建通用工作流微服务；本阶段先统一运行契约和证据格式。
- 不把 UAT 通过等同于允许实盘。实盘仍需独立风险评审和签字。
- 不在本 PRD 内完成全部 224 个 Tushare API 的业务表建模。

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 产品负责人 | 看到每个功能的真实可用状态和阻塞原因 | 不把演示数据、空结果或服务故障误判为业务正常 |
| US-2 | 量化研究员 | 每次模型运行绑定数据日期、代码、参数和回测证据 | 能复现结果并区分样本内表现与样本外表现 |
| US-3 | 交易用户 | 下单前确认数据、模型和风控均处于可执行状态 | 避免过期数据或研究模型进入交易链路 |
| US-4 | 前端开发者 | 路由、菜单、权限和 API 类型由单一来源维护 | 修改页面时减少重复配置和契约漂移 |
| US-5 | 后端开发者 | 每个服务能独立测试并使用同一健康检查格式 | 在 CI 中快速定位真实失败，而不是包导入冲突 |
| US-6 | 数据工程师 | 查看所有必需表的目标日期、实际日期、覆盖率和回补状态 | 在模型运行前修复数据缺口 |
| US-7 | QA 工程师 | 用一组固定命令验证五条工作流 | 每次发布留下相同格式的证据 |

## 4. Acceptance Criteria

### 4.1 前端

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-FE-1 | P0 | 运行前端类型检查、全量单测和生产构建时全部返回 exit 0，且不存在跳过当前失败用例的配置 | `bash tools/codex-lowio.sh fe-typecheck`、`bash tools/codex-lowio.sh fe-test --run`、`cd frontend && npm run build` |
| AC-FE-2 | P1 | 新增、删除或修改一个受保护页面时，只修改一处路由注册数据即可同步菜单、权限、标题和路由 | 单测构造临时 route definition，断言四类派生结果一致 |
| AC-FE-3 | P1 | 页面不再从一个超过 1,000 行的 API 客户端直接获取全部业务接口；市场、选股、数据、模型、策略和交易 API 由独立模块导出 | 静态检查模块边界 + TypeScript 构建 |
| AC-FE-4 | P0 | 任一核心页面收到 `blocked`、`stale`、`unavailable` 或空数据响应时，显示原因、数据日期和建议动作，不显示伪造成功数据 | Vitest 分别注入四类响应并断言页面状态 |
| AC-FE-5 | P1 | 运行状态页通过真实 gateway readiness API 展示服务、数据库和必要依赖状态，不使用硬编码健康矩阵 | API mock 契约测试 + UAT 网络证据 |

### 4.2 后端与架构

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-BE-1 | P0 | 从仓库根目录执行统一测试命令时，每个微服务在隔离的工作目录和 Python 进程中运行，所有核心服务测试返回 exit 0 | `python3 tools/run_service_tests.py --core` |
| AC-BE-2 | P0 | 每个核心服务保留 `/api/v1/health` 兼容入口，并提供 `/api/v1/health/live` 与 `/api/v1/health/ready`；live 只表示进程存活，ready 检查本服务必需依赖并返回结构化原因 | pytest TestClient + 断开 PG/MLflow 场景 |
| AC-BE-3 | P1 | gateway readiness 汇总返回所有核心服务的状态、耗时和错误类型；单个服务失败不导致汇总接口 500 | gateway 单测模拟 200、503、timeout |
| AC-BE-4 | P1 | 拆分 `screener.py` 后，现有 `/api/v1/screener/*` 和 `/api/v1/supply-chain/*` 契约测试无需修改请求或响应即可通过 | `bash tools/codex-lowio.sh py services/screener-service/tests -q` |
| AC-BE-5 | P0 | 生产模式的 HTTP 请求不得直接通过 `subprocess` 启动数据同步或模型流水线；请求进入受控 job 接口并返回 `run_id` | 静态检查生产 router + API 行为测试 |
| AC-AR-1 | P0 | 所有跨服务模型响应包含统一 `run_id`、`model_metadata`、`data_readiness`、`result_status` 和 `fallback_reason` 字段 | OpenAPI schema 检查 + screener/prediction/diagnosis 合同测试 |
| AC-AR-2 | P1 | 架构清单为每个业务表声明唯一 owner 和允许写入者；发现非 owner 写入时审计脚本返回 exit 1 | 运行 ownership audit 并注入违规 fixture |
| AC-AR-3 | P0 | 新建数据库可由受控迁移和初始化流程复现；schema drift high/medium 未豁免项为 0 | fresh DB smoke + `schema_audit.py --fail-on medium` |
| AC-AR-4 | P0 | gateway 丢弃外部传入的 `X-Service-Auth` 和 `X-Owner-User-Id`，owner 从已验证 JWT 重建；tenant/account 选择由所属服务再次校验 | gateway header 单测 + 越权负向测试 |

### 4.3 数据采集

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-DATA-1 | P0 | `GET /api/v1/data/readiness?profile=<model>&trade_date=<date>` 返回目标日期、截止时间、每个必需源的实际日期、覆盖率、状态和原因 | data-service API 测试 + 本地 PG 查询比对 |
| AC-DATA-2 | P0 | 任一必需源落后于目标交易日或覆盖率低于 profile 阈值时，readiness 返回 409/blocked，模型运行不启动 | 删除 fixture 中一张表当日数据并断言阻断 |
| AC-DATA-3 | P0 | 需要复权收益的 profile 在 `adj_factor` 落后于 `daily_kline` 时被阻断，不允许使用原始 close 代替复权收益 | 数据门禁单测 + 回测集成测试 |
| AC-DATA-4 | P1 | schema 审计同时输出 Markdown 和 JSON，包含 severity、owner、豁免原因和截止日期；过期豁免导致 exit 1 | 审计脚本单测 + CI 运行 |
| AC-DATA-5 | P0 | `KRONOS_ENV=production` 下缺少 PG 或必需数据时，因子引擎返回显式失败，不降级为空 stub 或 SQLite | 环境变量行为测试 |
| AC-DATA-6 | P1 | 数据目录区分 `collected`、`requires_params`、`unsupported_api`、`planned`，并显示最近成功采集时间与行数 | 数据目录生成测试 + 文档 diff |

### 4.4 算法模型

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-ML-1 | P0 | 每次正式模型运行生成不可变 manifest，包含模型键、版本、代码 commit、参数哈希、目标交易日、截止时间、数据快照、股票池哈希、成本、产物和最终状态 | pipeline 单测 + JSON schema 校验 |
| AC-ML-2 | P0 | 正式 walk-forward 和发布流水线强制时间线检查；策略 commit 晚于样本外起始日期或工作区 dirty 时返回 exit 2 | `test_walk_forward_timeline.py` + CLI 集成测试 |
| AC-ML-3 | P0 | 通用 backtest API 不再用历史涨幅代理模型预测或用同一市场均值校准不同因子；未完成真实因子接入前接口返回 `unsupported`，不得返回可执行结论 | backtest-service 行为测试 |
| AC-ML-4 | P0 | 多日收益回测使用目标日期可得的复权因子、交易成本和滑点，并记录信号时点与成交时点 | 固定价格夹具验证收益数值 |
| AC-ML-5 | P0 | 模型注册为 `paper` 或 `production` 前必须同时通过数据就绪、样本外、回撤、成本和时间线五个 gate；任一失败返回具体 gate 结果 | training-service 注册测试 |
| AC-ML-6 | P1 | UI 和 API 把 `research`、`candidate`、`paper`、`production` 四种模型状态分开展示；只有 `paper` 和 `production` 可进入交易方案 | 前端权限测试 + strategy-service 合同测试 |
| AC-ML-7 | P1 | 同一模型的样本外报告至少包含基准收益、净收益、胜率、最大回撤、Sharpe-like、样本数和逐期结果 | report schema 测试 + 一个真实样本报告 |
| AC-ML-8 | P0 | 生产 API 和页面在缺少真实统计时返回 `insufficient_data` 或 `unsupported`，不得用固定值、随机数、模型分数映射或默认指标生成 IC、ICIR、Sharpe、收益、相关性、分层收益或模型置信度；此状态不得写权重或触发模型晋级 | 静态检查 + Screener、backtest、training、signal 行为测试 |

### 4.5 端到端与发布

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-E2E-1 | P0 | UAT 环境连续 3 次完成 auth、screener、diagnosis、strategy、backtest、paper order 和 account query，无 mock API | `python3 tools/full_stack_smoke.py` + 三份 JSON 结果 |
| AC-E2E-2 | P0 | 浏览器访问所有受保护路由时无白屏、无未处理异常；核心页面能显示真实数据或明确阻塞原因 | Playwright UAT + screenshot/network evidence |
| AC-E2E-3 | P0 | 交易相关变更通过 paper 模式、风控预检和审计日志验证；live 模式在没有券商连接和签字时保持阻断 | trade-service tests + UAT 审计记录 |
| AC-E2E-4 | P1 | 每个阶段都提供回滚点；回滚后旧 API 契约和数据库读取仍能工作 | 发布演练记录 + 回滚 smoke |
| AC-E2E-5 | P0 | xtquant 的下单、撤单、持仓和资产查询未接通真实 SDK 并完成对账前，live broker readiness 返回 blocked，任何 live 请求不得回落到 stub 成交 | trade-service 负向测试 + broker readiness UAT |

## 5. Design

团队采用渐进治理方案：不增加新微服务，先建立共享契约和四类门禁，再在兼容测试保护下拆分巨型模块。

- 前端：用 route registry 生成菜单、路由和权限；拆分 API 模块；统一 loading、empty、blocked、stale、error 状态。
- 后端：隔离微服务测试；增加 liveness/readiness；gateway 汇总 readiness；路由层只负责 HTTP 契约，业务逻辑进入 service/repository。
- 数据：data-service 提供 profile 驱动的 readiness snapshot；schema audit 进入 CI；生产环境禁用静默 fallback。
- 模型：统一 run manifest 和 admission gate；真实因子进入回测；研究模型与可执行模型分层。
- 发布：先跑合同测试和数据门禁，再跑真实 API smoke、浏览器 UAT，最后允许 paper 发布。

接口、数据结构和迁移顺序见详细设计文档。

## 6. Technical Constraints

- 保留 React 18、Vite、TypeScript、Ant Design、FastAPI、PostgreSQL 和现有 `/api/v1` 路径。
- 不在任务中顺带升级主要框架版本；依赖升级单独评审。
- 交易相关改动只在 paper 环境验证，禁止自动切换 live。
- `daily_kline.close` 按原始价格处理，多日回测必须结合 `adj_factor`。
- 正式模型运行必须连接 PostgreSQL；SQLite 和 neutral stub 只允许显式 dev/test 模式。
- 现有 dirty worktree 中的用户改动不得被重置或混入提交。
- 先写失败测试，再改实现；每个任务运行聚焦测试后才能进入下一门。
- API P95 目标：普通读接口 ≤ 500ms，readiness 聚合 ≤ 1s；耗时模型任务必须在 2 秒内异步返回持久化 `run_id`。

## 7. Cost Estimate

- 预估新增线上 LLM token：0。现有 LLM 功能不因本次治理增加调用频率。
- 预估 Agent Team 开发 token：2M–4M。单条工作流按 Medium/Large 管理，总项目按 Large Program 管理；任何一次 Large 会话遵守 `.claude/standards/cost-budget.md` 的 1.6M 提示线、2M 预算线和 3M 硬停线。
- 触发档位：Large。
- 预估实施周期：6–10 周。前两周完成 P0 可信度门，后续按工作流并行。

## 8. Out of Scope / Future Work

- Kubernetes、服务网格、消息队列和独立工作流编排平台。
- 全量替换同步数据库访问方式。
- 新策略研发、策略调参和收益承诺。
- 全量历史数据重新采集。
- 实盘券商接入扩展。
- 把所有巨型文件一次性拆完；本次优先处理 `screener.py`、前端路由和 API 客户端。

### 既有文档关系

| 文档 | 本 PRD 的处理方式 |
|---|---|
| `phase0-stabilization-2026-06-21.md` | 继承已完成的认证、审计和资金止血要求，不重复开发；在当前代码上复验 |
| `phase1-backtest-credibility-2026-06-22.md` | 保留为模型工作流输入；本 PRD 补充统一 manifest、准入门和禁止伪统计要求 |
| `data-pipeline-refactor-2026-06-12.md` | 以已落地代码和 Accepted 的 ADR-012 为准，不按仍为 Proposed 的 ADR-006 重新大改 |
| `full-stack-model-connectivity` 相关计划 | 继承真实 API smoke 和禁止浏览器 mock 的验收方式 |

## 9. Open Questions

以下问题不阻塞 P0 质量门和数据门实施，但会阻塞对应的 P1/P2 任务。

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | 哪些模型列入首批可执行模型白名单？ | product-lead | 2026-07-14 | 默认从 `configs/model_pipeline.json` 已启用模型中选择，不自动全量纳入 |
| Q-2 | 业务表最终采用单一迁移链，还是继续 init SQL + Alembic 双轨？ | tech-lead | 2026-07-14 | P0 先做 drift gate，最终合并方式需要 ADR |
| Q-3 | paper 模型晋级 production 的最大回撤和最小样本数阈值是多少？ | product-lead + ml-engineer | 2026-07-16 | 在真实样本分布出来前不写死收益阈值 |
| Q-4 | API 性能预算是否以单机 UAT 还是未来生产规格为准？ | tech-lead | 2026-07-16 | P0 先记录基线，不因未定阈值阻塞正确性治理 |

## 10. Sign-offs

- [x] product-lead: 初稿
- [ ] tech-lead: 架构、迁移和性能预算 review
- [ ] frontend-dev: 前端实施可行性确认
- [ ] backend-dev: 后端与数据实施可行性确认
- [ ] ml-engineer: 模型门禁与回测口径确认
- [ ] code-reviewer: 任务边界与风险检查
- [ ] qa-engineer: AC 可测性确认
- [ ] deploy-engineer: UAT、回滚和发布门确认

## Changelog

- 2026-07-10: 初稿，基于五域代码、测试、数据库和历史审计结果。
