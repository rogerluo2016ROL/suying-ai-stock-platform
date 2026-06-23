# Supply Chain BOM Phase A Expert Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Turn the current supply-chain BOM page into a node-driven expert workbench where a selected BOM node controls the thesis, candidate company pool, scoring, commercialization stage, resonance, and company research card.

**Architecture:** Keep the existing route and data source, but extend the `/supply-chain/workbench` aggregation API with optional `theme_id` and `node_id` filters. The backend owns candidate-to-node projection, and the frontend renders the selected node view without guessing from global candidates.

**Tech Stack:** FastAPI, pytest, React 18, TypeScript, Ant Design 5, ECharts, Vitest, Testing Library.

## Global Constraints

- Preserve existing API fields `themes`, `nodes`, `edges`, `candidates`, `candidate_count`, `model`, and `stage_options` for compatibility.
- Add fields `selected_node_thesis`, `node_candidate_companies`, `node_candidate_count`, `evidence_summary`, and `resonance_model` to the workbench payload.
- `node_candidate_companies` must never silently fall back to the global candidate pool when `node_id` is present.
- Candidate rows must show company, product/material, commercialization stage, cycle position, score, rating, trade research signal, selection reason, and resonance.
- Company detail must show BOM path, product/material mapping, financial indicators, score breakdown, moat evidence, resonance, and risk.
- No new frontend runtime dependencies.
- No direct real-trading changes.

---

## File Structure

- Modify `services/screener-service/app/routers/screener.py`
  - Add query parameters `theme_id` and `node_id` to `supply_chain_workbench`.
  - Add helper functions that project enriched candidates onto selected BOM nodes.
  - Add selected node thesis and no-mapping evidence messages.

- Modify `services/screener-service/tests/test_supply_chain_bom_api.py`
  - Add backend contract tests for node-filtered workbench payloads.
  - Add backend contract tests for nodes with no company mapping evidence.

- Modify `frontend/src/api/client.ts`
  - Change `getSupplyChainWorkbench` to accept `{ topN, themeId, nodeId }`.
  - Preserve compatibility with the existing numeric call form used by older callers.

- Create `frontend/src/pages/supply-chain-bom/types.ts`
  - Move shared page types out of `SupplyChainBom.tsx`.

- Create `frontend/src/pages/supply-chain-bom/formatters.ts`
  - Move `scoreColor`, `formatNumber`, and `dimensionLabel` out of the page.

- Create `frontend/src/pages/supply-chain-bom/CandidateCompanyTable.tsx`
  - Render the node-scoped company pool and no-mapping empty state.

- Create `frontend/src/pages/supply-chain-bom/CompanyResearchDrawer.tsx`
  - Render company research card detail.

- Create `frontend/src/pages/supply-chain-bom/NodeThesisPanel.tsx`
  - Render selected node thesis, trigger conditions, risks, keywords, and evidence stats.

- Modify `frontend/src/pages/SupplyChainBom.tsx`
  - Load workbench initially, then reload workbench with `node_id` whenever a node is selected.
  - Use `node_candidate_companies` for the table when a node is selected.
  - Keep model summary, graph, tree, extraction, and existing route.

- Modify `frontend/src/__tests__/SupplyChainBom.test.tsx`
  - Add tests proving node selection refetches the workbench with `nodeId`.
  - Add tests proving no-mapping nodes show “该节点缺少公司映射证据”.
  - Add tests proving company detail renders research-card fields.

---

### Task 1: Backend Node-Aware Workbench Contract

**Files:**
- Modify: `services/screener-service/tests/test_supply_chain_bom_api.py`
- Modify: `services/screener-service/app/routers/screener.py`

**Interfaces:**
- Consumes: existing `_get_supply_chain_candidate_pool(top_n: int, trade_date: Optional[str]) -> list[dict]`
- Produces: `GET /api/v1/screener/supply-chain/workbench?top_n=10&node_id=embodied_ai_core`
- Produces helper `_candidate_matches_node(candidate: dict, node: dict) -> bool`
- Produces helper `_build_selected_node_thesis(node: dict, candidates: list[dict]) -> dict`

