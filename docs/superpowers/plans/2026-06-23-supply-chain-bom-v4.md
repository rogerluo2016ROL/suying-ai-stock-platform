# Supply Chain BOM V4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V4 大葱产业链 BOM model: policy themes, BOM graph APIs, company evidence, scoring, LLM extraction, frontend drill-down, and validation.

**Architecture:** Keep the current `supply_chain` mode as the public entry point. Add focused graph/evidence modules under `packages/kronos-factors`, expose read APIs through `services/screener-service`, and add a dedicated frontend view that uses existing Ant Design and ECharts. Use PostgreSQL tables for graph/evidence state, JSON seed files for first policy themes, and DeepSeek-compatible LLM extraction behind a small adapter.

**Tech Stack:** FastAPI, PostgreSQL, Alembic, pytest, React 18, Vite, TypeScript, Ant Design, ECharts, DeepSeek/OpenAI-compatible LLM client, Tushare.

## Global Constraints

- Do not execute real trades. `trade_signal` is a research signal only.
- Do not add `httpx` or `aiohttp`; keep project HTTP conventions.
- Do not add React Flow or another graph dependency unless tech-lead approves it.
- Preserve `trade_date` historical cutoff for scoring and validation.
- Every LLM-extracted fact must carry source, date, confidence, and review status.
- Tushare high-permission interfaces must be probe-tested before implementation claims coverage.
- Manual overrides outrank LLM extraction.
- Do not stage or commit `outputs/intraday_v8_2026-06-23_*.json`.

---

## File Structure

- Create `backend/alembic/versions/012_supply_chain_bom_v4.py`: PostgreSQL schema for policy sources, themes, BOM nodes/edges, mappings, evidence, scores, and manual overrides.
- Create `packages/kronos-factors/configs/supply_chain_bom_v4.json`: seed policy themes and BOM nodes for the six future-industry directions.
- Create `packages/kronos-factors/kronos_factors/engine/supply_chain_bom.py`: graph loader, node matching, evidence aggregation, and score helpers.
- Modify `packages/kronos-factors/kronos_factors/engine/supply_chain.py`: call V4 scorer and enrich picks while preserving existing fields.
- Create `packages/kronos-factors/tests/test_supply_chain_bom_v4.py`: unit tests for seed loading, scoring, cutoff behavior, and signal labels.
- Modify `services/screener-service/app/routers/screener.py`: add BOM graph APIs and route V4 fields through `/run`.
- Create `services/screener-service/tests/test_supply_chain_bom_api.py`: API contract tests.
- Create `services/screener-service/app/llm_supply_chain.py`: LLM extraction adapter, provider guardrails, and deterministic fallback.
- Create `services/screener-service/tests/test_llm_supply_chain.py`: mocked LLM boundary tests.
- Modify `frontend/src/api/client.ts`: add supply-chain API client methods.
- Create `frontend/src/pages/SupplyChainBom.tsx`: dedicated drill-down workspace.
- Modify `frontend/src/App.tsx`: add menu item and route.
- Create `frontend/src/pages/__tests__/SupplyChainBom.test.tsx`: rendering and drill-down tests.
- Modify `packages/kronos-factors/kronos_factors/backtest/supply_chain_validation.py`: add V4 baseline comparison label if needed.
- Create `docs/design/supply-chain-bom-v4/api-contract.md`: API response examples used by QA.

---

### Task 1: Database Schema and Seed Contract

**Files:**
- Create: `backend/alembic/versions/012_supply_chain_bom_v4.py`
- Create: `packages/kronos-factors/configs/supply_chain_bom_v4.json`
- Test: `services/screener-service/tests/test_supply_chain_bom_api.py`

**Interfaces:**
- Produces table names used by later tasks: `policy_sources`, `policy_themes`, `supply_chain_bom_nodes`, `supply_chain_bom_edges`, `company_bom_mapping`, `company_evidence`, `supply_chain_scores`, `manual_overrides`.
- Produces seed keys used by Task 2: `themes[].theme_id`, `chains[].chain_id`, `nodes[].node_id`, `nodes[].keywords`.

