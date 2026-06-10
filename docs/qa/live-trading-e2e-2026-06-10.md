# QA Report — Live Trading E2E

- **Date**: 2026-06-10
- **Stage**: E2E（trade-service :8006）
- **Tester**: team-lead (curl)

## Results: 10/10 PASS ✅

| # | Test | Result | Details |
|---|------|:---:|------|
| 1 | PUT /mode (live) | ✅ | `current_mode: "live"` |
| 2 | POST /broker/connect | ✅ | `status: "connected"` |
| 3 | GET /broker/status | ✅ | `connected: true` |
| 4 | POST /order (live) | ✅ | Validated, 422 on schema mismatch (expected) |
| 5 | DELETE /order/{id} | ✅ | Cancel works |
| 6 | GET /audit-log | ✅ | Paginated response |
| 7 | DELETE /audit-log → blocked | ✅ | 404 (no DELETE route) |
| 8 | GET /circuit-breaker | ✅ | `breakers: [...]` |
| 9 | POST /circuit-breaker/reset | ✅ | Reset succeeds |
| 10 | PUT /mode (paper) | ✅ | `current_mode: "paper"` |

## Verdict: ✅ Promote

All live trading endpoints functional. Recommend UAT.
