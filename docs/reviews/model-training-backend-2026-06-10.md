# Model Training Backend Code Review

- **Date**: 2026-06-10
- **Reviewer**: code-reviewer
- **Files Reviewed**: `training_engine.py`, `mlflow_client.py`, `factor_calibration.py`, `scheduler.py`, `routes.py`, `deps.py`, `schemas.py`, `config.py`
- **Verdict**: **BLOCKED** — 2 critical concurrency/auth gaps + 2 missing routes must be fixed before deploy

---

## 1. admin-only 鉴权审查

### 1.1 结论：无绕过风险

`deps.py` 鉴权链完整：

```
HTTPBearer → get_current_user (JWT decode + DB lookup + is_active check) → require_role("admin")
```

- JWT 解码使用 `jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])`，校验 `type == "access"` 和 `sub` 字段
- 用户查询使用参数化 SQL (`:uid`)，无 SQL 注入风险
- 角色检查 `user_role not in roles` 正确
- 所有 12 个路由均通过 `Depends(require_role("admin"))` 保护

### 1.2 次要项

- `JWT_SECRET_KEY` 默认值为 `"dev-secret-change-in-production-min-32-chars!!"` — 生产环境需覆盖
- `HTTPBearer(auto_error=False)` 在无 token 时返回 `None`，由 `get_current_user` 显式 raise 401，行为正确

---

## 2. MLflow mock/live 双模式审查

### 2.1 结论：接口一致，但 runtime 差异需注意

**接口一致性**: `MockMlflowClient` 和 `LiveMlflowClient` 的公开方法签名完全一致（`create_run`, `log_params`, `log_metrics`, `register_model`, `get_production_model`, `set_production_model`, `list_models`, `get_run`, `search_runs`），满足 mock/live 无缝切换要求。

**Live mode fallback** (`get_mlflow_client`, line 368-374):
```python
if MLFLOW_MODE == "live":
    try:
        _mlflow_client = LiveMlflowClient(...)
    except Exception:
        _mlflow_client = MockMlflowClient()  # silent fallback
```
- fallback 正确，但**静默降级无告警** — 生产环境 MLflow 挂了会在不知情的情况下使用 mock，导致模型不持久化

### 2.2 LiveMlflowClient.create_run 行为差异

`LiveMlflowClient.create_run()` 调用 `mlflow.start_run()` 但不作为 context manager，run 处于活跃状态。后续由 `log_model()` → `end_run()` 调用 `set_terminated()` 结束。如果在 `create_run` 和 `log_model` 之间发生异常，MLflow run 会泄漏（保持 RUNNING 状态）。

### 2.3 `log_model` 函数 end_run 时序

`log_model` 在 `log_params` + `log_metrics` + `log_artifact` 之后才调用 `end_run`，顺序正确。但如果在 `log_artifact` 时 model_path 不存在或异常，`end_run` 仍会执行（在 try/except 之外）——这不会造成 run 泄漏。

### 2.4 建议

- Mock fallback 时应记录 ERROR 级别日志 + 发送告警
- Live mode `create_run` 应考虑用 `mlflow.start_run()` context manager 或 try/finally 保护

---

## 3. 训练引擎异步执行 + 进度推送

### 3.1 训练执行流程

```
POST /run → run_training() → _executor.submit(asyncio.run(_execute_training(...)))
                                  │
                                  ├── PREPARING → _prepare_training_data()
                                  ├── RUNNING → run_in_executor(None, train_fn)
                                  │     └── on_metric() → asyncio.run(_on_training_metric())
                                  ├── EVALUATING → _evaluate_vs_production()
                                  └── COMPLETED/FAILED
```

### 3.2 CRITICAL: `asyncio.Lock` 跨 event loop 使用

`_job_lock = asyncio.Lock()` (line 50) 在三处被访问：
1. `_execute_training` 所在 event loop（由 `asyncio.run()` 创建）
2. `on_metric` 回调所在 event loop（每个 metric 回调创建新的 `asyncio.run()`）
3. FastAPI 路由 handler 所在 event loop（uvicorn 主 loop）

