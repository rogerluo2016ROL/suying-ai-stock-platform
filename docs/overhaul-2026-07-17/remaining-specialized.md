# 剩余三项专项执行清单(#10 连接池 / #12 create_app 工厂 / #13 模板裁剪)

> 2026-07-17 会话整理。Wave 2 优化 7 项中 #7/#8/#9 已完成(npm audit / ErrorBoundary flaky / scheduler P0-3 分离),
> #11(C 3 域)清单见 `supply-chain-split.md`。本文档覆盖剩余 3 项——**都较大或带行为变化/模板自检风险**,
> 不宜在疲劳长会话里硬推,故拆成"专项执行清单",下次清醒时按项推进。
>
> 三项都**无功能 bug**(是优化/重构),可按触发条件择时做。

---

## #10 — P0-2 连接池迁移 — repository ✅ 完成(2026-07-18)/ routes 📋 专项

> **repository pool 已完成**:`repository.connect()` 改 `@contextmanager`(用 `kronos_contracts.db.pg_conn` 池);3 个 owned-cur 函数(`list_token_output_pools`/`token_output_counts`/`get_token_output_evidence`)用 `ExitStack` 条件 enter(保留"复用外层 cur"的事务组合语义);service.py 13 处 `with repository.connect() as pg` **零改动**(contextmanager 兼容 with)。`db.get_pg_pool` 建池加 `connect_timeout=PG_CONNECT_TIMEOUT`(默认 5,避免池初始化卡)。
> **docker PG 运行时验证**:`token_output_counts` 返回 1405 mappings(真实查询)+ pool singleton count=1(复用,未重建)。
> **routes 仍专项**:prediction/backtest/signal/data routes 的 `connect_timeout=3/5` 是 readiness 倾向(快速失败),迁 pool 是行为变化,留生产多 worker 前。

### 现状(2026-07-17 勘察)

`kronos_contracts.db.get_pg_pool/pg_conn` 池 API 已建(stage 3)。`etl._get_etl_db` 写入已确认单连接复用(安全)。剩余裸 `psycopg2.connect` 点分三类:

| 类别 | 文件:行 | 模式 | 迁移判断 |
|---|---|---|---|
| **A. 上下文管理器(最干净)** | `screener-service/app/domains/supply_chain/repository.py` 的 `connect()` | 被 `with repository.connect() as pg:` 调用 **11 处**(`service.py:187/631/1580/1806/1858/1908/1960/2024/2787/2843`…) | ✅ **改 `connect()` 内部一处,11 处调用方零改动** |
| **B. 请求路径(routes)** | `prediction-service/routes.py:86,146,274`(connect_timeout=3/5)<br>`backtest-service/routes.py:45(helper),451`(connect_timeout=5)<br>`signal-service/routes.py`(~3 处,connect_timeout=3/5)<br>`data-service/routers/data.py:64,86,185`、`inventory.py:9`(connect_timeout=2/3)<br>`data-service/quality/repository.py:11` | `with psycopg2.connect(url, connect_timeout=N) as conn` 或 `conn=...; try/finally close` | ⚠️ **行为变化**:lose connect_timeout 快速失败语义 |
| **C. 后台批处理(非请求路径)** | `data-service/scheduler.py:242,285,465,1159,1222`<br>`data-service/sync/*.py`(fina_audit:27 / namechange:135 / cb_sync:196 / pg_writer:221 / scheduled_research:34) | APScheduler/asyncio 定时长任务,串行写大量数据 | ❌ **不适合 pool**:串行长任务,连接复用价值低,改了徒增风险 |
| **D. 类持有长连接** | `screener-service/adapters.py:58`(`self._conn = psycopg2.connect(...)`)、`market_strength.py:85`(`connect = psycopg2.connect`) | 实例级单连接,生命周期 = 服务进程 | ❌ **不适合 pool**:本就是长连接复用,无 per-request 建连开销 |

### 顾虑(为什么不一刀切)

