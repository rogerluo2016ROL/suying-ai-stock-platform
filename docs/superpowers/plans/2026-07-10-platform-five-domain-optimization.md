# 平台五域可信度与可维护性治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除伪数据、伪指标和假健康，建立前端、后端、架构、数据采集和算法模型的统一可信门与可复现证据链。

**Architecture:** 保留 React、FastAPI、PostgreSQL、Redis 和现有服务。先关闭不真实的生产路径，再统一服务所有权、数据 readiness、运行 manifest 和模型晋级门，最后拆分巨型模块并完成真实 API UAT。

**Tech Stack:** React 18、TypeScript、Vite、Ant Design、FastAPI、PostgreSQL 15、Redis、Pydantic v2、pytest、Vitest、Docker Compose、MLflow。

## Global Constraints

- 实施必须使用独立 git worktree；当前工作区已有用户改动，禁止 reset、覆盖或混入提交。
- 交易和 schema 任务在编码前先由 tech-lead review；所有交易验证只使用 paper 模式。
- 保留现有 `/api/v1` 外部路径；迁移使用兼容 facade，不做一次性破坏式切换。
- `daily_kline.close` 是原始价格，多日回测必须结合 `adj_factor`。
- `KRONOS_ENV=production` 下禁止 SQLite、neutral stub、synthetic 指标和 mock MLflow 进入正式结果。
- 缺少真实观测时只返回 `unavailable`、`unsupported` 或 `insufficient_data`，不得补固定数、随机数或 proxy 统计。
- 先写失败测试，再改最小实现；每个任务独立提交并保留回滚点。
- 使用低 I/O 命令：`bash tools/codex-lowio.sh py ...`、`fe-test`、`fe-typecheck`。
- CodeGraph 索引存在，移动核心符号前先运行 `codegraph impact` 或 `codegraph callers`。
- 普通读 API P95 目标 ≤ 500ms；耗时任务在 2 秒内返回持久化 `run_id`。

---

## Program file map

| Workstream | Create | Modify |
|---|---|---|
| 可信度止血 | backtest/training truth tests | Screener、DataUpdate、gateway、backtest、training、signal、xtquant |
| 测试与运行契约 | `tools/run_service_tests.py`、`packages/kronos-contracts/` | CI、各服务 health、gateway registry |
| 数据可信度 | readiness config/evaluator/repository、Alembic migration | data router/scheduler、schema audit |
| 模型可信度 | manifest schema、backtest adapters、admission gate | pipeline、walk-forward、training registry |
| 前后端维护性 | route registry、域 API、screener domains | App、client、巨型页面和 router |
| 发布 | UAT 报告和真实浏览器 smoke | full-stack smoke、compose healthchecks |

## Execution order

```text
Tasks 1–5 可信止血和 CI
      ↓
Tasks 6–8 服务边界、身份和数据 API
      ↓
Tasks 9–10 数据 readiness 与 schema 门
      ↓
Tasks 11–12 运行 manifest、真实回测和模型晋级
      ↓
Tasks 13–15 前端与后端拆分
      ↓
Task 16 真实 UAT、回滚和签字
```

Tasks 1、2、3、4、5 可并行；Tasks 13 和 14 可并行。其余按依赖顺序执行。

## Schedule and owners

| Wave | Tasks | Primary owners | Estimate | Exit gate |
|---|---|---|---:|---|
| 0 可信止血 | 1–6 | frontend-dev、backend-dev、ml-engineer | 7–10 人日 | 伪数据路径关闭，CI 可独立测试所有目标 |
| 1 服务边界 | 7–9 | tech-lead、backend-dev、frontend-dev | 6–9 人日 | 路由、身份、health 和 data 语义收敛 |
| 2 数据可信 | 10–11 | backend-dev、ml-engineer、tech-lead | 8–12 人日 | readiness 强制，schema/owner gate 通过 |
| 3 模型可信 | 12–14 | ml-engineer、backend-dev | 9–14 人日 | 正式 manifest、真实回测、晋级门通过 |
| 4 模块拆分 | 15–16 | frontend-dev、backend-dev | 10–15 人日 | 前后端兼容测试全绿，巨型入口收敛 |
| 5 验收发布 | 17 | qa-engineer、deploy-engineer | 3–5 人日 | E2E、UAT、paper smoke 和回滚签字 |

总工作量约 43–65 人日。3–4 个执行角色按依赖并行时，日历周期约 6–10 周。每个 wave 独立 review 和签字，不能用总项目尚未完成为理由跳过阶段验收。

### Task 1: 恢复前端基线并删除失败时的演示数据

**Files:**
- Modify: `frontend/src/__tests__/SupplyChainBom.test.tsx`
- Modify: `frontend/src/pages/DataUpdate.tsx`
- Modify: `frontend/src/__tests__/DataUpdate.test.tsx`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes: `DataStatusResponse` from `frontend/src/api/types.ts`.
- Produces: `DataStatusView`，失败时只包含 unknown 状态和真实错误原因。

- [ ] **Step 1: 写失败测试，锁定真实空状态**

```tsx
it('does not show demo row counts when data status fails', async () => {
  vi.mocked(signalApi.getDataStatus).mockRejectedValueOnce(new Error('gateway unavailable'))
  render(<DataUpdate />)
  expect(await screen.findByText('数据状态不可用')).toBeInTheDocument()
  expect(screen.queryByText('982,000')).not.toBeInTheDocument()
  expect(screen.queryByText('2026-06-27')).not.toBeInTheDocument()
})
```

在 `SupplyChainBom.test.tsx` 中把标题断言改为当前产品文案的精确值：

```tsx
expect(screen.getByText('节点下钻、链路模板、候选横评、证据复核集中处理')).toBeInTheDocument()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run:

```bash
bash tools/codex-lowio.sh fe-test src/__tests__/DataUpdate.test.tsx src/__tests__/SupplyChainBom.test.tsx
```

Expected: DataUpdate 新用例失败；SupplyChainBom 旧断言问题被准确定位。

- [ ] **Step 3: 删除 `fallbackStatus` 的固定业务数据**

用以下结构替代固定行数和日期：

```ts
const unavailableStatus: DataStatusResponse = {
  status: 'unavailable',
  total_tables: 0,
  active_tables: 0,
  total_rows: 0,
  sources: [],
  sync_map: {},
  fallback_reason: '数据状态接口不可用',
}
```

`normalizeDataStatus` 只补结构默认值，不补业务记录。请求异常时保留异常消息并渲染 blocked/error 状态。

- [ ] **Step 4: 运行前端基线**

```bash
bash tools/codex-lowio.sh fe-test src/__tests__/DataUpdate.test.tsx src/__tests__/SupplyChainBom.test.tsx
bash tools/codex-lowio.sh fe-typecheck
```

Expected: focused tests exit 0，TypeScript exit 0。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/DataUpdate.tsx frontend/src/api/types.ts frontend/src/__tests__/DataUpdate.test.tsx frontend/src/__tests__/SupplyChainBom.test.tsx
git commit -m "fix(frontend): remove demo data fallbacks"
```

### Task 2: 删除选股页伪 IC、相关性和分层收益

**Files:**
- Modify: `frontend/src/pages/Screener.tsx`
- Modify: `frontend/src/__tests__/Screener.test.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/pages/screener/factorEvidence.ts`
- Create: `frontend/src/pages/screener/FactorEvidencePanel.tsx`

