# 速赢AI 后端 + 数据 + 基础设施审计报告

> 审计日期：2026-06-21  
> 审计范围：`backend/`（认证）、`services/{api-gateway, alert, backtest, data, diagnosis, prediction, screener, signal, strategy, trade, training}-service/`、`packages/{kronos-data, kronos-auth, kronos-factors, kronos-core}`、`docker/docker-compose.yml`、`services/sql/`  
> 方法：只读代码审查（文件路径 + 行号证据），未启动任何服务、未跑任何 destructive 命令

---

## 1. 总体结论

| 维度 | 评分（1-5） | 说明 |
|---|---|---|
| **可用性**（在已知前置下能起来） | **3** | 认证链路（JWT + Argon2id + Refresh family 重放检测）严谨；但 docker-compose 首次启动会因双 schema 系统分裂而失败；3 个核心数据治理函数有 NameError bug；自动交易引擎有结构性隐患。 |
| **有效性**（接口返回真实数据、非 stub/mock） | **2** | 7 个 service 中有 4 个核心功能处于 stub/mock/placeholder：LLM 方案生成（宣称 DeepSeek 实际未接）、实盘交易（xtquant 未 wire）、训练管线（placeholder）、审计日志（未接 DB）、alert 多渠道（仅 in-memory app 推送）。回测的"IC 校准"和"IC 衰减追踪"是逻辑假数据。 |

**一句话**：认证层（Argon2id / JWT / Refresh family 重放检测 / RBAC）做得相当扎实，但周边业务有效性差，且存在多个**会导致首次部署失败或运行时崩溃**的 P0/P1 bug。系统目前**远未达到"实盘交易"状态**，对真实资金的防护只是设计层面的纸面承诺。

---

## 2. 服务清单与真实状态

| service | 端口 | 职责（声明） | 实现完成度 | 关键风险 |
|---|---|---|---|---|
| `backend` (auth) | 9001*（main.py:38 默认 8000）| JWT/Argon2id/RBAC/用户管理 | **90%** 真实可用 | schema 与 init_postgres.sql 割裂（首次 docker 启动 roles 表不存在 → seed admin 失败） |
| `api-gateway` | 8080 | 反向代理 + 限流 | **70%** 可用 | urllib 同步代理（每个请求阻塞 1 个 executor 线程，30s 超时占用 worker）；rate store 内存不清理 |
| `screener-service` | 8001 | 选股（kronos-factors 6 模型） | **80%** 真实 | PG/SQLite 双适配器，路径 hack sys.path；启动 socket.setdefaulttimeout(5) 全局污染（main.py:43） |
| `prediction-service` | 8002 | Kronos 30 日 K 线预测 | **70%** 真实 | 启动从 HuggingFace 拉 `NeoQuasar/Kronos-*`（线上网络依赖）；auxiliary score 链式比较 bug（routes.py:369）；`app.main._predictor` 跨模块全局，难测 |
| `strategy-service` | 8003 | "LLM 方案生成 + 自动交易引擎" | **20%** | **完全没接 LLM**（grep 全服务无 `DEEPSEEK`/`openai` 任何引用）；`/optimize`、`/report` 返回硬编码中文模板；PlanStore 内存；自动交易执行器真实但下游 broker 是 stub |
| `signal-service` | 8004 | 50 维综合交易信号 + dashboard 聚合 | **75%** 真实 | signal_store 内存；dashboard_summary 单 endpoint 拉全市场，潜在慢查询 |
| `alert-service` | 8005 | 多渠道预警 | **30%** | 完全无 DB（alert_store.py:1 注释 "In-memory alert store"），重启数据丢失；`/channels` 明示 wecom/dingtalk/email 全部 `enabled: False`（routes.py:61-63） |
| `trade-service` | 8006 | 模拟/实盘交易 + 风控 | **40%** | PaperEngine 内存（engine.py:132 单例）；XtquantBroker 完全 stub（xtquant_broker.py:120-161 全部 `# TODO: wire to xtquant.xttrader.*`）；**audit_log 模块写了但 routes 没接 DB**（routes.py:510-520 返回硬编码空数组） |
| `backtest-service` | 8007 | 回测 + IC/ICIR 校准 | **50%** | `/run` 有真 IC 计算但严重 N+1（30 股 × 4 查询/股 × N 窗口）；`/calibrate` 和 `/ic-decay` 是**假数据**（routes.py:255 `ic_val = round(avg_ret / 10, 4)`，routes.py:651-660 全部返回固定 neutral） |
| `diagnosis-service` | 8009 | 五维个股诊断 | **80%** 真实 | 评分逻辑真；PDF 渲染依赖 Playwright 可用性（routes.py:48 检测）；schema 与 init_postgres.sql 分裂 |
| `training-service` | 8008 | 模型训练 + MLflow | **15%** | `training_engine.py:667` 注释自承 "placeholder until Kronos fine-tune is ready (ADR-004)"；MLflow 默认 MockMlflowClient（mlflow_client.py:23，本地 JSON），LiveMlflowClient 虽实现但 docker-compose 未配 tracking server |
| `data-service` | 8010 | Tushare 数据采集 + 调度 | **60%** | 业务逻辑真实，但 **scheduler.py / pg_writer.py 多处 NameError**（用了 `SQL(...)` 和 `Identifier(...)` 但没 import）；scheduler 模块级 PG 全局状态 |

