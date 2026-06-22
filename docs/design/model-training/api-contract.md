# Model-Training API 契约文档

> 基于 PRD AC-6.1~6.9 + 重构方案五训练服务
> 对应微服务：`services/training-service/`（端口 8008）
> 生成时间：2026-06-10

---

## 1. 概览

Training-Service 提供三类核心 API：

| 类别 | 前缀 | 说明 |
|------|------|------|
| 训练任务 (Job) | `/api/v1/training/` | 触发训练、查询状态、实时指标 SSE 推送 |
| 模型管理 (Model) | `/api/v1/training/models` | 模型列表、模型上线/回滚、新旧对比 |
| 调度与历史 | `/api/v1/training/` | 自动调度配置、训练历史追溯 |
| 因子分析 | `/api/v1/training/factors` | 因子校准、IC/ICIR 分析 |

---

## 2. 端点总览（11 个端点）

| # | 方法 | 路径 | AC 覆盖 | 说明 |
|---|------|------|---------|------|
| 1 | `POST` | `/api/v1/training/run` | AC-6.1 | 手动触发模型训练 |
| 2 | `GET` | `/api/v1/training/status/{job_id}` | AC-6.3 | 训练状态 + 实时指标 (SSE) |
| 3 | `GET` | `/api/v1/training/models` | -- | 模型注册表列表 |
| 4 | `GET` | `/api/v1/training/models/{id}` | -- | 模型详情（参数/指标/文件） |
| 5 | `POST` | `/api/v1/training/models/{id}/deploy` | AC-6.5 | 模型一键上线 (A/B 切换) |
| 6 | `POST` | `/api/v1/training/models/{id}/rollback` | AC-6.6 | 模型回滚 |
| 7 | `GET` | `/api/v1/training/models/{id}/compare` | AC-6.4 | 新旧模型回测对比 |
| 8 | `POST` | `/api/v1/training/schedule` | AC-6.2 | 配置自动训练调度 |
| 9 | `GET` | `/api/v1/training/schedule` | AC-6.2 | 查看当前调度配置 |
| 10 | `GET` | `/api/v1/training/history` | AC-6.8 | 训练历史列表 |
| 11 | `POST` | `/api/v1/training/calibrate` | AC-6.7 | 因子权重自动校准 |
| 12 | `GET` | `/api/v1/training/factors/ic` | AC-5.6 | IC/ICIR 滚动窗口分析 |

---

## 3. Pydantic Schema 定义

### 3.1 TrainingJob

```python
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


class ModelType(str, Enum):
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    KRONOS_FINETUNE = "kronos_finetune"


class JobStatus(str, Enum):
    PENDING = "pending"        # 排队等待
    PREPARING = "preparing"    # 准备数据
    RUNNING = "running"        # 训练中
    EVALUATING = "evaluating"  # 评估中（对比旧模型）
    COMPLETED = "completed"    # 完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消


class TrainingParams(BaseModel):
    """训练超参数（透传 Optuna search_space 或固定值）。"""
    model_type: ModelType = Field(..., description="模型类型")
    horizon: int = Field(default=10, ge=1, le=60, description="预测持仓天数")
    lookback: int = Field(default=90, ge=30, le=500, description="回看天数")
    n_trials: int = Field(default=50, ge=1, le=500, description="Optuna 试验次数")
    cv_folds: int = Field(default=5, ge=2, le=10, description="交叉验证折数")
    early_stopping_rounds: int = Field(default=50, ge=10, le=200)
    learning_rate: Optional[float] = Field(default=None, ge=0.001, le=1.0,
        description="None 表示由 Optuna 搜索")
    max_depth: Optional[int] = Field(default=None, ge=2, le=16,
        description="None 表示由 Optuna 搜索")
    num_leaves: Optional[int] = Field(default=None, ge=8, le=512,
        description="仅 LightGBM，None 表示由 Optuna 搜索")
    subsample: Optional[float] = Field(default=None, ge=0.3, le=1.0)
    colsample_bytree: Optional[float] = Field(default=None, ge=0.3, le=1.0)
    data_start_date: Optional[str] = Field(default=None,
        description="训练数据起始日期 (YYYY-MM-DD)，None 表示全部可用数据")
    data_end_date: Optional[str] = Field(default=None,
        description="训练数据截止日期 (YYYY-MM-DD)，None 表示最新")
    factor_whitelist: Optional[List[str]] = Field(default=None,
        description="限定使用因子列表，None 表示全部 14 因子")
    test_size: float = Field(default=0.2, ge=0.05, le=0.5,
        description="验证集比例")


class TrainingMetrics(BaseModel):
    """训练过程中的实时指标快照。"""
    trial: int = Field(..., description="当前 Optuna trial 编号")
    epoch: Optional[int] = Field(default=None, description="当前 epoch（LightGBM/CatBoost）")
    train_loss: float
    valid_loss: float
    best_valid_loss: float
    ic: Optional[float] = Field(default=None, description="验证集 IC (Rank IC)")
    icir: Optional[float] = Field(default=None, description="验证集 ICIR")
    feature_importance: Optional[Dict[str, float]] = Field(default=None,
        description="Top 10 特征重要性")
    elapsed_seconds: float


class TrainingJob(BaseModel):
    """训练任务完整记录。"""
    job_id: str = Field(..., description="UUID v4")
    model_type: ModelType
    status: JobStatus
    params: TrainingParams
    best_params: Optional[Dict[str, Any]] = Field(default=None,
        description="Optuna 搜索到的最优超参")
    metrics: List[TrainingMetrics] = Field(default_factory=list,
        description="训练过程指标序列")
    final_metrics: Optional[TrainingMetrics] = Field(default=None,
        description="训练完成时的最终指标")
    model_uri: Optional[str] = Field(default=None,
        description="MLflow model URI (models:/<name>/<version>)")
    run_id: Optional[str] = Field(default=None,
        description="MLflow Run ID")
    experiment_id: Optional[str] = Field(default=None,
        description="MLflow Experiment ID")
    created_by: str = Field(..., description="触发人用户名")
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class TrainRequest(BaseModel):
    """POST /api/v1/training/run 请求体。"""
    params: TrainingParams
    auto_deploy: bool = Field(default=False,
        description="训练完成后若优于旧模型自动上线")


class TrainResponse(BaseModel):
    """POST /api/v1/training/run 响应体。"""
    job_id: str
    status: JobStatus
    created_at: datetime
```