**Interfaces:**
- Consumes: `FactorEvidenceResponse` from backtest API.
- Produces: `toFactorEvidenceView(response): FactorEvidenceView`，不做统计推导。

- [ ] **Step 1: 写失败测试**

```tsx
it('does not derive IC or returns from pick scores', async () => {
  vi.mocked(screenerApi.run).mockResolvedValue({
    data: { picks: [{ code: '600000', score: 88, factor_breakdown: { technical: 9 } }] },
  } as never)
  vi.mocked(backtestApi.getFactorEvidence).mockResolvedValue({
    data: {
      status: 'insufficient_data', observations: 0, factors: [], correlations: [],
      deciles: [], missing_requirements: ['future_returns'],
    },
  } as never)
  render(<Screener />)
  expect(await screen.findByText('暂无真实因子回测数据')).toBeInTheDocument()
  expect(screen.queryByText('IC Mean')).not.toBeInTheDocument()
  expect(screen.queryByText('多-空对冲')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: 验证测试失败**

```bash
bash tools/codex-lowio.sh fe-test src/__tests__/Screener.test.tsx
```

Expected: 页面仍生成 IC 或分层收益，测试失败。

- [ ] **Step 3: 删除三个派生函数并接入证据响应**

删除 `deriveFactorStats`、近似相关性矩阵和 `buildDecileRows` 的生产调用。新增：

```ts
export type FactorEvidenceView =
  | { kind: 'ready'; factors: FactorMetric[]; correlations: CorrelationCell[]; deciles: DecileMetric[] }
  | { kind: 'insufficient'; reasons: string[] }
  | { kind: 'unsupported'; reasons: string[] }

export function toFactorEvidenceView(response: FactorEvidenceResponse): FactorEvidenceView {
  if (response.status !== 'ready') {
    return { kind: response.status, reasons: response.missing_requirements ?? [] }
  }
  return {
    kind: 'ready',
    factors: response.factors,
    correlations: response.correlations,
    deciles: response.deciles,
  }
}
```

`FactorEvidencePanel` 只渲染 API 返回值。

在 `frontend/src/api/client.ts` 增加兼容方法，Task 15 再移动到 models domain：

```ts
getFactorEvidence: (modelKey: string) =>
  api.get<FactorEvidenceResponse>('/backtest/factor-evidence', { params: { model_key: modelKey } })
```

- [ ] **Step 4: 运行 focused tests 和 typecheck**

```bash
bash tools/codex-lowio.sh fe-test src/__tests__/Screener.test.tsx
bash tools/codex-lowio.sh fe-typecheck
```

Expected: exit 0，源码中不再用 score 生成 IC、相关性和收益。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/Screener.tsx frontend/src/pages/screener frontend/src/api/types.ts frontend/src/__tests__/Screener.test.tsx
git commit -m "fix(frontend): show only observed factor evidence"
```

### Task 3: 关闭网关预览数字和伪 lineage

**Files:**
- Modify: `services/api-gateway/app/main.py`
- Modify: `services/api-gateway/tests/test_workbench_contract.py`
- Modify: `services/api-gateway/tests/test_gateway_routes.py`

**Interfaces:**
- Consumes: no downstream data in this temporary stop-gap.
- Produces: workbench envelope with `status=unavailable` until Task 7 provides real aggregation.

- [ ] **Step 1: 写失败合同测试**

```python
def test_workbench_never_returns_preview_business_values(client):
    body = client.get("/api/v1/workbench/p0").json()
    rendered = json.dumps(body, ensure_ascii=False)
    assert "CTX-preview" not in rendered
    assert "CAND-preview" not in rendered
    assert body["status"] == "unavailable"
    assert body["sections"] == []
    assert body["freshness"]["status"] == "missing"
```

- [ ] **Step 2: 运行测试并确认失败**

```bash
cd services/api-gateway && ../../.venv/bin/python -m pytest tests/test_workbench_contract.py -q
```

Expected: 固定 preview 数据导致 FAIL。

- [ ] **Step 3: 移除 `_WORKBENCH_MODULES` 固定业务值**

暂时返回：

```python
def _workbench_envelope(module_path: str, request: Request) -> dict:
    module = module_path.strip("/") or "p0"
    return {
        "status": "unavailable",
        "page": {"module": module, "route": f"/{module}", "title": module},
        "context": _workbench_context(request),
        "freshness": {
            "status": "missing",
            "as_of": None,
            "source": "api-gateway",
            "fallback_reason": "real workbench aggregation is not connected",
        },
        "lineage": {},
        "sections": [],
        "actions": [],
    }
```

- [ ] **Step 4: 运行 gateway 测试**

```bash
cd services/api-gateway && ../../.venv/bin/python -m pytest tests -q
```

Expected: exit 0，无 preview ID 和固定数量。

- [ ] **Step 5: 提交**

```bash
git add services/api-gateway/app/main.py services/api-gateway/tests
git commit -m "fix(gateway): remove preview business metrics"
```

### Task 4: 关闭后端随机校准、默认成绩和 proxy 回测

**Files:**
- Modify: `services/training-service/app/factor_calibration.py`
- Modify: `services/training-service/app/routes.py`
- Modify: `services/training-service/app/scheduler.py`
- Create: `services/training-service/tests/test_truthfulness_gate.py`
- Modify: `services/backtest-service/app/routes.py`
- Create: `services/backtest-service/tests/test_truthful_factor_contract.py`

**Interfaces:**
- Produces: `EvidenceStatus = ready | insufficient_data | unsupported`.
- Blocks: weight writes and model comparison when evidence is incomplete.

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_calibration_does_not_apply_random_evidence(monkeypatch):
    monkeypatch.setattr(calibration, "compute_ic_from_db", AsyncMock(return_value={
        "factors": [], "window_start": "2026-04-01", "window_end": "2026-07-10",
    }))
    apply_spy = AsyncMock()
    monkeypatch.setattr(calibration, "_apply_calibration", apply_spy)
    result = await calibration.run_calibration(apply=True)
    assert result["status"] == "insufficient_data"
    apply_spy.assert_not_awaited()

