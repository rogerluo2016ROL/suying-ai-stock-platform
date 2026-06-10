# QA Report -- 模型训练管线 -- E2E + UAT 测试策略

- **Date**: 2026-06-10
- **Stage**: Strategy（E2E + UAT 测试策略框架，非执行报告）
- **Tester**: qa-engineer
- **Branch**: HEAD
- **Environment**: local docker-compose（PostgreSQL + strategy-service :8003 + MLflow Tracking Server :5000 + React frontend :5173）
- **PRD**: Kronos/docs/投资管理平台_PRD_产品需求文档.md SS3.6 AC-6.1~6.9
- **Codebase Reviewed**:
  - Kronos/tools/train_lgbm_v2.py（LightGBM Ranker v2 训练脚本，100+ 树，14 因子特征）
  - Kronos/tools/train_catboost.py（CatBoost Ranker 训练脚本，19 因子特征，ICIR 感知权重）
  - Kronos/tools/finetune_single_device.py（Kronos VQ-VAE + AR Predictor 微调）
  - Kronos/tools/calibrate_weights.py（因子权重校准，滑动窗口 IC/ICIR 分析）
  - Kronos/tools/run_pipeline.py（一键流水线：Tushare 更新 → 12 模型筛选 → Kronos 预测 → 回测）
  - Kronos/tools/forward_validate.py（前向验证：新模型 vs 旧模型回测对比）
  - services/strategy-service/app/routes.py（REST API 路由）
  - services/strategy-service/app/main.py（FastAPI 入口）
- **Mock Dependencies**: Tushare 数据源使用本地 SQLite 缓存；MLflow 使用 localhost Tracking Server

---

## Summary

> 本文件为**模型训练管线 E2E + UAT 测试策略框架**，基于已实现的训练脚本和 PRD AC-6.1~6.9 编写。覆盖从手动触发训练 → 进度监控 → 自动评估 → 模型注册 → 一键上线/回滚 → 自动调度 → 因子校准 → 训练历史 → 权限控制的完整闭环。

- **Total E2E Scenarios**: 14
- **Total UAT Scenarios**: 10
- **AC Coverage**: AC-6.1, AC-6.2, AC-6.3, AC-6.4, AC-6.5, AC-6.6, AC-6.7, AC-6.8, AC-6.9（全部 9 条验收条件）
- **Status**: 等待 code-review 通过

---

## AC 覆盖矩阵

| AC | 描述 | E2E 场景 | UAT 场景 |
|----|------|----------|----------|
| AC-6.1 | 管理员手动触发模型训练（LightGBM / CatBoost / Kronos Fine-tune） | E2E-1, E2E-2, E2E-3 | UAT-1, UAT-3 |
| AC-6.2 | 自动训练调度（每周六凌晨自动执行） | E2E-9 | UAT-4 |
| AC-6.3 | 训练过程可视化（Loss 曲线、特征重要性排名） | E2E-4, E2E-5 | UAT-1 |
| AC-6.4 | 训练完成后自动评估：新模型 vs 旧模型在回测集上的表现对比 | E2E-6 | UAT-1, UAT-2 |
| AC-6.5 | 新模型优于旧模型 → 管理员一键上线（A/B 切换） | E2E-7 | UAT-1, UAT-5 |
| AC-6.6 | 新模型不如旧模型 → 保留旧模型，记录失败原因 | E2E-8 | UAT-2, UAT-10 |
| AC-6.7 | 因子权重自动校准（基于最新 IC/ICIR 数据，每周自动更新） | E2E-10 | UAT-6 |
| AC-6.8 | 训练历史可追溯（时间/数据/参数/效果） | E2E-11 | UAT-7 |
| AC-6.9 | 仅管理员可访问训练功能 | E2E-12, E2E-13, E2E-14 | UAT-8 |

---

## Pre-conditions Checked

> 执行测试前必须全部勾选。

- [ ] 单元测试 + lint + typecheck 全绿
- [ ] code-reviewer 报告已存在且 verdict != Block
- [ ] PRD SS3.6 AC-6.1~6.9 可访问
- [ ] 测试数据库已启动（`docker compose up -d`）
- [ ] strategy-service 已启动（FastAPI on localhost:8003）
- [ ] MLflow Tracking Server 已启动（localhost:5000）
- [ ] Kronos 预训练权重已下载到本地缓存
- [ ] Tushare 数据缓存已就绪（SQLite db 含最近 5 个交易日数据）
- [ ] 前端服务已启动（React on localhost:5173）
- [ ] 测试用户已登录（`admin` / `analyst` / `viewer` 三账号）
- [ ] chrome-devtools-mcp 可用于浏览器截图

---

## 测试环境准备

### 1. MLflow Tracking Server 启动

```bash
mlflow server \
  --backend-store-uri sqlite:///./mlflow/mlruns.db \
  --default-artifact-root ./mlflow/artifacts \
  --host 0.0.0.0 --port 5000
```

### 2. 训练数据 Seed

```sql
-- 确认 SQLite daily_kline 表有足够数据用于训练
SELECT COUNT(DISTINCT code) as stock_count,
       COUNT(*) as record_count,
       MIN(trade_date) as earliest,
       MAX(trade_date) as latest
FROM daily_kline;
-- 预期: stock_count >= 2000, record_count >= 500000, latest 距今天 ≤ 5 天
```

### 3. 基线模型准备（模拟"旧模型"）

```bash
# 注册一个基础版本作为 A 模型（当前线上）
python Kronos/tools/train_lgbm_v2.py   # 产出 models/lgbm_ranker_v2.pkl
python Kronos/tools/train_catboost.py  # 产出 models/catboost_ranker.cbm
```

### 4. 测试用户与角色