- [x] **Step 1: Write the failing node-filter test**

Add this test after `test_supply_chain_workbench_returns_candidate_pool_with_model_context`:

```python
def test_supply_chain_workbench_filters_candidates_by_selected_node(monkeypatch):
    fake_candidates = [
        {
            "code": "688017",
            "name": "绿的谐波",
            "chain": "机器人",
            "layer": "减速器",
            "score": 78.5,
            "rating": "A",
            "trade_signal": "启动",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "具身智能", "中游", "减速器"],
            "products": ["谐波减速器"],
            "materials": ["高精密轴承材料"],
            "commercialization_stage": "量产爬坡",
            "commercialization_cycle": "量产启动",
            "resonance": {"summary": "政策、商业化、业绩三维共振"},
            "selection_reason": "绿的谐波卡位具身智能减速器节点，量产爬坡阶段。",
            "dimension_scores": {"policy": 13.0, "bom": 14.0, "commercialization": 13.0},
        },
        {
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "高速光模块",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "AI算力", "硬件", "高速光模块"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {"summary": "政策、商业化、业绩、市场四维共振"},
            "selection_reason": "中际旭创卡位AI算力光模块节点。",
            "dimension_scores": {"policy": 12.0, "bom": 13.0, "commercialization": 14.0},
        },
    ]
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: fake_candidates,
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10&node_id=embodied_ai_core")

    assert r.status_code == 200
    body = r.json()
    assert body["selected_node_thesis"]["node_id"] == "embodied_ai_core"
    assert body["selected_node_thesis"]["name"] == "具身智能"
    assert body["node_candidate_count"] == 1
    assert [c["code"] for c in body["node_candidate_companies"]] == ["688017"]
    assert body["node_candidate_companies"][0]["matched_node_id"] == "embodied_ai_core"
    assert body["node_candidate_companies"][0]["matched_node_name"] == "具身智能"
    assert "中际旭创" not in [c["name"] for c in body["node_candidate_companies"]]
```

- [x] **Step 2: Write the failing no-mapping test**

Add this test after the previous one:

```python
def test_supply_chain_workbench_keeps_empty_node_pool_when_mapping_missing(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "300308",
            "name": "中际旭创",
            "chain": "AI算力",
            "layer": "高速光模块",
            "score": 72.4,
            "rating": "B",
            "trade_signal": "观察",
            "policy_theme": "未来产业主攻方向",
            "bom_path": ["未来产业主攻方向", "AI算力", "硬件", "高速光模块"],
            "products": ["高速光模块"],
            "materials": ["光芯片"],
            "commercialization_stage": "规模推广",
            "commercialization_cycle": "业绩兑现",
            "resonance": {"summary": "政策、商业化、业绩、市场四维共振"},
            "selection_reason": "中际旭创卡位AI算力光模块节点。",
            "dimension_scores": {"policy": 12.0},
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10&node_id=quantum_core")

    assert r.status_code == 200
    body = r.json()
    assert body["selected_node_thesis"]["node_id"] == "quantum_core"
    assert body["node_candidate_count"] == 0
    assert body["node_candidate_companies"] == []
    assert body["selected_node_thesis"]["mapping_status"] == "missing_company_mapping"
    assert body["selected_node_thesis"]["mapping_message"] == "该节点缺少公司映射证据"
```

- [x] **Step 3: Run backend tests and verify the new tests fail**

Run:

```bash
cd services/screener-service
../../.venv/bin/pytest tests/test_supply_chain_bom_api.py -v
```

Expected: the two new tests fail because `node_id`, `selected_node_thesis`, and `node_candidate_companies` are not implemented in the workbench response.

- [x] **Step 4: Implement node matching and thesis helpers**