### 3.2 ModelRecord

```python
class ModelStage(str, Enum):
    NONE = "none"           # 刚注册，未上线
    STAGING = "staging"     # 预发布（待人工确认）
    PRODUCTION = "production"  # 线上
    ARCHIVED = "archived"   # 已下线（新模型不如旧模型）


class CompareResult(BaseModel):
    """AC-6.4: 新模型 vs 旧模型回测对比。"""
    metric: str = Field(..., description="对比指标名称")
    new_value: float
    old_value: float
    delta: float = Field(..., description="new - old")
    delta_pct: float = Field(..., description="变化百分比")
    better: bool = Field(..., description="新模型是否更优")
    threshold: float = Field(default=0.0,
        description="优于旧模型的判定阈值")


class ModelRecord(BaseModel):
    """模型注册表记录（映射 MLflow RegisteredModel + Version）。"""
    id: str = Field(..., description="模型版本 ID")
    name: str = Field(..., description="注册模型名称，如 lightgbm-ranker")
    version: int = Field(..., ge=1, description="MLflow 版本号")
    model_type: ModelType
    stage: ModelStage
    run_id: Optional[str] = None
    experiment_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = Field(default=None,
        description="训练参数快照")
    metrics: Optional[Dict[str, Any]] = Field(default=None,
        description="模型指标（train_loss, valid_loss, ic, icir, sharpe 等）")
    artifact_uri: Optional[str] = Field(default=None,
        description="模型文件路径 (MLflow artifact_uri)")
    deployed_at: Optional[datetime] = None
    deployed_by: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, description="备注/失败原因")


class ModelCompareResponse(BaseModel):
    """GET /models/{id}/compare 响应体。"""
    new_model: ModelRecord
    old_model: Optional[ModelRecord] = Field(default=None,
        description="当前线上模型，None 表示无旧模型")
    comparison: List[CompareResult]
    verdict: str = Field(...,
        description="综合判定: 'new_better' | 'old_better' | 'inconclusive'")
    recommendation: str = Field(...,
        description="操作建议: '建议上线' | '保留旧模型' | '需人工判断'")
```

### 3.3 调度与校准

```python
class ScheduleConfig(BaseModel):
    """自动训练调度配置 (AC-6.2)。"""
    enabled: bool = Field(default=False)
    cron: str = Field(default="0 2 * * 6",
        description="Cron 表达式，默认每周六凌晨 2:00")
    model_type: ModelType = Field(default=ModelType.LIGHTGBM)
    params: TrainingParams
    auto_deploy: bool = Field(default=False)
    notify_on_complete: bool = Field(default=True,
        description="训练完成后通知管理员")
    notify_channels: List[str] = Field(default_factory=lambda: ["email", "wecom"],
        description="通知渠道")


class CalibrateRequest(BaseModel):
    """POST /api/v1/training/calibrate 请求体 (AC-6.7)。"""
    mode: str = Field(default="all", description="all | short | both")
    window_days: int = Field(default=90, ge=30, le=365,
        description="滚动窗口天数")
    min_samples: int = Field(default=30, ge=10, le=200,
        description="每个因子最少有效样本数")
    apply: bool = Field(default=False,
        description="是否自动应用校准结果到选股引擎")


class CalibrateResponse(BaseModel):
    """因子校准结果。"""
    calibrated_at: datetime
    window_start: str
    window_end: str
    factors: List[FactorWeight]
    summary: str


class FactorWeight(BaseModel):
    factor_name: str
    factor_label: str
    ic: float = Field(..., description="信息系数 (Spearman Rank IC)")
    icir: float = Field(..., description="IC 信息比率 = mean(IC) / std(IC)")
    old_weight: float
    new_weight: float
    direction: str = Field(..., description="long | short")
    significance: str = Field(..., description="t 检验显著性: significant | marginal | none")


class ICWindow(BaseModel):
    """IC 滚动窗口数据点。"""
    window_end: str = Field(..., description="窗口截止日期")
    ic: float
    icir: float
    n_stocks: int
```