> *CLAUDE.md 与代码不一致：CLAUDE.md 写 `backend 9001`，但 `backend/app/config.py:38 PORT=8000`。docker-compose.yml:71 暴露 `9001:9001`，但容器内 uvicorn 默认监听 8000 → **backend 容器启动后无法从 host:9001 访问**（端口不匹配）。

---

## 3. 发现的问题

### P0（会导致首次部署失败 / 运行时崩溃 / 资金损失）

#### P0-1　数据治理函数多处 NameError（运行时崩溃）
- **证据**：
  - `services/data-service/app/scheduler.py:204, 433, 449, 472` 使用 `SQL(...)` 和 `Identifier(...)`，但全文 grep 无 `from psycopg2.sql import SQL, Identifier`（AST 验证：scheduler.py uses SQL/Identifier=True, imports them=False）。
  - `services/data-service/app/sync/pg_writer.py:181` 同样使用 `SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(Identifier(view))`，未导入。
- **影响**：`detect_data_gaps()`、`run_data_quality_report()`、`refresh_materialized_views()` 这些 L4 数据治理关键函数**触发即崩**。其中 `refresh_materialized_views` 是 scheduler 每个交易日 15:37 的定时任务（scheduler.py:951），意味着每日盘后物化视图刷新**从不成功**；物化视图过期 → 前端 dashboard 看到的"今日强势股"、"板块动量"等是旧数据。
- **建议**：在每个文件顶部加 `from psycopg2.sql import SQL, Identifier`（5 行修复）。Workload: **S**。

#### P0-2　双 schema 系统割裂（docker-compose 首次启动失败）
- **证据**：
  - `docker/docker-compose.yml:32` 仅挂载 `init_postgres.sql:ro` 作为 PG entrypoint。
  - `services/sql/init_postgres.sql` 共 65 张业务表，但 `grep users|roles|refresh_tokens|circuit_breaker|training|diagnosis|audit` 在该文件中**全部 0 命中**。
  - 这些表只存在于 `backend/alembic/versions/001-006.py`（6 个 alembic 迁移）。
  - `backend/Dockerfile` 启动命令是 uvicorn，**不在 docker-compose entrypoint 中跑 `alembic upgrade head`**。
- **影响**：
  1. `docker compose up -d` 后 backend lifespan 启动时调用 `seed_roles(db)` → `INSERT INTO roles` → **表不存在 → 抛异常 → startup 失败**（backend/app/main.py:25）。
  2. 即便手动跑 alembic，alembic env.py 用 `DATABASE_SYNC_URL`（psycopg2），而 backend app 用 `DATABASE_URL`（asyncpg），schema drift 完全无法自动检测。
- **建议**：让 init_postgres.sql 显式 source alembic，或在 backend Dockerfile 入口加 `alembic upgrade head && uvicorn ...`。Workload: **M**。

#### P0-3　KRONOS_SERVICE_SECRET 默认值可被任意越权（安全漏洞 + 资金风险）
- **证据**：
  - `packages/kronos-auth/kronos_auth/config.py:10-13`：`KRONOS_SERVICE_SECRET = os.environ.get("KRONOS_SERVICE_SECRET", "dev-service-secret-change-in-production")` —— **硬编码默认值**。
  - `packages/kronos-auth/kronos_auth/deps.py:68-77`：任何请求只要带 `X-Service-Auth: dev-service-secret-change-in-production` 即被视为 `role=admin`，**绕过 JWT、绕过 Argon2id、绕过 refresh token**。
  - `services/trade-service/app/routes.py:328-363`（switch to live mode）、`:366-428`（broker connect）、`:465-492`（circuit breaker reset）—— 全部 admin-only，全部可被 `X-Service-Auth` 绕过。
- **影响**：知道默认值的人可无 JWT 调用所有 admin 端点，包括切换到实盘交易、重置熔断器（绕过当日 5% 亏损保护）。CLAUDE.md "密钥从不进代码" 铁律被违反。
- **建议**：`KRONOS_SERVICE_SECRET = os.environ["KRONOS_SERVICE_SECRET"]`（缺失即启动失败，与 `JWT_SECRET_KEY` 同等待遇）。Workload: **S**。

#### P0-4　JWT_SECRET_KEY backend 启动随机化，导致多实例 token 互不兼容
- **证据**：`backend/app/config.py:16-21`：未设 env 时 `secrets.token_hex(32)` 生成**进程内随机** secret（仅 `warnings.warn`，不 raise）。
- **影响**：
  1. 多副本部署时，每个实例签发的 JWT 互不识别（用户从 gateway 路由到任意实例时 token 失效）。
  2. 进程重启后所有签发过的 access/refresh token **全部作废**，用户被强制登出。
  3. docker-compose.yml:74 默认值 `dev-secret-change-in-production`（明文，非 dev-secret 短串），但生产硬编码风险仍在。
- **建议**：启动时缺失即 raise（与 KRONOS_SERVICE_SECRET 同步）。Workload: **S**。

