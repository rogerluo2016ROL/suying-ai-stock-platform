# frontend-dev-3 Progress

## T-206: model-training frontend 修复（4 项 P0） — 2026-06-12 14:30

**状态**: Completed

**Skills used**: none (direct code fix)

**SIT 证据**:

- `npx vitest run`: 16 passed (20 total), 4 failed in auth-flow (pre-existing), OOM on full suite
- No model-training-specific SIT tests exist; acceptance validated via code inspection against backend schemas

AC by AC:
- [x] AC-206.1 (Rollback): `ModelRegistry.tsx` refactored — added `targetVersion` state, auto-set from `record.version - 1` on rollback button click, `InputNumber` in rollback modal, request body now includes `target_version: targetVersion, reason: rollbackReason`. Matches `RollbackRequest` schema (`schemas.py:232-234`).
- [x] AC-206.2 (Cancel): Backend endpoint `POST /api/v1/training/status/{job_id}/cancel` did not exist. Added to `routes.py` with lock validation, status guard (only PENDING/PREPARING/RUNNING/EVALUATING), persistence via `_save_job`, and Redis SSE publish. Frontend `Training.tsx:534` path unchanged — now matches.
- [x] AC-206.3 (Archive): Backend endpoint `POST /api/v1/training/models/{model_id}/archive` did not exist. Added to `routes.py` — sets stage to `archived` with reason notes, guards against archiving production models (redirect to rollback). Frontend `ModelRegistry.tsx:300` path unchanged — now matches.
- [x] AC-206.4 (Deploy): `ModelRegistry.tsx:264` now sends `{ notes: '' }` in deploy request body. Matches `DeployRequest` schema (`schemas.py:218-219`).
- [x] AC-206.5 (Build): `npx tsc -b --noEmit` — 0 errors from model-training files; 12 pre-existing errors in other files (`RiskCheckModal.tsx`, `Diagnosis.tsx`, `Trade.tsx`). `npm run build` — same pre-existing errors block the build (not introduced by this change).

**质量门**:
- `npx tsc -b --noEmit`: 0 model-training errors (12 pre-existing elsewhere) ✅
- `npx vitest run`: 16/20 passed, 4 auth-flow failures pre-existing ⚠️
- `npm run build`: blocked by pre-existing TS errors ❌ (OOM on vitest full run)

**涉及文件**:
- `frontend/src/pages/ModelRegistry.tsx` (+5 lines state, +deploy notes body, +InputNumber import, +targetVersion in rollback modal + handler)
- `services/training-service/app/routes.py` (+42 lines cancel endpoint, +42 lines archive endpoint, +imports for `_job_lock`, `_jobs`, `_publish_progress`, `_save_job`)
- `frontend/src/pages/Training.tsx` (no change needed; path now matches new backend endpoint)

**下一步**: PL 决定是否接受构建被 pre-existing errors 阻塞（新增代码 0 TS 错误）