def test_backtest_proxy_is_not_reported_as_real(client):
    response = client.post("/api/v1/backtest/run", params={"mode": "all"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_BACKTEST_NOT_IMPLEMENTED"
```

再增加模型 compare 测试，缺任一 required metric 时断言 422 `INSUFFICIENT_EVIDENCE`。

- [ ] **Step 2: 运行三组测试并确认失败**

```bash
cd services/training-service && ../../.venv/bin/python -m pytest tests/test_truthfulness_gate.py -q
cd ../backtest-service && ../../.venv/bin/python -m pytest tests/test_truthful_factor_contract.py -q
```

Expected: 当前随机/默认/proxy 路径导致失败。

- [ ] **Step 3: 实现失败关闭**

新增异常：

```python
class InsufficientEvidence(RuntimeError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("insufficient observed evidence")
```

生产校准找不到真实观测时返回 `insufficient_data`；scheduler 跳过 apply。模型 compare 必须读取真实指标，不提供默认参数。backtest `/run` 和 `/calibrate` 在真实 adapter 完成前返回 409，且不更新 `factor_weights`。新增只读 `/api/v1/backtest/factor-evidence?model_key=...`，在 Task 13 完成前返回：

```json
{
  "status": "unsupported",
  "observations": 0,
  "factors": [],
  "correlations": [],
  "deciles": [],
  "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"]
}
```

- [ ] **Step 4: 运行 training 和 backtest 测试**

```bash
cd services/training-service && ../../.venv/bin/python -m pytest tests -q
cd ../backtest-service && ../../.venv/bin/python -m pytest tests -q
```

Expected: exit 0；证据不足时数据库写入 spy 未调用。

- [ ] **Step 5: 提交**

```bash
git add services/training-service services/backtest-service
git commit -m "fix(models): fail closed on missing evaluation evidence"
```

### Task 5: 禁止固定 Kronos 分和 xtquant live 回落 stub

**Files:**
- Modify: `services/signal-service/app/routes.py`
- Modify: `services/signal-service/tests/test_signal_contracts.py`
- Modify: `services/trade-service/app/xtquant_broker.py`
- Create: `services/trade-service/tests/test_xtquant_capabilities.py`

**Interfaces:**
- Produces: signal `coverage` and `unavailable_dimensions`.
- Produces: broker `capabilities` and fail-closed readiness.

- [ ] **Step 1: 写失败测试**

```python
def test_missing_kronos_is_unavailable_not_neutral():
    body = routes._combine_signal_dimensions({
        "kronos": None, "technical": 72.0, "money_flow": 65.0,
        "fundamental": 61.0, "event_risk": 70.0, "market": 58.0,
    })
    assert "kronos" in body["unavailable_dimensions"]
    assert body["dimensions"]["kronos"] is None

@pytest.mark.asyncio
async def test_connected_sdk_without_order_capability_never_stubs(monkeypatch):
    broker = XtquantBroker()
    monkeypatch.setattr(xtquant_broker, "_XTQUANT_AVAILABLE", True)
    broker._trader = object()
    order = OrderRequest(
        symbol="600000.SH", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, quantity=100, price=10.0,
    )
    with pytest.raises(BrokerCapabilityError):
        await broker.place_order(order)
```

- [ ] **Step 2: 运行测试并确认失败**

```bash
cd services/signal-service && ../../.venv/bin/python -m pytest tests/test_signal_contracts.py -q
cd ../trade-service && ../../.venv/bin/python -m pytest tests/test_xtquant_capabilities.py -q
```

- [ ] **Step 3: 实现 coverage 和 broker capability gate**

```python
REQUIRED_LIVE_CAPABILITIES = {
    "place_order", "cancel_order", "query_positions", "query_account", "order_callbacks"
}

def live_readiness(self) -> dict:
    missing = sorted(REQUIRED_LIVE_CAPABILITIES - self._implemented_capabilities)
    return {"status": "ready" if not missing else "blocked", "missing_capabilities": missing}
```

真实方法未实现时抛 `BrokerCapabilityError`，不执行 `_place_order_stub`。signal 根据可用维度重新归一权重，并返回 coverage；若关键维度缺失则 `result_status=insufficient_data`。

- [ ] **Step 4: 运行 focused tests**

```bash
cd services/signal-service && ../../.venv/bin/python -m pytest tests -q
cd ../trade-service && ../../.venv/bin/python -m pytest tests -q
```

Expected: exit 0，live 请求没有 stub 订单。

- [ ] **Step 5: 提交**

```bash
git add services/signal-service services/trade-service
git commit -m "fix(trading): block unsupported live broker operations"
```

### Task 6: 建立微服务隔离测试和 CI 矩阵

**Files:**
- Create: `tools/run_service_tests.py`
- Create: `tools/tests/test_run_service_tests.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tools/codex-lowio.sh`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `run_service(service: str, extra_args: list[str]) -> int`.
- Produces: CLI `python3 tools/run_service_tests.py --core`.

- [ ] **Step 1: 写 runner 单测**

```python
def test_each_service_uses_own_cwd_and_process(monkeypatch):
    calls = []
    def fake_run(cmd, cwd, env, check):
        calls.append((cmd, cwd, env))
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_service("trade-service", ["-q"]) == 0
    assert calls[0][1].endswith("services/trade-service")
    assert calls[0][0][:3] == [sys.executable, "-m", "pytest"]
    assert calls[0][2]["PYTHONPATH"].split(os.pathsep)[0].endswith("services/trade-service")
```

- [ ] **Step 2: 运行测试确认模块不存在**

```bash
bash tools/codex-lowio.sh py tools/tests/test_run_service_tests.py -q
```

Expected: FAIL with import error for `run_service_tests`.

- [ ] **Step 3: 实现独立进程 runner**

```python
CORE_TARGETS = [
    "backend", "api-gateway", "data-service", "screener-service", "prediction-service",
    "strategy-service", "signal-service", "alert-service", "trade-service",
    "backtest-service", "training-service", "diagnosis-service",
]

def run_service(service: str, extra_args: list[str]) -> int:
    service_dir = ROOT / "backend" if service == "backend" else ROOT / "services" / service
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(service_dir), str(ROOT / "packages" / "kronos-contracts"), str(ROOT / "packages" / "kronos-factors"), str(ROOT / "packages" / "kronos-core"), str(ROOT / "packages" / "kronos-data")])
    result = subprocess.run([sys.executable, "-m", "pytest", "tests", *extra_args], cwd=service_dir, env=env, check=False)
    return result.returncode
```

CI service matrix 为每个服务调用 runner；frontend job 增加 `npm run build`。Docker build 依赖 test jobs 成功。

- [ ] **Step 4: 验证 runner 和 CI YAML**

```bash
bash tools/codex-lowio.sh py tools/tests/test_run_service_tests.py -q
python3 tools/run_service_tests.py --core -q
cd frontend && npm run build
```

Expected: 每个服务单独报告；不出现跨服务 `app` 导入冲突。

- [ ] **Step 5: 提交**

```bash
git add tools/run_service_tests.py tools/tests/test_run_service_tests.py tools/codex-lowio.sh pyproject.toml .github/workflows/ci.yml
git commit -m "ci: test every core service in isolation"
```

### Task 7: 收敛 gateway 路由所有权并清洗身份头

**Files:**
- Create: `services/api-gateway/app/service_registry.py`
- Modify: `services/api-gateway/app/main.py`
- Modify: `services/api-gateway/tests/test_gateway_routes.py`
- Modify: `services/api-gateway/tests/test_workbench_contract.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/__tests__/apiClientPlatformContext.test.ts`
- Modify: `docker/docker-compose.yml`
- Create: `docs/adr/016-platform-runtime-contracts.md`

**Interfaces:**
- Produces: `sanitize_client_headers(headers, claims) -> dict[str, str]`.
- Produces: `/api/v1/data` owner `data-service:8010`.

- [ ] **Step 1: 写路由和越权测试**

```python
def test_data_routes_to_data_service():
    assert resolve_service("/api/v1/data/status").name == "data-service"
    assert resolve_service("/api/v1/data/status").port == 8010

def test_spoofed_owner_and_service_headers_are_removed():
    headers = sanitize_client_headers(
        {"X-Owner-User-Id": "victim", "X-Service-Auth": "forged", "X-Tenant-Id": "tenant-a"},
    )
    assert "X-Owner-User-Id" not in headers
    assert "X-Service-Auth" not in headers