#### P0-5　实盘交易审计日志完全未接 DB（资金风险）
- **证据**：
  - `services/trade-service/app/audit_log.py`（200 行）有完整的 `record(db, ...)` 和 `query(db, ...)` 实现。
  - 但 `services/trade-service/app/routes.py:525-544` 的 `_audit_record_safe` 只做 `logger.info(...)`，注释明示 "In production: from app.audit_log import record"（**当前没调用**）。
  - `services/trade-service/app/routes.py:497-520` 的 `/audit-logs` 接口返回硬编码 `{"total": 0, "records": [], "note": "Audit log requires a PostgreSQL database session..."}`。
- **影响**：所有交易（含切 live mode、broker connect、circuit breaker reset）**只在 stdout 留日志，无 DB 落盘**。容器重启或日志滚动后审计链断。监管/合规层面这是**重大缺陷**，更关键的是出问题时**无法追溯**真实资金操作历史。
- **建议**：trade-service 接 asyncpg session（与 diagnosis-service 一样的 database.py + get_db），在 `_audit_record_safe` 中 `await record(db, ...)`。Workload: **M**。

---

### P1（功能性 bug / 性能问题 / 数据质量问题）

#### P1-1　stocks 表 market_cap/float_mv/pe_ratio/pb_ratio 永远 NULL
- **证据**：
  - `services/sql/init_postgres.sql:10-22`：`stocks` 表有 `market_cap`、`float_mv`、`pe_ratio`、`pb_ratio` 列。
  - `services/data-service/app/sync/stocks.py:67-72` 和 `:142-148` 的 INSERT 只写 `code,name,board,industry,listed_date,is_st,updated_at` —— **遗漏 4 个估值列**。
  - `services/data-service/app/scheduler.py:457-459` 的数据质量报告检测 `stocks.market_cap IS NULL AND is_st=0`，但永远全表告警。
- **影响**：依赖 `stocks.market_cap` 的所有下游（估值因子、PE 分位、POR 估值因子等）都失效，相关因子回到 fallback 默认值。`hard_tech`、`por`、`long_term` 等回测因子在 init_postgres.sql 中声明但实际无数据。
- **建议**：stocks.py 写入时联表 `daily_basic`（已有 PE/PB/总市值），或新增 `stock_profiles` 拉取。Workload: **M**。

#### P1-2　backtest `/run` 严重 N+1 查询
- **证据**：`services/backtest-service/app/routes.py:130-164`：对每只 picks 股票，循环内做 **4 次** PG 查询（fwd close、now close、adj latest、adj fwd、adj now），30 股 × N 窗口 = 数百次查询/请求。
- **影响**：`/run?windows=6&top_n=30&forward_days=60` 的单请求 = 6 × 30 × 4 ≈ 720 次 PG 往返，按每次 5ms 计就是 3.6s 仅 DB 部分。多个并发回测请求会打爆连接池。
- **建议**：改成单条 `WHERE code IN (...)` + `GROUP BY code` 拿全部窗口数据。Workload: **M**。

#### P1-3　backtest `/calibrate` 与 `/ic-decay` 返回假数据
- **证据**：
  - `services/backtest-service/app/routes.py:255` `ic_val = round(float(avg_ret) / 10, 4)` —— 所有因子取**同一个** `avg_ret / 10` 作为"IC proxy"，不是真 IC。
  - `services/backtest-service/app/routes.py:651-660`：所有因子返回相同的 `{"status": "tracking", "current_weight_multiplier": 1.0, "recommendation": "neutral"}`，注释明示 "Simplified: use daily returns as proxy"。
- **影响**：UI 展示"IC 校准"和"因子 IC 衰减"全无业务意义，前端给用户看的"建议权重"是垃圾。但这些假权重会写入 `factor_weights` 表（routes.py:267-279）影响下游选股（如果选股模块读这张表）。
- **建议**：要么实现真 IC（rolling spearman with forward return），要么在路由明确返回 `status: "stub"` 让前端不展示。Workload: **M**。

#### P1-4　prediction-service routes.py:369 链式比较 bug
- **证据**：`services/prediction-service/app/routes.py:369`：`vb = 2.0 if (5<(feats.get("pe",0)<25) and (feats.get("pb",0)<3)) else (-2.0 if feats.get("pe",0)>100 else 0)`。
- Python 解析 `5 < (pe < 25)` = `5 < bool(...)` → 恒 False（因 Python `5 < True` = False，`5 < False` = False）。
- **影响**：`/prediction/{code}/meta` 的 valuation bonus 永远不是 2.0（除非 PE>100 时给 -2.0），与设计意图（PE ∈ [5,25] 给正分）相反。
- **建议**：改成 `5 < pe < 25 and pb < 3`。Workload: **S**。

