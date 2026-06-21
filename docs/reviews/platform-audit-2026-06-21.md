# 速赢AI 平台全栈审计 — 综合报告（前端 / 后端 / 模型）

- 审计日期：2026-06-21
- 审计模式：只读分析（3 个域 agent 并行 + PL 综合），未启动服务、未改代码
- 子报告：
  - 前端：`docs/reviews/audit-frontend-2026-06-21.md`
  - 后端 + 数据 + 基础设施：`docs/reviews/audit-backend-2026-06-21.md`
  - 模型 + 量化策略：`docs/reviews/audit-model-2026-06-21.md`

---

## 0. 一句话结论

> **平台的工程骨架完整、认证层扎实、自动交易的风控设计专业，但「AI 驱动量化」的核心价值主张在三个层面同时落空：前端核心业务页登录后 401 跑不通、后端 LLM/训练/实盘/审计全是 stub 或假数据、模型 Kronos 与选股/回测完全解耦且回测不可信。当前既不能给真实用户用（业务跑不通 + 多个 P0 安全洞），也不能产生可信 alpha（回测零成本 + 样本内调参 + 幸存者偏差）。**

## 1. 评分总表

| 域 | 可用性 (Availability) | 有效性 (Effectiveness) | 最致命问题 |
|---|---|---|---|
| **前端** | 2.5 / 5 | 3 / 5 | Strategy/Trade/AutoTrade 登录态必然 401（裸 fetch 绕过鉴权） |
| **后端 + 数据** | 3 / 5 | 2 / 5 | KRONOS_SERVICE_SECRET 硬编码可越权 admin；strategy 全 stub；4 个 store 纯内存 |
| **模型 + 策略** | 3.5 / 5 | 1.5 / 5 | 回测零交易成本吃光 alpha；6 月样本内调参；Kronos 与选股解耦 |
| **平台整体** | **2.5 / 5** | **1.5 / 5** | 价值主张落空 + 多个 P0 安全/启动洞 |

---

## 2. 跨域交叉验证洞察（综合报告核心增值）

> 单看任一域报告只能看到局部问题；三个域对账后，浮现 5 个**系统性结构问题**——它们才是真正决定平台生死的根因。

### 洞察 1：「AI 驱动量化」三层全线落空（核心定位危机）

平台对外宣称「自研 Kronos K线预测 Transformer + AI 方案生成」，但三域对账显示这条链路**从 UI 到模型全断**：

| 层 | 宣称 | 实际（证据） |
|---|---|---|
| 前端 | AI 方案 / 预测 / 诊断页 | Predictions 页裸 fetch、Strategy 页 9 处裸 fetch 全 401、Diagnosis 用 DEV mock 掩盖断链（frontend 报告 P0-1 / P1-1） |
| 后端 | strategy-service 用 DeepSeek 生成方案 | **grep 全服务零 LLM 引用**，`/optimize` `/report` 返回硬编码中文模板（backend 报告 P1-5） |
| 模型 | Kronos 驱动选股/回测 | **bi_trend 全源码 grep `kronos` 0 命中**；prediction-service 跑的是 HuggingFace 公开 `NeoQuasar/Kronos-mini`，自研 checkpoint 只有 16MB demo 玩具权重（model 报告 P0-3 / §2.1） |

**结论**：实际产品 = 「OBV+WR+ADX 规则选股 + 纯规则 T+1 回测 + K线预测展示页」。要么改产品定位（撤"AI 选股"宣传），要么真正把 Kronos 30 日预测接入 bi_trend 评分维度并 A/B 验证增量。**这是 P0 级的产品决策，不是技术细节。**

### 洞察 2：资金链整条未打通，但风控设计是真的