- [x] **Step 1: Write migration smoke test**

Create `services/screener-service/tests/test_supply_chain_bom_api.py` with this first test:

```python
def test_supply_chain_bom_schema_table_names_are_stable():
    expected = {
        "policy_sources",
        "policy_themes",
        "supply_chain_bom_nodes",
        "supply_chain_bom_edges",
        "company_bom_mapping",
        "company_evidence",
        "supply_chain_scores",
        "manual_overrides",
    }
    assert len(expected) == 8
```

- [x] **Step 2: Create Alembic migration**

Create `backend/alembic/versions/012_supply_chain_bom_v4.py` with revision `012_supply_chain_bom_v4`, down revision `011_ths_daily_align`, and SQL `CREATE TABLE IF NOT EXISTS` statements. Use these primary keys:

```python
revision = "012_supply_chain_bom_v4"
down_revision = "011_ths_daily_align"
branch_labels = None
depends_on = None
```

Tables must include these minimum columns:

```sql
policy_sources(source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, title TEXT NOT NULL, source_url TEXT, published_at DATE, content_hash TEXT, raw_text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
policy_themes(theme_id TEXT PRIMARY KEY, name TEXT NOT NULL, policy_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0, keywords JSONB NOT NULL DEFAULT '[]', source_ids JSONB NOT NULL DEFAULT '[]');
supply_chain_bom_nodes(node_id TEXT PRIMARY KEY, theme_id TEXT NOT NULL, chain_id TEXT NOT NULL, parent_node_id TEXT, level TEXT NOT NULL, name TEXT NOT NULL, node_type TEXT NOT NULL, keywords JSONB NOT NULL DEFAULT '[]', policy_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0);
supply_chain_bom_edges(edge_id TEXT PRIMARY KEY, from_node_id TEXT NOT NULL, to_node_id TEXT NOT NULL, relation TEXT NOT NULL DEFAULT 'upstream_downstream');
company_bom_mapping(mapping_id TEXT PRIMARY KEY, code TEXT NOT NULL, node_id TEXT NOT NULL, product_name TEXT, material_name TEXT, evidence_ids JSONB NOT NULL DEFAULT '[]', confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0, status TEXT NOT NULL DEFAULT 'pending_review', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
company_evidence(evidence_id TEXT PRIMARY KEY, code TEXT, node_id TEXT, source_id TEXT, evidence_type TEXT NOT NULL, summary TEXT NOT NULL, excerpt TEXT, confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0, evidence_date DATE, status TEXT NOT NULL DEFAULT 'pending_review');
supply_chain_scores(score_id TEXT PRIMARY KEY, code TEXT NOT NULL, trade_date DATE NOT NULL, node_id TEXT, total_score DOUBLE PRECISION NOT NULL, rating TEXT NOT NULL, trade_signal TEXT NOT NULL, dimension_scores JSONB NOT NULL DEFAULT '{}', evidence_ids JSONB NOT NULL DEFAULT '[]');
manual_overrides(override_id TEXT PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}', operator TEXT NOT NULL DEFAULT 'system', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
```

- [x] **Step 3: Add seed config**

Create `packages/kronos-factors/configs/supply_chain_bom_v4.json` with seed themes:

```json
{
  "version": "4.0",
  "themes": [
    {"theme_id": "future_industry_core", "name": "未来产业主攻方向", "policy_weight": 1.5, "keywords": ["量子科技", "生物制造", "氢能", "核聚变能", "脑机接口", "具身智能", "第六代移动通信"]},
    {"theme_id": "new_quality_productivity", "name": "新质生产力", "policy_weight": 1.3, "keywords": ["新质生产力", "硬科技", "科技自立自强"]},
    {"theme_id": "tech_self_reliance", "name": "科技自立自强", "policy_weight": 1.25, "keywords": ["关键核心技术", "卡脖子", "国产替代"]}
  ],
  "nodes": [
    {"node_id": "quantum_core", "theme_id": "future_industry_core", "chain_id": "quantum", "parent_node_id": null, "level": "chain", "name": "量子科技", "node_type": "industry", "keywords": ["量子计算", "量子通信", "量子测量"]},
    {"node_id": "embodied_ai_core", "theme_id": "future_industry_core", "chain_id": "embodied_ai", "parent_node_id": null, "level": "chain", "name": "具身智能", "node_type": "industry", "keywords": ["具身智能", "机器人", "伺服", "减速器", "控制器"]},
    {"node_id": "6g_core", "theme_id": "future_industry_core", "chain_id": "6g", "parent_node_id": null, "level": "chain", "name": "第六代移动通信", "node_type": "industry", "keywords": ["6G", "第六代移动通信", "卫星互联网", "太赫兹"]}
  ],
  "edges": []
}
```