| 账号 | 角色 | 权限 |
|------|------|------|
| `admin` | 管理员 | 全部训练功能（触发/调度/上线/回滚/校准） |
| `analyst` | 分析师 | 可查看训练历史，不可触发训练 |
| `viewer` | 只读用户 | 不可访问训练页面 |

---

## E2E 测试场景

### E2E-1: 手动触发 LightGBM 训练并完成全流程

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1 |
| **优先级** | P0 |
| **前置** | admin 已登录；Tushare 数据已更新；基线模型已存在 |
| **步骤** | |
| | 1. 浏览器访问训练管理页面 `/training` |
| | 2. 点击"新建训练任务"按钮 |
| | 3. 选择模型类型 `LightGBM` |
| | 4. 配置参数：样本量 2000、树数量 100、学习率 0.05 |
| | 5. 点击"开始训练" |
| | 6. 等待训练完成（观察进度指示器） |
| | 7. 查看训练结果摘要 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/jobs` 返回 201，`job_id` 非空，`status: "pending"` |
| | - [ ] 训练任务立即入队列，status 流转: `pending → running → completed` |
| | - [ ] 训练过程中可通过 `GET /api/v1/training/jobs/{job_id}` 获取实时状态 |
| | - [ ] `status: "running"` 时 `progress.current_epoch` / `progress.total_epochs` 非空 |
| | - [ ] 训练完成后 `result.model_path` 指向合法文件路径（如 `models/lgbm_ranker_v2.pkl`） |
| | - [ ] 训练完成后 MLflow 自动注册实验：`experiment_id` + `run_id` 非空 |
| | - [ ] MLflow run 包含 metrics（`train_loss`, `val_loss`）、params（`num_trees`, `learning_rate`）、artifacts（`model.pkl`, `feature_importance.json`） |
| | - [ ] 前端训练列表刷新后出现新记录，状态为 ✅ 已完成 |
| | - [ ] 训练时长记录准确（`duration_seconds >= 0`） |

---

### E2E-2: 手动触发 CatBoost 训练

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1 |
| **优先级** | P0 |
| **前置** | admin 已登录；至少有一个完整训练周期数据 |
| **步骤** | |
| | 1. 点击"新建训练任务" |
| | 2. 选择模型类型 `CatBoost` |
| | 3. 配置参数：样本量 3000、迭代 500、深度 6 |
| | 4. 点击"开始训练" |
| | 5. 观察日志输出包含 ICIR 感知权重调整信息 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/jobs` 返回 201，`model_type: "catboost"` |
| | - [ ] 训练日志包含 "P0-optimized feature order" 和 ICIR 感知权重日志 |
| | - [ ] CatBoost 训练使用 GPU 加速（若可用），否则 CPU 回退 |
| | - [ ] 训练产物 `models/catboost_ranker.cbm` 文件存在且大小 > 0 |
| | - [ ] MLflow 注册时 `model_flavor: "catboost"` |
| | - [ ] 特征重要性排名包含 19 个因子（momentum, volume_factor, technical, ...） |
| | - [ ] 训练完成后自动触发评估流水线（见 E2E-6） |

---