| 组件 | 设计层 | 落地层 | 缺口 |
|---|---|---|---|
| RiskGateway（6 维风控） | ✅ 严谨 | ⚠️ 涨跌停只对 >1 万元告警，A 股 ±10% 未做 | 需昨收价 |
| CircuitBreaker（5% 日亏熔断） | ✅ 三态机 + DB 持久化 | ⚠️ 表只在 alembic 002，docker 首启不存在则退回内存 | P0-2 连带 |
| 防静默 fallback | ✅ 拒绝静默降级 stub | ✅ 落地 | — |
| **XtquantBroker 实盘下单** | ✅ 抽象完整 | ❌ **全部 `# TODO: wire`**（P1-7） | 功能不存在 |
| **Audit Log** | ✅ 模块写完整 | ❌ **routes 只 logger.info，没接 DB**（P0-5） | 资金操作不可追溯 |
| **风控函数异常处理** | ✅ 逻辑实现 | ❌ **裸 psycopg2.connect + try/except 吞异常 → DB 挂时继续下单不止损**（P2-6） | 真实资金风险 |

**结论**：「防护了不存在的实盘」——风控真跑、下单是 stub、审计没落盘。一旦 wire 上真 broker，P2-6 的「风控 DB 挂则不止损」会直接变成真实资金损失。**必须在接 xtquant 之前修复 P2-6 + P0-5。**

### 洞察 3：鉴权防线「前紧后松」——认证扎实但下游裸奔

- backend auth：Argon2id + JWT + Refresh family 重放检测 + RBAC = **行业水准以上**（backend 报告 §4.1）。
- 但下游 8 个业务 service（screener/prediction/signal/backtest/diagnosis...）**路由普遍无 `require_role` 依赖**，全靠 gateway 转发 token——**gateway 不过滤也不校验**（backend 报告 §4.4）。
- 叠加 **KRONOS_SERVICE_SECRET 硬编码默认值**（`dev-service-secret-change-in-production`），任何人带 `X-Service-Auth` 头即可越权 admin，含「切换实盘 / 重置熔断器」（backend P0-3）。

**结论**：知道默认值的人直接访问 `localhost:8006` 即可绕过全部认证调用 admin 交易端点。**这是最高优先级安全洞。**

### 洞察 4：数据双轨——同一只股票不同服务看到的可能不一样

- prediction-service 只读 **SQLite** `stock_screening.db`（routes.py:174），不经 pg_adapter。
- bi_trend / screener / signal / backtest 走 **PostgreSQL**。
- 列名映射（`pct_chg` vs `change_pct`、`ts_code` vs `code`）散落在 `pg_adapter._COLUMN_MAP`、`etl.py`、`pg_writer.py` 三处重复实现（backend 报告 §5.2）。
- `stocks` 表的 `market_cap/float_mv/pe_ratio/pb_ratio` 4 列**永远 NULL**（写入遗漏），导致估值因子全失效（backend P1-1）。

**结论**：「同一只股同一日」在 prediction 页和选股页可能数据不一致；Kronos 预测与 bi_trend 融合无数据基础。

### 洞察 5：回测不可信 = 整个策略迭代建立在沙地上

> 这是**全平台最根本的问题**。没有可信回测，所有 bi_trend V12→V13 的 15 次密集调参、所有「+1.60%/trade」的承诺都无意义。

| 偏差 | 存在 | 严重度 | 证据 |
|---|---|---|---|
| 零交易成本 | ✅ | **致命** | 往返 0.13-0.16% 吃光 +0.173% 聚合收益 → 归零（model P0-1） |
| 样本内调参 | ✅ | **致命** | 6 月 15 次调参 + 6 月回测 → +1.60% 是调参目标函数产物（model P0-2） |
| 幸存者偏差 | ✅ | 高 | 用 2026-06 的 ST 状态过滤 2026-01 股票池（model P1-2） |
| 策略声明未实现 | ✅ | 高 | 声称 hold_days 3-10 天 + TP 20/25% + 移动止损，回测只算 T+1（model P1-1） |
| 参数密度过高 | ✅ | 中 | 100+ 常量 + 15+ 权重，逐股 case-by-case 调出（model P2-4） |
| 加权不进产物 | ✅ | 中 | S 级降权只进 stdout，不进 JSON（model P1-4） |