- [x] **Step 4: Run syntax checks**

Run:

```bash
.venv/bin/python -c "import ast; ast.parse(open('backend/alembic/versions/012_supply_chain_bom_v4.py').read())"
python3 -m json.tool packages/kronos-factors/configs/supply_chain_bom_v4.json >/tmp/supply_chain_bom_v4.json
```

Expected: both commands exit 0.

---

### Task 2: BOM Loader, Scoring, and Signals

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/supply_chain_bom.py`
- Modify: `packages/kronos-factors/kronos_factors/engine/supply_chain.py`
- Test: `packages/kronos-factors/tests/test_supply_chain_bom_v4.py`

**Interfaces:**
- Consumes: `packages/kronos-factors/configs/supply_chain_bom_v4.json`
- Produces: `load_bom_config() -> dict`, `score_company_v4(base_pick: dict, evidence: list[dict]) -> dict`, `derive_trade_signal(total_score: float, dimension_scores: dict) -> str`

- [x] **Step 1: Write failing tests**

Create `packages/kronos-factors/tests/test_supply_chain_bom_v4.py`:

```python
from kronos_factors.engine.supply_chain_bom import derive_trade_signal, load_bom_config, score_company_v4


def test_load_bom_config_contains_future_industry_core():
    cfg = load_bom_config()
    names = {theme["name"] for theme in cfg["themes"]}
    assert "未来产业主攻方向" in names


def test_derive_trade_signal_labels():
    assert derive_trade_signal(86, {"commercialization": 14, "market": 9}) == "强启动"
    assert derive_trade_signal(78, {"commercialization": 12, "market": 7}) == "启动"
    assert derive_trade_signal(70, {"commercialization": 7, "market": 4}) == "观察"
    assert derive_trade_signal(48, {"risk": 9}) == "风险回避"


def test_score_company_v4_adds_required_fields():
    pick = {"code": "688001", "name": "测试科技", "total_score": 72, "growth_score": 24, "profit_score": 10}
    enriched = score_company_v4(pick, [{"evidence_type": "policy", "confidence": 0.9}])
    assert enriched["rating"] in {"S", "A", "B", "C", "D"}
    assert enriched["trade_signal"] in {"观察", "关注", "启动", "强启动", "风险回避"}
    assert "dimension_scores" in enriched
    assert "evidence" in enriched
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_bom_v4.py -v
```

Expected: FAIL because `supply_chain_bom` does not exist.

- [x] **Step 3: Implement `supply_chain_bom.py`**

Create the module with pure functions. `score_company_v4` must be deterministic and must not call external services.

Core scoring formula:

```python
DIM_WEIGHTS = {
    "policy": 15,
    "bom": 15,
    "chokepoint": 20,
    "growth": 15,
    "profit": 10,
    "commercialization": 15,
    "market": 10,
}
```

Use existing `growth_score` and `profit_score` from V3 when available. Default missing evidence to low but nonzero scores so the API still works before LLM extraction is populated.

- [x] **Step 4: Wire enrichment into `SupplyChainEngine.run`**

In `packages/kronos-factors/kronos_factors/engine/supply_chain.py`, import `score_company_v4` and enrich each pick before final sorting. Preserve existing keys: `total_score`, `score`, `chain`, `layer`, `moat_score`, `growth_score`, `profit_score`, `rating_score`, `consensus_score`.

- [x] **Step 5: Run package tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_bom_v4.py tests/test_engines.py -v
```

