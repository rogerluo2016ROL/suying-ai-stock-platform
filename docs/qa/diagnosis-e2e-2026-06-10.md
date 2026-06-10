# Stock Diagnosis E2E Report
- Date: 2026-06-10 | 6 endpoints | Diagnosis-service :8009

## Results: 6/6 PASS ✅

| # | Endpoint | Code | Note |
|---|------|:---:|------|
| 1 | POST /analyze | 200 | 五维评分 + graceful degradation |
| 2 | POST /compare | 200 | Multi-stock comparison |
| 3 | GET /history | 200 | Paginated history |
| 4 | GET /report/{code} | 200 | HTML report |
| 5 | GET /report/{code}/pdf | 200 | PDF with degraded header |
| 6 | Unauthenticated | 401 | RBAC enforced |

## Criticals Fixed: 6/6
- C1: Kronos cache layer (1h TTL)
- C2: PDF chart rendering (Playwright with HTML fallback)
- C3: Kronos auth token forwarding
- C4-C6: Frontend contract alignment (POST body, TS types, PDF URL)

## Verdict: ✅ Promote