```

前端测试断言 axios 不再发送 `X-Owner-User-Id`。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd services/api-gateway && ../../.venv/bin/python -m pytest tests -q
bash tools/codex-lowio.sh fe-test src/__tests__/apiClientPlatformContext.test.ts
```

- [ ] **Step 3: 实现 registry 和 header policy**

`service_registry.py` 定义 name、prefix、host env、compose host 和 port。gateway 不再维护 `_COMPOSE_HOSTS`、`_HOST_ENV`、`SERVICES` 三份映射。

客户端只发送 tenant/account/trade mode 选择值。gateway 删除客户端 owner 和 service credential；业务服务从已验证 JWT 重建 owner，并验证 tenant membership 和 account ownership。

- [ ] **Step 4: 验证 gateway、前端和 compose 配置**

```bash
cd services/api-gateway && ../../.venv/bin/python -m pytest tests -q
bash tools/codex-lowio.sh fe-test src/__tests__/apiClientPlatformContext.test.ts
docker compose -f docker/docker-compose.yml config >/dev/null
```

Expected: exit 0；生产 compose 只 publish gateway/backend，内部服务用 expose。

- [ ] **Step 5: 提交**

```bash
git add services/api-gateway frontend/src/api/client.ts frontend/src/__tests__/apiClientPlatformContext.test.ts docker/docker-compose.yml docs/adr/016-platform-runtime-contracts.md
git commit -m "fix(gateway): enforce service ownership and trusted identity"
```

### Task 8: 统一 liveness、readiness 和运行状态

**Files:**
- Create: `packages/kronos-contracts/pyproject.toml`
- Create: `packages/kronos-contracts/kronos_contracts/__init__.py`
- Create: `packages/kronos-contracts/kronos_contracts/health.py`
- Create: `packages/kronos-contracts/tests/test_health_contract.py`
- Modify: `backend/app/main.py`
- Modify: `services/api-gateway/app/main.py`
- Modify: `services/alert-service/app/main.py`
- Modify: `services/backtest-service/app/main.py`
- Modify: `services/data-service/app/main.py`
- Modify: `services/diagnosis-service/app/main.py`
- Modify: `services/prediction-service/app/main.py`
- Modify: `services/screener-service/app/main.py`
- Modify: `services/signal-service/app/main.py`
- Modify: `services/strategy-service/app/main.py`
- Modify: `services/trade-service/app/main.py`
- Modify: `services/training-service/app/main.py`
- Modify: `backend/Dockerfile`
- Modify: `services/api-gateway/Dockerfile`
- Modify: `services/alert-service/Dockerfile`
- Modify: `services/backtest-service/Dockerfile`
- Modify: `services/data-service/Dockerfile`
- Modify: `services/diagnosis-service/Dockerfile`
- Modify: `services/prediction-service/Dockerfile`
- Modify: `services/screener-service/Dockerfile`
- Modify: `services/signal-service/Dockerfile`
- Modify: `services/strategy-service/Dockerfile`
- Modify: `services/trade-service/Dockerfile`
- Modify: `services/training-service/Dockerfile`
- Modify: `services/alert-service/pyproject.toml`
- Modify: `services/backtest-service/pyproject.toml`
- Modify: `services/diagnosis-service/pyproject.toml`
- Modify: `services/prediction-service/pyproject.toml`
- Modify: `services/screener-service/pyproject.toml`
- Modify: `services/signal-service/pyproject.toml`
- Modify: `services/strategy-service/pyproject.toml`
- Modify: `services/trade-service/pyproject.toml`
- Modify: `services/training-service/requirements.txt`
- Create: `services/api-gateway/tests/test_runtime_readiness.py`
- Modify: `frontend/src/pages/RuntimeStatus.tsx`
- Modify: `frontend/src/__tests__/Phase5SystemPages.test.tsx`

**Interfaces:**
- Produces: `ServiceHealth`, `ComponentCheck` and `/api/v1/runtime/readiness`.

- [ ] **Step 1: 写 contract 和聚合失败测试**

```python
def test_readiness_distinguishes_process_from_dependencies(client, monkeypatch):
    monkeypatch.setattr(health, "check_postgres", AsyncMock(return_value=ComponentCheck(status="unavailable", latency_ms=10)))
    body = client.get("/api/v1/health/ready").json()
    assert body["live"] is True
    assert body["ready"] is False

def test_gateway_readiness_survives_one_timeout(client, monkeypatch):
    monkeypatch.setattr(runtime, "probe_services", AsyncMock(return_value={"trade-service": {"ready": False, "error": "timeout"}}))
    response = client.get("/api/v1/runtime/readiness")
    assert response.status_code == 200
    assert response.json()["services"]["trade-service"]["ready"] is False
```

- [ ] **Step 2: 运行 contract tests 并确认失败**

```bash
bash tools/codex-lowio.sh py packages/kronos-contracts/tests services/api-gateway/tests/test_runtime_readiness.py -q
```

- [ ] **Step 3: 实现统一 health models 和 probes**

```python
class ComponentCheck(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    latency_ms: int | None = None
    reason: str | None = None

class ServiceHealth(BaseModel):
    service: str
    version: str
    live: bool
    ready: bool
    checks: dict[str, ComponentCheck]
    checked_at: datetime
```

旧 `/api/v1/health` 保持兼容；新增 `/api/v1/health/live` 和 `/api/v1/health/ready`。gateway 聚合真实 probes，前端不再硬编码服务端口和在线数量。

每个镜像在安装服务前安装 contract package：

```dockerfile
COPY packages/kronos-contracts /app/packages/kronos-contracts
RUN pip install --no-cache-dir /app/packages/kronos-contracts
```

有 `pyproject.toml` 的服务同时声明 `kronos-contracts` 依赖；training-service 在 requirements 中使用本地镜像安装步骤，不填写无法从公共索引下载的版本号。

- [ ] **Step 4: 运行服务合同与前端测试**

```bash
bash tools/codex-lowio.sh py packages/kronos-contracts/tests -q
python3 tools/run_service_tests.py --core -q
bash tools/codex-lowio.sh fe-test src/__tests__/Phase5SystemPages.test.tsx
bash tools/codex-lowio.sh fe-typecheck
docker compose -f docker/docker-compose.yml build api-gateway data-service screener-service backtest-service training-service
```

Expected: 所有服务 health contract 通过；断开依赖时 ready=false。

- [ ] **Step 5: 提交**

```bash
git add packages/kronos-contracts services frontend/src/pages/RuntimeStatus.tsx frontend/src/__tests__/Phase5SystemPages.test.tsx
git commit -m "feat(runtime): add dependency-aware readiness contracts"
```

### Task 9: 拆分 data inventory、job status 和 readiness 语义

**Files:**
- Create: `services/data-service/app/inventory.py`
- Create: `services/data-service/app/quality/readiness.py`
- Modify: `services/data-service/app/routers/data.py`
- Create: `services/data-service/tests/test_data_status_semantics.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/DataUpdate.tsx`
- Modify: `frontend/src/__tests__/DataUpdate.test.tsx`
- Modify: `services/signal-service/app/routes.py`
- Modify: `services/signal-service/tests/test_signal_contracts.py`

**Interfaces:**
- Produces: `/api/v1/data/inventory`, `/jobs`, `/schedules`, `/readiness`.
- Keeps: `/api/v1/data/status` as compatibility summary.

- [ ] **Step 1: 写语义测试**