Expected: PASS.

---

### Task 3: Screener BOM APIs

**Files:**
- Modify: `services/screener-service/app/routers/screener.py`
- Test: `services/screener-service/tests/test_supply_chain_bom_api.py`
- Create: `docs/design/supply-chain-bom-v4/api-contract.md`

**Interfaces:**
- Produces API endpoints:
  - `GET /api/v1/screener/supply-chain/themes`
  - `GET /api/v1/screener/supply-chain/bom`
  - `GET /api/v1/screener/supply-chain/node/{node_id}`
  - `GET /api/v1/screener/supply-chain/company/{code}`

- [x] **Step 1: Add API tests**

Append tests that import `router` through FastAPI `TestClient` and verify response keys:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.screener import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_supply_chain_themes_endpoint_returns_themes():
    r = _client().get("/api/v1/screener/supply-chain/themes")
    assert r.status_code == 200
    body = r.json()
    assert "themes" in body
    assert any(t["name"] == "未来产业主攻方向" for t in body["themes"])


def test_supply_chain_bom_endpoint_returns_nodes_and_edges():
    r = _client().get("/api/v1/screener/supply-chain/bom")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body
    assert "edges" in body
```

- [x] **Step 2: Implement endpoints**

Use `load_bom_config()` from Task 2. For `node/{node_id}` and `company/{code}`, return empty arrays if database evidence is unavailable:

```json
{"node_id":"quantum_core","companies":[],"evidence":[]}
```

- [x] **Step 3: Document response contract**

Create `docs/design/supply-chain-bom-v4/api-contract.md` with one request and response example per endpoint. The examples must include `policy_theme`, `bom_path`, `rating`, `rank`, and `trade_signal`.

- [x] **Step 4: Run API tests**

Run:

```bash
cd services/screener-service && pytest tests/test_supply_chain_bom_api.py -v
```

Expected: PASS.

---

### Task 4: LLM Extraction Adapter

**Files:**
- Create: `services/screener-service/app/llm_supply_chain.py`
- Test: `services/screener-service/tests/test_llm_supply_chain.py`

**Interfaces:**
- Produces `extract_supply_chain_facts(text: str, source: dict, provider: str = "deepseek") -> dict`
- Produces `normalize_llm_usage(response: object) -> dict`

- [x] **Step 1: Write mocked SDK-boundary tests**

Create `services/screener-service/tests/test_llm_supply_chain.py`:

```python
from app.llm_supply_chain import build_extraction_prompt, parse_extraction_json


def test_build_extraction_prompt_mentions_required_fields():
    prompt = build_extraction_prompt("公司公告：产品已小批量交付")
    for key in ["policy_theme", "bom_nodes", "companies", "products", "commercialization_stage", "evidence"]:
        assert key in prompt


def test_parse_extraction_json_accepts_clean_json():
    raw = '{"policy_theme":"未来产业主攻方向","bom_nodes":["具身智能"],"companies":[{"code":"688001","name":"测试科技"}],"evidence":[{"summary":"小批量交付","confidence":0.8}]}'
    data = parse_extraction_json(raw)
    assert data["policy_theme"] == "未来产业主攻方向"
    assert data["evidence"][0]["confidence"] == 0.8
```

- [x] **Step 2: Implement prompt and parser**

Use JSON-only output instructions. Parser must reject non-object JSON by returning:

```python
{"policy_theme": "", "bom_nodes": [], "companies": [], "evidence": [], "parse_error": "non_object_json"}
```

- [x] **Step 3: Add provider guardrails**

Read `DEEPSEEK_API_KEY` from env. If missing, return a structured disabled result:

```python
{"status": "disabled", "reason": "DEEPSEEK_API_KEY missing"}
```

Do not log secrets. Do not add provider failover in this task.

- [x] **Step 4: Run LLM adapter tests**

Run:

```bash
cd services/screener-service && pytest tests/test_llm_supply_chain.py -v
```

Expected: PASS.

---

### Task 5: Frontend Supply Chain Drill-Down Page

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/SupplyChainBom.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/__tests__/SupplyChainBom.test.tsx`