Add these helpers near `_get_supply_chain_candidate_pool`:

```python
def _normalize_match_terms(values: list[object]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            terms.update(_normalize_match_terms(value))
            continue
        text = str(value).strip().lower()
        if text:
            terms.add(text)
    return terms


def _candidate_search_terms(candidate: dict) -> set[str]:
    return _normalize_match_terms([
        candidate.get("chain"),
        candidate.get("layer"),
        candidate.get("policy_theme"),
        candidate.get("bom_path") if isinstance(candidate.get("bom_path"), list) else [],
        candidate.get("products") if isinstance(candidate.get("products"), list) else [],
        candidate.get("materials") if isinstance(candidate.get("materials"), list) else [],
        candidate.get("selection_reason"),
    ])


def _candidate_matches_node(candidate: dict, node: dict) -> bool:
    search_text = " ".join(_candidate_search_terms(candidate))
    node_terms = _normalize_match_terms([
        node.get("name"),
        node.get("chain_id"),
        node.get("level"),
        node.get("node_type"),
        node.get("policy_theme"),
        node.get("bom_path") if isinstance(node.get("bom_path"), list) else [],
        node.get("keywords") if isinstance(node.get("keywords"), list) else [],
    ])
    return any(term and term in search_text for term in node_terms)


def _filter_candidates_for_node(candidates: list[dict], node: dict | None) -> list[dict]:
    if not node:
        return []
    matched = []
    for candidate in candidates:
        if _candidate_matches_node(candidate, node):
            enriched = dict(candidate)
            enriched["matched_node_id"] = node.get("node_id")
            enriched["matched_node_name"] = node.get("name")
            matched.append(enriched)
    return matched


def _build_selected_node_thesis(node: dict | None, node_candidates: list[dict]) -> dict:
    if not node:
        return {}
    keywords = node.get("keywords") if isinstance(node.get("keywords"), list) else []
    name = node.get("name") or "BOM节点"
    candidate_count = len(node_candidates)
    mapping_status = "mapped" if candidate_count else "missing_company_mapping"
    mapping_message = f"已映射 {candidate_count} 家候选上市公司" if candidate_count else "该节点缺少公司映射证据"
    return {
        "node_id": node.get("node_id"),
        "name": name,
        "policy_theme": node.get("policy_theme", ""),
        "bom_path": node.get("bom_path", []),
        "keywords": keywords,
        "thesis": f"{name}是{node.get('policy_theme') or '政策主题'}下的关键BOM节点，需要用产品、材料、订单、产能和财务兑现证据验证公司映射。",
        "trigger_conditions": ["政策持续加码", "产品进入量产或规模推广", "订单与产能公告验证", "收入和利润增速同步改善"],
        "risk_factors": ["商业化进度低于预期", "国产替代节奏放缓", "毛利率下降", "市场交易拥挤"],
        "mapping_status": mapping_status,
        "mapping_message": mapping_message,
    }
```

- [x] **Step 5: Extend the workbench route**

Change the route signature and response:

```python
@router.get("/supply-chain/workbench")
async def supply_chain_workbench(
    top_n: int = Query(30, ge=5, le=MAX_TOP_N),
    trade_date: Optional[str] = Query(None),
    theme_id: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
):
    loop = asyncio.get_running_loop()
    payload = _load_supply_chain_bom_payload()
    candidates = await loop.run_in_executor(
        _executor,
        _get_supply_chain_candidate_pool,
        top_n,
        trade_date,
    )
    node_by_id = {node.get("node_id"): node for node in payload["nodes"]}
    selected_node = node_by_id.get(node_id or "")
    if node_id and not selected_node:
        raise HTTPException(status_code=404, detail=f"Unknown BOM node '{node_id}'")
    node_candidates = _filter_candidates_for_node(candidates, selected_node) if selected_node else []
    evidence_summary = {
        "approved": sum(1 for c in node_candidates if c.get("evidence")),
        "pending_review": 0,
        "low_confidence": 0,
    }
    return {
        "version": payload["version"],
        "source": payload["source"],
        "model": _supply_chain_model_payload(),
        "themes": payload["themes"],
        "policy_themes": payload["themes"],
        "nodes": payload["nodes"],
        "graph_nodes": payload["nodes"],
        "edges": payload["edges"],
        "graph_edges": payload["edges"],
        "selected_theme_id": theme_id,
        "selected_node_id": selected_node.get("node_id") if selected_node else None,
        "selected_node_thesis": _build_selected_node_thesis(selected_node, node_candidates),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "node_candidate_count": len(node_candidates),
        "node_candidate_companies": node_candidates,
        "evidence_summary": evidence_summary,
        "resonance_model": {"dimensions": ["policy", "commercialization", "order_capacity", "performance", "market"]},
        "stage_options": ["预研验证", "中试", "小批量验证", "量产爬坡", "规模推广", "成熟"],
    }
```

- [x] **Step 6: Run backend tests and verify they pass**

Run:

```bash
cd services/screener-service
../../.venv/bin/pytest tests/test_supply_chain_bom_api.py -v
```

Expected: all tests in `test_supply_chain_bom_api.py` pass.

---

### Task 2: Frontend API Contract and Node-Scoped Tests

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/__tests__/SupplyChainBom.test.tsx`

**Interfaces:**
- Consumes: backend workbench fields from Task 1.
- Produces: `screenerApi.getSupplyChainWorkbench({ topN?: number, themeId?: string, nodeId?: string })`.

- [x] **Step 1: Write the failing frontend test for node refetch**

Update the workbench mock so it can return node-specific company pools:

```typescript
const greenHarmonic = {
  code: '688017',
  name: '绿的谐波',
  chain: '机器人',
  layer: '减速器',
  score: 78.5,
  rating: 'A',
  trade_signal: '启动',
  products: ['谐波减速器'],
  materials: ['高精密轴承材料'],
  selection_reason: '绿的谐波卡位具身智能减速器节点，量产爬坡阶段。',
  commercialization_stage: '量产爬坡',
  commercialization_cycle: '量产启动',
  resonance: { summary: '政策、商业化、业绩三维共振' },
  dimension_scores: { policy: 13, bom: 14, commercialization: 13 },
  financial_indicators: { revenue_growth: 28.5, profit_growth: 31.2, roe: 15.2, gross_margin: 44.1 },
  moat_evidence: [{ evidence_type: 'patent', summary: '谐波减速器专利与客户认证' }],
}
```

Add this test:

```typescript
it('reloads the company pool for the selected BOM node', async () => {
  vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockImplementation((params?: any) => {
    if (params?.nodeId === 'embodied_ai_core') {
      return Promise.resolve({
        data: Object.assign({}, workbench, {
          selected_node_id: 'embodied_ai_core',
          selected_node_thesis: {
            node_id: 'embodied_ai_core',
            name: '具身智能',
            thesis: '具身智能节点需要验证减速器、伺服、控制器等核心部件。',
            mapping_status: 'mapped',
            mapping_message: '已映射 1 家候选上市公司',
            trigger_conditions: ['产品进入量产或规模推广'],
            risk_factors: ['商业化进度低于预期'],
          },
          node_candidate_count: 1,
          node_candidate_companies: [greenHarmonic],
        }),
      })
    }
    return Promise.resolve({ data: workbench })
  })

  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainBom />
    </ConfigProvider>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /具身智能/ }))

  await waitFor(() => {
    expect((screenerApi as any).getSupplyChainWorkbench).toHaveBeenCalledWith({
      topN: 30,
      nodeId: 'embodied_ai_core',
      themeId: 'future_industry_core',
    })
  })
  expect(await screen.findByText('绿的谐波')).toBeInTheDocument()
  expect(screen.getByText('谐波减速器')).toBeInTheDocument()
  expect(screen.queryByText('中际旭创')).not.toBeInTheDocument()
})
```

- [x] **Step 2: Write the failing frontend test for no-mapping node**

Add this test:

```typescript
it('shows an explicit missing-mapping state instead of global candidates', async () => {
  vi.mocked((screenerApi as any).getSupplyChainWorkbench).mockImplementation((params?: any) => {
    if (params?.nodeId === 'quantum_core') {
      return Promise.resolve({
        data: Object.assign({}, workbench, {
          selected_node_id: 'quantum_core',
          selected_node_thesis: {
            node_id: 'quantum_core',
            name: '量子科技',
            thesis: '量子科技节点需要补充上市公司产品映射证据。',
            mapping_status: 'missing_company_mapping',
            mapping_message: '该节点缺少公司映射证据',
            trigger_conditions: ['政策持续加码'],
            risk_factors: ['商业化进度低于预期'],
          },
          node_candidate_count: 0,
          node_candidate_companies: [],
        }),
      })
    }
    return Promise.resolve({ data: workbench })
  })

  render(
    <ConfigProvider locale={zhCN}>
      <SupplyChainBom />
    </ConfigProvider>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /量子科技/ }))

  expect(await screen.findByText('该节点缺少公司映射证据')).toBeInTheDocument()
  expect(screen.queryByText('中际旭创')).not.toBeInTheDocument()
})
```

- [x] **Step 3: Run the frontend tests and verify they fail**

Run:

```bash
cd frontend
npx vitest run src/__tests__/SupplyChainBom.test.tsx
```

Expected: the new tests fail because the API client only accepts a number and the page does not refetch the workbench for selected nodes.

- [x] **Step 4: Implement the API client signature**

Replace the current `getSupplyChainWorkbench` entry with:

```typescript
type SupplyChainWorkbenchParams = number | {
  topN?: number
  themeId?: string
  nodeId?: string
}