1. **B 类 connect_timeout 是有意的快速失败**:dashboard/查询 routes 用 `connect_timeout=2~5` 防 PG 慢时请求卡死。pool 的连接在**服务启动时**建立(getconn 复用,运行时无 connect_timeout 语义)。迁移后 PG 运行时抖动会从"快速失败"变成"连接失效报错",**行为变了**。
2. **readiness/health 必须保留裸 connect**(已确立原则):pool 建立时若 PG 不可达,池初始化卡住,readiness 检查无法 fast-fail。`kronos_contracts.health.check_postgres` 已是裸 connect,勿动。
3. **C/D 类迁移无收益**:批处理串行、类已长连接,迁移只增风险。

### ⚠️ 2026-07-17 勘察修正(批 1 假设不成立 → 批 1 作废)

实读 `repository.py` 后发现 `connect()` 是**裸函数返回 connection**(非 `@contextmanager`):

- repository 内部用 **owned-cur 模式**:`pg = connect() if owned else None` + finally `pg.close()`(见 line 254-256 / 279-281 / 311-313,共 3 处 close)
- service.py 11 处 `with repository.connect() as pg` 靠 **psycopg2 connection 原生 with 语义**(`__exit__` 仅 commit/rollback,**不 close**;CPython 引用计数兜底在函数返回时 close)

故原"批 1 改一处、11 处零改动"**不成立**:

1. pool 连接**不能 close** → owned-cur 的 `pg.close()` 会误关 pool 连接(池耗尽)
2. 若 `connect()` 改成 `@contextmanager`,内部 `pg = connect()`(非 with)拿到的是 contextmanager 对象而非连接,`pg.cursor()` 报错

正确 pool 化需**重构整个 repository owned-cur 层**(`connect`→contextmanager + 所有 owned-cur 函数适配)——属批 2 级工程。**批 1 作废,归入批 2 专项**。

> 附带发现(非严重):service.py 的 `with repository.connect() as pg` 不显式 close,靠 CPython 引用计数兜底(函数返回时 close)。单 worker 低并发下不崩,但不健壮。若要修,**最小正确改动** = `connect()` 改 `@contextmanager` + `finally conn.close()`(不上 pool,保留 `connect_timeout` 快速失败)——仍是 repository 层重构,非顺手。

### 执行步骤(批 1 已作废,仅留批 2)

**~~批 1 — A 类 screener repository(低风险高价值,可独立做,~20 分钟)~~** — 见上修正,作废

```bash
# 1. 读 repository.connect() 当前实现(确认是否 @contextmanager)
grep -n "def connect\|@contextmanager\|psycopg2.connect\|close()" \
  services/screener-service/app/domains/supply_chain/repository.py | head -20
```

改 `connect()` 内部:`psycopg2.connect(...)` → `kronos_contracts.db.pg_conn(KRONOS_PG_URL)`。
调用方 11 处 `with repository.connect() as pg:` 零改动(pool 的 with 自动借/还)。

⚠️ **关键**:确认调用方 `with ... as pg:` 后**没有显式 `pg.close()`**(pool 连接不能 close,只能 putconn)。grep 验证:
```bash
grep -n "pg.close\|pg\.close" services/screener-service/app/domains/supply_chain/service.py
# 应为 0(若非 0,迁移前先去掉这些 close,否则 pool 连接被误关)
```

**批 2 — B 类请求路径(行为变化,需评估后做)**

逐文件迁移 `with psycopg2.connect(url, connect_timeout=N) as conn` → `with pg_conn(url) as conn:`。
顺序(按风险从低到高):`prediction routes`(3 处 with 模式最规整)→ `backtest routes`(先改 line 45 helper)→ `signal routes` → `data routers`(4 处)。

⚠️ **行为变化确认**:迁移前与用户对齐——是否接受"PG 运行时抖动 → 连接失效报错"替代"connect_timeout 快速失败"。若不接受,B 类**保留裸 connect**。

### 验证

```bash
# 每个 migrated 服务
cd services/<name>
.venv/bin/python -c "import ast; ast.parse(open('app/routes.py').read())"   # 语法
.venv/bin/python -c "from app.routes import router"                          # import 链
pytest tests/ -v 2>/dev/null || true
# 启动 + 打一次查询接口,确认 pool 借还正常(看日志无 "connection already closed")
```

### 触发条件(何时做)