---

## 3. P0 紧急清单（合并去重，按风险降序）

> 必须在面向任何真实用户 / 任何资金操作之前修复。

| # | 问题 | 域 | 风险 | 工作量 |
|---|---|---|---|---|
| **S1** | `KRONOS_SERVICE_SECRET` 硬编码默认值 → `X-Service-Auth` 越权 admin（含实盘/熔断） | 后端 | **最高（资金+越权）** | S |
| **S2** | `JWT_SECRET_KEY` 缺失时进程内随机 → 多实例/重启 token 全废 | 后端 | 高（认证崩溃） | S |
| **S3** | 13 个前端页 40+ 处裸 `fetch()` 绕过鉴权拦截器 → 核心业务页登录后 401 | 前端 | 高（业务全断） | S |
| **S4** | data-service `scheduler.py`/`pg_writer.py` 用 `SQL/Identifier` 未 import → 数据治理函数触发即崩，每日物化视图刷新从不成功 | 后端 | 高（数据腐烂） | S |
| **S5** | 双 schema 割裂：docker 首启只挂 `init_postgres.sql`（无 roles 表），backend lifespan `seed_roles` 抛异常启动失败 | 后端 | 高（首次部署崩） | M |
| **S6** | trade-service audit_log 没接 DB → 所有资金操作只在 stdout，重启/日志滚动即丢，不可追溯 | 后端 | 高（合规+资金） | M |
| **S7** | 回测零交易成本 → 所有回测盈利承诺不可信 | 模型 | 高（决策基础） | S |
| **S8** | SIT 测试套件 4 failed / 24 + worker 崩溃 → CI 破窗 | 前端 | 中（CI/质量门） | S |
| **S9** | auto_trading_executor 风控函数裸 connect + 吞异常 → DB 挂时继续下单不止损 | 后端 | 中（接实盘前必修） | M |

> 注：S7 单独是 S（加 `ret -= 0.13`），但重跑全部历史回测 + 解读翻转后的结论是后续决策，非纯工程量。

---

## 4. 优化路线图（分 4 阶段）

### 阶段 0 — 止血（~1-2 天，全部 S/M，解锁可用）

目标：让平台「能起来 + 业务跑通 + CI 绿 + 无可被秒破的安全洞」。

1. S1 / S2：密钥缺失即 `raise`，移除所有硬编码默认值。
2. S3：把所有裸 `fetch()` 改走 `client.ts` axios 实例（机械替换，享受拦截器）。
3. S4：给两个文件加 `from psycopg2.sql import SQL, Identifier`（5 行）。
4. S5：backend Dockerfile 入口加 `alembic upgrade head &&`。
5. S8：`fillRegisterForm` 改 `userEvent.type` 或显式 `validateFields`。
6. （前端 P1-1）删除 Diagnosis DEV mock fallback。

**验收**：`docker compose up -d` 全绿、登录后 Strategy/Trade/AutoTrade 能加载、`vitest run` 24/24 绿、`curl -H "X-Service-Auth: dev-..."` 被拒。

### 阶段 1 — 重建回测可信度（~1-2 周，模型的根）

目标：在动任何「提升收益」的事之前，先让回测指标值得相信。

1. S7：回测加交易成本（佣金 0.025% 双边 + 印花税 0.05% 卖单 + 过户费 0.001%）。
2. 实现 bi_trend 声明的多日持有 + 止盈/移动止损回测引擎（model P1-1）。
3. walk-forward / rolling window 替代整月回测，冻结参数跑 2024-2025 样本外（model P0-2）。
4. 修幸存者偏差：按 `trade_date` 关联 ST 标记，剔除历史曾戴帽/退市股（model P1-2）。
5. 加权逻辑进 JSON 产物（model P1-4）。

**验收门**：扣成本后聚合收益的符号 / 样本外 Sharpe-like > 0.2，才谈后续。**如果扣成本后是负的——这就是真实结论，策略需要重设计而非继续调参。**