```python
def test_inventory_rows_are_table_counts_not_last_job_writes(client, monkeypatch):
    monkeypatch.setattr(inventory, "count_table", lambda table: 8_642_399)
    monkeypatch.setattr(scheduler, "get_job_status", lambda: {"daily": {"pg_written": 5200}})
    body = client.get("/api/v1/data/inventory").json()
    assert body["tables"]["daily_kline"]["rows"] == 8_642_399
    assert body["tables"]["daily_kline"]["rows"] != 5200
```

- [ ] **Step 2: 运行测试确认当前 status 混淆**

```bash
cd services/data-service && ../../.venv/bin/python -m pytest tests/test_data_status_semantics.py -q
```

- [ ] **Step 3: 实现四个资源并移除 signal subprocess fallback**

inventory 查询真实 count/min/max；jobs 返回 scheduler run state；schedules 返回配置；readiness 暂返回 profile evaluator 结果。signal-service 的 `/api/v1/data/*` 兼容路由只转发到 data-service，并带 `Deprecation` header，不执行 subprocess。

- [ ] **Step 4: 运行 data、signal 和前端测试**

```bash
cd services/data-service && ../../.venv/bin/python -m pytest tests -q
cd ../signal-service && ../../.venv/bin/python -m pytest tests -q
bash tools/codex-lowio.sh fe-test src/__tests__/DataUpdate.test.tsx
bash tools/codex-lowio.sh fe-typecheck
```

Expected: 四类状态不再共用 `rows` 语义。

- [ ] **Step 5: 提交**

```bash
git add services/data-service services/signal-service frontend/src/pages/DataUpdate.tsx frontend/src/api/types.ts frontend/src/__tests__/DataUpdate.test.tsx
git commit -m "feat(data): separate inventory jobs schedules and readiness"
```

### Task 10: 建立 profile 驱动的数据 readiness 快照

**Files:**
- Create: `configs/data_readiness_profiles.json`
- Create: `backend/alembic/versions/026_data_readiness_snapshots.py`
- Create: `services/data-service/app/quality/contracts.py`
- Create: `services/data-service/app/quality/evaluator.py`
- Create: `services/data-service/app/quality/repository.py`
- Modify: `services/data-service/app/routers/data.py`
- Create: `services/data-service/tests/test_data_readiness_profiles.py`
- Create: `services/screener-service/app/data_readiness_client.py`
- Modify: `services/screener-service/app/orchestrator.py`
- Modify: `services/backtest-service/app/routes.py`
- Modify: `services/training-service/app/training_engine.py`
- Create: `docs/adr/017-data-readiness-snapshots.md`

**Interfaces:**
- Produces: `evaluate_readiness(profile, target_trade_date, cutoff_time) -> DataReadiness`.
- Persists: immutable `data_readiness_snapshots`.

- [ ] **Step 1: 写关键失败测试**

```python
def test_backtest_profile_blocks_lagging_adjustment_factor():
    states = {
        "daily_kline": SourceState(actual_as_of="2026-07-10", coverage_ratio=0.999),
        "adj_factor": SourceState(actual_as_of="2026-07-07", coverage_ratio=0.999),
    }
    evaluator = ReadinessEvaluator(source_loader=lambda table: states[table])
    result = evaluator.evaluate("backtest_v1", date(2026, 7, 10), cutoff_time=None)
    assert result.status == "blocked"
    assert next(s for s in result.sources if s.source == "adj_factor").status == "stale"
```

增加盘中 14:27 截止时间和可选源缺失的测试。

- [ ] **Step 2: 运行测试确认 evaluator 不存在**

```bash
cd services/data-service && ../../.venv/bin/python -m pytest tests/test_data_readiness_profiles.py -q
```

- [ ] **Step 3: 实现 migration、profiles 和 evaluator**

Migration 建表：

```python
op.create_table(
    "data_readiness_snapshots",
    sa.Column("snapshot_id", sa.String(64), primary_key=True),
    sa.Column("profile", sa.String(80), nullable=False),
    sa.Column("target_trade_date", sa.Date(), nullable=False),
    sa.Column("cutoff_time", sa.DateTime(timezone=True)),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("sources", postgresql.JSONB(), nullable=False),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("expires_at", sa.DateTime(timezone=True)),
)
```

首批 profiles：`daily_screening_v1`、`intraday_screening_v1`、`backtest_v1`、`training_v1`、`cb_auction_v1`。正式模式 blocked 时 screener、backtest、training 不启动执行。

- [ ] **Step 4: 运行 migration 和集成测试**

```bash
cd backend && ../.venv/bin/alembic upgrade head
cd .. && bash tools/codex-lowio.sh py services/data-service/tests/test_data_readiness_profiles.py -q
bash tools/codex-lowio.sh py services/screener-service/tests/test_api.py -q
```

Expected: lagging adj_factor 阻断；snapshot 可按 ID 查询。

- [ ] **Step 5: 提交**

```bash
git add configs/data_readiness_profiles.json backend/alembic/versions/026_data_readiness_snapshots.py services/data-service services/screener-service/app/data_readiness_client.py services/screener-service/app/orchestrator.py services/backtest-service/app/routes.py services/training-service/app/training_engine.py docs/adr/017-data-readiness-snapshots.md
git commit -m "feat(data): enforce model-specific readiness snapshots"
```

### Task 11: 把 schema drift 和表所有权变成发布门

**Files:**
- Create: `configs/data_ownership.json`
- Modify: `services/sql/audit/schema_audit.py`
- Create: `services/sql/audit/test_schema_contract.py`
- Create: `tools/audit_table_ownership.py`
- Create: `tools/tests/test_audit_table_ownership.py`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/adr/018-schema-and-table-ownership.md`

**Interfaces:**
- Produces: schema audit JSON with severity, owner, exemption and expiry.
- Produces: `python3 tools/audit_table_ownership.py --fail-on violation`.

- [ ] **Step 1: 写 drift 和过期豁免测试**

```python
def test_expired_high_drift_exemption_fails():
    finding = Finding(table="stk_mins", severity="high", exempt_until=date(2026, 7, 1))
    assert exit_code([finding], today=date(2026, 7, 10), fail_on="medium") == 1

def test_table_has_exactly_one_owner():
    registry = {"daily_kline": {"owner": "data-service", "writers": ["data-service"]}}
    assert audit_registry(registry).violations == []
```

- [ ] **Step 2: 运行测试确认 CLI 能力缺失**

```bash
bash tools/codex-lowio.sh py services/sql/audit/test_schema_contract.py tools/tests/test_audit_table_ownership.py -q
```

- [ ] **Step 3: 实现 JSON 输出、退出码和 ownership registry**

`configs/data_ownership.json` 至少覆盖 readiness profiles、策略、训练、回测和交易关键表。审计器把 PostgreSQL 类型别名标准化，避免 `varchar/character varying` 和 `timestamptz/timestamp with time zone` 假阳性。

- [ ] **Step 4: 在现有 PG 和 fresh DB 运行**

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 services/sql/audit/schema_audit.py --json outputs/schema-audit.json --fail-on medium
python3 tools/audit_table_ownership.py --fail-on violation
```

Expected: 未豁免 high/medium 为 0；若当前仍有真实 drift，任务保持红灯并按表创建后续 migration，不修改测试阈值。

- [ ] **Step 5: 提交**