---

## 4. 端点详细契约

### 4.1 POST /api/v1/training/run — 触发训练 (AC-6.1)

**权限**：仅 `admin` 角色 (AC-6.9)

**Request Body:**

```json
{
  "params": {
    "model_type": "lightgbm",
    "horizon": 10,
    "lookback": 90,
    "n_trials": 50,
    "cv_folds": 5,
    "early_stopping_rounds": 50,
    "learning_rate": null,
    "max_depth": null,
    "data_start_date": "2025-01-01",
    "data_end_date": null,
    "factor_whitelist": null,
    "test_size": 0.2
  },
  "auto_deploy": false
}
```

**Response 202:**

```json
{
  "job_id": "c7e3d4a2-8f1b-4a3c-9d5e-1f2a3b4c5d6e",
  "status": "pending",
  "created_at": "2026-06-10T08:30:00Z"
}
```

**Response 409 (已有训练任务运行中):**

```json
{
  "error": "training_already_running",
  "message": "已有训练任务 job-abc123 正在运行中 (LIGHTGBM, status=running)",
  "active_job_id": "job-abc123"
}
```

**处理流程**：

1. 校验管理员权限
2. 检查无同类活跃任务（model_type 相同且 status in [pending, preparing, running, evaluating]）
3. 创建 TrainingJob 记录（status=pending）→ 写入 PostgreSQL
4. 投递异步任务到 Celery/RQ → Worker 执行：数据准备 → Optuna 超参搜索 → 训练 → 评估 → MLflow 注册
5. 返回 202 + job_id

---

### 4.2 GET /api/v1/training/status/{job_id} — 训练状态 + SSE 推送 (AC-6.3)

**权限**：仅 `admin` 角色

**Response 200 (JSON 快照):**

```json
{
  "job_id": "c7e3d4a2-...",
  "model_type": "lightgbm",
  "status": "running",
  "params": { "...": "..." },
  "current_metrics": {
    "trial": 23,
    "epoch": null,
    "train_loss": 0.342,
    "valid_loss": 0.389,
    "best_valid_loss": 0.371,
    "ic": 0.048,
    "icir": 0.62,
    "feature_importance": {
      "technical": 0.182,
      "momentum": 0.151,
      "volume": 0.133,
      "composite": 0.119,
      "quality": 0.098,
      "hard_tech": 0.087,
      "growth": 0.073,
      "daily_basic": 0.062,
      "moneyflow": 0.049,
      "short_term": 0.046
    },
    "elapsed_seconds": 234.5
  },
  "started_at": "2026-06-10T08:30:05Z",
  "error_message": null
}
```

**SSE 实时推送 (Accept: text/event-stream):**

```
GET /api/v1/training/status/{job_id}
Accept: text/event-stream

event: metric
data: {"trial":1,"train_loss":0.852,"valid_loss":0.861,"best_valid_loss":0.861,"ic":0.031,"icir":0.38,"elapsed_seconds":12.3,"feature_importance":{"technical":0.156,"momentum":0.142,...}}

event: metric
data: {"trial":2,"train_loss":0.821,"valid_loss":0.835,"best_valid_loss":0.835,"ic":0.035,"icir":0.42,"elapsed_seconds":23.1,...}

event: trial_complete
data: {"trial":50,"best_params":{"learning_rate":0.05,"max_depth":8,"num_leaves":128,"subsample":0.8,"colsample_bytree":0.7}}

event: evaluating
data: {"status":"evaluating","message":"正在对比新旧模型回测表现..."}

event: complete
data: {"job_id":"...","status":"completed","final_metrics":{...},"model_uri":"models:/lightgbm-ranker/7"}

event: error
data: {"job_id":"...","status":"failed","error_message":"CUDA OOM at trial 34"}
```

**SSE 事件类型**：

| event | 触发时机 | data 内容 |
|-------|---------|----------|
| `metric` | 每个 trial/epoch 结束 | `TrainingMetrics` JSON |
| `trial_complete` | Optuna study 完成 | best_params |
| `evaluating` | 训练完成，开始评估 | 状态变更 |
| `complete` | 全部完成 | final_metrics + model_uri |
| `error` | 失败 | error_message |

---

### 4.3 GET /api/v1/training/models — 模型注册表列表

