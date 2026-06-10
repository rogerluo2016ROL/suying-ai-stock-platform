# Model Training Frontend Code Review

- **Date**: 2026-06-10
- **Reviewer**: code-reviewer
- **Files Reviewed**: `Training.tsx`, `ModelRegistry.tsx`
- **Verdict**: **BLOCKED** — 4 critical frontend-backend contract mismatches must be resolved

---

## 1. 前后端接口一致性

### 1.1 CRITICAL: Rollback 缺少 `target_version` 字段

**Frontend** (`ModelRegistry.tsx:281`):
```typescript
await api.post(`/training/models/${modelId}/rollback`, { reason: rollbackReason })
```

**Backend** (`schemas.py:231-234`):
```python
class RollbackRequest(BaseModel):
    target_version: int = Field(..., ge=1)  # REQUIRED
    reason: str = Field(default="")
```

前端只传 `{ reason }`，缺少必填字段 `target_version`。后端会返回 **422 Validation Error**。回滚功能完全不可用。

**修复**: 前端需要在 rollback modal 中添加版本号输入框，或在确定回滚目标后发送 `{ target_version, reason }`。

---

### 1.2 CRITICAL: Cancel 端点不存在

**Frontend** (`Training.tsx:534`):
```typescript
await api.post(`/training/status/${jobId}/cancel`)
```

**Backend**: `routes.py` 中无 `POST /api/v1/training/status/{job_id}/cancel` 路由。

取消按钮会返回 **404**。需后端补充 cancel 路由实现（更新 job status 为 CANCELLED + 中断训练线程）。

---

### 1.3 CRITICAL: Archive 端点不存在

**Frontend** (`ModelRegistry.tsx:300`):
```typescript
await api.post(`/training/models/${archiveModelId}/archive`, { reason: archiveReason })
```

**Backend**: `routes.py` 中无 `POST /api/v1/training/models/{id}/archive` 路由。

归档按钮会返回 **404**。"保留旧模型"交互不可用。

---

### 1.4 MEDIUM: Deploy 请求缺少 body

**Frontend** (`ModelRegistry.tsx:264`):
```typescript
await api.post(`/training/models/${modelId}/deploy`)
```

**Backend** (`schemas.py:216-219`):
```python
class DeployRequest(BaseModel):
    force: bool = Field(default=False)
    notes: Optional[str] = None
```

前端未传任何 body。由于 `DeployRequest` 所有字段都有默认值，**空 body 不会导致错误**，但 `notes` 信息会丢失（无法记录上线备注）。

**建议**: 前端应支持填写上线备注（`notes`），对应 API 契约 4.5 节。

---

### 1.5 OK: SSE EventSource header

**Frontend** (`Training.tsx:468`):
```typescript
const es = new EventSource(`/api/v1/training/status/${liveJobId}`)
```

浏览器原生 `EventSource` 自动发送 `Accept: text/event-stream` header，与后端 `request.headers.get("accept", "")` 检查匹配。无需修改。

---

## 2. Training.tsx 功能审查

### 2.1 训练触发 Modal

触发参数构建正确：
- 所有 `TrainingParams` 字段均有映射
- `data_range` → `data_start_date` / `data_end_date` 正确转换
- `num_leaves` 仅在 `lightgbm` 时发送
- `factor_groups` → `factor_whitelist` 正确

### 2.2 SSE 实时监控

事件监听覆盖：
- `metric` → 追加指标到图表
- `complete` → 显示完成消息 + 刷新列表
- `error` → 显示错误消息
- `evaluating` → 添加日志项

**LOW**: `es.onerror` 中 retry 逻辑在 5 秒后调用 `loadTasks()` 但不会重新连接 SSE。如果连接因网络问题断开，用户不会自动恢复实时监控。

**LOW**: `es.addEventListener('trial_complete', ...)` 注册了但 handler 为空。SSE 流中可能发送 `trial_complete` 事件但前端不处理。

### 2.3 定时调度配置

- 加载/保存调度配置的字段与 `ScheduleConfig` 完全匹配
- `notify_on_complete: true` 和 `notify_channels: ['email']` 硬编码在保存逻辑中 — 这是合理默认值
- 每次保存都重建默认 `params`，如果用户修改了训练参数但未在调度表单中体现，可能丢失自定义参数

**LOW**: `handleSave` 中 `config?.params` 来自上一次加载的调度配置。如果用户从未加载成功（`loadConfig` 抛异常），`config` 为 null，则使用硬编码默认值。这在首次配置时行为正确。

### 2.4 调度历史

- 通过 `/training/history?created_by=schedule` 查询历史记录
- 使用 `result === 'success'` / `'failed'` 判断，与后端 `JobStatus` enum 匹配 OK

---

## 3. ModelRegistry.tsx 功能审查

### 3.1 A/B 对比

**前端逻辑**（`handleCompare`, line 213-259):
1. 调用 `GET /training/models/${model.id}/compare`
2. 如果 API 返回数据，直接使用
3. 如果 API 失败（catch），在前端本地计算对比数据