```bash
git add configs/data_ownership.json services/sql/audit tools/audit_table_ownership.py tools/tests/test_audit_table_ownership.py .github/workflows/ci.yml docs/adr/018-schema-and-table-ownership.md
git commit -m "feat(governance): gate releases on schema and table ownership"
```

### Task 12: 建立不可变模型运行 manifest 和正式时间线

**Files:**
- Create: `packages/kronos-contracts/kronos_contracts/model_run.py`
- Create: `packages/kronos-contracts/tests/test_model_run_contract.py`
- Modify: `tools/run_research_pipeline.py`
- Create: `tools/tests/test_run_research_manifest.py`
- Modify: `tools/walk_forward.py`
- Modify: `services/training-service/tests/test_walk_forward_timeline.py`
- Modify: `configs/model_pipeline.json`

**Interfaces:**
- Produces: `ModelRunManifest` schema version 1.0.
- Produces: official run requires clean worktree and strict timeline.

- [ ] **Step 1: 写 manifest 测试**

```python
def test_official_manifest_requires_clean_strict_run():
    with pytest.raises(ValidationError):
        ModelRunManifest(
            schema_version="1.0", run_id="RUN-1", official=True,
            working_tree_dirty=True, strict_timeline=False,
            model_key="bi_trend_launch", model_version="v13",
            code_commit="abc123", parameters_hash="sha256:x",
            target_trade_date=date(2026, 7, 10), data_snapshot_id="DS-1",
            universe_hash="sha256:u", result_status="success",
        )
```

- [ ] **Step 2: 运行测试确认 schema 缺失**

```bash
bash tools/codex-lowio.sh py packages/kronos-contracts/tests/test_model_run_contract.py tools/tests/test_run_research_manifest.py -q
```

- [ ] **Step 3: 实现 manifest 和 pipeline 输出**

manifest 必含 code commit、dirty、参数 hash、目标交易日、截止时间、snapshot、股票池 hash、成本、产物和状态。`walk_forward --official` 自动启用 strict timeline；诊断性关闭 strict 的结果强制 `official=false`。

- [ ] **Step 4: 运行时间线和 pipeline tests**

```bash
bash tools/codex-lowio.sh py packages/kronos-contracts/tests/test_model_run_contract.py tools/tests/test_run_research_manifest.py services/training-service/tests/test_walk_forward_timeline.py -q
```

Expected: official + dirty/late commit/非 strict 均 exit 2 或 validation failure。

- [ ] **Step 5: 提交**

```bash
git add packages/kronos-contracts tools/run_research_pipeline.py tools/walk_forward.py tools/tests/test_run_research_manifest.py services/training-service/tests/test_walk_forward_timeline.py configs/model_pipeline.json
git commit -m "feat(models): record immutable official run manifests"
```

### Task 13: 用真实因子快照重建 backtest adapter

**Files:**
- Create: `packages/kronos-factors/kronos_factors/evaluation/factor_ic.py`
- Create: `packages/kronos-factors/tests/test_factor_ic.py`
- Create: `services/backtest-service/app/adapters/base.py`
- Create: `services/backtest-service/app/adapters/registry.py`
- Create: `services/backtest-service/app/adapters/bi_trend.py`
- Create: `services/backtest-service/app/adapters/cb_auction_t0.py`
- Modify: `services/backtest-service/app/routes.py`
- Create: `services/backtest-service/tests/test_factor_evidence_api.py`
- Modify: `services/training-service/app/factor_calibration.py`

**Interfaces:**
- Produces: `BacktestAdapter.run(request, readiness) -> BacktestReport`.
- Produces: observed factor IC from factor snapshots and future adjusted returns.

- [ ] **Step 1: 写数值行为测试**

```python
def test_monotonic_scores_have_positive_rank_ic():
    scores = np.array([1, 2, 3, 4, 5], dtype=float)
    returns = np.array([-0.02, -0.01, 0.0, 0.01, 0.02], dtype=float)
    assert compute_cross_section_ic(scores, returns).rank_ic == pytest.approx(1.0)

def test_shuffled_returns_do_not_create_stable_ic():
    rng = np.random.default_rng(42)
    scores = np.arange(100, dtype=float)
    period_ics = [
        compute_cross_section_ic(scores, rng.permutation(scores)).rank_ic
        for _ in range(60)
    ]
    assert abs(float(np.mean(period_ics))) < 0.10
```

增加复权、T+1 open、成本和 minimum sample tests。

- [ ] **Step 2: 运行测试并确认真实 evaluator 缺失**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_factor_ic.py services/backtest-service/tests/test_factor_evidence_api.py -q
```

- [ ] **Step 3: 实现 factor evaluator 和 adapter registry**

```python
class BacktestAdapter(Protocol):
    model_key: str
    def run(self, request: BacktestRequest, readiness: DataReadiness) -> BacktestReport: ...

BACKTEST_ADAPTERS = {
    "bi_trend_launch": BiTrendWalkForwardAdapter(),
    "cb_auction_t0": CbAuctionT0Adapter(),
}
```

每个横截面交易日计算 Spearman IC，再跨期计算 ICIR。少于 20 个交易日、每日至少 30 个股票或总观测少于 500 时返回 `insufficient_data`。training calibration 只能消费已保存的 evaluation ID。

- [ ] **Step 4: 运行因素、服务和回测 tests**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_factor_ic.py -q
cd services/backtest-service && ../../.venv/bin/python -m pytest tests -q
cd ../training-service && ../../.venv/bin/python -m pytest tests -q
```

Expected: 真实数值夹具通过；未注册模型返回 `MODEL_BACKTEST_NOT_IMPLEMENTED`。

- [ ] **Step 5: 提交**

```bash
git add packages/kronos-factors/kronos_factors/evaluation packages/kronos-factors/tests/test_factor_ic.py services/backtest-service services/training-service/app/factor_calibration.py
git commit -m "feat(backtest): evaluate observed factors with adjusted returns"
```

### Task 14: 建立模型晋级门

**Files:**
- Create: `configs/model_admission_gates.json`
- Create: `services/training-service/app/admission.py`
- Modify: `services/training-service/app/schemas.py`
- Modify: `services/training-service/app/routes.py`
- Modify: `services/training-service/app/mlflow_client.py`
- Create: `services/training-service/tests/test_model_admission.py`
- Create: `docs/adr/019-model-admission-gate.md`

**Interfaces:**
- Produces: `evaluate_admission(model_version_id, target_stage) -> AdmissionDecision`.
- Enforces stages: research → candidate → paper → production.

- [ ] **Step 1: 写五个独立阻断测试**

```python
@pytest.mark.parametrize("failed_gate", [
    "data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample",
])
def test_each_required_gate_blocks_promotion(failed_gate):
    evidence = {
        gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"}
        for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]
    }
    evidence[failed_gate] = {"status": "failed"}
    decision = evaluate_admission(evidence, target_stage="paper")
    assert decision.allowed is False
    assert failed_gate in decision.failed_gates
```

增加 mock MLflow 和无 baseline 的测试。

- [ ] **Step 2: 运行测试确认 admission 模块不存在**

```bash
cd services/training-service && ../../.venv/bin/python -m pytest tests/test_model_admission.py -q
```

- [ ] **Step 3: 实现 gate 和 promotion transaction**

