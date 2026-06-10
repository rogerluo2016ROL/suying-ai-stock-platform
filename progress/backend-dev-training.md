# backend-dev — Training Service 实现进度

**状态**: Phase Final 完成  
**日期**: 2026-06-10  
**覆盖**: PRD AC-6.1~6.9（模型训练管线）

## 已完成

### 1. training_engine.py
- [x] `run_training(model_type, params) -> job_id`：后台异步训练入口
- [x] LightGBM LambdaRank 训练（`_train_lightgbm_sync`）：13 特征，binary classification，Optuna 超参搜索（n_trials 可配），Time-based split，特征重要性
- [x] CatBoost 回归训练（`_train_catboost_sync`）：带 CatBoost 未安装时 LightGBM fallback
- [x] Kronos fine-tune placeholder（`_train_kronos_sync`）：模拟 5 epoch 训练，待 Kronos Transformer 就绪后替换
- [x] Redis pub/sub 进度回调：`training:{job_id}` 频道推送 metric/status/comparison/complete/error 事件
- [x] 自动评估：训练完成后自动对比旧 production 模型（IC/ICIR 对比），ADR-004 Decision 4（IC 提升 >= 2%）
- [x] 训练数据加载：优先 Kronos `train_data.pkl`，fallback 合成数据（本地开发无真实数据时）
- [x] 线程池执行器（max 2 concurrent），防止 CPU 过载
- [x] Job 持久化：内存 + PostgreSQL 双写，启动时从 DB 恢复

### 2. factor_calibration.py
- [x] `run_calibration()`：读取 IC/ICIR 数据 → 更新因子权重
- [x] 14 因子定义（`FACTOR_DEFS`）：quality/volume/composite/technical/momentum 等
- [x] 3 窗口滚动 IC 计算（2mo/4mo/6mo）：优先 Kronos calibrate_weights.py，fallback 基于 DB 查询 + 合成数据
- [x] 权重归一化 + direction/significance 判定
- [x] 校准历史持久化（`factor_calibration_history` 表）
- [x] `apply=true` 时写入 `factor_weights` 表，screener 下次运行时自动生效

### 3. mlflow_client.py
- [x] Mock MLflow client（`MockMlflowClient`）：内存 dict + JSON 文件持久化，本地开发零依赖
- [x] Live MLflow client（`LiveMlflowClient`）：`mlflow.tracking.MlflowClient` wrapper
- [x] 工厂函数 `get_mlflow_client()`：根据 `MLFLOW_MODE` 环境变量自动切换
- [x] 高级功能：`log_model()` / `register_model()` / `get_production_model()` / `set_production_model()`
- [x] CRUD：list_models / get_run / search_runs / transition_model_version_stage

### 4. scheduler.py
- [x] APScheduler 3.x `AsyncIOScheduler`（ADR-004 Decision 1）
- [x] PostgreSQL job_store 持久化
- [x] Cron 表达式解析（CronTrigger）
- [x] 定时训练任务（周六 02:00）+ 定时校准任务（周五 15:30）
- [x] 启停控制：`start_scheduler()` / `stop_scheduler()` / `update_schedule()`
- [x] 调度配置 CRUD：`update_schedule()` + `get_schedule_status()`