本地 fallback 对比逻辑使用 `metrics` 对象中的字段名（`sharpe`, `icir`, `max_drawdown` 等），与 API 契约匹配。

**LOW**: 本地 fallback 的 `better` 判据是 `delta > 0` (higher_better) 或 `delta < 0` (lower_better)，`threshold` 始终为 `0`。后端可配置 threshold（如 sharpe >= 0.05）。前端 fallback 比后端更宽松，可能在 API 不可用时给出过于乐观的比较结果。

### 3.2 一键上线

- 仅在 `compareVerdict === 'new_better'` 时显示"一键上线"按钮
- 调用 `handleDeploy(modelB.id)` — modelB 是"新模型"
- 上线后关闭对比 modal + 刷新列表

流程正确。

### 3.3 模型详情 Drawer

- 从 `/training/models/${id}` 获取详情
- 展示：名称、版本、类型、状态、创建时间、上线时间、创建人、上线人
- 评估指标：AUC、夏普比率、年化收益、最大回撤、Precision、Recall、F1、ICIR
- 超参数：JSON 美化展示
- 备注：展示 `notes` 字段

字段映射完整。

### 3.4 因子分析面板

- 加载 `/training/factors/ic?window_days=120` 两次（`loadFactors` 中 duplicated call）
- IC 折线图正确使用 `rolling` 数组构建时间序列
- 因子排名表正确展示 IC、ICIR、方向、显著性

**LOW**: `loadFactors` 中两次调用同一个 endpoint（`fRes` 和 `icRes`），实际只需一次。

### 3.5 权重校准

- 调用 `POST /training/calibrate` with `mode: 'all', window_days: 90, min_samples: 30, apply: true`
- 请求体与 `CalibrateRequest` schema 完全匹配
- 成功后刷新因子列表

---

## 4. 前端代码质量问题

### 4.1 Training.tsx

- `liveMetrics.map(() => liveMetrics[0]?.epoch ?? 0.05)` (line 725) — 学习率图表使用固定值 `0.05`，未实际从 metric 中提取学习率
- `es.addEventListener('trial_complete', (() => {}))` — 空回调，无实际效果
- `Progress` 进度计算 `latestTrial / (liveMetrics.length * 2 || 1)` — 进度公式依赖于"trial 数是 metric 数的一半"的假设，不够健壮

### 4.2 ModelRegistry.tsx

- `loadFactors` 中 `fRes` 和 `icRes` 重复请求同一 endpoint
- 本地 fallback compare 逻辑（`catch` 块）与 API 返回值格式略有不同（缺少 `threshold` 验证）

---

## 5. 修复优先级

| 优先级 | 问题 | 文件 |
|--------|------|------|
| P0 | Rollback 缺少 `target_version` 字段 | `ModelRegistry.tsx:281` |
| P0 | Cancel 端点不存在（需配合后端新增） | `Training.tsx:534` + `routes.py` |
| P0 | Archive 端点不存在（需配合后端新增） | `ModelRegistry.tsx:300` + `routes.py` |
| P1 | Deploy 应支持 `notes` 参数 | `ModelRegistry.tsx:264` |
| P2 | SSE 断线不自动重连 | `Training.tsx:515-522` |
| P2 | `loadFactors` 重复 API 调用 | `ModelRegistry.tsx:172-175` |
| P3 | 学习率图表使用固定值 | `Training.tsx:725` |
| P3 | 空 `trial_complete` 回调 | `Training.tsx:503-505` |

---

## 6. 兼容性矩阵

| 端点 | 前端调用方式 | 后端定义 | 状态 |
|------|-------------|---------|------|
| POST /training/run | `{ params, auto_deploy }` | `TrainRequest` | OK |
| GET /training/status/{id} | EventSource | SSE + JSON | OK |
| GET /training/models | query params | `PaginatedModelsResponse` | OK |
| GET /training/models/{id} | path param | `ModelRecord` | OK |
| POST /training/models/{id}/deploy | **no body** | `DeployRequest` (all optional) | OK (notes lost) |
| POST /training/models/{id}/rollback | **`{ reason }` missing `target_version`** | `RollbackRequest` (target_version required) | **BROKEN** |
| GET /training/models/{id}/compare | query params | `ModelCompareResponse` | OK |
| POST /training/schedule | `ScheduleConfig` | `ScheduleConfig` | OK |
| GET /training/schedule | none | `ScheduleStatusResponse` | OK |
| GET /training/history | query params | `PaginatedHistoryResponse` | OK |
| POST /training/calibrate | `CalibrateRequest` | `CalibrateRequest` | OK |
| GET /training/factors/ic | query params | `FactorICResponse` | OK |
| POST /training/status/{id}/cancel | **not implemented** | — | **MISSING** |
| POST /training/models/{id}/archive | **not implemented** | — | **MISSING** |