- **批 1(screener repository)**:可随时做,低风险。**建议本次或下次顺手**。
- **批 2(routes)**:**生产多 worker 部署前**做(单 worker 下 per-request connect 未撑爆 max_connections,风险未触发)。

---

## #12 — create_app 工厂(统一 main.py 启动样板)✅ 已完成(2026-07-18)

> **已完成**:工厂 `kronos_contracts.app_factory.create_app` 就位(支持 `lifespan` / `health_extra` dict|callable)。
> **10/11 服务迁移**:alert/diagnosis/strategy/trade(标准)+ backtest/signal/training/data/screener/prediction(各自保留特殊 lifespan:inject_adapters / scheduler / PG-adapter+sockettimeout / Kronos-src / 模型加载)。
> **api-gateway 不迁(N/A)**:网关非标准服务——catch-all `@app.api_route("/{path:path}")` 代理(非 router include)+ `probe_services` health(探测上游,非 check_postgres)+ 额外 `/api/v1/runtime/readiness` + 裸 FastAPI 无样板可消除;工厂模式不匹配,强迁会破坏 readiness 探测且收益 ~0。
> 验证:10 服务 `from app.main import app` 通过(title / health 3 路由 / CORS / signal 的 Deprecate 中间件 / prediction 动态 health_extra)。commit: `86610dcc` / `7bd956cb` / `f58fff56`。

### ~~create_app 工厂(原方案,已完成,留作记录)~~

### 现状(2026-07-17 勘察)

11 个 `services/*/app/main.py`,共 1166 行。每个都重复 8 步样板(以 `alert-service` 56 行为基准):

| 步 | 内容 | 各服务差异 |
|---|---|---|
| 1 | `sys.path` 注入 packages(kronos-factors/core/data…) | **packages 列表不同**(alert 要 factors/core/data;prediction 还要 contracts) |
| 2 | `logging.basicConfig` + `logger` | logger name = service name |
| 3 | `@asynccontextmanager lifespan` | 几乎相同(Starting/stopped 日志) |
| 4 | `app = FastAPI(title="速赢AI - X", version=…)` | **title/version 不同** |
| 5 | `app.add_middleware(CORSMiddleware, allow_origins=CORS_ALLOWED_ORIGINS…)` | **完全相同**(env 读 CORS_ALLOWED_ORIGINS) |
| 6 | `app.include_router(router)` | **router 不同** |
| 7 | `/health/live` + `/health/ready` + `/health` 三端点 | service name/version 不同,逻辑相同(kronos_contracts) |
| 8 | `if __name__: uvicorn.run(..., port=N)` | **port 不同** |

各 main.py 行数:api-gateway 259(最大,有特殊路由聚合)· prediction 164 · screener 133 · training 128 · signal 101 · data 74 · backtest 66 · strategy 64 · trade 65 · alert 56 · diagnosis 56。

### 目标

`packages/kronos-contracts/kronos_contracts/app_factory.py`:

```python
def create_app(
    service_name: str,          # "alert-service"
    version: str,               # "0.1.0"
    router,                     # 各服务自己的 APIRouter
    packages: list[str],        # ["kronos-factors", "kronos-core", "kronos-data"]
    *,
    extra_routers: list = None, # api-gateway 的特殊聚合路由
    lifespan_hook=None,         # 各服务 lifespan 额外初始化(如预测模型加载)
) -> FastAPI:
    # 1-8 步全部内置(sys.path 注入要放在函数体最前——模块 import 前生效)
```

各 `main.py` 缩成 ~10 行:
```python
from kronos_contracts.app_factory import create_app
from app.routes import router
app = create_app("alert-service", "0.1.0", router, ["kronos-factors","kronos-core","kronos-data"])
if __name__ == "__main__":
    import uvicorn; uvicorn.run("app.main:app", host="0.0.0.0", port=8005, reload=True)
```

### 顾虑(为什么是专项不是顺手)