const buildSupplyChainWorkbenchPath = (params: SupplyChainWorkbenchParams = {}) => {
  const topN = typeof params === 'number' ? params : params.topN ?? 30
  const search = new URLSearchParams({ top_n: String(topN) })
  if (typeof params !== 'number') {
    if (params.themeId) search.set('theme_id', params.themeId)
    if (params.nodeId) search.set('node_id', params.nodeId)
  }
  return `/screener/supply-chain/workbench?${search.toString()}`
}
```

Then use:

```typescript
getSupplyChainWorkbench: (params: SupplyChainWorkbenchParams = {}) =>
  api.get(buildSupplyChainWorkbenchPath(params)),
```

- [x] **Step 5: Run the frontend tests and verify API expectations move to page behavior**

Run:

```bash
cd frontend
npx vitest run src/__tests__/SupplyChainBom.test.tsx
```

Expected: API-client-related failures are gone; page behavior still fails until Task 3 is implemented.

---

### Task 3: Frontend Expert Workbench Refactor

**Files:**
- Create: `frontend/src/pages/supply-chain-bom/types.ts`
- Create: `frontend/src/pages/supply-chain-bom/formatters.ts`
- Create: `frontend/src/pages/supply-chain-bom/CandidateCompanyTable.tsx`
- Create: `frontend/src/pages/supply-chain-bom/CompanyResearchDrawer.tsx`
- Create: `frontend/src/pages/supply-chain-bom/NodeThesisPanel.tsx`
- Modify: `frontend/src/pages/SupplyChainBom.tsx`

**Interfaces:**
- Consumes: `CandidateCompany`, `BomNode`, `ThemeRow`, and selected node workbench payload fields.
- Produces: node-scoped UI with explicit empty state and company research drawer.

- [x] **Step 1: Extract shared types**

Create `frontend/src/pages/supply-chain-bom/types.ts`:

```typescript
export interface ThemeRow {
  theme_id: string
  name: string
  policy_weight: number
  keywords: string[]
  node_count: number
  matrix?: Record<string, number | null>
}

