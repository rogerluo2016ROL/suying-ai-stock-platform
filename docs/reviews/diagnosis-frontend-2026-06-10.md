# Diagnosis Frontend Code Review — 2026-06-10

Reviewer: code-reviewer
Scope: `frontend/src/pages/Diagnosis.tsx` + `frontend/src/api/client.ts` (diagnosisApi)
Reference: `docs/adr/005-stock-diagnosis.md`
Focus: 前后端契约一致性 / UI 数据映射 / PDF 导出 / RBAC 前端行为

---

## Verdict: **BLOCKED — 3 Critical contract mismatches**

The UI is well-structured and visually comprehensive (radar charts, prediction overlay, comparison modal, operation suggestion cards), but the frontend TypeScript interfaces and API call signatures do not match the backend Pydantic schemas. The mock data fallback silently masks all integration breakages — the page works in demo mode but has never been tested against the real API.

---

## Findings

### C1 — `analyze` API 调用契约断裂: query param vs request body

**File**: `client.ts:132`
```typescript
analyze: (code: string) => api.post(`/diagnosis/analyze?code=${code}`),
```

**Backend expectation** (`schemas.py:104-107`):
```python
class DiagnosisAnalyzeRequest(BaseModel):
    code: str
    force_refresh: bool = False
```

前端将 `code` 放在 URL query string 中 (`?code=000001`)，POST body 为空。后端从 `body.code`（Pydantic model）读取，收到的 `code` 为 `None` → 400 Bad Request。`force_refresh` 参数也完全没有暴露给前端。

**Fix**:
```typescript
analyze: (code: string, forceRefresh = false) =>
  api.post('/diagnosis/analyze', { code, force_refresh: forceRefresh }),
```

---

### C2 — `DiagnosisResult` 类型形状与 `DiagnosisReport` 完全不兼容

**File**: `Diagnosis.tsx:64-94` vs `schemas.py:88-101`

| 前端字段 | 后端字段 | 匹配? |
|----------|---------|-------|
| `result.overall_score` (number) | `report.overall_score` (float) | 类型 OK，但访问路径是 `res.data` |
| `result.grade` ("strong_buy") | `report.grade` ("A"/"B"/...) | **不匹配** — 前端期望英文 snake_case，后端返回字母等级 |
| `result.grade_label` ("强烈买入") | 不存在 | 后端无此字段 |
| `result.dimensions.technical` (number) | `report.dimensions["technical"].score` (float) | **不匹配** — 前端拿的是 number，后端是 DimensionScore 对象 |
| `result.name` | 不存在 | 后端 DiagnosisReport 无 stock name |
| `result.current_price` | 不存在 | 同上 |
| `result.factor_details: FactorDetail[]` | `report.dimensions["technical"].factor_scores` (Dict) | **完全不匹配** — 结构完全不同 |
| `result.capital_flow.north_bound.net_inflow` | `report.dimensions["capital_flow"].northbound_net` | **字段名不匹配** (`north_bound` vs `northbound`) |
| `result.suggestion.action` | `report.recommendation` (enum) | **不匹配** — 前端自建 suggestion 对象，后端是 recommendation + key_levels |

前后端是**两套完全不同的数据模型**。如果不做适配层（data transformer），前端拿到后端响应后所有渲染都会 crash（例如 `result.grade_label` 是 `undefined`）。

**Fix**: 在前端添加一个 `transformDiagnosisReport(apiResponse: DiagnosisReport): DiagnosisResult` 函数，将后端 Pydantic 模型映射到前端 TypeScript 接口；或者在 `diagnosisApi.analyze` 的响应拦截器中做转换。

---

### C3 — PDF 导出 URL 路径错误

**File**: `Diagnosis.tsx:715`
```typescript
const url = `/api/v1/report/${result.code}/pdf`
```

**Backend 路由** (`routes.py:299`):
```python
@router.get("/report/{code}/pdf")
# Full path: /api/v1/diagnosis/report/{code}/pdf
```

缺少 `/diagnosis` 路径段。前端请求 `/api/v1/report/000001/pdf` → 404 Not Found。

**Fix**:
```typescript
const url = `/api/v1/diagnosis/report/${result.code}/pdf`
```

---

### H1 — 历史记录 API 响应字段名不匹配

**File**: `Diagnosis.tsx:640-643`
```typescript
const data = await res.json()
setHistory(data.records || [])
```

**Backend** (`schemas.py:141-147`):
```python
class PaginatedDiagnosisHistory(BaseModel):
    items: List[DiagnosisHistoryItem]  # <-- "items", not "records"
```

前端访问 `data.records`，后端返回 `data.items` → `history` 始终为空数组。

---

### H2 — `grade` 字段枚举值不匹配

**File**: `Diagnosis.tsx:108-114`
```typescript
const GRADE_CONFIG: Record<string, ...> = {
  strong_buy: { color: '#ff1f1f', label: '强烈买入', ... },
  buy:      { color: '#ff7a45', label: '买入', ... },
  ...
}
```

前端 `GRADE_CONFIG` 的 key 是英文 snake_case (`strong_buy`, `buy`, `hold`, `reduce`, `sell`)。

**Backend** (`schemas.py:17-22`):
```python
class RecommendationGrade(str, Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    ...
```

后端 `recommendation` 字段的值是中文（"强烈买入"、"买入"…），`grade` 字段是字母（"A"、"B+"…）。前端 `renderGradeTag(result.grade, result.grade_label)` 使用 `GRADE_CONFIG[result.grade]` 查找，但后端 `grade` 是 "A" / "B+" 等字母，不是 `strong_buy`。