#### P1-5　strategy-service 完全没接 LLM（CLAUDE.md 宣称 vs 实际）
- **证据**：
  - CLAUDE.md "AI/ML" 一行写 "DeepSeek (方案生成, strategy-service)"，"LLM SDK" 写 "DeepSeek"。
  - `grep -rn "DEEPSEEK\|deepseek\|openai" services/strategy-service/app/` = **0 命中**（确认：main.py docstring 提 "LLM-powered" 但代码无 LLM 引用）。
  - `services/strategy-service/app/routes.py:137-148`：`/optimize` 返回硬编码 `{"status": "optimized", "message": "优化完成 (Kronos预测对接中)"}`。
  - `services/strategy-service/app/routes.py:151-225`：`/report` 全部 `tech_analysis`、`capital_analysis` 等是**固定中文字符串模板**（"均线多头排列，MACD金叉"、"主力净流入，北向增持"），与具体股票无关。
- **影响**：所有"AI 生成方案"是字面意义的前端模板字符串。skill `agf-wiring-multi-llm-sdk` 未被遵守。
- **建议**：按 skill 接 DeepSeek，至少接通 `/optimize` 走真 LLM。Workload: **L**。

#### P1-6　training-service 是 placeholder
- **证据**：
  - `services/training-service/app/training_engine.py:667`：函数 docstring 自承 "Synchronous Kronos fine-tune training (placeholder). This is a placeholder until Kronos fine-tune is ready (ADR-004)"。
  - `services/training-service/app/mlflow_client.py:23`：`MockMlflowClient` 是 in-memory mock（本地 JSON 文件持久化），docker-compose.yml 未配 MLflow tracking server。
- **影响**：UI 上点"训练"会返回 job_id，但后台跑的是模拟流程；模型 registry 也是 mock。生产上线后**无法真正迭代模型**。
- **建议**：在 PRD 中明确"训练功能为 demo 占位"，或集成真 MLflow + Kronos 微调。Workload: **L**。

#### P1-7　XtquantBroker 完全 stub（实盘资金风险已消除但功能不成立）
- **证据**：`services/trade-service/app/xtquant_broker.py:120-161`：`place_order`、`cancel_order`、`get_positions`、`get_account` 全部 `if _XTQUANT_AVAILABLE: # TODO: wire to xtquant.xttrader.*`，然后 fall through 到 stub（routes.py:127 logger.info "xtquant place_order not yet wired — falling back to stub"）。
- **缓解**：当 xtquant SDK 真存在但未连接时，broker 会 `raise RuntimeError("拒绝静默 fallback 到 stub")`（xtquant_broker.py:122-125）—— **这个防护是好的**，避免了"以为在实盘实际是 stub"的灾难性混淆。
- **影响**：实盘交易功能**完全不存在**，但 RiskGateway + CircuitBreaker + 防静默 fallback 的设计是真做了的。
- **建议**：要么在 PRD 中标注实盘功能未实现，要么按 ADR-002 完成 xtquant wire（Windows QMT 环境下）。Workload: **L**。

#### P1-8　alert-service / signal-store / plan-store / paper-engine 全部纯内存
- **证据**：
  - `services/alert-service/app/alert_store.py:1` "In-memory alert store"，重启数据丢失，限制 200 条。
  - `services/signal-service/app/signal_store.py:17`：`SignalStore` 内存 dataclass。
  - `services/strategy-service/app/plan_store.py:20`：`PlanStore` 内存 list，重启所有"方案"丢失。
  - `services/trade-service/app/engine.py:132`：`_engine = PaperTradingEngine()` 单例，重启所有持仓和订单消失。
- **影响**：所有"持久化"的功能（方案、纸面交易持仓、信号历史、预警历史）**重启即丢**。多实例（CLAUDE.md 说 backend-dev pool 上限 5）下数据完全不一致。
- **建议**：把这 4 个 store 切到 PostgreSQL（backend 已有 asyncpg 模式可复用）。Workload: **L**（最大块）。

#### P1-9　api-gateway 用 urllib 同步代理 + 内存限流不可扩展
- **证据**：
  - `services/api-gateway/app/main.py:79-83`：`loop.run_in_executor(None, _proxy)`，每个请求占用一个默认线程池线程；`urlopen(req, timeout=30)` 同步阻塞 30s。
  - `services/api-gateway/app/main.py:20, 39-46`：`_rate_store` 是进程内存字典，**永不清理过期 key**，长期运行内存泄漏。
  - `services/api-gateway/app/main.py:52`：health check path 判断 `if path in ("api/health", "health")`，但 `@app.api_route("/{path:path}")` 已捕获所有路径，逻辑上 health 端点在 `8080/health` 时 `path="health"` 成立；但用户访问 `8080/api/v1/auth/login` 时 path 为 `api/v1/auth/login`，路由表 SERVICES 用 `/api/v1/auth` 前缀匹配 OK；问题在于 `full = "/" + path`（gateway.py:61）拼成 `/api/v1/auth/login`，与 SERVICES key `/api/v1/auth` startswith 匹配。**逻辑通**，但单点故障 + 单线程并发受限。
- **影响**：所有前端请求过 gateway；gateway 单实例、无健康依赖检查、限流内存不可扩展。
- **建议**：换 nginx/caddy 反向代理 + Redis-based rate limiter。Workload: **M**。

---

### P2（代码质量 / 一致性 / 可观测性）