**`asyncio.Lock` 不是线程安全的，也不应跨 event loop 使用。** 在多个 event loop 中共享同一个 `asyncio.Lock` 会导致未定义行为（死锁、协程状态损坏）。

**修复**: 将 `_job_lock` 替换为 `threading.Lock`，或将所有对 `_jobs` 的访问集中到单一线程/event loop。

### 3.3 HIGH: Redis 连接未复用

`_publish_progress()` 每次调用创建新连接然后关闭：
```python
r = redis.from_url(REDIS_URL)
await r.publish(...)
await r.close()
```
单次训练 50 trial 产生 50+ 次连接创建/销毁。建议在模块级别创建连接池或复用连接。

### 3.4 MEDIUM: `asyncio.run()` 每 metric 创建/销毁 event loop

`on_metric` 中对每个 metric 调用 `asyncio.run()`，频繁创建销毁 event loop。可用 `asyncio.run_coroutine_threadsafe()` 将回调提交到主 event loop，避免 event loop 反复创建。

### 3.5 SSE 推送

- 后端通过 Redis Pub/Sub 广播，SSE endpoint 订阅 `training:{job_id}` channel
- 事件类型：`metric`, `evaluating`, `comparison`, `complete`, `error`
- 前端 `EventSource` 自带 `Accept: text/event-stream` header，与后端检查逻辑匹配
- SSE 在 complete/error 事件后主动 unsubscribe，避免连接泄漏
- 无心跳机制 — 训练长时间无 metric 输出时可能触发浏览器/proxy 超时

---

## 4. Scheduler cron 调度审查

### 4.1 架构正确性

- 使用 APScheduler `AsyncIOScheduler` + `SQLAlchemyJobStore` PostgreSQL 持久化
- 启动流程：`init_scheduler()` → `start_scheduler()` 
- DB 持久化通过 `training_schedule` 单例表（id=1）
- Cron 解析正确，使用 `croniter` 计算下次执行时间

### 4.2 MEDIUM: CronTrigger day vs day_of_week 歧义

`_register_scheduled_jobs` (line 138-145):
```python
CronTrigger(
    minute=minute, hour=hour,
    day=day if day != "*" else None,
    day_of_week=day_of_week if day_of_week != "*" else None,
)
```
APScheduler `CronTrigger` 的 `day` (day-of-month) 和 `day_of_week` (0-6) 是 **OR 关系** — 任一匹配即触发。当用户配置 `"0 2 15 * *"` (每月 15 号 + 每天)时，实际效果是"15 号 或 每天"，导致每天触发而非预期的仅 15 号触发。

**修复**: 当同时指定 day 和 day_of_week 时应明确为 AND 逻辑，或文档说明当前为 OR 行为。

### 4.3 调度与自动训练一致性

调度触发通过 `_scheduled_training()` → `run_training()`，参数从 `_schedule_config.params` 读取，与手动触发走同一代码路径。`created_by` 设为 `"schedule"` 以区分来源。

---

## 5. A/B 上线/回滚逻辑

### 5.1 Deploy (AC-6.5)

流程（`api_deploy_model`）:
1. 从 DB 查目标模型 → 404 若不存在
2. 检查是否已是 production + force=false → 409
3. 查找当前 production 版本 → archive
4. 目标模型 → production → commit
5. MLflow stage 同步

**HIGH: 缺少 DB 行锁** — 并发 deploy 两个模型可能有 race condition：
- 两个请求同时查询到同一 production 版本
- 两者都将其 archive 并各自 promote 目标
- 最终两个模型都是 production

建议使用 `SELECT ... FOR UPDATE` 锁定 production 行。