```python
class AdmissionDecision(BaseModel):
    allowed: bool
    target_stage: Literal["candidate", "paper", "production"]
    passed_gates: list[str]
    failed_gates: list[str]
    evidence_run_ids: list[str]
```

production 模式下 MLflow 连接失败直接失败；PG stage 只有在 MLflow alias 更新成功后提交。阈值未由 PRD Q-3 批准前，production promotion 固定 blocked。

- [ ] **Step 4: 运行 training suite**

```bash
cd services/training-service && ../../.venv/bin/python -m pytest tests -q
```

Expected: 所有负向 gate 通过；旧 production 版本在晋级失败后保持不变。

- [ ] **Step 5: 提交**

```bash
git add configs/model_admission_gates.json services/training-service docs/adr/019-model-admission-gate.md
git commit -m "feat(training): gate model promotion on observed evidence"
```

### Task 15: 收敛前端 route registry 和域 API

**Files:**
- Create: `frontend/src/app/routeRegistry.tsx`
- Create: `frontend/src/__tests__/RouteRegistry.test.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/api/core/http.ts`
- Create: `frontend/src/api/core/context.ts`
- Create: `frontend/src/api/domains/data.ts`
- Create: `frontend/src/api/domains/screener.ts`
- Create: `frontend/src/api/domains/models.ts`
- Create: `frontend/src/api/domains/strategy.ts`
- Create: `frontend/src/api/domains/trade.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/__tests__/PrototypeRoutes.test.tsx`
- Modify: `frontend/src/__tests__/ProtectedRoute.test.tsx`

**Interfaces:**
- Produces: `AppRouteDefinition[]` as menu/router/permission SSOT.
- Keeps: `client.ts` compatibility re-exports.

- [ ] **Step 1: 写单一来源测试**

```tsx
it('derives menu and protected routes from the same registry', () => {
  const definition = routeRegistry.find(item => item.path === '/screener')!
  expect(buildMenuItems('admin')).toContainEqual(expect.objectContaining({ key: definition.path }))
  expect(buildProtectedRoutes()).toContainEqual(expect.objectContaining({ path: definition.path }))
  expect(definition.permission).toBe('screener')
})
```

- [ ] **Step 2: 运行测试确认 registry 不存在**

```bash
bash tools/codex-lowio.sh fe-test src/__tests__/RouteRegistry.test.tsx
```

- [ ] **Step 3: 迁移路由并拆 API，保留兼容 barrel**

```tsx
export interface AppRouteDefinition {
  key: string
  path: string
  aliases?: string[]
  label: string
  group: MenuGroup
  roles: Role[]
  permission: PermissionKey
  navVisible: boolean
  load: () => Promise<{ default: ComponentType }>
}
```

`App.tsx` 删除重复的菜单和 protected route arrays。`client.ts` 从 domain modules re-export 旧 API 名称，页面可以分批迁移。

- [ ] **Step 4: 跑全部前端质量门**

```bash
bash tools/codex-lowio.sh fe-typecheck
bash tools/codex-lowio.sh fe-test --run
cd frontend && npm run build
```