### E2E-3: 手动触发 Kronos Fine-tune

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1 |
| **优先级** | P1 |
| **前置** | admin 已登录；Kronos 预训练权重已下载；GPU/MPS 可用 |
| **步骤** | |
| | 1. 点击"新建训练任务" |
| | 2. 选择模型类型 `Kronos` |
| | 3. 选择 Stage: `tokenizer`（VQ-VAE）或 `predictor`（AR） |
| | 4. 设置 epochs=5, batch_size=16 |
| | 5. 点击"开始训练" |
| | 6. 观察 GPU 利用率和 Loss 曲线 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/jobs` 返回 201，`model_type: "kronos"` |
| | - [ ] `params.finetune_stage` 为 `tokenizer` 或 `predictor` |
| | - [ ] 训练日志显示 `Device:` 为 `mps` / `cuda` / `cpu` |
| | - [ ] Stage=tokenizer 时 metrics 包含 `vq_loss`, `recon_loss` |
| | - [ ] Stage=predictor 时 metrics 包含 `ce_loss`, `perplexity` |
| | - [ ] Fine-tune 权重保存到 `models/kronos_ft_{stage}.pt` |
| | - [ ] MLflow 注册 `model_flavor: "kronos"` |
| | - [ ] 前端实时展示 epoch-level loss 曲线（WebSocket 推送或轮询） |

---

### E2E-4: 训练进度实时监控 — Loss 曲线

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.3 |
| **优先级** | P0 |
| **前置** | 有一个正在运行的训练任务 |
| **步骤** | |
| | 1. 在训练列表中点击正在运行的任务，进入详情页 |
| | 2. 观察 Loss 曲线图（train_loss / val_loss 双线） |
| | 3. 等待至少 3 个 epoch 完成，观察曲线更新 |
| | 4. 检查横轴为 epoch、纵轴为 loss 值 |
| **验证点** | |
| | - [ ] 详情页包含实时 Loss 曲线图（ECharts / Recharts） |
| | - [ ] 曲线有两条线：蓝色 train_loss、橙色 val_loss |
| | - [ ] 每个 epoch 完成后曲线自动追加新数据点（无需手动刷新） |
| | - [ ] 鼠标悬停数据点显示 (epoch, loss) tooltip |
| | - [ ] 图例可点击切换显示/隐藏 |
| | - [ ] `GET /api/v1/training/jobs/{job_id}/metrics` 返回 `[{epoch, train_loss, val_loss}, ...]` |
| | - [ ] 训练异常（loss NaN 或爆炸）时曲线上有警告标记 |
| | - [ ] 支持缩放（zoom）和拖拽平移（pan） |

---

### E2E-5: 训练进度实时监控 — 特征重要性排名

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.3 |
| **优先级** | P1 |
| **前置** | LightGBM 或 CatBoost 训练已完成 |
| **步骤** | |
| | 1. 进入已完成训练任务的详情页 |
| | 2. 切换到"特征重要性"标签页 |
| | 3. 查看横向条形图 |
| | 4. 验证各因子重要性值总和 = 100%（或归一化后） |
| **验证点** | |
| | - [ ] 特征重要性以横向条形图展示（ECharts bar 图，y 轴为因子名，x 轴为重要性值） |
| | - [ ] 因子按重要性降序排列 |
| | - [ ] Top 5 因子有颜色高亮 |
| | - [ ] `GET /api/v1/training/jobs/{job_id}/feature-importance` 返回 `[{feature, importance}, ...]` |
| | - [ ] LightGBM 训练返回 14 个因子特征 |
| | - [ ] CatBoost 训练返回 19 个因子特征 |
| | - [ ] 支持导出为 CSV |
| | - [ ] 可与历史训练的特征重要性对比（显示变化趋势箭头 ↑↓） |

---

### E2E-6: 训练完成后自动评估 — 新模型 vs 旧模型回测对比

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.4 |
| **优先级** | P0 |
| **前置** | 训练任务完成；存在旧模型（基线）；回测数据可用 |
| **步骤** | |
| | 1. 训练任务完成后，系统自动触发评估流水线 |
| | 2. 进入训练详情页，切换到"模型评估"标签页 |
| | 3. 查看新模型 vs 旧模型的指标对比表 |
| | 4. 查看回测收益曲线对比图 |
| **验证点** | |
| | - [ ] 训练完成后 60 秒内自动触发评估（无需手动） |
| | - [ ] 评估对比指标包含：年化收益率、夏普比率、最大回撤、胜率、盈亏比、换手率、Calmar 比率 |
| | - [ ] 每个指标显示：新模型值、旧模型值、差值（Δ）、↑↓箭头 |
| | - [ ] 新模型年化收益 ≥ 旧模型时显示 🟢，否则显示 🔴 |
| | - [ ] 回测收益曲线对比图（双线：蓝色新模型、灰色旧模型） |
| | - [ ] 回撤对比图（双面积图） |
| | - [ ] 月度收益热力图对比 |
| | - [ ] `GET /api/v1/training/jobs/{job_id}/evaluation` 返回完整评估 JSON |
| | - [ ] 评估结论明确："推荐上线" / "不推荐上线" + 原因摘要 |
| | - [ ] MLflow 中注册 evaluation metrics 到 run 的 tags |

---

### E2E-7: 一键上线 — 新模型优于旧模型时 A/B 切换

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.5 |
| **优先级** | P0 |
| **前置** | 训练完成 + 评估完成 + 评估结论为"推荐上线" |
| **步骤** | |
| | 1. 在训练详情页看到"推荐上线"标记 |
| | 2. 点击"一键上线"按钮 |
| | 3. 在确认对话框中确认切换 |
| | 4. 观察模型版本状态变化 |
| | 5. 验证选股系统使用了新模型 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/models/{model_id}/deploy` 返回 200 |
| | - [ ] 旧模型（A）状态变更为 `staged`（保留快照，不下线） |
| | - [ ] 新模型（B）状态变更为 `production`（线上） |
| | - [ ] MLflow 模型注册表中 `production` stage 指向新模型版本 |
| | - [ ] `GET /api/v1/training/models/active` 返回新模型 ID |
| | - [ ] 选股系统 `model_name` 参数自动切换为新模型（无需重启服务） |
| | - [ ] 前端训练列表显示 🟢 线上标记在当前生产模型旁边 |
| | - [ ] A/B 切换操作记录到 `model_deployment_log`，含操作人、时间、原因 |
| | - [ ] 切换完成 < 5 秒（不含模型加载到 GPU 的时间） |
| | - [ ] 切换期间选股请求不中断（使用旧模型继续服务，切换完成后无缝衔接） |

---

### E2E-8: 评估不通过 — 保留旧模型并记录失败原因

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.6 |
| **优先级** | P0 |
| **前置** | 训练完成 + 评估完成 + 评估结论为"不推荐上线" |
| **步骤** | |
| | 1. 在训练详情页看到"不推荐上线"标记（🟡） |
| | 2. 查看失败原因摘要 |
| | 3. 确认旧模型仍为 production 状态 |
| | 4. 确认"一键上线"按钮不可用（灰色/隐藏） |
| **验证点** | |
| | - [ ] 评估不通过时不显示"一键上线"按钮（或置灰 + tooltip 说明原因） |
| | - [ ] 失败原因清晰展示：如"新模型年化收益 12.3% < 旧模型 15.7%（差 -3.4pp）" |
| | - [ ] "不推荐上线"的具体条件可配置（如年化收益差 ≥ -2pp 则拒绝） |
| | - [ ] 新模型自动标记为 `evaluated_failed`，记录失败原因到 MLflow tag |
| | - [ ] 旧模型保持 `production` 状态不变 |
| | - [ ] 训练历史中该记录的 `deploy_status` 为 `rejected` |
| | - [ ] 后续管理员仍可手动覆盖上线（高级操作，需二次确认） |
| | - [ ] `GET /api/v1/training/models/active` 仍返回旧模型 ID |

---