**Interfaces:**
- Consumes `screenerApi.getSupplyChainThemes()`, `getSupplyChainBom()`, `getSupplyChainNode(nodeId)`, `getSupplyChainCompany(code)`.
- Produces route `/supply-chain-bom`.

- [x] **Step 1: Extend API client**

Add methods under `screenerApi`:

```ts
getSupplyChainThemes: () => api.get('/screener/supply-chain/themes'),
getSupplyChainBom: () => api.get('/screener/supply-chain/bom'),
getSupplyChainNode: (nodeId: string) => api.get(`/screener/supply-chain/node/${encodeURIComponent(nodeId)}`),
getSupplyChainCompany: (code: string) => api.get(`/screener/supply-chain/company/${encodeURIComponent(code)}`),
```

- [x] **Step 2: Create page skeleton**

Create `SupplyChainBom.tsx` with:

- Theme matrix using Ant Design `Table`
- BOM graph using `ReactECharts`
- Node detail panel
- Company detail drawer

No marketing copy. The first screen is the usable workbench.

- [x] **Step 3: Add route and menu item**

In `frontend/src/App.tsx`, lazy-load `SupplyChainBom`, add menu item label `产业链拆解`, route `/supply-chain-bom`, roles matching `/screener`.

- [x] **Step 4: Add frontend test**

Create a test that mocks `screenerApi` and verifies page renders `未来产业主攻方向` and node click updates detail panel.

- [x] **Step 5: Run frontend checks**

Run:

```bash
cd frontend && npx vitest run frontend/src/pages/__tests__/SupplyChainBom.test.tsx
cd frontend && npx tsc -b --noEmit
```

Expected: PASS.

---

### Task 6: V4 Validation and SIT

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/backtest/supply_chain_validation.py`
- Modify: `packages/kronos-factors/tools/supply_chain_validate.py`
- Modify: `progress/backend-dev.md`

**Interfaces:**
- Produces validation report fields: `model_version`, `baseline`, `test.mean_ic`, `criteria`, `verdict`.

- [x] **Step 1: Add V4 label to validation output**

Add `model_version="supply_chain_bom_v4"` to validation config when the engine returns V4 fields.

- [x] **Step 2: Record V3 baseline decision**

`supply_chain_v3` cannot be cleanly run after V4 wiring without preserving the old scorer behind a separate engine or fixture. Keep `random` and `chokepoint`, and document the reason in `progress/backend-dev.md`.

- [x] **Step 3: Run focused verification**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_supply_chain_bom_v4.py -v
cd services/screener-service && pytest tests/test_supply_chain_bom_api.py tests/test_llm_supply_chain.py -v
cd frontend && npx tsc -b --noEmit
```

Expected: PASS.

- [x] **Step 4: Record SIT evidence**

Append to `progress/backend-dev.md`:

```markdown
## supply_chain BOM V4 SIT Evidence (2026-06-23)

- Backend unit:
- Screener API:
- Frontend typecheck:
- Known limitations:
```

Fill each line with exact command and result.

---

## Self-Review

Spec coverage:
- PRD AC-1 to AC-6 are covered by Tasks 1 to 3.
- PRD AC-7 is covered by Task 4.
- PRD AC-8 and AC-9 are covered by Task 6.
- PRD AC-10 and AC-11 are covered by Tasks 3 and 5.
- PRD AC-12 is covered by Task 2 signal labels and Task 3 response contract.
- PRD AC-13 is partially covered by Task 4 disabled/fallback behavior; full external patent and bidding connectors remain future work per PRD scope.
- PRD AC-14 is covered at schema level in Task 1; write APIs for manual overrides need a follow-up task if user wants in-app editing in this release.

Placeholder scan:
- No `TBD`, `TODO`, or unspecified file paths remain.

Type consistency:
- `load_bom_config`, `score_company_v4`, and `derive_trade_signal` are introduced in Task 2 and consumed by later tasks.
- API client method names in Task 5 match endpoint names in Task 3.