**权限**：仅 `admin` 角色

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `model_type` | string | 否 | -- | 过滤: lightgbm / catboost / kronos_finetune |
| `stage` | string | 否 | -- | 过滤: staging / production / archived |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数 (1..100) |

**Response 200:**

```json
{
  "models": [
    {
      "id": "mdl-001",
      "name": "lightgbm-ranker",
      "version": 7,
      "model_type": "lightgbm",
      "stage": "production",
      "run_id": "a1b2c3d4...",
      "metrics": {
        "train_loss": 0.312,
        "valid_loss": 0.371,
        "ic": 0.052,
        "icir": 0.71,
        "sharpe": 1.84
      },
      "deployed_at": "2026-06-08T10:00:00Z",
      "deployed_by": "admin",
      "created_at": "2026-06-08T04:30:00Z"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20
}
```

---

### 4.4 GET /api/v1/training/models/{id} — 模型详情

**权限**：仅 `admin` 角色

**Response 200:**

返回完整 `ModelRecord`，包含 `params`、`metrics`、`artifact_uri`、`notes` 等全部字段。

---

### 4.5 POST /api/v1/training/models/{id}/deploy — 模型上线 (AC-6.5)

**权限**：仅 `admin` 角色

**Request Body (可选):**

```json
{
  "force": false,
  "notes": "新模型在 2025Q4 回测中夏普比率提升 0.3"
}
```

**处理逻辑 (A/B 切换)**：

1. 校验目标模型存在
2. 若已有 `stage=production` 的同名模型 → 将其 `stage` 改为 `archived`（下线）
3. 将目标模型 `stage` 更新为 `production`
4. 通过 MLflow Client `transition_model_version_stage()` 同步状态
5. 通知选股引擎 (screener-service) 刷新模型引用 → 下次选股使用新模型
6. 写入审计日志

**Response 200:**

```json
{
  "model_id": "mdl-001",
  "stage": "production",
  "deployed_at": "2026-06-10T12:00:00Z",
  "previous_production_version": 6,
  "message": "模型 lightgbm-ranker v7 已上线 (替换 v6)"
}
```

**Response 409 (force=false 且模型未通过评估):**

```json
{
  "error": "model_not_validated",
  "message": "该模型尚未完成对比评估，请先调用 /compare 确认表现优于旧模型。或设置 force=true 强制上线。"
}
```

---

### 4.6 POST /api/v1/training/models/{id}/rollback — 模型回滚 (AC-6.6)

**权限**：仅 `admin` 角色

**Request Body:**

```json
{
  "target_version": 5,
  "reason": "v7 在实盘中 ICIR 从 0.71 下降到 0.38，回退到 v5"
}
```

**处理逻辑**：

1. 将当前 production 模型 `stage` 改为 `archived`
2. 在 `notes` 字段记录失败原因 (AC-6.6)
3. 将 `target_version` 的 `stage` 改为 `production`
4. 同步 MLflow stage
5. 通知选股引擎刷新模型引用

**Response 200:**

```json
{
  "model_id": "mdl-rollback-001",
  "new_production_version": 5,
  "rolled_back_from": 7,
  "reason": "v7 在实盘中 ICIR 从 0.71 下降到 0.38",
  "message": "已回滚到 lightgbm-ranker v5"
}
```

---

### 4.7 GET /api/v1/training/models/{id}/compare — 新旧模型对比 (AC-6.4)

**权限**：仅 `admin` 角色

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `backtest_start` | string | 否 | 最近 90 天 | YYYY-MM-DD |
| `backtest_end` | string | 否 | 最近交易日 | YYYY-MM-DD |
| `top_k` | int | 否 | 50 | 回测选股数 |

**处理逻辑**：

1. 加载新模型（指定 id）和旧模型（当前 production）
2. 在相同回测集上分别跑回测
3. 对比关键指标：IC、ICIR、夏普比率、最大回撤、年化收益、胜率、盈亏比
4. 输出 `verdict` + `recommendation`

**Response 200:**