### E2E-9: 自动训练调度 — 定时触发

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.2 |
| **优先级** | P0 |
| **前置** | admin 已登录；调度器已配置 |
| **步骤** | |
| | 1. 进入"训练调度"配置页面 |
| | 2. 创建调度规则：模型=LightGBM，cron=`0 2 * * 6`（每周六凌晨 2:00） |
| | 3. 查看调度列表，确认规则已保存 |
| | 4. 查看下一次执行时间 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/schedules` 返回 201，`schedule_id` 非空 |
| | - [ ] cron 表达式校验：非法表达式（如 `0 0 * * 8`）返回 400 |
| | - [ ] `GET /api/v1/training/schedules` 列出所有调度规则，含 next_run_at |
| | - [ ] next_run_at 计算正确（按 cron 表达式推算下一个触发时间） |
| | - [ ] 到预定时间后，系统自动创建训练任务（job_type=`scheduled`） |
| | - [ ] 调度产生的任务在训练列表中显示来源为 `🕐 自动调度` |
| | - [ ] 支持启用/禁用调度规则（`PUT /api/v1/training/schedules/{id}` 切换 `enabled`） |
| | - [ ] 禁用的调度规则不会触发训练 |
| | - [ ] 同一时间最多运行 N 个并发训练（可配置，默认 1） |
| | - [ ] 若上一轮训练仍在运行，新调度任务排队等待（队列状态 `queued`） |

---

### E2E-10: 因子权重自动校准

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.7 |
| **优先级** | P0 |
| **前置** | admin 已登录；至少 60 个交易日的历史数据可用于 IC 计算 |
| **步骤** | |
| | 1. 进入"因子校准"页面 |
| | 2. 点击"执行校准" |
| | 3. 观察因子权重调整前后的对比 |
| | 4. 选择应用模式（ALL / short / long） |
| | 5. 点击"应用新权重" |
| **验证点** | |
| | - [ ] `POST /api/v1/training/calibrate` 返回 200，包含 14 个因子的新旧权重对比 |
| | - [ ] 每个因子返回：name, old_weight, new_weight, ic, icir, delta_pct |
| | - [ ] IC 值为正且显著的因子权重上调（如 technical ICIR=+20.86 → 权重 5%→25%） |
| | - [ ] ICIR 为负的因子权重下调或标记为反转信号（如 momentum ICIR=-7.49） |
| | - [ ] 校准基于滚动窗口（默认 60 交易日），窗口大小可配置 |
| | - [ ] `--apply` 模式：POST 请求带 `apply: true`，权重写入 screening_top50.py 的 ALL_MODE_WEIGHTS |
| | - [ ] 校准日志记录到 `calibration_log` 表（含时间、窗口、各因子 IC/ICIR） |
| | - [ ] 查看因子 IC 时间序列图（滚动窗口 IC 折线图） |
| | - [ ] 前端以雷达图展示校准前后权重变化 |
| | - [ ] 校准过程中不阻塞选股服务 |

---

### E2E-11: 训练历史可追溯

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.8 |
| **优先级** | P1 |
| **前置** | 已有至少 3 条训练历史记录 |
| **步骤** | |
| | 1. 进入"训练历史"页面 |
| | 2. 使用筛选器：按模型类型、日期范围、状态、上线状态筛选 |
| | 3. 点击某条历史记录查看详情 |
| | 4. 检查记录内容的完整性 |
| **验证点** | |
| | - [ ] `GET /api/v1/training/jobs?page=1&page_size=20` 返回分页列表 |
| | - [ ] 每条记录包含：训练时间（created_at / completed_at）、模型类型、参数、样本量、评估指标摘要 |
| | - [ ] 支持按 model_type 筛选：`?model_type=lightgbm` / `catboost` / `kronos` |
| | - [ ] 支持按状态筛选：`?status=completed` / `failed` / `running` |
| | - [ ] 支持按日期范围筛选：`?from=2026-05-01&to=2026-06-10` |
| | - [ ] 点击某条历史 → 详情页展示完整信息： |
| | | - [ ] 训练参数（完整 params JSON） |
| | | - [ ] 训练数据（样本量、数据时间范围、因子列表） |
| | | - [ ] 评估效果（各指标值、vs 旧模型对比） |
| | | - [ ] 上线状态（是否已上线、上线时间、操作人） |
| | | - [ ] MLflow run 链接 |
| | - [ ] 支持导出历史为 CSV |
| | - [ ] 详情页支持"基于此参数重新训练"一键操作 |

---

### E2E-12: 非管理员访问训练页面返回 403

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.9 |
| **优先级** | P0 |
| **前置** | 以 `analyst` 或 `viewer` 账号登录 |
| **步骤** | |
| | 1. 以 analyst 身份登录，尝试直接访问 `/training` 页面 |
| | 2. 以 viewer 身份登录，尝试直接访问 `/training` 页面 |
| | 3. 以 viewer 身份尝试调用训练 API |
| **验证点** | |
| | - [ ] `GET /training` 页面：analyst 访问返回 403 Forbidden（前端路由守卫拦截） |
| | - [ ] `GET /training` 页面：viewer 访问返回 403 Forbidden |
| | - [ ] `POST /api/v1/training/jobs`：analyst 调用返回 403，`{"error": "仅管理员可触发训练"}"" |
| | - [ ] `POST /api/v1/training/jobs`：viewer 调用返回 403 |
| | - [ ] `POST /api/v1/training/models/{id}/deploy`：analyst 调用返回 403 |
| | - [ ] `POST /api/v1/training/schedules`：analyst 调用返回 403 |
| | - [ ] `GET /api/v1/training/jobs`：analyst 可查看列表（只读），返回 200 |
| | - [ ] `GET /api/v1/training/jobs/{id}`：analyst 可查看详情（只读），返回 200 |
| | - [ ] `GET /api/v1/training/jobs`：viewer 返回 403 或空列表 |
| | - [ ] 前端导航菜单对非管理员隐藏"模型训练"入口 |

---