### 阶段 2 — 接通「真东西」（~2-4 周，兑现价值主张）

目标：让 stub/假数据变成真实功能。

1. strategy-service 按 skill `agf-wiring-multi-llm-sdk` 接 DeepSeek，`/optimize` `/report` 走真 LLM（backend P1-5）。
2. training-service 接真实 PG 训练数据 + 真 MLflow，去掉 synthetic fallback（backend P1-6 / model P1-3）。
3. 4 个 in-memory store（alert/signal/plan/paper）切 PostgreSQL（backend P1-8）。
4. S6 + S9：audit_log 接 DB；风控函数用连接池 + DB 异常 fail-safe 暂停交易。
5. **产品决策**（洞察 1）：要么明确撤"AI 选股"宣传，要么把 Kronos 30 日预测作为 bi_trend 评分维度并 A/B 验证增量（model P0-3）。
6. XtquantBroker 按 ADR-002 wire（仅在产品决定上实盘时）（backend P1-7）。

### 阶段 3 — 质量 / 性能 / 可维护性（持续）

1. 前端：引入 TanStack Query + orval 从 OpenAPI 生成类型/hook（消除手写 fetch + `any`，P1-2/P1-4）。
2. 前端：路由级 lazy + ECharts 按需 + manualChunks，首屏 gzip 862KB → <300KB（P1-3）。
3. 后端：docker-compose 每 service 加 healthcheck；引入 OpenTelemetry（gateway/trade/strategy 主线 span）（P2-1/P2-2）。
4. 后端：补 trade/data-service/backend auth 单元测试（当前全仓仅 3 个测试文件，P2-4）。
5. 模型：`bi_trend_launch.py` / `bi_trend_full_market.py` 两份 2100 行近重复代码合并为单一可信源（P2-1）。
6. 数据：prediction-service 统一走 PG，消除 SQLite/PG 双轨（洞察 4 / P2-5）。
7. 全局：review CLAUDE.md "Verified Facts"（backend 端口、模型数等多处与代码不符，P2-3）。

---

## 5. 关键不确定项（动态验证才能坐实）

> 本次为只读静态审计，以下结论需启动服务 / 连库 / 跑回测才能 100% 坐实，但证据链已足够强：

1. 前端「401 跑不通」是基于「裸 fetch + 后端路由 require auth」静态对账，未做真实 HTTP（frontend §7.1）。
2. docker 首启崩是基于 lifespan + schema 双轨推断，未实跑 `compose up`（backend §8.1）。
3. Kronos-mini 在 A 股的预测精度未评估，P3 后处理 ±2% 偏置合理性未知（model §8.2）。
4. PG `daily_kline.close` 是否前复权未确认，影响绝对收益与回测真实性（model §8.1）。
5. `tools/backtest_bi_trend.py:444` `obv_score -= 5` 疑似 NameError 被 `except: continue` 吞掉 → 可能引入**选择性偏差**（静默跳过本该入选的股），需单测（model §8.5）。

**建议**：阶段 0 修完后，跑一次全栈动态验证（docker 全启 + curl 实测 + 重跑历史回测）坐实上述 5 项。

---

## 6. 给决策者的三条提醒

1. **先别再调参了**。在阶段 1（可信回测）完成前，任何新的 bi_trend 参数调整都是在「样本内 + 零成本」的假象上加码，越调越偏离真实。
2. **「实盘交易」目前是零风险也是零功能**。风控设计是亮点，但 broker/audit/风控异常处理三个落地缺口意味着——一旦真正 wire 上 broker，资金风险会立刻变成现实。**接实盘前必须先修 S6 + S9**。
3. **最大的 ROI 在阶段 0 + 阶段 1**，不在新功能。用 ~2 天堵住安全洞和业务断链，用 ~2 周确认策略到底赚不赚钱——比任何新页面、新因子、新模型都重要。

---

**综合报告完。三份子报告含完整证据链与逐条 file:line，本报告仅做顶层视图与跨域综合。**