```json
{
  "new_model": {
    "id": "mdl-001",
    "name": "lightgbm-ranker",
    "version": 7,
    "model_type": "lightgbm",
    "stage": "staging",
    "metrics": {
      "ic": 0.052,
      "icir": 0.71,
      "sharpe": 1.84,
      "max_drawdown": -0.12,
      "annual_return": 0.38,
      "win_rate": 0.62,
      "profit_loss_ratio": 1.9
    }
  },
  "old_model": {
    "id": "mdl-000",
    "name": "lightgbm-ranker",
    "version": 6,
    "model_type": "lightgbm",
    "stage": "production",
    "metrics": {
      "ic": 0.045,
      "icir": 0.61,
      "sharpe": 1.54,
      "max_drawdown": -0.15,
      "annual_return": 0.31,
      "win_rate": 0.58,
      "profit_loss_ratio": 1.7
    }
  },
  "comparison": [
    {"metric": "sharpe", "new_value": 1.84, "old_value": 1.54, "delta": 0.30, "delta_pct": 19.5, "better": true, "threshold": 0.05},
    {"metric": "icir", "new_value": 0.71, "old_value": 0.61, "delta": 0.10, "delta_pct": 16.4, "better": true, "threshold": 0.02},
    {"metric": "max_drawdown", "new_value": -0.12, "old_value": -0.15, "delta": 0.03, "delta_pct": 20.0, "better": true, "threshold": 0.0},
    {"metric": "annual_return", "new_value": 0.38, "old_value": 0.31, "delta": 0.07, "delta_pct": 22.6, "better": true, "threshold": 0.02},
    {"metric": "win_rate", "new_value": 0.62, "old_value": 0.58, "delta": 0.04, "delta_pct": 6.9, "better": true, "threshold": 0.02},
    {"metric": "profit_loss_ratio", "new_value": 1.9, "old_value": 1.7, "delta": 0.2, "delta_pct": 11.8, "better": true, "threshold": 0.05}
  ],
  "verdict": "new_better",
  "recommendation": "建议上线。新模型在全部 6 项指标上优于旧模型，夏普比率提升 19.5%。"
}
```

---

### 4.8 POST /api/v1/training/schedule — 配置自动调度 (AC-6.2)

**权限**：仅 `admin` 角色

**Request Body:**

```json
{
  "enabled": true,
  "cron": "0 2 * * 6",
  "model_type": "lightgbm",
  "params": {
    "model_type": "lightgbm",
    "horizon": 10,
    "lookback": 90,
    "n_trials": 50,
    "cv_folds": 5,
    "early_stopping_rounds": 50,
    "test_size": 0.2
  },
  "auto_deploy": false,
  "notify_on_complete": true,
  "notify_channels": ["email", "wecom"]
}
```

**处理逻辑**：

- 将配置持久化到 PostgreSQL
- 注册/更新 APScheduler 或 Celery Beat 定时任务
- 每次触发时自动创建 TrainingJob，流程同手动触发
- 若 `auto_deploy=true` 且新模型优于旧模型，自动调用 deploy

**Response 200:**

```json
{
  "enabled": true,
  "cron": "0 2 * * 6",
  "next_run": "2026-06-13T02:00:00Z",
  "message": "自动训练调度已启用：每周六凌晨 2:00 (Asia/Shanghai)"
}
```

---

### 4.9 GET /api/v1/training/schedule — 查看调度配置 (AC-6.2)

**权限**：仅 `admin` 角色

**Response 200:**

返回当前 `ScheduleConfig` + `next_run` + `last_run` + `last_job_id`。

```json
{
  "enabled": true,
  "cron": "0 2 * * 6",
  "model_type": "lightgbm",
  "auto_deploy": false,
  "next_run": "2026-06-13T02:00:00Z",
  "last_run": "2026-06-06T02:00:05Z",
  "last_job_id": "job-abc123",
  "last_job_status": "completed"
}
```

---

### 4.10 GET /api/v1/training/history — 训练历史 (AC-6.8)

**权限**：仅 `admin` 角色

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `model_type` | string | 否 | -- | 过滤 |
| `status` | string | 否 | -- | 过滤 |
| `created_by` | string | 否 | -- | 过滤触发人 |
| `start_date` | string | 否 | -- | YYYY-MM-DD |
| `end_date` | string | 否 | -- | YYYY-MM-DD |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数 (1..100) |

**Response 200:**