1. **sys.path 注入时机**:`sys.path.insert` 必须在 `from app.routes import router` **之前**执行(routes 依赖 packages)。工厂函数里要把 path 注入放最前,且 **import app.routes 必须在工厂调用处**(不能在工厂模块顶层),否则 packages 没注入就 import routes 会失败。这是最容易踩的坑。
2. **api-gateway 259 行特殊**:它有路由聚合/代理逻辑,不能简单套工厂——单独保留或工厂 `extra_routers` 参数承接。
3. **prediction lifespan 特殊**:加载 Kronos 模型 checkpoint,需要 `lifespan_hook` 参数。
4. **11 个服务逐个改 + 每个启动验证**:工作量大,且 main.py 是服务入口,改错直接服务起不来。

### 执行步骤

```bash
# 0. 先建工厂(不动现有 main.py)
# 1. 写 packages/kronos-contracts/kronos_contracts/app_factory.py
# 2. 拿 alert-service(最简 56 行)试点:改 main.py 用工厂 → 启动验证
cd services/alert-service && KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
  .venv/bin/python -c "from app.main import app; print(app.routes[0].path)"
# 3. 验证三 health 端点 + CORS + router 全通,再推广到其余 9 个
# 4. api-gateway / prediction 最后做(特殊 lifespan/路由)
```

### 验证

```bash
# 每个服务:import 链 + 启动 + 三 health 端点
.venv/bin/python -c "from app.main import app"
# 起服务 curl /api/v1/health/live /ready /health,确认 200
# CORS: curl -I -X OPTIONS http://localhost:8005/api/v1/health -H "Origin: http://localhost:5173"
```

### 触发条件(何时做)

**无紧迫性**(纯重构,无 bug)。建议:**下次需要新增微服务时**——先建工厂,新服务直接用,顺便迁移 1-2 个现有服务。避免专门起一轮"改 11 个 main.py"。

---

## #13 — D 框架/模板裁剪(`.claude/` AGF v6.27.1)

> **Apple 轨专项裁剪 ✅ 已完成(2026-07-18)**:虽本文档一般建议"默认不裁模板",但 Apple 轨作为本项目明确不用的整轨已专项裁剪——
> 核心(4 agent + 3 skill + command + apple-native.md,`9097a330`)+ 真角色残留(verified-facts/team-roles,`a8559bea`)+ team-capability-map 33 处(`cf2b2af7`)+ **framework 文档残留 4 文件**(deployment §7 整段 / coding Apple 子节 / testing 3 处 / repo-layout 7 处,本批 -44/+8)。
> **刻意留(无害)**:A 类 = hooks/scripts 里 apple role-name 字符串匹配(check-progress-file / gate-deploy-release-auth / validate-verdict / agf-board / agf-next-instance + 对应 test)——功能代码有测试覆盖、customize.sh 设计不动、角色不 spawn 即不命中;C 类 = scan-secrets/scan-commit 的 Apple 签名密钥防御扫描——verified-facts 厂商数=11 含 Apple,通用安全防御。
> 下文"现状/顾虑/执行步骤"是**通用模板裁剪建议**(仍默认不做,仅模板升级时顺带),与 Apple 专项裁剪无关。

### 现状(2026-07-17 勘察)

`.claude/` 是完整 AGF 团队模板,非本项目业务代码:

```
agents(22)  commands(12)  hooks(19)  rules(5)  scripts(24)
security  skills(17)  standards(20)  settings.json
```

关键约束(`.claude/settings.json` + 各 hook 联动):

1. **`roles.yaml` 是唯一 SSOT**:`.claude/agents/roles.yaml` 定义角色能力。`.claude/standards/team-roles.md` 两张能力表 + 各 `agents/*.md` frontmatter 都是 `scripts/gen-roles.py` 的**生成物**。
2. **`lint-all.sh` 硬阻断 drift**:改 agents/standards 后不重跑生成器,lint-all 会检测出生成物与 SSOT 不一致并阻断 commit。
3. **`block-config-edit.sh`** 护 lint 配置:试图改 lint-all 的判定逻辑会被 hook 拦。
4. **`enforce-write-scope.sh`**:角色越界写(如 code-reviewer 改源码)被拦。
5. 四层安全防御(`block-dangerous-bash`/`scan-secrets`/`sanitize-tool-output`/`scan-commit`)+ 诚实层 gates(`agf-claims-audit`/`agf-deny-baseline`)**永不降级**。