export interface BomNode {
  node_id: string
  theme_id: string
  chain_id: string
  parent_node_id?: string | null
  child_node_ids?: string[]
  level: string
  name: string
  node_type: string
  keywords: string[]
  policy_theme?: string
  bom_path?: string[]
}

export interface ScoreDimension {
  key: string
  name: string
  weight: number
}

export interface CandidateCompany {
  code: string
  name?: string
  rank?: number
  chain?: string
  layer?: string
  score?: number
  rating?: string
  trade_signal?: string
  policy_theme?: string
  bom_path?: string[]
  products?: string[]
  materials?: string[]
  selection_reason?: string
  commercialization_stage?: string
  commercialization_cycle?: string
  resonance?: Record<string, string>
  dimension_scores?: Record<string, number>
  financial_indicators?: Record<string, number | string>
  moat_evidence?: Array<{ evidence_type?: string; summary?: string; confidence?: number }>
  evidence?: any[]
}

export interface SelectedNodeThesis {
  node_id?: string
  name?: string
  policy_theme?: string
  bom_path?: string[]
  keywords?: string[]
  thesis?: string
  trigger_conditions?: string[]
  risk_factors?: string[]
  mapping_status?: string
  mapping_message?: string
}
```

- [x] **Step 2: Extract formatting helpers**

Create `frontend/src/pages/supply-chain-bom/formatters.ts`:

```typescript
export const dimensionLabel: Record<string, string> = {
  policy: '政策力度',
  bom: 'BOM关键度',
  chokepoint: '卡脖子',
  growth: '业绩成长',
  profit: '盈利质量',
  commercialization: '商业化阶段',
  moat: '护城河',
  market: '市场共振',
  risk: '风险扣分',
}

export function scoreColor(score?: number) {
  if ((score || 0) >= 80) return 'red'
  if ((score || 0) >= 65) return 'green'
  if ((score || 0) >= 50) return 'blue'
  return 'default'
}

export function formatNumber(value: unknown, digits = 1) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return n.toFixed(digits)
}
```

- [x] **Step 3: Create the node-scoped company table**

Create `frontend/src/pages/supply-chain-bom/CandidateCompanyTable.tsx` with props:

```typescript
interface CandidateCompanyTableProps {
  candidates: CandidateCompany[]
  loading?: boolean
  selectedNodeName?: string
  mappingMessage?: string
  onOpenCompany: (company: CandidateCompany) => void
}
```

The component renders the same columns currently in `SupplyChainBom.tsx`, but its `locale.emptyText` must render `mappingMessage || '该节点缺少公司映射证据'` when `candidates.length === 0`.

- [x] **Step 4: Create the node thesis panel**

Create `frontend/src/pages/supply-chain-bom/NodeThesisPanel.tsx` with props:

```typescript
interface NodeThesisPanelProps {
  node?: BomNode
  thesis?: SelectedNodeThesis
  evidenceCount: number
  policyWeight: number
}
```

Render:

```tsx
<Text strong>{thesis?.name || node?.name || '请选择BOM节点'}</Text>
<Paragraph type="secondary">{thesis?.thesis || '选择节点后查看产业链拆解逻辑、触发条件与风险。'}</Paragraph>
```

Render `trigger_conditions` and `risk_factors` as tags.

- [x] **Step 5: Create the company research drawer**

Create `frontend/src/pages/supply-chain-bom/CompanyResearchDrawer.tsx` with props:

```typescript
interface CompanyResearchDrawerProps {
  open: boolean
  company: CandidateCompany | null
  fallbackCompany?: CandidateCompany
  onClose: () => void
}
```

Move the current drawer description, score breakdown, financial indicators, and moat evidence into this component.

- [x] **Step 6: Refactor the page load flow**

In `SupplyChainBom.tsx`, add state:

```typescript
const [nodeCandidates, setNodeCandidates] = useState<CandidateCompany[]>([])
const [selectedNodeThesis, setSelectedNodeThesis] = useState<SelectedNodeThesis>({})
const [candidateLoading, setCandidateLoading] = useState(false)
```

Create:

```typescript
const applyWorkbenchPayload = (data: any, replaceCatalog = false) => {
  const nextThemes = data.themes || data.policy_themes || []
  const nextNodes = data.nodes || data.graph_nodes || []
  if (replaceCatalog) {
    setThemes(nextThemes)
    setNodes(nextNodes)
    setEdges(data.edges || data.graph_edges || [])
    setModel(data.model || {})
  }
  setCandidates(data.candidates || [])
  setNodeCandidates(data.node_candidate_companies || [])
  setSelectedNodeThesis(data.selected_node_thesis || {})
}
```

Initial load calls:

```typescript
screenerApi.getSupplyChainWorkbench({ topN: 30 })
```

Node selection calls:

```typescript
screenerApi.getSupplyChainWorkbench({ topN: 30, nodeId: nextNode.node_id, themeId: nextNode.theme_id })
```

The candidate table receives:

```tsx
<CandidateCompanyTable
  candidates={selectedNodeId ? nodeCandidates : candidates}
  loading={candidateLoading}
  selectedNodeName={selectedNode?.name}
  mappingMessage={selectedNodeThesis.mapping_message}
  onOpenCompany={openCompany}