```json
{
  "jobs": [
    {
      "job_id": "c7e3d4a2-...",
      "model_type": "lightgbm",
      "status": "completed",
      "params": {
        "model_type": "lightgbm",
        "horizon": 10,
        "n_trials": 50,
        "data_start_date": "2025-01-01",
        "data_end_date": "2026-06-05"
      },
      "final_metrics": {
        "train_loss": 0.312,
        "valid_loss": 0.371,
        "ic": 0.052,
        "icir": 0.71,
        "trial": 50
      },
      "model_uri": "models:/lightgbm-ranker/7",
      "created_by": "schedule",
      "created_at": "2026-06-06T02:00:00Z",
      "started_at": "2026-06-06T02:00:05Z",
      "completed_at": "2026-06-06T02:45:30Z",
      "duration_seconds": 2725
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

### 4.11 POST /api/v1/training/calibrate — 因子权重校准 (AC-6.7)

**权限**：仅 `admin` 角色

**Request Body:**

```json
{
  "mode": "all",
  "window_days": 90,
  "min_samples": 30,
  "apply": true
}
```

**处理逻辑**：

1. 对每个因子，在最近 `window_days` 天内计算滚动 IC/ICIR
2. 基于 ICIR 重新分配权重（ICIR 越高权重越大，ICIR 为负则反向）
3. 若 `apply=true`，将新权重写入选股引擎配置（更新 `screening_top50.py` 中的权重表或数据库中的配置）
4. 记录校准历史到 `factor_calibration_history` 表

**Response 200:**

```json
{
  "calibrated_at": "2026-06-10T08:00:00Z",
  "window_start": "2026-03-12",
  "window_end": "2026-06-09",
  "factors": [
    {"factor_name":"technical","factor_label":"五因子-技术","ic":0.048,"icir":0.86,"old_weight":4.0,"new_weight":6.2,"direction":"long","significance":"significant"},
    {"factor_name":"momentum","factor_label":"五因子-动量","ic":-0.031,"icir":-0.63,"old_weight":2.5,"new_weight":3.1,"direction":"short","significance":"significant"},
    {"factor_name":"volume","factor_label":"五因子-量能","ic":0.022,"icir":0.41,"old_weight":2.8,"new_weight":2.3,"direction":"long","significance":"marginal"},
    {"factor_name":"composite","factor_label":"综合评分","ic":0.035,"icir":0.58,"old_weight":2.7,"new_weight":3.8,"direction":"long","significance":"significant"}
  ],
  "summary": "完成 14 个因子校准，窗口 2026-03-12 ~ 2026-06-09。6 个因子权重上调，5 个下调，3 个维持。校准结果已应用。"
}
```

---

### 4.12 GET /api/v1/training/factors/ic — IC/ICIR 分析 (AC-5.6)

**权限**：仅 `admin` 角色

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `factors` | string | 否 | -- | 逗号分隔因子名，默认全部 |
| `window_days` | int | 否 | 90 | 滚动窗口天数 |
| `start_date` | string | 否 | 最近 365 天前 | YYYY-MM-DD |
| `end_date` | string | 否 | 最近交易日 | YYYY-MM-DD |

**Response 200:**

```json
{
  "window_days": 90,
  "date_range": "2025-06-10 ~ 2026-06-10",
  "factors": [
    {
      "factor_name": "technical",
      "factor_label": "五因子-技术",
      "current_ic": 0.048,
      "current_icir": 0.86,
      "ic_mean": 0.042,
      "ic_std": 0.056,
      "icir_mean": 0.75,
      "direction": "long",
      "rolling": [
        {"window_end": "2026-06-09", "ic": 0.048, "icir": 0.86, "n_stocks": 4823},
        {"window_end": "2026-06-02", "ic": 0.044, "icir": 0.79, "n_stocks": 4815}
      ]
    }
  ]
}
```

---

## 5. 实时指标 SSE 推送方案

### 5.1 架构

```
Training Worker (Celery/RQ)
  │
  ├── Optuna Trial 完成 → push metric → Redis Pub/Sub (channel: training:{job_id})
  │
  ▼
FastAPI SSE Endpoint
  │
  ├── subscribe Redis Pub/Sub
  ├── yield Server-Sent Events (text/event-stream)
  │
  ▼
Frontend (EventSource)
  │
  ├── 实时渲染 Loss 曲线 (ECharts)
  └── 实时渲染特征重要性柱状图
```

### 5.2 实现要点

```python
# training-service/app/routers/training.py

from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis

async def training_status_sse(job_id: str, current_user = Depends(get_current_admin)):
    """SSE endpoint: GET /api/v1/training/status/{job_id} (Accept: text/event-stream)"""

    async def event_generator():
        r = await redis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"training:{job_id}")

        # 先发送当前状态快照
        job = await get_job(job_id)
        yield {"event": "status", "data": job.model_dump_json()}

        # 监听实时指标
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                yield {"event": data["type"], "data": json.dumps(data)}

            # 训练终止时主动断开
            if data.get("type") in ("complete", "error"):
                await pubsub.unsubscribe(f"training:{job_id}")
                break

    return EventSourceResponse(event_generator())
```

### 5.3 前端消费

```typescript
// frontend/src/hooks/useTrainingMetrics.ts
const eventSource = new EventSource(
  `/api/v1/training/status/${jobId}`,
  { headers: { Accept: 'text/event-stream' } }
);

eventSource.addEventListener('metric', (e) => {
  const metric = JSON.parse(e.data);
  updateLossChart(metric);       // 追加 Loss 曲线数据点
  updateImportanceChart(metric);  // 更新特征重要性
});

eventSource.addEventListener('complete', (e) => {
  const result = JSON.parse(e.data);
  eventSource.close();
  showResult(result);
});
```

---

## 6. MLflow 集成方案

### 6.1 总体架构

```
training-service (FastAPI :8008)
  │
  ├── 训练触发器 → Celery Worker
  │     ├── Optuna Study (超参搜索)
  │     ├── 最优参数 → MLflow Tracking (log_params, log_metrics, log_artifacts)
  │     └── MLflow Model Registry (register_model)
  │
  ├── 模型管理 API → mlflow.tracking.MlflowClient
  │     ├── list_registered_models()
  │     ├── get_model_version()
  │     └── transition_model_version_stage()
  │
  └── Screener 选股时 → mlflow.pyfunc.load_model(model_uri)
        └── 加载 production stage 模型进行推理