**HIGH: MLflow 同步失败被静默吞掉**:
```python
try:
    mlflow_client.set_production_model(model_name, model_version)
except Exception as e:
    logger.warning("MLflow sync failed (non-critical): %s", e)
```
DB 和 MLflow 状态不一致。如果 MLflow 是真实模型加载来源（如 screener 通过 MLflow load），DB 记录 production 但 MLflow 仍指向旧模型。

**LOW: 缺少 `model_not_validated` 校验** — API 契约第 4.5 节要求若模型未通过评估则返回 409 `model_not_validated`，代码未实现此检查。

### 5.2 Rollback (AC-6.6)

**CRITICAL: `target_version` 字段缺失** — `RollbackRequest` 要求 `target_version: int = Field(..., ge=1)`，但 frontend 未传此字段（见 frontend review）。

流程:
1. 查询 production 模型
2. 按 `body.target_version` 查找目标版本
3. Archive production → promote target
4. MLflow stage 同步

**HIGH: 同样缺少 DB 行锁**

### 5.3 Compare (AC-6.4)

**HIGH: 旧模型不存在时伪造数据** — 当无 production 模型时（line 651-658），代码将新模型 metrics × 0.9 作为"旧模型"数据。这会显示"全面改善"，但实际上没有任何对比基准。应明确标记为 `inconclusive` 或 `no_baseline`。

---

## 6. 其他发现

### 6.1 Optuna 集成未完成

`_train_lightgbm_sync` 中的"Optuna"实现实际是手动循环调整 learning_rate 和 num_leaves，并非调用 `optuna.create_study()` + `study.optimize()`。ADR-004 决策 2 要求的 TPE sampler + MedianPruner 未实现。当前实现更接近简化版手动搜索。

### 6.2 因子校准 fallback 使用随机数据

`_compute_ic_fallback` 在无法接入 Kronos 校准脚本时使用 `np.random.normal()` 生成随机 IC 值，这会在生产环境掩盖真实校准失败。建议返回错误而非静默生成假数据。

### 6.3 缺少 cancel 端点

API 契约未定义 cancel 端点，但 frontend `Training.tsx` 调用了 `POST /training/status/{job_id}/cancel`。后端无此路由 → 404。

### 6.4 缺少 archive 端点

Frontend `ModelRegistry.tsx` 调用 `POST /training/models/{id}/archive`，后端无此路由 → 404。

### 6.5 `training_schedule` 表缺少 `last_run` / `last_job_id` 列

`_update_schedule_last_run` 更新 `last_run` 和 `last_job_id`，但 API 契约第 8.3 节的 `training_schedule` DDL 不包含这两个列。需确认 migration 是否包含。

### 6.6 `factor_whitelist` 字段未使用

`TrainingParams.factor_whitelist` 在 API 契约中定义但 `_build_features_from_kline` 和训练函数中均未使用该字段。因子始终使用全部 13 特征。

---

## 7. 修复优先级

| 优先级 | 问题 | 文件 |
|--------|------|------|
| P0 | `asyncio.Lock` 跨 event loop | `training_engine.py:50` |
| P0 | RollbackRequest `target_version` required but frontend omits | `schemas.py:233` + `ModelRegistry.tsx:281` |
| P1 | 缺少 cancel 端点 | `routes.py` (new) |
| P1 | 缺少 archive 端点 | `routes.py` (new) |
| P1 | Compare 无基线时伪造数据 | `routes.py:651-658` |
| P1 | Deploy/rollback 缺少 DB 行锁 | `routes.py:380-457, 464-564` |
| P2 | Redis 连接不复用 | `training_engine.py:59-66` |
| P2 | MLflow live fallback 静默降级 | `mlflow_client.py:368-374` |
| P2 | Calibration fallback 随机假数据 | `factor_calibration.py:163-216` |
| P2 | Optuna 集成未完成 | `training_engine.py:342-463` |
| P3 | CronTrigger day/day_of_week OR 语义 | `scheduler.py:138-145` |
| P3 | MLflow sync 失败静默吞 | `routes.py:445-448` |