#### P2-1　docker-compose 8 服务全无 healthcheck（只有 pg/redis 有）
- **证据**：`docker/docker-compose.yml` 全文 grep `healthcheck` 只命中 postgres:33-37 和 redis:43-47。所有 service 容器即便挂掉也不会被 `restart: unless-stopped` 知道。
- **建议**：每个 service 加 `healthcheck: curl /api/v1/health` 或 python urllib probe。Workload: **M**。

#### P2-2　无 metrics / tracing（仅 basicConfig 日志）
- **证据**：`grep -rn "prometheus\|opentelemetry\|otlp\|tracing\|metrics" services backend | grep -v __pycache__ | wc -l` = **119**，但全部是业务字段命名（如 `total_metrics`、`model_metrics`），**无任何可观测性 SDK**。
- **影响**：12 个微服务跨调用无法追踪一次用户请求的全链路；熔断器、限流、SLA 无量化依据。
- **建议**：引入 OpenTelemetry SDK，至少在 gateway + trade + strategy 三条主线加 span。Workload: **L**。

#### P2-3　CLAUDE.md 多处与代码不符（文档腐烂）
- 实例：
  - 端口表 `backend 9001` vs `config.py:38 PORT=8000`，docker `9001:9001` 但容器内默认 8000。
  - "screener-service ... 6 模式选股" vs "12 模型"（docker-compose.yml:8 注释）—— 实际看 `screener-service/app/orchestrator.py` 应核对。
  - "data-service + training-service ... 3 个手动启动"——docker-compose 8 + 手动 3 = 11，但 CLAUDE.md 端口表只有 11 行（包含 backend/auth），所以"11 services"实际包含 backend，与 services/ 目录下 11 个子目录一致；表述不清。
- **建议**：review CLAUDE.md "Verified Facts" 段，所有数字跑一次验证脚本。Workload: **M**。

#### P2-4　测试覆盖严重不足
- **证据**：`find services -name test_*.py | wc -l` = **1**；`find backend/tests -name test_*.py | wc -l` = **2**。
- 11 个服务总计 3 个测试文件。考虑到 trade/strategy 涉及资金、data-service 涉及数据完整性，这是高风险。
- **建议**：至少 trade-service（RiskGateway、CircuitBreaker）+ data-service（pg_writer 重试 + 数据量门禁）+ backend auth（refresh token 重放检测）补单元测试。Workload: **L**。

#### P2-5　prediction-service `_get_kline` 只读 SQLite，不读 PG
- **证据**：`services/prediction-service/app/routes.py:174-198` `_get_kline` 用 `sqlite3.connect(DB_PATH)` 读 `daily_kline`；而 `_get_auxiliary_features`（routes.py:49-114）才走 PG。
- **影响**：如果生产只配 PG（KRONOS_DB_PATH 未设），prediction 直接 404；同时 SQLite 与 PG 数据可能不同步（`stocks.py` 双写策略，但 `daily_kline` 写 PG + SQLite fallback，两边列名、类型、时区不一致风险）。
- **建议**：统一走 PG，或显式声明 SQLite 是 prediction 的事实 DB。Workload: **M**。

#### P2-6　auto_trading_executor 每次循环裸 `psycopg2.connect`
- **证据**：`services/strategy-service/app/auto_trading_executor.py:476-497`（_check_announcement_risk）、`:508-539`（_get_atr_stop_loss）、`:547-564`（_check_forecast_risk）：每个函数体都 `psycopg2.connect(pg_url, connect_timeout=3)` + `conn.close()`，且都包在 `try/except: return` 里**吞所有异常**。
- **影响**：自动交易循环（默认 5 分钟一轮）每只持仓都做 3 次 connect/close；并且**异常全部静默**（return False/""），意味着风控数据库故障时自动交易**继续下单而不止损**。
- **建议**：用连接池（asyncpg pool 或 sqlalchemy engine）；风控数据库异常时 fail-safe 暂停交易而非继续。Workload: **M**。

#### P2-7　所有 service 重复 `sys.path.insert(packages/...)` 模式
- **证据**：每个 service main.py 都有类似 `services/trade-service/app/main.py:11-15` 的 `_PACKAGES = ...; for _pkg in [...]: sys.path.insert(0, ...)`。
- **影响**：路径 hack 不可移植、IDE 跳转困难、CI 容易断。
- **建议**：用 pip editable install (`pip install -e packages/kronos-factors`)，Dockerfile 中固化。Workload: **S**。

#### P2-8　Alembic 缺少业务表迁移
- **证据**：`backend/alembic/versions/` 只有 6 个迁移，全是 auth/audit/training/diagnosis/legacy/snapshots。`init_postgres.sql` 的 65 张业务表（daily_kline, moneyflow, announcements 等）**没有对应的 alembic 迁移**。
- **影响**：任何对业务表的 schema 修改（加列、加索引）只能改 init_postgres.sql，对已存在的库**不会生效**（CREATE TABLE IF NOT EXISTS 跳过）。CLAUDE.md "alembic upgrade head" 命令在干净环境上跑完，业务表仍不存在。
- **建议**：要么把 init_postgres.sql 转成 baseline alembic 迁移，要么明确"业务表用 SQL，auth/training 用 alembic"的双轨约定并写进 ADR。Workload: **L**。

---

## 4. 安全专项