```

### 6.2 MLflow 部署配置

```yaml
# docker-compose.yml (追加)
services:
  mlflow:
    image: ghcr.io/mlflow/mlflow:v3.2.0
    ports:
      - "5010:5000"
    environment:
      - MLFLOW_BACKEND_STORE_URI=postgresql://user:pass@postgres:5432/mlflow
      - MLFLOW_DEFAULT_ARTIFACT_ROOT=s3://mlflow-artifacts
    command: >
      mlflow server
      --backend-store-uri postgresql://user:pass@postgres:5432/mlflow
      --default-artifact-root s3://mlflow-artifacts
      --host 0.0.0.0
      --port 5000
```

### 6.3 模型命名规范

| MLflow Registered Model | 对应 ModelType | 说明 |
|------------------------|---------------|------|
| `lightgbm-ranker` | lightgbm | LambdaRank 排序模型 |
| `catboost-ranker` | catboost | CatBoost 排序模型 |
| `kronos-finetune` | kronos_finetune | Kronos 时序预测微调 |

### 6.4 训练 Worker 与 MLflow 交互

```python
import mlflow
import mlflow.lightgbm
from optuna.integration.mlflow import MLflowCallback

def train_worker(job_id: str, params: TrainingParams):
    mlflow.set_tracking_uri("http://mlflow:5000")
    mlflow.set_experiment(f"training-{params.model_type.value}")

    mlflc = MLflowCallback(tracking_uri="http://mlflow:5000")

    with mlflow.start_run(run_name=f"job-{job_id}") as run:
        # Log params
        mlflow.log_params(params.model_dump())

        # Optuna study
        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=params.n_trials, callbacks=[mlflc])

        # Train best model
        best_model = train_with_params(study.best_params)

        # Log metrics & model
        mlflow.log_metrics({"best_valid_loss": study.best_value, "ic": ic, "icir": icir})
        mlflow.lightgbm.log_model(best_model, "model")

        # Register
        result = mlflow.register_model(
            f"runs:/{run.info.run_id}/model",
            f"{params.model_type.value}-ranker"
        )

        return result.version