### E2E-13: 非管理员无法执行校准和上线操作

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.9 |
| **优先级** | P1 |
| **前置** | 以 analyst 身份登录 |
| **步骤** | |
| | 1. analyst 尝试调用校准 API |
| | 2. analyst 尝试调用上线 API |
| | 3. analyst 尝试修改调度规则 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/calibrate` → 403，`{"error": "仅管理员可执行因子校准"}` |
| | - [ ] `POST /api/v1/training/calibrate?apply=true` → 403 |
| | - [ ] `POST /api/v1/training/models/{id}/deploy` → 403 |
| | - [ ] `POST /api/v1/training/models/{id}/rollback` → 403 |
| | - [ ] `POST /api/v1/training/schedules` → 403 |
| | - [ ] `PUT /api/v1/training/schedules/{id}` → 403 |
| | - [ ] `DELETE /api/v1/training/schedules/{id}` → 403 |
| | - [ ] 前端对应按钮对 analyst 隐藏或置灰 + tooltip "仅管理员可操作" |

---

### E2E-14: 模型回滚 — 从生产模型恢复到历史版本

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.5（引申：A/B 切换后发现问题需回退） |
| **优先级** | P1 |
| **前置** | 当前生产模型为 B（新上线），历史有 A 版本（staged） |
| **步骤** | |
| | 1. 进入"模型版本"页面 |
| | 2. 找到 staged 状态的 A 版本 |
| | 3. 点击"回滚到该版本" |
| | 4. 在确认对话框中填写回滚原因 |
| | 5. 确认 |
| **验证点** | |
| | - [ ] `POST /api/v1/training/models/{model_id}/rollback` 返回 200 |
| | - [ ] `reason` 字段必填，为空时返回 400 |
| | - [ ] 回滚后 A 版本变更为 `production` |
| | - [ ] B 版本变更为 `archived`（保留记录） |
| | - [ ] MLflow 模型注册表中 `production` stage 重新指向 A |
| | - [ ] 选股系统自动切换到回滚后的模型 |
| | - [ ] `GET /api/v1/training/models/active` 返回 A 的 model_id |
| | - [ ] 回滚操作记录到 `model_deployment_log`，含操作人、时间、原因 |
| | - [ ] 支持多次回滚（A → B → A → B → ...），每次生成完整日志 |

---

## UAT 测试场景

### UAT-1: 端到端完整流程 — 触发训练 → 监控 → 评估 → 上线

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1, AC-6.3, AC-6.4, AC-6.5 |
| **优先级** | P0 |
| **角色** | 管理员 |
| **前置** | 所有服务就绪；Tushare 数据缓存完整；至少有一个基线旧模型 |
| **用户故事** | 作为管理员，当市场风格发生变化导致模型表现下降时，我需要手动触发 LightGBM 重训练，实时监控训练进度，在自动评估确认新模型优于旧模型后，一键将新模型上线替换旧模型。 |
| **操作流程** | |
| | 1. 以 admin 登录，进入模型训练页面 |
| | 2. 创建 LightGBM 训练任务（样本量 2000、树 150、学习率 0.03） |
| | 3. 训练任务进入 running 状态 |
| | 4. 在详情页实时观察 Loss 曲线下降（train_loss 从 ~0.5 降至 ~0.1） |
| | 5. 训练完成（status → completed），自动触发评估 |
| | 6. 评估页面对比新模型（年化 18.2%）vs 旧模型（年化 15.7%），结论显示"推荐上线 🟢" |
| | 7. 点击"一键上线" → 确认 → 新模型标记为 production |
| | 8. 进入选股页面，用新模型执行一次选股，确认结果有效 |
| **关键证据** | |
| | - [ ] 训练任务创建成功，job_id 可追踪 |
| | - [ ] Loss 曲线实时更新、无中断 |
| | - [ ] 评估指标全部自动计算完成 |
| | - [ ] 上线操作一次点击完成（含确认 < 3 步） |
| | - [ ] 上线后选股结果使用新模型 |
| | - [ ] MLflow 中完整记录了实验、run、metrics、artifacts |
| | - [ ] 训练历史中新增一条完整记录 |

---

### UAT-2: 训练失败处理 — 数据不足 / OOM / 超时

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.4, AC-6.6 |
| **优先级** | P0 |
| **角色** | 管理员 |
| **前置** | 模拟各种失败场景 |
| **用户故事** | 作为管理员，当训练因数据不足、内存溢出或超时而失败时，系统需要优雅地终止训练、记录详细错误信息，而不是静默崩溃或留下僵尸进程。 |
| **操作流程** | |
| | **场景 A: 数据不足** |
| | 1. 清空 daily_kline 表，触发训练 |
| | 2. 观察训练快速失败，状态变为 failed |
| | **场景 B: 内存溢出** |
| | 3. 设置极小的 Docker 内存限制（256MB），触发 Kronos Fine-tune |
| | 4. 观察 OOM 时训练进程被终止，状态变为 failed |
| | **场景 C: 超时** |
| | 5. 设置训练超时 = 30 秒，触发大样本训练 |
| | 6. 观察 30 秒后训练被强制终止 |
| **关键证据** | |
| | - [ ] 数据不足时：status 变为 `failed`，error 包含 "训练数据不足（至少需要 500 条记录）" |
| | - [ ] OOM 时：训练进程被正确终止，无僵尸进程残留，error 包含 "内存不足" |
| | - [ ] 超时时：status 变为 `failed`，error 包含 "训练超时（超过 30s）" |
| | - [ ] 所有失败场景下：旧模型保持 production 状态不变 |
| | - [ ] 失败原因记录到训练历史，可在历史页面查看 |
| | - [ ] 前端有明确的失败提示（红色 Tag + 错误摘要），而非空白页面 |
| | - [ ] 失败后可点击"重试"按钮（使用相同参数） |
| | - [ ] MLflow run 标记为 `status: "FAILED"` |

---

### UAT-3: 并行训练 — 多个模型同时训练互不干扰

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1 |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 资源充足（GPU 显存 / 内存足够同时跑 2 个训练） |
| **用户故事** | 作为管理员，我需要同时训练 LightGBM 和 CatBoost 两个模型，它们各自独立运行，互不干扰，训练结果各自记录。 |
| **操作流程** | |
| | 1. 创建并启动 LightGBM 训练任务（Job-A） |
| | 2. 立即创建并启动 CatBoost 训练任务（Job-B） |
| | 3. 观察两个任务同时 running |
| | 4. 分别进入各自详情页查看进度 |
| | 5. 等待两个任务完成 |
| **关键证据** | |
| | - [ ] Job-A 和 Job-B 同时处于 running 状态 |
| | - [ ] 两个任务使用独立的进程/线程，无数据竞争 |
| | - [ ] 各自 Loss 曲线独立更新 |
| | - [ ] 一个任务失败不影响另一个（Job-A 失败，Job-B 继续运行至完成） |
| | - [ ] 各自模型输出到独立文件（无覆盖） |
| | - [ ] MLflow 中两个 run 同时存在、各自独立 |
| | - [ ] 前端训练列表同时展示两个 running 任务，可切换查看 |

---

### UAT-4: 自动调度即时生效 — 新建/修改/禁用调度规则

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.2 |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 调度器已启动 |
| **用户故事** | 作为管理员，我需要创建和修改自动训练调度规则，规则变更应即时生效（无需重启服务），禁用的规则不会触发训练。 |
| **操作流程** | |
| | 1. 创建调度规则：LightGBM，每周六凌晨 2:00 |
| | 2. 查看调度列表：确认 next_run_at 为本周六 2:00 |
| | 3. 修改 cron 为 `0 4 * * 0`（每周日凌晨 4:00） |
| | 4. 确认 next_run_at 更新为本周日 4:00 |
| | 5. 禁用该规则 |
| | 6. 手动将系统时间调到周六 2:01（或等待） |
| | 7. 确认没有触发训练 |
| | 8. 重新启用规则 |
| | 9. 手动将系统时间调到周日 4:01 |
| | 10. 确认自动触发了训练 |
| **关键证据** | |
| | - [ ] 规则创建后 next_run_at 即时计算并展示 |
| | - [ ] 修改 cron 后 next_run_at 即时更新 |
| | - [ ] 禁用规则：到预定时间不触发训练 |
| | - [ ] 启用规则：到预定时间自动触发训练 |
| | - [ ] 删除规则：立即从调度器中移除 |
| | - [ ] 调度触发产生系统日志：`[Scheduler] Triggered job LightGBM at 2026-06-14 04:00:00` |
| | - [ ] 调度规则持久化到 DB，服务重启后恢复 |

---

### UAT-5: A-B 上线验证 — 新模型上线后选股结果变化可观察

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.5 |
| **优先级** | P0 |
| **角色** | 管理员/分析师 |
| **前置** | 旧模型 A 在生产环境；新模型 B 训练完成且评估优于 A |
| **用户故事** | 作为管理员，我将新模型上线后，需要验证选股系统确实使用了新模型，并且选股结果与旧模型相比有明显变化（但不应该完全随机/异常）。 |
| **操作流程** | |
| | 1. 使用旧模型 A 执行一次选股，截图保存 Top50 结果 |
| | 2. 将新模型 B 一键上线 |
| | 3. 使用新模型 B 执行一次选股 |
| | 4. 对比两次选股结果：重合度、排序变化、新增/移除标的 |
| | 5. 验证新模型的选股质量（如平均因子得分）优于旧模型 |
| **关键证据** | |
| | - [ ] 上线后 `GET /api/v1/training/models/active` 返回 B |
| | - [ ] 选股 API 中 `model_name` 自动使用新模型 |
| | - [ ] 两次选股 Top50 重合率在合理范围（30%~80%，取决于模型差异程度） |
| | - [ ] 新模型选股的平均综合得分 ≥ 旧模型 |
| | - [ ] 模型版本页面显示 B 为 🟢 production，A 为 🟡 staged |
| | - [ ] 上线操作记录到操作日志，audit trail 完整 |

---

### UAT-6: 因子校准对选股结果的直接影响

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.7 |
| **优先级** | P0 |
| **角色** | 管理员 |
| **前置** | 有足够历史数据用于 IC 计算；校准前执行一次基线选股 |
| **用户故事** | 作为管理员，当我执行因子权重校准后，选股系统使用新的权重组合，选股结果应该反映权重的变化（如技术因子权重从 5% 调到 25% 后，技术面强的股票排名应提升）。 |
| **操作流程** | |
| | 1. 校准前：执行一次选股（ALL mode），保存 Top20 |
| | 2. 进入因子校准页面，查看 IC/ICIR 分析结果 |
| | 3. 确认 technical 因子 ICIR=+20.86（显著），momentum ICIR=-7.49（负） |
| | 4. 点击"应用校准权重" |
| | 5. 校准后：再次执行一次选股（ALL mode），保存 Top20 |
| | 6. 对比两次结果的因子得分构成变化 |
| **关键证据** | |
| | - [ ] 校准日志显示每个因子的 IC/ICIR 值和权重变化 |
| | - [ ] technical 因子权重上调后，Top20 中技术面评分均值提升 |
| | - [ ] momentum 因子反转后（contraian），高动量股票不再被过度加分 |
| | - [ ] 校准后的选股结果仍包含合理数量的股票（不含异常值/停牌/ST） |
| | - [ ] 校准不影响其他 mode（short / long）的权重（除非显式选择） |
| | - [ ] 校准参数持久化，服务重启后不丢失 |
| | - [ ] 支持查看历史校准记录，对比多次校准的权重演进 |

---

### UAT-7: 训练历史可追溯 — 完整审计追踪

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.8 |
| **优先级** | P1 |
| **角色** | 管理员/分析师 |
| **前置** | 已有多个训练记录、多次上线/回滚操作 |
| **用户故事** | 作为管理员或分析师，我需要追溯任意一次训练的全部细节：什么时间、用了什么数据（数据范围、样本量）、用了什么参数、训练效果如何、是否上线、由谁操作的，以确保模型迭代过程完全可审计。 |
| **操作流程** | |
| | 1. 进入训练历史页面 |
| | 2. 筛选 2026 年 5 月的 LightGBM 训练记录 |
| | 3. 点击第一条记录进入详情 |
| | 4. 检查：训练参数、数据来源、评估指标、操作人、上线记录 |
| | 5. 点击 MLflow 链接跳转到 MLflow UI |
| | 6. 导出筛选结果为 CSV |
| **关键证据** | |
| | - [ ] 历史记录按时间倒序排列 |
| | - [ ] 每条记录显示：created_at、model_type、sample_count、train_loss、val_loss、sharpe、status、deploy_status |
| | - [ ] 详情页有独立 URL（可分享/bookmark）：`/training/history/{job_id}` |
| | - [ ] 详情页完整展示：`params` JSON（含全部超参数）、`data_range`（训练数据时间范围）、`factor_list`（使用的因子列表） |
| | - [ ] 操作日志子表显示：谁创建的、谁上线的、谁回滚的，含时间戳 |
| | - [ ] 点击 MLflow 链接直接跳转到对应 run 页面 |
| | - [ ] CSV 导出包含所有列表字段 |
| | - [ ] 分析师角色可查看全部历史但不可做任何写操作 |

---

### UAT-8: 非管理员权限闭环 — 前端 + API 双重拦截

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.9 |
| **优先级** | P0 |
| **角色** | 分析师 / 只读用户 |
| **前置** | analyst 和 viewer 账号已就绪 |
| **用户故事** | 作为分析师，我只能查看训练历史和模型版本信息，不能触发训练、不能上线模型、不能修改调度。作为只读用户，我完全看不到训练功能入口。系统必须在前端 UI 和后端 API 两个层面都做了权限校验，无法通过直接调用 API 绕过前端限制。 |
| **操作流程** | |
| | **分析师（analyst）**： |
| | 1. 以 analyst 登录 |
| | 2. 确认导航菜单中无"模型训练"入口（但有"训练历史"只读入口） |
| | 3. 手动访问 `/training` → 被重定向到首页或显示 403 |
| | 4. 使用 curl/Postman 调用 `POST /api/v1/training/jobs` → 返回 403 |
| | 5. 访问 `/training/history` → 可查看历史列表和详情（200） |
| | 6. 尝试 `POST /api/v1/training/models/{id}/deploy` → 返回 403 |
| | **只读用户（viewer）**： |
| | 7. 以 viewer 登录 |
| | 8. 确认导航菜单中无训练相关入口 |
| | 9. 手动访问 `/training` → 403 |
| | 10. 手动访问 `/training/history` → 403 或空数据 |
| | 11. 所有训练 API 调用均返回 403 |
| **关键证据** | |
| | - [ ] 前端路由守卫：非 admin 访问 `/training` 被拦截 |
| | - [ ] 前端 UI：非 admin 看不到"新建训练"/"因子校准"/"调度管理"按钮 |
| | - [ ] 后端中间件：所有写操作 API 校验 `request.user.role == "admin"` |
| | - [ ] analyst 可访问只读 API（`GET /api/v1/training/jobs`, `GET /api/v1/training/jobs/{id}`） |
| | - [ ] viewer 对所有训练 API 均返回 403 |
| | - [ ] 绕过前端直接调用 API 同样被拦截 |
| | - [ ] 权限错误响应格式统一：`{"error": "权限不足", "detail": "仅管理员可执行此操作"}` |

---

### UAT-9: MLflow 模型注册表集成 — 版本管理与追溯

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.1, AC-6.5, AC-6.8（引申：模型资产管理） |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | MLflow Tracking Server 已启动；已有多次训练记录 |
| **用户故事** | 作为管理员，每次训练完成后模型应自动注册到 MLflow Model Registry，我可以查看所有模型版本、各版本的 stage（staging/production/archived），并可从 MLflow UI 直接下载模型文件。 |
| **操作流程** | |
| | 1. 触发一次 LightGBM 训练并完成 |
| | 2. 检查 MLflow Registry 中是否新增了模型版本 |
| | 3. 将该版本 transition 到 production |
| | 4. 触发另一次训练 |
| | 5. 在 MLflow UI 中查看多个版本的 lineage |
| **关键证据** | |
| | - [ ] 训练完成后 MLflow 自动创建 registered model（如 `lgbm_ranker`） |
| | - [ ] 每次训练注册为新版本（v1, v2, v3...） |
| | - [ ] 版本包含完整 metadata：params、metrics、artifacts、tags |
| | - [ ] 平台上线操作同步更新 MLflow stage（staging → production） |
| | - [ ] 平台回滚操作同步更新 MLflow stage（production → archived） |
| | - [ ] MLflow UI 中可下载 model artifacts（.pkl / .cbm / .pt） |
| | - [ ] 平台中训练详情页包含 MLflow run 直达链接 |

---

### UAT-10: 回滚后验证 — 选股结果恢复为旧模型行为

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-6.6（引申：回滚功能闭环验证） |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 当前 production 为新模型 B；有历史 staged 模型 A |
| **用户故事** | 作为管理员，当新模型 B 上线后发现选股效果不如预期（如实战中回撤增大），我需要将模型回滚到 A，并验证选股结果恢复为 A 的行为。 |
| **操作流程** | |
| | 1. 记录模型 B 下的选股 Top20 结果 |
| | 2. 执行回滚操作，将模型 A 恢复为 production |
| | 3. 再次执行选股，验证结果与 A 的历史行为一致 |
| | 4. 确认模型 B 被正确标记为 archived（非删除） |
| **关键证据** | |
| | - [ ] 回滚后 `GET /api/v1/training/models/active` 返回 A |
| | - [ ] 选股结果与回滚前 A 模型的结果一致（相同输入 → 相同输出） |
| | - [ ] B 模型保留在已归档列表中，仍可查看其训练信息 |
| | - [ ] 回滚日志记录完整（操作人、时间、从 B → A、原因） |
| | - [ ] 支持从 archived 模型重新上线（`POST /api/v1/training/models/{id}/deploy`） |
| | - [ ] MLflow Registry 中 stage 同步更新 |

---

## 附录 A: API 端点速查（设计提案，待实现）

| Method | Path | 用途 | 相关 AC |
|--------|------|------|---------|
| POST | `/api/v1/training/jobs` | 创建训练任务 | AC-6.1 |
| GET | `/api/v1/training/jobs` | 训练任务列表 | AC-6.8 |
| GET | `/api/v1/training/jobs/{id}` | 训练任务详情 | AC-6.3, AC-6.8 |
| GET | `/api/v1/training/jobs/{id}/metrics` | 训练实时指标（Loss 等） | AC-6.3 |
| GET | `/api/v1/training/jobs/{id}/feature-importance` | 特征重要性 | AC-6.3 |
| GET | `/api/v1/training/jobs/{id}/evaluation` | 自动评估结果 | AC-6.4 |
| POST | `/api/v1/training/jobs/{id}/retry` | 重试失败任务 | AC-6.6 |
| POST | `/api/v1/training/models/{id}/deploy` | 一键上线 | AC-6.5 |
| POST | `/api/v1/training/models/{id}/rollback` | 回滚 | AC-6.5, AC-6.6 |
| GET | `/api/v1/training/models/active` | 当前生产模型 | AC-6.5 |
| GET | `/api/v1/training/models` | 模型版本列表 | AC-6.8 |
| POST | `/api/v1/training/calibrate` | 因子权重校准 | AC-6.7 |
| POST | `/api/v1/training/schedules` | 创建调度规则 | AC-6.2 |
| GET | `/api/v1/training/schedules` | 调度规则列表 | AC-6.2 |
| PUT | `/api/v1/training/schedules/{id}` | 修改调度规则 | AC-6.2 |
| DELETE | `/api/v1/training/schedules/{id}` | 删除调度规则 | AC-6.2 |

---

## 附录 B: 训练任务状态机

```
pending → running → completed → (auto-evaluation) → evaluated
                   → failed                         → (deploy)     → deployed
                                   evaluated_passed  → (rollback)    → archived
                                   evaluated_failed  → (manual deploy) → deployed