### 顾虑(为什么余地有限)

之前审计结论:**裁剪余地有限**。`.claude/` 是活跃的团队模板,大部分组件互相联动:

- 删一个 hook → settings.json 注册残留 → `claims-audit` 报 written≠working(此前删 skill-suggester.sh 就踩过,需同步删 settings.json 注册)。
- 删一个 agent → roles.yaml + team-roles.md + gen-roles.py 三处同步,漏一处 lint-all 阻断。
- 删一个 standard → CLAUDE.md "Team Runtime Contract" 的权威源引用残留。

**裁剪收益低**(模板不进运行时,不影响服务性能/体积),**风险高**(联动多、lint 自检严)。

### 可安全裁剪的候选(需逐项验证联动)

仅以下"孤岛"组件可能安全删(删前 grep 全仓引用 + 跑 lint-all):

1. **项目未用到的 skill**(如 `agf-writing-pptx-reports`/`agf-writing-docx-reports` 是选装 office 组,若本项目从不用中文报告)——但 CLAUDE.md 明确标注"选装,默认不分发",可能本就没装。
2. **未引用的 agent**(grep `roles.yaml` + 各 standard,确认无引用)。
3. `.claude.backup`(此前已 `git rm --cached`,确认磁盘残留是否还要清)。

### 执行步骤(每项都要)

```bash
# 对每个候选裁剪目标 X:
# 1. 全仓引用扫描
grep -rn "X" .claude/ CLAUDE.md docs/ 2>/dev/null
# 2. 若仅自身定义、无引用 → 可删;删除
# 3. 同步清理引用(settings.json 注册 / CLAUDE.md 路由行 / roles.yaml)
# 4. 若动了 agents/standards → 重跑生成器
bash .claude/scripts/gen-roles.py
# 5. 跑 lint-all 自检(必须 0 阻断)
bash .claude/scripts/lint-all.sh
```

### 触发条件(何时做)

**几乎不建议主动裁剪**。仅在以下情况:
- 模板升级(v6.27.1 → v7.x)时顺带清理废弃组件。
- 明确发现某组件**误报/阻断**正常开发(此时按 security.md「No Equivalent Bypass」走,不是偷删)。

裁剪的 ROI 低于任何业务/服务优化项。**默认保留**。

---

## 总结:Wave 2 优化 7 项最终状态(2026-07-18 收尾)

| 项 | 状态 | 备注 |
|---|---|---|
| #7 npm audit | ✅ 完成 | |
| #8 ErrorBoundary flaky | ✅ 完成 | |
| #9 scheduler P0-3 分离 | ✅ 完成 | |
| #10 P0-2 连接池 | 🟡 repository ✅ / routes defer | repository 已池化(`036d008c`,docker PG 运行时验证 1405 mappings);routes(15 处裸 connect)**用户决策 defer 到多 worker 生产前**(2026-07-18,保留 connect_timeout 快速失败,见上文 #10 节批 2) |
| #11 C 域拆分 | ✅ 完成 | 15/15 domain,client.ts 130 行,根 `types.ts` 为共享类型 barrel(设计内,非残留),`npx tsc -b --noEmit` = 0(`5c407160`) |
| #12 create_app 工厂 | ✅ 完成 | 10/11,api-gateway N/A(`86610dcc`/`7bd956cb`/`f58fff56`) |
| #13 模板裁剪 | ✅ Apple 专项完成 | 核心+真角色残留+team-capability-map+framework 文档全清(`9097a330`/`a8559bea`/`cf2b2af7`/`ed857f31`);通用裁剪默认不做 |

> **Wave 2 实质完成**:7 项中 6 项 ✅,#10 routes 按用户决策 defer(单 worker 下裸 connect + connect_timeout 快速失败更安全且可预测)。
> 触发 #10 routes 的条件 = **生产多 worker 部署前**;届时回到上文「#10 — P0-2 连接池迁移」节批 2 执行(行为变化需重新对齐是否接受"PG 运行时抖动→连接失效报错"替代快速失败)。
> A 类(hooks/scripts apple role-name 匹配)+ C 类(scan-secrets Apple 密钥防御)刻意留,无害。