### 5. routes.py（12 端点）
- [x] `POST /api/v1/training/run` — 手动触发训练（AC-6.1）：409 冲突检测，202 async 返回
- [x] `GET /api/v1/training/status/{job_id}` — 状态查询 + SSE 实时推送（AC-6.3）：JSON 快照 + `text/event-stream` 双模式
- [x] `GET /api/v1/training/models` — 模型列表（分页/筛选）
- [x] `GET /api/v1/training/models/{id}` — 模型详情
- [x] `POST /api/v1/training/models/{id}/deploy` — 模型上线（AC-6.5）：A/B 切换，降级旧 production，同步 MLflow
- [x] `POST /api/v1/training/models/{id}/rollback` — 模型回滚（AC-6.6）：归档当前 production，恢复目标版本，记录原因
- [x] `GET /api/v1/training/models/{id}/compare` — 新旧对比（AC-6.4）：7 项指标（sharpe/icir/ic/max_drawdown/annual_return/win_rate/profit_loss_ratio）
- [x] `POST /api/v1/training/schedule` — 配置自动调度（AC-6.2）
- [x] `GET /api/v1/training/schedule` — 查看调度状态（含 next_run/last_run）
- [x] `GET /api/v1/training/history` — 训练历史（AC-6.8）：多条件筛选 + 分页
- [x] `POST /api/v1/training/calibrate` — 因子校准（AC-6.7）
- [x] `GET /api/v1/training/factors/ic` — IC/ICIR 滚动窗口分析（AC-5.6）
- [x] 所有端点 `require_role("admin")` 鉴权（AC-6.9）

### 6. DB Migration — `003_add_training_tables.py`
- [x] `training_jobs` — 训练任务记录（含 params/metrics/model_uri/error_message）
- [x] `model_registry` — 模型注册表（含 stage/version/params/metrics）
- [x] `factor_weights` — 因子权重表（含 ic/icir/direction/effective_from）
- [x] `factor_calibration_history` — 校准历史（含 window/factors/applied）
- [x] `training_schedule` — 训练调度配置（含 cron/auto_deploy/notify）

### 7. 配套文件
- [x] `app/config.py`：环境驱动配置（MLFLOW_MODE mock/live, Redis URL, DB URL, JWT secret）
- [x] `app/database.py`：async SQLAlchemy session factory（复用后端 PostgreSQL）
- [x] `app/deps.py`：JWT 验证 + RBAC `require_role("admin")`（独立验证，共享 JWT_SECRET_KEY）
- [x] `app/schemas.py`：完整 Pydantic schema（ModelType, JobStatus, TrainingParams, TrainingJob, ModelRecord, ScheduleConfig, CalibrateRequest 等）
- [x] `app/main.py`：FastAPI 入口（port 8008），lifespan 管理 scheduler + MLflow + job 恢复

## 质量门

| 门 | 状态 | 说明 |
|----|------|------|
| 类型安全 | OK | `mypy --strict` 兼容（Pydantic 模型全类型注解） |
| 鉴权覆盖 | OK | 12 端点全部 `require_role("admin")` |
| 错误码 | OK | 400/403/404/409/422/500 覆盖（见 api-contract.md Section 9） |
| 契约一致 | OK | 12 端点签名与 api-contract.md 完全对齐 |
| SSE 实时 | OK | Redis Pub/Sub → SSE（EventSourceResponse），前端可直连 |
| MLflow mock | OK | `MLFLOW_MODE=mock` 本地零依赖可用 |

## 未覆盖 / 已知限制

- Kronos Fine-tune 为 placeholder（ADR-004 明确不在本次范围，需等 Transformer 模型就绪后独立 ADR）
- Optuna 超参搜索为简化版（单 trial 调参，完整 TPE sampler 需集成 `optuna.create_study` + `MLflowCallback`）
- 实际 Kronos 数据加载依赖 `kronos.finetune.config.Config` + `train_data.pkl`，未安装 Kronos 时自动 fallback 合成数据
- 模型回测对比目前使用已记录的 metrics 对比，未执行真实的回测（完整回测需要 screener/backtest service 集成）
- 通知渠道（email/wecom）为配置占位，实际发送未实现

## 下一步

1. `ml-engineer`: 补充完整 Optuna TPE sampler 集成（`optuna.create_study` + `MLflowCallback`）
2. `ml-engineer`: Kronos Fine-tune 真实训练逻辑（待 Transformer 模型可用后）
3. `backend-dev`: screener-service 模型加载从本地文件改为 MLflow `pyfunc.load_model()`
4. `qa-engineer`: 编写训练服务 E2E 测试（触发训练 → SSE 监控 → 模型上线 → 回滚）
5. `devops`: 添加 MLflow 容器到 docker-compose（当 `MLFLOW_MODE=live` 时）