```

**状态说明**:
- `pending`: 任务已创建，等待资源分配（队列中）
- `running`: 训练执行中（实时推送 metrics）
- `completed`: 训练完成，等待自动评估
- `failed`: 训练异常终止（数据不足/OOM/超时/代码异常）
- `evaluated`: 自动评估已完成，带 `passed` / `failed` 标记
- `deployed`: 已上线到生产环境
- `archived`: 已从生产环境下线（回滚或替换），保留只读记录

---

## 附录 C: 模型生命周期

```
训练完成 → MLflow 注册 (staging)
         → 自动评估通过 → 管理员确认上线 → production
         → 自动评估不通过 → rejected (保留记录)
production → 新模型上线 → archived
production → 表现不佳回滚 → archived
archived → 手动重新上线 → production
```

---

## 附录 D: 现有训练脚本映射

| PRD 模型类型 | 对应脚本 | 关键参数 | 产出文件 |
|-------------|---------|---------|---------|
| LightGBM | `Kronos/tools/train_lgbm_v2.py` | trees=100+, features=14, sample=2000 | `models/lgbm_ranker_v2.pkl` |
| CatBoost | `Kronos/tools/train_catboost.py` | iterations=500, depth=6, features=19, sample=3000 | `models/catboost_ranker.cbm` |
| Kronos Fine-tune | `Kronos/tools/finetune_single_device.py` | stage=tokenizer\|predictor, epochs=5, batch=16 | `models/kronos_ft_{stage}.pt` |
| Factor Calibration | `Kronos/tools/calibrate_weights.py` | window=60d, factors=14, mode=ALL\|short\|long | 更新 `screening_top50.py` 权重常量 |

---

## 附录 E: 已知限制与测试注意事项

1. **训练时间不确定性**: LightGBM 在 2000 样本上约 2-5 分钟，CatBoost 约 5-10 分钟，Kronos Fine-tune 约 15-30 分钟（MPS/GPU）。E2E 测试需预留足够超时时间。
2. **MLflow 依赖**: 训练流程深度依赖 MLflow Tracking Server，测试前必须确认 MLflow 服务可用。
3. **Tushare 数据依赖**: 训练和因子校准都需要 Tushare 数据，离线测试需使用预缓存的 SQLite 数据。
4. **Kronos 预训练权重**: Fine-tune 需要从 HuggingFace 下载预训练权重（~500MB），首次运行需网络。
5. **并发训练资源**: 同时运行多个训练任务时需注意 GPU 显存/Core ML 资源竞争。
6. **时间模拟**: 调度类测试需要能够模拟系统时间（如使用 `freezegun` 或手动调整 Docker 容器时间）。
7. **权限中间件**: 后端权限校验应使用 Decorator/Middleware 统一拦截，避免在每个 handler 中重复校验。
8. **WebSocket vs 轮询**: 训练进度实时更新建议使用 WebSocket（否则用短轮询，间隔 2-5 秒）。