/>
```

- [x] **Step 7: Run frontend tests and verify they pass**

Run:

```bash
cd frontend
npx vitest run src/__tests__/SupplyChainBom.test.tsx
```

Expected: all tests in `SupplyChainBom.test.tsx` pass.

---

### Task 4: Regression Verification and Browser UAT

**Files:**
- Verify: `services/screener-service/tests/test_supply_chain_bom_api.py`
- Verify: `frontend/src/__tests__/SupplyChainBom.test.tsx`
- Verify: frontend TypeScript and production build

**Interfaces:**
- Consumes: all outputs from Tasks 1 to 3.
- Produces: verified Phase A expert workbench.

- [x] **Step 1: Run backend supply-chain API tests**

Run:

```bash
cd services/screener-service
../../.venv/bin/pytest tests/test_supply_chain_bom_api.py -v
```

Expected: all tests pass.

- [x] **Step 2: Run frontend workbench tests**

Run:

```bash
cd frontend
npx vitest run src/__tests__/SupplyChainBom.test.tsx
```

Expected: all tests pass.

- [x] **Step 3: Run TypeScript verification**

Run:

```bash
cd frontend
npx tsc -b --noEmit
```

Expected: command exits with code 0.

- [x] **Step 4: Run production build**

Run:

```bash
cd frontend
npm run build
```

Expected: command exits with code 0.

- [x] **Step 5: Refresh local services**

Restart the local screener service on port `18001` so the browser uses the new backend code. Keep the Vite server on port `3002`.

- [x] **Step 6: Browser UAT**

Open:

```text
http://127.0.0.1:3002/supply-chain-bom
```

Verify:

- The first viewport shows BOM tree, graph, node thesis panel, and candidate company area.
- Clicking `具身智能` changes the company pool to node-related companies only.
- Clicking a node with no mapping shows `该节点缺少公司映射证据`.
- Opening a company shows product/material, score breakdown, financial indicators, moat evidence, commercialization stage, resonance, and selection reason.

---

## Self-Review

- Spec coverage: Phase A acceptance items map to Tasks 1, 3, and 4.
- Type consistency: backend returns `selected_node_thesis`, `node_candidate_companies`, and `node_candidate_count`; frontend consumes the same names.
- Scope control: B-stage repository/service extraction and C-stage automatic LLM ingestion are outside this Phase A implementation batch, while the added API fields are compatible with those stages.