Mock 数据中 `grade` 被设为 `strong_buy` 等值，所以 mock 模式能正常工作。

---

### H3 — Mock fallback 掩蔽所有集成问题

**File**: `Diagnosis.tsx:618-635`
```typescript
try {
  const res = await diagnosisApi.analyze(stockCode)
  setResult(res.data)
} catch {
  const mock = generateMockResult(stockCode)  // <-- silent fallback
  setResult(mock)
}
```

**每次** API 调用失败都静默降级到 mock 数据，用户看到 `"诊断完成 (演示数据)"` 的提示。问题在于：

1. 如果后端 API 完全不可达（CORS、404、500），前端不会报错，用户无从知晓看到的是假数据
2. 开发者无法区分"后端还没部署"和"后端有 bug"——两种情况都会走 mock 路径
3. `generateMockResult` 生成的随机数据独立于真实市场数据，可能给出严重误导的建议

建议：mock 数据仅在 `import.meta.env.DEV` 下启用，或至少用明显的红色 banner 标明"演示数据，仅供参考"。生产环境应显示错误并引导用户重试。

---

### M1 — `compare` API 缺少 `dimensions` 参数传递

**File**: `client.ts:133`
```typescript
compare: (codes: string[]) => api.post('/diagnosis/compare', codes),
```

后端 `DiagnosisCompareRequest` 支持 `dimensions?: List[str]` 参数用于筛选对比维度（ADR-005 Decision 3: "对比维度可配置"），但前端完全没有使用。对比 modal 中也无维度筛选 UI。ADR-005 专门列出了这个能力，当前未实现。

---

### M2 — 缺少 `force_refresh` 的 UI 入口

ADR-005 Decision 4: "用户在同一天反复查看同一股票不应每次都重新计算"，48h 缓存。但前端没有提供"强制刷新"按钮让用户跳过缓存。后端 `DiagnosisAnalyzeRequest.force_refresh` 字段已定义但前端从未传递。

---

### M3 — K 线预测图数据来源问题

**File**: `Diagnosis.tsx:323-454`

`buildPredictionOverlayChart` 使用 `result.historical_klines` 和 `result.predictions` 渲染 K 线预测叠加图。这两个字段：
- 在 mock 数据中由 `generateMockResult` 生成（30 个历史点 + 30 个预测点）
- 在后端 `DiagnosisReport` 中**完全不存在**

后端 `AIPredictDimension` 有 `pred_return`、`pred_30d_close`、`inflection_days`、`max_drawdown`，但没有逐日的 historical klines 或 prediction points 数据。K 线预测图需要后端返回时间序列数组，当前后端 schema 不包含这些字段。

---

### M4 — 基本面数据缺少 `pe_percentile` 显示

**File**: `Diagnosis.tsx:1139-1170`

后端 `FundamentalDimension` 有 `pe_percentile`（PE 历史分位），这是基本面的核心评分依据之一。前端 `Fundamentals` 接口有 `pe` 和 `pb` 但没有 `pe_percentile`，基本面详情卡片也不显示 PE 分位。用户看不到 PE 在历史中的相对位置，只能看到绝对值。

---

### L1 — `useCallback` 依赖数组不完整

**File**: `Diagnosis.tsx:618-635`
```typescript
const runDiagnosis = useCallback(async (stockCode: string) => {
  ...
  loadHistory()  // <-- loadHistory is in closure but not in deps
}, [])
```

`runDiagnosis` 的依赖数组是 `[]`，但函数体内调用了 `loadHistory()`。虽然 `loadHistory` 也是 `useCallback` 且 deps 为 `[]`（所以引用稳定），但 ESLint `react-hooks/exhaustive-deps` 规则会报警。建议将 `loadHistory` 加入依赖数组或使用 `useRef` 存储。

---

### L2 — 暗黑模式参数未连接

**File**: `Diagnosis.tsx:131,183,241,326`

`buildRadarOption(dimensions, dark)`、`buildCompareRadarOption(stocks, dark)`、`buildKlinePredictionOption(historical, predictions, dark)`、`buildPredictionOverlayChart(historical, predictions, dark)` 都接受 `dark` 参数，但调用时始终使用默认值 `false`（不传第二个参数）。暗黑模式的样式代码已写好但未接入全局主题。

---

### L3 — 空状态 UI 文案与功能矩阵一致

**File**: `Diagnosis.tsx:1344-1361`

空状态展示五维标签（技术面 / 资金面 / 基本面 / AI预测 / 情绪面），与 ADR-005 定义一致。五维标签使用图标 + 颜色区分，视觉清晰。无问题，仅记录。

---

## Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| Critical | 3 | C1 (query param vs body), C2 (type shape mismatch), C3 (PDF URL wrong) |
| High | 3 | H1 (history items vs records), H2 (grade enum mismatch), H3 (mock fallback masking) |
| Medium | 4 | M1-M4 |
| Low | 3 | L1-L3 |

**Root cause**: 前端和后端是独立开发的，使用了两套不同的 TypeScript interface / Pydantic model 定义，且从未联调验证。所有 API 调用失败后静默降级到 mock 数据，使得这些断裂在 demo 中不可见。

**必须修复** (在 UAT 前): C1, C2, C3, H1, H2.
**强烈建议**: 移除生产环境的 mock fallback (H3)，或至少添加 "DEMO DATA" 水印。