### 4.1 认证链路（整体良好）
- `backend/app/routers/auth.py` + `auth_service.py` + `deps.py` 设计严谨：
  - Argon2id 参数可配（time=3 / mem=65536 / parallel=2，auth_service.py:26-30）。
  - Refresh token 用 family + DB 持久化，rotate 时整族撤销，**重放检测**正确实现（auth_service.py:200-250，220-225）。
  - `require_role(*roles)` 工厂依赖可用（deps.py:75-95）。
  - access/refresh token type 校验（deps.py:47）。
- Cookie 配置：`httpOnly + Secure + SameSite=Strict + path=/api/v1/auth`（auth.py:43-53），符合 ADR-001。

### 4.2 密钥管理（有 P0 漏洞）
| 项 | 评级 | 证据 |
|---|---|---|
| `JWT_SECRET_KEY` | **P0** | backend/app/config.py:16-21，未设 env 时 `secrets.token_hex(32)` 进程内随机，仅 warn 不 raise；多实例/重启即 token 全废 |
| `KRONOS_SERVICE_SECRET` | **P0** | kronos-auth/config.py:10-13，硬编码默认 `dev-service-secret-change-in-production`；可被 `X-Service-Auth` 头越权为 admin（含 live trade 端点）|
| `ADMIN_PASSWORD` 默认 `Admin123!` | **P1** | config.py:33，docker-compose.yml:76 也明文默认；任何看过 CLAUDE.md 的人都能登 admin |
| `KRONOS_PG_URL` / `DATABASE_URL` 默认 `kronos:kronos@localhost` | **P2** | 多处默认弱口令，仅 dev 友好；生产必须强制 env |
| `TUSHARE_TOKEN` / `DEEPSEEK_API_KEY` 默认空 | OK | config.py 不硬编码，缺失即跳过功能 |
| `.env` gitignored | OK | `scan-secrets.sh` hook + pre-commit 防御（CLAUDE.md Tool Boundaries）|

### 4.3 SQL 注入防护
- **参数化查询整体良好**：auth_service、pg_writer、data-service 的 sync 模块全部用 `%s` 占位符。
- **白名单场景使用 psycopg2.sql**：scheduler.py/pg_writer.py 本意用 `SQL(...).format(Identifier(table))` 防 table/column 注入（这是对的做法），但因未 import 触发 P0-1 NameError。
- **少量 f-string 拼接风险点**：
  - `services/backtest-service/app/routes.py:481-484`：`f"SELECT close FROM cb_daily WHERE {col}=%s ..."`，`col` 来自 `("ts_code", "code")` 白名单，安全。
  - `services/data-service/app/scheduler.py:218`：`f"SELECT MAX({date_col}) FROM {table}"`，date_col/table 来自 MONITORED_TABLES 静态字典，安全；但**SQLite fallback 路径**（scheduler.py:218）没走 Identifier，若未来字典扩到外部输入有风险。

### 4.4 RBAC 实际覆盖（端点 × 角色）
- trade-service：所有受保护端点都用 `Depends(require_role(...))`，覆盖正确（routes.py:125, 222, 230, 241, 271, 309, 329, 374, 432, 457, 469, 504）。
- backend admin：`require_role("admin")` 覆盖（admin.py:47, 66）。
- **缺口**：screener-service、prediction-service、signal-service、backtest-service、diagnosis-service 的路由**普遍无认证依赖**（grep 各 routes.py 无 `Depends(require_role)`）—— 全靠 api-gateway 转发时附 token；但 gateway 转发所有 header 包括 `Authorization`（api-gateway/app/main.py:77 不过滤），下游即便没校验也只是"裸奔"，**实际无授权检查**。等价于"任何能直接访问 8001-8009 端口的人都能调用选股/预测/回测"。

---

## 5. 数据管道专项（新鲜度 / 完整性 / PG-SQLite 一致性）

### 5.1 调度设计（健全）
- `services/data-service/app/scheduler.py:919-1072` 注册了 **42 个定时任务**，覆盖 L0（实时分钟线，交易时段每分钟）到 L4（每日 4:00 数据完整性检查 + 周六 4:30 数据质量），按 cron 严格错峰（9:25 竞价、15:30/15:35 盘后核心、16:00-17:45 风控/财务、18:00-19:00 资讯、周六/月度/每月 1 日周月级）。
- 重试策略：3 次指数退避（1s/4s/16s），与 ADR-006 决策 6 一致（scheduler.py:777-810，pg_writer.py:9-47）。
- 数据量门禁：<1000 行 ERROR、<3000 行 WARN（pg_writer.py:50-58）—— **这是好的设计**，能在 Tushare token 过期时立即报警。

### 5.2 PG-SQLite 双写一致性（设计良好但边界多）
- `stocks.py:56-99`：PG `INSERT ... ON CONFLICT DO UPDATE` + SQLite `INSERT OR REPLACE`，两边 schema 列名对齐（code/name/board/industry/listed_date/is_st）。
- 列名映射在 `pg_adapter._PgCursor._KEY_MAP` 和 `_COLUMN_MAP` 做（CLAUDE.md 项目规则）。
- **不一致点**：
  - `etl.py` 与 `pg_writer.py` 各自实现一遍写 PG 的逻辑，**列映射重复**（如 `moneyflow` 跳过 `net_mf_vol` 在 pg_writer.py:88；`daily_basic` 重排在 pg_writer.py:108）—— 易随 schema 漂移。
  - `pg_writer.write_ths_daily` 用 `ts_code` 作主键（pg_writer.py:165），其他表用 `code`，schema 不一致。