Expected: 0 failed，build exit 0，所有现有路由保持。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/app frontend/src/api frontend/src/App.tsx frontend/src/__tests__
git commit -m "refactor(frontend): centralize routes and domain APIs"
```

### Task 16: 拆分 screener router 并把流水线改成受控 job

**Files:**
- Create: `services/screener-service/app/domains/screening/router.py`
- Create: `services/screener-service/app/domains/screening/service.py`
- Create: `services/screener-service/app/domains/candidates/router.py`
- Create: `services/screener-service/app/domains/candidates/repository.py`
- Create: `services/screener-service/app/domains/supply_chain/router.py`
- Create: `services/screener-service/app/domains/supply_chain/service.py`
- Create: `services/screener-service/app/jobs/pipeline_runner.py`
- Create: `backend/alembic/versions/027_task_runs.py`
- Modify: `services/screener-service/app/routers/screener.py`
- Modify: `services/screener-service/app/routers/dashboard.py`
- Modify: `services/screener-service/app/main.py`
- Modify: `services/screener-service/tests/test_api.py`
- Modify: `services/screener-service/tests/test_chain_api.py`
- Modify: `services/screener-service/tests/test_candidate_pool_api.py`
- Create: `services/screener-service/tests/test_pipeline_runner.py`
- Create: `services/screener-service/tests/fixtures/openapi_paths.json`

**Interfaces:**
- Preserves: all current `/api/v1/screener/*` and `/api/v1/supply-chain/*` paths.
- Produces: `submit_pipeline(request, idempotency_key) -> run_id`.

- [x] **Step 1: 保存 OpenAPI characterization fixture**

```python
def test_openapi_paths_match_baseline(client):
    baseline_paths = json.loads(
        Path("tests/fixtures/openapi_paths.json").read_text(encoding="utf-8")
    )
    current = sorted(client.get("/openapi.json").json()["paths"])
    assert current == baseline_paths
```

把当前路径列表保存为 `services/screener-service/tests/fixtures/openapi_paths.json`，只保存 path 和 method，不保存动态 schema 排序。

- [x] **Step 2: 运行 characterization tests**

```bash
cd services/screener-service && ../../.venv/bin/python -m pytest tests/test_api.py tests/test_chain_api.py tests/test_candidate_pool_api.py -q
```

Expected: baseline green before moving symbols。

- [x] **Step 3: 按 candidates → screening → supply chain 顺序移动代码**

每移动一个 router 都从旧 `screener.py` re-export 测试直接使用的 helper。`screener.py` 最终只 include subrouters 和兼容导出。

Pipeline runner 使用持久化状态和幂等键；dashboard router 不再 `Popen(... DEVNULL)`。engine 失败返回 failed，不自动切 subprocess。

`027_task_runs.py` 创建最小任务表：

```python
op.create_table(
    "task_runs",
    sa.Column("run_id", sa.String(64), primary_key=True),
    sa.Column("task_type", sa.String(80), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("request_payload", postgresql.JSONB(), nullable=False),
    sa.Column("result_payload", postgresql.JSONB()),
    sa.Column("error_payload", postgresql.JSONB()),
    sa.Column("code_commit", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)
```

- [x] **Step 4: 运行 screener 全量 tests 和 OpenAPI diff**

```bash
cd services/screener-service && ../../.venv/bin/python -m pytest tests -q
wc -l app/routers/screener.py
```

Expected: tests exit 0；`screener.py` ≤ 2,500 行；OpenAPI path/method 与 baseline 一致。

- [x] **Step 5: 提交三个可回滚 commit**

```bash
git add services/screener-service/app/domains/candidates services/screener-service/app/routers/screener.py services/screener-service/tests
git commit -m "refactor(screener): extract candidate domain"
git add services/screener-service/app/domains/screening services/screener-service/app/routers/screener.py services/screener-service/tests
git commit -m "refactor(screener): extract screening domain"
git add services/screener-service/app/domains/supply_chain services/screener-service/app/jobs services/screener-service/app/routers services/screener-service/app/main.py services/screener-service/tests backend/alembic/versions/027_task_runs.py
git commit -m "refactor(screener): extract supply chain and pipeline jobs"
```

### Task 17: 真实 API SIT、浏览器 UAT 和回滚演练

**Files:**
- Modify: `tools/full_stack_smoke.py`
- Modify: `tools/tests/test_full_stack_smoke.py`
- Create: `tools/page_api_smoke.py`
- Create: `tools/tests/test_page_api_smoke.py`
- Create: `frontend/tests/sit/platform-five-domain.spec.ts`
- Create: `docs/qa/platform-five-domain-e2e-2026-07-10.md`
- Create: `docs/qa/platform-five-domain-uat-2026-07-10.md`
- Modify: `docker/docker-compose.yml`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: release evidence and rollback verdict.

- [x] **Step 1: 写 smoke unit tests**

覆盖 request ID、run ID、readiness blocked、合法 no-pick、paper-only 和 safe skip：

```python
def test_smoke_rejects_live_mode():
    with pytest.raises(SystemExit):
        load_config(["--trade-mode", "live"])

def test_no_pick_is_success_when_readiness_passes():
    assert classify_screener_result({"result_status": "success_no_matches", "picks": []}) == "pass"
```

- [x] **Step 2: 实现 paper-only 和 no-pick 两种 smoke 模式**

给 `SmokeConfig` 增加 `trade_mode` 和 `require_pick`。CLI 只接受 `--trade-mode paper`；`--require-pick` 用于 AC-E2E-1，合法 no-pick 在普通市场 smoke 中通过，但明确跳过依赖候选的步骤，不能计入全链路三次通过。

```python
parser.add_argument("--trade-mode", choices=("paper",), default="paper")
parser.add_argument("--require-pick", action="store_true")

if result_status == "success_no_matches":
    if config.require_pick:
        raise SmokeError("screener returned a valid no-pick result; full-chain evidence requires a real pick")
    return {"status": "pass", "result_status": result_status, "safe_skips": [
        "diagnosis", "strategy", "backtest", "paper_order",
    ]}
```

全链路 UAT 必须使用真实模型候选，不得注入或填充候选。若目标日所有模型均合法无候选，AC-E2E-1 保持 blocked，另行保存 no-pick 市场 smoke 证据。

- [x] **Step 3: 运行所有静态和单元质量门**

```bash
bash tools/codex-lowio.sh fe-typecheck
bash tools/codex-lowio.sh fe-test --run
cd frontend && npm run build
cd .. && python3 tools/run_service_tests.py --core -q
```

Expected: 全部 exit 0。

- [blocked] **Step 4: 部署独立 UAT 并验证 schema/readiness**

已完成同等范围的功能分支隔离验证栈：schema、ownership、readiness、页面 API 和浏览器均通过；正式 UAT 仍受“必须从已合并 main 的干净代码部署”门禁约束。

按项目 UAT skill 部署后运行：

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python3 services/sql/audit/schema_audit.py --json outputs/schema-audit.json --fail-on medium
python3 tools/audit_table_ownership.py --fail-on violation
python3 tools/page_api_smoke.py --timeout 30
```

Expected: schema/ownership gate 通过，页面 API 不使用 mock。

- [blocked] **Step 5: 连续三次核心 smoke 和真实浏览器 UAT**

真实候选链路已跑通到诊断和策略确认，但回测当前只有 13 个交易期，未达到 20 期/30 股/500 条观测门槛；smoke 已 fail-closed，未伪造回测或订单。

```bash
python3 tools/full_stack_smoke.py --mode short --top-n 5 --timeout 45 --trade-mode paper --require-pick
python3 tools/full_stack_smoke.py --mode short --top-n 5 --timeout 45 --trade-mode paper --require-pick
python3 tools/full_stack_smoke.py --mode short --top-n 5 --timeout 45 --trade-mode paper --require-pick
cd frontend && npx playwright test tests/sit/platform-five-domain.spec.ts
```

报告必须记录代码 commit、交易日、截止时间、data snapshot、plan ID、backtest run ID、paper order ID 和账户查询结果。

- [blocked] **Step 6: 回滚演练和签字**

正式回滚需要 main 发布镜像与上一版本镜像；当前分支验证不覆盖已有旧 UAT 栈。

回滚上一波应用镜像，不回滚数据库新增表；运行同一套 read-only smoke，确认旧 API 可读取新增 nullable 元数据。交易保持 paper。把结果写入两份 QA 报告。

- [x] **Step 7: 提交验证资产**

```bash
git add tools/full_stack_smoke.py tools/tests/test_full_stack_smoke.py tools/page_api_smoke.py tools/tests/test_page_api_smoke.py frontend/tests/sit/platform-five-domain.spec.ts docs/qa/platform-five-domain-e2e-2026-07-10.md docs/qa/platform-five-domain-uat-2026-07-10.md docker/docker-compose.yml
git commit -m "test: add five-domain release gates"
```

## AC traceability

| PRD AC | Primary tasks |
|---|---|
| AC-FE-1 | 1、6、15、17 |
| AC-FE-2 | 15 |
| AC-FE-3 | 15 |
| AC-FE-4 | 1、2 |
| AC-FE-5 | 8 |
| AC-BE-1 | 6 |
| AC-BE-2、AC-BE-3 | 8 |
| AC-BE-4 | 16 |
| AC-BE-5 | 9、16 |
| AC-AR-1 | 8、10、12 |
| AC-AR-2、AC-AR-3 | 11 |
| AC-AR-4 | 7 |
| AC-DATA-1、AC-DATA-2、AC-DATA-3 | 9、10 |
| AC-DATA-4、AC-DATA-6 | 11 |
| AC-DATA-5 | 4、5、10 |
| AC-ML-1、AC-ML-2 | 12 |
| AC-ML-3、AC-ML-4、AC-ML-7 | 4、13 |
| AC-ML-5、AC-ML-6 | 14、15 |
| AC-ML-8 | 2、3、4、5 |
| AC-E2E-1、AC-E2E-2 | 17 |
| AC-E2E-3、AC-E2E-5 | 5、17 |
| AC-E2E-4 | 17 |

## Final verification checklist

- [x] PRD 所有已执行 P0 AC 有对应任务和自动化证据；E2E-1 保持 blocked。
- [x] 生产响应中没有 preview、fixed、random、proxy 指标。
- [x] live broker 未接通时保持 blocked，没有 stub 成交。
- [x] frontend typecheck、tests、build 全绿。
- [x] backend 与 11 个核心微服务在独立进程中测试通过。
- [x] `/api/v1/data` 唯一 owner 是 data-service。
- [x] gateway 不信任客户端 owner/service headers。
- [x] readiness snapshot 阻断复权因子或必需数据落后，且已持久化到 PostgreSQL。
- [x] schema high/medium 未豁免项为 0。
- [blocked] 正式模型产物有 clean commit、strict timeline、snapshot 和成本。
- [x] 模型晋级失败不会改变当前 production alias。
- [x] screener 外部路径兼容，主 router ≤ 2,500 行。
- [blocked] 三次真实 API smoke 和一次无 mock 浏览器 UAT：浏览器已通过，三次全链路受真实回测观测门槛阻断。
- [blocked] 回滚演练和正式签字：等待 main 发布基线，交易验证保持 paper。

## Plan self-review

- PRD 的前端、后端、架构、数据和模型要求都映射到至少一个任务。
- 所有新接口在任务中给出名称、输入、输出或失败行为。
- schema、身份和交易任务设置了失败关闭与 review 门。
- 计划没有要求在同一任务中重写整套系统。
- 每项改动都先有失败测试、聚焦验证和独立提交。