```

---

## 7. 安全与权限

| 端点 | 角色要求 | 说明 |
|------|---------|------|
| 全部 `/api/v1/training/*` | `admin` | AC-6.9: 仅管理员可访问训练功能 |
| 模型推理（选股引擎内部） | 服务间 mTLS | screener-service → training-service 内部调用 |

API Gateway 层 (`/api/training/*`) 统一拦截非 admin 角色 → 返回 403。

---

## 8. 数据库表设计（概要）

### 8.1 training_jobs

```sql
CREATE TABLE training_jobs (
    job_id UUID PRIMARY KEY,
    model_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    params JSONB NOT NULL,
    best_params JSONB,
    metrics JSONB DEFAULT '[]',
    final_metrics JSONB,
    model_uri VARCHAR(512),
    run_id VARCHAR(128),
    experiment_id VARCHAR(128),
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);
CREATE INDEX idx_training_jobs_status ON training_jobs(status);
CREATE INDEX idx_training_jobs_created_at ON training_jobs(created_at DESC);
```

### 8.2 model_registry (缓存 MLflow 元数据)

```sql
CREATE TABLE model_registry (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    version INT NOT NULL,
    model_type VARCHAR(32) NOT NULL,
    stage VARCHAR(32) NOT NULL DEFAULT 'none',
    run_id VARCHAR(128),
    experiment_id VARCHAR(128),
    params JSONB,
    metrics JSONB,
    artifact_uri VARCHAR(512),
    deployed_at TIMESTAMPTZ,
    deployed_by VARCHAR(64),
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    notes TEXT
);
CREATE UNIQUE INDEX idx_model_name_version ON model_registry(name, version);
CREATE INDEX idx_model_stage ON model_registry(stage);
```

### 8.3 training_schedule

```sql
CREATE TABLE training_schedule (
    id INT PRIMARY KEY DEFAULT 1,  -- 单例
    enabled BOOLEAN DEFAULT FALSE,
    cron VARCHAR(64) DEFAULT '0 2 * * 6',
    model_type VARCHAR(32) NOT NULL,
    params JSONB NOT NULL,
    auto_deploy BOOLEAN DEFAULT FALSE,
    notify_on_complete BOOLEAN DEFAULT TRUE,
    notify_channels JSONB DEFAULT '["email","wecom"]',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 8.4 factor_calibration_history

```sql
CREATE TABLE factor_calibration_history (
    id SERIAL PRIMARY KEY,
    calibrated_at TIMESTAMPTZ DEFAULT NOW(),
    mode VARCHAR(16) NOT NULL,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    factors JSONB NOT NULL,
    applied BOOLEAN DEFAULT FALSE,
    summary TEXT
);
CREATE INDEX idx_calibration_date ON factor_calibration_history(calibrated_at DESC);
```

---

## 9. 错误码汇总

| HTTP Status | 错误码 | 说明 |
|-------------|--------|------|
| 400 | `invalid_params` | 训练参数校验失败 |
| 403 | `forbidden` | 非管理员访问 (AC-6.9) |
| 404 | `job_not_found` | 训练任务不存在 |
| 404 | `model_not_found` | 模型不存在 |
| 409 | `training_already_running` | 同类型训练任务已在运行 |
| 409 | `model_not_validated` | 模型未通过对比评估时尝试上线 |
| 409 | `deploy_conflict` | 目标模型已上线 |
| 422 | `validation_error` | Pydantic 校验失败 |
| 500 | `mlflow_error` | MLflow 服务不可用 |
| 500 | `internal_error` | 内部错误 |

---

## 10. 开放问题

### Q1: Optuna 超参搜索的执行环境

**问题**：LightGBM/CatBoost 训练 + Optuna 搜索是 CPU 密集型任务（50 trials × 5-fold CV × 训练），单次训练可能耗时 30-90 分钟。是否需要一个独立的 GPU/高配 CPU Worker 池，避免阻塞其他异步任务？

**选项**：
- A) Celery 独立队列 `training-gpu`，绑定 GPU worker
- B) 提交到 Kubernetes Job，自动创建 Pod 执行后销毁
- C) 复用现有 Celery Worker，通过优先级队列区分

**建议**：Phase 3 先用选项 A（Kronos 项目已有 Celery 基础设施），Phase 4 评估是否需要 K8s Job 的弹性扩缩。

---

### Q2: Kronos Fine-tune 的模型格式与部署

**问题**：Kronos 是基于时序 Transformer 的 K 线预测模型（PyTorch/ONNX），与 LightGBM/CatBoost 的模型格式和管理方式完全不同。MLflow 支持 `mlflow.pytorch.log_model()`，但：

- Kronos Fine-tune 是否需要独立的训练脚本（不在 Optuna 框架内）？
- ONNX 导出的模型能否通过 MLflow 的 `pyfunc` 统一加载？
- GPU 推理 vs CPU 推理的选择？

**建议**：Kronos Fine-tune 使用独立的训练流程（不对接 Optuna），用 `mlflow.pytorch.autolog()` 记录实验，注册为独立的 `kronos-finetune` 模型。推理时通过 ONNX Runtime 加载，选股引擎统一通过 `mlflow.pyfunc.load_model()` 接口。

> **修订 (M05/M10, audit-model-2026-06-22)**: 上述"ONNX Runtime 加载"为早期设计假设, 实际未实现 — `services/prediction-service/app/onnx_optimizer.py` 全为 placeholder 死代码, 已删除 (M10). 生产 prediction-service 当前基于公开 `NeoQuasar/Kronos-mini` 的 PyTorch 托管推理 (非自研, M05), 自研 fine-tune 训练见 ADR-004 待定项.

---

### Q3: 模型 A/B 测试的流量分配策略

**问题**：AC-6.5 提到 A/B 切换，但当前选股流程是管理员手动发起或定时调度。是否需要支持 A/B 流量分配（如 50% 选股请求使用新模型，50% 使用旧模型），还是仅支持全量切换？

**选项**：
- A) 全量切换（当前 AC 描述）：新模型替换旧模型，不保留 A/B 并行
- B) A/B 流量分配：新模型上线后同时保留旧模型，按配置比例路由选股请求，持续对比真实表现，确认优于旧模型后再全量切换

**建议**：Phase 3 采用全量切换（选项 A，更快落地），Phase 4 根据实际需要评估 A/B 流量分配。

---

### Q4: 训练数据版本管理

**问题**：AC-6.8 要求训练历史可追溯（什么数据），但当前 Kronos 数据管道（每日增量同步）不保留历史快照。如何确保"用 2026-01-01 ~ 2026-06-05 的数据训练"是可复现的？

**建议**：
- 训练任务启动时，记录数据快照的 `data_fingerprint`（统计摘要：股票数、特征缺失率、日期范围）
- 关键数据（因子值、标签）在 MLflow 中作为 `input_example` 或额外 artifact 存储
- Phase 4 引入 DVC (Data Version Control) 管理数据版本

---

### Q5: 因子校准与选股引擎的配置同步

**问题**：AC-6.7 因子校准后需要更新选股引擎的权重配置。当前 `screening_top50.py` 通过代码内权重字典管理。校准后的权重如何同步到 running screener-service？

**建议**：
- 权重配置从代码迁移到 PostgreSQL 配置表或 Redis
- screener-service 启动时加载，支持热更新（通过 Redis Pub/Sub 或 HTTP callback）
- 校准 `apply=true` 时 → 写入配置表 → 通知 screener-service 刷新