### 5.3 KRONOS_PG_URL 不设的坑（CLAUDE.md 提及，代码确认）
- `services/data-service/app/scheduler.py:53`、`stocks.py:12`、`pg_writer.py:7`、`backtest-service/routes.py:14`、`strategy-service/auto_trading_executor.py:478` 等多处：默认 `"postgresql://kronos:kronos@localhost:6432/kronos"`。
- **但** `prediction-service/routes.py:174` `_get_kline` 完全不用 PG 只用 SQLite；`screener-service/main.py:42-60` 的 PG 适配器在失败时 fallback 到 SQLite。
- 真实坑：若 `KRONOS_PG_URL` 未设但 DB_PATH 指向**空 SQLite**（fresh clone 后 Kronos/webui/stock_screening.db 可能不存在或空），screener/signal 服务起来后**所有查询返回 0 行**，前端看到空列表而非明确报错。CLAUDE.md "Verified Facts" 提示了这点。

### 5.4 数据新鲜度检测（设计好，但有 P0 bug 阻断）
- `MONITORED_TABLES`（scheduler.py:57-114）覆盖 42 张表的预期频率 + gap_threshold。
- `detect_data_gaps()`（scheduler.py:250-303）用真实交易日历（`trade_cal`）算滞后天数，比自然日准。
- **阻断**：`check_table_latest_date()`（scheduler.py:187-226）触发 P0-1 NameError，整个 L4 治理链断。
- `trigger_data_backfill()` 设计正确（dry_run + gap_threshold 触发对应 sync 函数）。

### 5.5 数据完整性（已在 alembic 005 / 006）
- `backend/alembic/versions/005_extend_legacy_tables.py`、`006_multi_horizon_snapshots.py` 是对业务表的扩展，但只是补丁式，未覆盖 init_postgres.sql 全部 65 张表。

---

## 6. 自动交易健壮性专项（资金风险点）

> 评级：**设计层面 4/5，落地层面 1/5**。所有真实资金风险防护设计都到位，但下游 broker 是 stub、审计日志没接 DB，意味着**整条资金链未真正打通**。

### 6.1 Circuit Breaker（设计正确，落地良好）
- `services/trade-service/app/circuit_breaker.py`：三态机（NORMAL / TRIGGERED / HALF_OPEN），每日亏损超 5% 触发，30 分钟冷却后允许一笔探测单。
- DB 持久化：`ensure_table` / `save_to_db` / `load_from_db` / `load_all_from_db` 全实现（circuit_breaker.py:259-435）。
- 跨日自动重置 + 跨日 DB 数据自动失效（circuit_breaker.py:362-368）。
- **唯一缺口**：circuit_breaker_state 表不在 init_postgres.sql，只在 alembic 002 中。docker 首次启动建表后 breaker 才能持久化；否则只在内存（circuit_breaker.py:55 `_breakers: dict`）。

### 6.2 RiskGateway（设计正确）
- `services/trade-service/app/risk_gateway.py`：6 维度风控（资金、持仓、涨跌停、单票仓位、单笔上限、大额二次确认）。
- 阈值全部 env 可配（risk_gateway.py:76-79）。
- **设计弱点**：涨跌停检查（risk_gateway.py:185-203）注释自承 "best-effort"，没接实时行情，只对 >10000 元价格告警；A 股 ±10% 涨跌停**实际未做**（需要昨收价）。

### 6.3 ExecutorManager（自动交易主循环，结构合理）
- `services/strategy-service/app/auto_trading_executor.py`：asyncio.Event 暂停/停止 + threading.Lock 状态隔离（与 CLAUDE.md 项目规则一致）。
- 日亏损超阈值自动 pause（executor.py:273-287）。
- 公告事件风险检测（_check_announcement_risk）、业绩预告负向过滤（_check_forecast_risk）、ATR 动态止损（_get_atr_stop_loss）—— **这些风控逻辑都真实实现了**。
- **P2-6 隐患**：这 3 个风控函数都裸 `psycopg2.connect` 且 `try/except: return` 吞异常。**风控 DB 不可用时，自动交易继续下单而不止损** —— 这是真实资金风险点（即便当前是 paper）。

### 6.4 XtquantBroker（设计良好，未落地）
- xtquant SDK 可用时**拒绝静默 fallback 到 stub**（xtquant_broker.py:122-125）—— 这个保护非常重要，避免了"以为在实盘实际是 stub"的灾难。
- 但所有 `place_order`/`cancel_order`/`get_positions`/`get_account` 都是 `# TODO: wire to xtquant.xttrader.*`。
- **结论**：实盘功能不存在；用户即便切到 live mode 也只是 stub 成交，但风控（RiskGateway、CircuitBreaker）会真跑 —— 这是矛盾的（防护了不存在的实盘）。

### 6.5 Audit Log（模块写了但没接）
- 见 P0-5。trade-service 的 audit_log.py 实现完整（record/query/SQLAlchemy session），但 routes.py 的 `_audit_record_safe` 只 logger.info，`/audit-logs` 返回硬编码空数组。

---

## 7. 优化建议（优先级清单 + 工作量）

| 优先级 | 编号 | 建议 | 工作量 |
|---|---|---|---|
| **P0 紧急** | P0-1 | 给 `scheduler.py` 和 `pg_writer.py` 加 `from psycopg2.sql import SQL, Identifier`（5 行） | **S** |
| **P0 紧急** | P0-2 | 让 docker-compose 首次启动跑 `alembic upgrade head`（backend Dockerfile entrypoint 或 init container） | **M** |
| **P0 紧急** | P0-3 | `KRONOS_SERVICE_SECRET` 缺失即启动失败（移除硬编码默认） | **S** |
| **P0 紧急** | P0-4 | `JWT_SECRET_KEY` 缺失即启动失败（生产模式） | **S** |
| **P0 紧急** | P0-5 | trade-service 接 asyncpg + 在 `_audit_record_safe` 中 `await record(db, ...)`；`/audit-logs` 走真查询 | **M** |
| **P1** | P1-1 | stocks.py 写入时联表 daily_basic 填充 market_cap/pe_ratio 等 4 列 | **M** |
| **P1** | P1-2 | backtest `/run` 改 `WHERE code IN (...)` + GROUP BY 消除 N+1 | **M** |
| **P1** | P1-3 | 实现 backtest `/calibrate` 真 IC（spearman with forward return）或显式 stub | **M** |
| **P1** | P1-4 | prediction routes.py:369 链式比较修复（`5 < pe < 25 and pb < 3`） | **S** |
| **P1** | P1-5 | strategy-service 按 skill `agf-wiring-multi-llm-sdk` 接 DeepSeek | **L** |
| **P1** | P1-6 | training-service 接真 MLflow + Kronos 微调（或 PRD 标注 placeholder） | **L** |
| **P1** | P1-7 | XtquantBroker 按 ADR-002 完成 wire（Windows QMT 环境） | **L** |
| **P1** | P1-8 | 4 个 in-memory store 切到 PostgreSQL | **L** |
| **P1** | P1-9 | api-gateway 换 nginx/caddy + Redis rate limiter | **M** |
| **P2** | P2-1 | docker-compose 每个 service 加 healthcheck | **M** |
| **P2** | P2-2 | 引入 OpenTelemetry（gateway/trade/strategy 主线先加 span） | **L** |
| **P2** | P2-3 | review CLAUDE.md "Verified Facts"，跑验证脚本 | **M** |
| **P2** | P2-4 | 补 trade/data-service/backend auth 单元测试 | **L** |
| **P2** | P2-5 | prediction-service 统一走 PG | **M** |
| **P2** | P2-6 | auto_trading_executor 风控函数用连接池；DB 异常 fail-safe 暂停交易 | **M** |
| **P2** | P2-7 | 用 `pip install -e packages/*` 替代 sys.path hack | **S** |
| **P2** | P2-8 | 业务表补 alembic baseline 或 ADR 明确双轨 | **L** |

---

## 8. 未验证项

以下问题已识别但本次审计**未跑代码验证**（只读静态分析），需后续动态验证：

1. **未启动任何服务**：所有"是否真能起来"的判断基于 main.py + lifespan + 路由 import 链的静态推演，未跑 `uvicorn`。
2. **未连 PG/Redis**：所有 schema 一致性、连接池、索引命中、查询计划的判断基于 SQL 文本和 ORM 定义，未跑 EXPLAIN。
3. **未跑测试**：未执行 `pytest` 或 `vitest`，未验证 3 个测试文件的实际通过率。
4. **未触发自动交易循环**：`_executor_loop` 的并发安全性、`asyncio.Event` + `threading.Lock` 分层是否真的无死锁，需 SIT 才能确认。
5. **未验证 kronos-factors 包**：`packages/kronos-factors/` 的 scorer / engine 模块未深入（不在本次审计范围声明内），但 screener/signal/backtest 都依赖它。如果 kronos-factors 自身有 bug，本报告的"功能可用度"评级会下调。
6. **未验证 Tushare 实际数据**：data-service 42 个 sync 任务的实际数据落库效果（是否真有 ~4500 只 A 股 daily_kline、字段是否齐全）需跑一次完整数据回补验证。
7. **xtquant 实际不可得**：本环境为 macOS，xtquant SDK 只在 Windows QMT 环境可用，`_XTQUANT_AVAILABLE` 默认 False → stub 路径。生产 Windows 环境下 `_connect_real` 路径未验证。
8. **Playwright PDF 渲染**：diagnosis-service PDF 导出依赖 Playwright 安装，本审计未验证容器内是否预装 chromium。
9. **CLAUDE.md "Verified Facts" 端口表**：本报告对部分条目（backend 端口、screener 模型数）做了 spot-check，但未对全部 13 条逐一交叉验证。

---

**报告生成于：2026-06-21　|　审计员：backend-dev（只读模式）**
