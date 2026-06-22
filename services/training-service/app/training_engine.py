"""Training Engine — asynchronous model training with progress tracking.

Supports LightGBM, CatBoost, and Kronos fine-tune.
Publishes training progress to Redis Pub/Sub for SSE streaming.
Auto-evaluates new model vs old production model after training completes.

Per ADR-004:
- Decision 1: APScheduler for scheduling (in scheduler.py)
- Decision 2: Optuna for hyperparameter search
- Decision 3: MLflow for model registry
- Decision 6: CPU training (LightGBM/CatBoost are CPU-optimized)
"""

import asyncio
import json
import logging
import math
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from app.config import (
    REDIS_URL,
    TRAINING_NUM_THREADS,
    TRAINING_OUTPUT_DIR,
)
from app.mlflow_client import get_mlflow_client, log_model, register_model
from app.mlflow_client import MLFLOW_MODE  # M04: auto-deploy 仅在 live MLflow 下允许
from app.schemas import (
    JobStatus,
    ModelType,
    TrainingJob,
    TrainingMetrics,
    TrainingParams,
)

logger = logging.getLogger("training-service.engine")

# ── Thread pool for CPU-bound training ──
_executor = ThreadPoolExecutor(max_workers=2)  # Max 2 concurrent trainings

# ── In-memory job store (backed by PostgreSQL in production) ──
_jobs: Dict[str, TrainingJob] = {}
_job_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# Redis Pub/Sub helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _publish_progress(job_id: str, event_type: str, data: Dict[str, Any]):
    """Publish a training progress event to Redis Pub/Sub (with 3s timeout)."""
    try:
        import redis.asyncio as redis
        r = redis.from_url(REDIS_URL, socket_connect_timeout=3)
        payload = json.dumps({"type": event_type, **data}, default=str)
        await asyncio.wait_for(r.publish(f"training:{job_id}", payload), timeout=5.0)
        await asyncio.wait_for(r.close(), timeout=2.0)
    except (Exception, asyncio.TimeoutError):
        pass  # Redis is non-critical, silent fail


# ═══════════════════════════════════════════════════════════════════════════
# Job management
# ═══════════════════════════════════════════════════════════════════════════

async def _save_job(job: TrainingJob):
    """Persist job to in-memory store and PostgreSQL."""
    with _job_lock:
        _jobs[job.job_id] = job

    # Persist to PostgreSQL
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_text(
                    "INSERT INTO training_jobs (job_id, model_type, status, params, "
                    "best_params, metrics, final_metrics, model_uri, run_id, "
                    "experiment_id, created_by, created_at, started_at, completed_at, "
                    "error_message) VALUES ("
                    ":job_id, :model_type, :status, :params, :best_params, :metrics, "
                    ":final_metrics, :model_uri, :run_id, :experiment_id, :created_by, "
                    ":created_at, :started_at, :completed_at, :error_message"
                    ") ON CONFLICT (job_id) DO UPDATE SET "
                    "status=:status, best_params=:best_params, metrics=:metrics, "
                    "final_metrics=:final_metrics, model_uri=:model_uri, "
                    "run_id=:run_id, experiment_id=:experiment_id, "
                    "started_at=:started_at, completed_at=:completed_at, "
                    "error_message=:error_message"
                ),
                {
                    "job_id": job.job_id,
                    "model_type": job.model_type.value,
                    "status": job.status.value,
                    "params": json.dumps(job.params.model_dump(), default=str),
                    "best_params": json.dumps(job.best_params, default=str) if job.best_params else None,
                    "metrics": json.dumps([m.model_dump() for m in job.metrics], default=str),
                    "final_metrics": json.dumps(job.final_metrics.model_dump(), default=str) if job.final_metrics else None,
                    "model_uri": job.model_uri,
                    "run_id": job.run_id,
                    "experiment_id": job.experiment_id,
                    "created_by": job.created_by,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                },
            )
            await db.commit()
    except Exception as e:
        logger.warning("Failed to persist job to PostgreSQL: %s", e)


async def _load_jobs_from_db():
    """Restore in-memory job store from PostgreSQL on startup."""
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM training_jobs ORDER BY created_at DESC LIMIT 100")
            )
            rows = result.fetchall()
            with _job_lock:
                for row in rows:
                    d = dict(row._mapping)
                    job = TrainingJob(
                        job_id=d["job_id"],
                        model_type=ModelType(d["model_type"]),
                        status=JobStatus(d["status"]),
                        params=TrainingParams(**d["params"]) if isinstance(d["params"], dict) else TrainingParams(**json.loads(d["params"])),
                        best_params=d["best_params"] if isinstance(d["best_params"], dict) else (json.loads(d["best_params"]) if d["best_params"] else None),
                        metrics=[TrainingMetrics(**m) for m in (d["metrics"] if isinstance(d["metrics"], list) else json.loads(d["metrics"] or "[]"))],
                        final_metrics=TrainingMetrics(**d["final_metrics"]) if d["final_metrics"] else None,
                        model_uri=d["model_uri"],
                        run_id=d["run_id"],
                        experiment_id=d["experiment_id"],
                        created_by=d["created_by"] or "unknown",
                        created_at=d["created_at"],
                        started_at=d["started_at"],
                        completed_at=d["completed_at"],
                        error_message=d["error_message"],
                    )
                    _jobs[job.job_id] = job
            logger.info("Loaded %d jobs from PostgreSQL", len(rows))
    except Exception as e:
        logger.warning("Failed to load jobs from PostgreSQL: %s", e)


def get_job(job_id: str) -> Optional[TrainingJob]:
    """Get a training job by ID."""
    return _jobs.get(job_id)


def list_jobs(
    model_type: Optional[str] = None,
    status: Optional[str] = None,
    created_by: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[TrainingJob]:
    """List training jobs with optional filters."""
    jobs = list(_jobs.values())
    if model_type:
        jobs = [j for j in jobs if j.model_type.value == model_type]
    if status:
        jobs = [j for j in jobs if j.status.value == status]
    if created_by:
        jobs = [j for j in jobs if j.created_by == created_by]
    if start_date:
        sd = datetime.fromisoformat(start_date)
        jobs = [j for j in jobs if j.created_at >= sd]
    if end_date:
        ed = datetime.fromisoformat(end_date)
        jobs = [j for j in jobs if j.created_at <= ed]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)


async def check_active_job(model_type: str) -> Optional[TrainingJob]:
    """Check if there is already an active job of the same model type."""
    active_statuses = {JobStatus.PENDING, JobStatus.PREPARING, JobStatus.RUNNING, JobStatus.EVALUATING}
    for job in _jobs.values():
        if job.model_type.value == model_type and job.status in active_statuses:
            return job
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Training execution (runs in thread pool)
# ═══════════════════════════════════════════════════════════════════════════

def _group_split_masks(train_df: pd.DataFrame, test_size: float,
                       horizon: int) -> tuple:
    """M06 (audit-model-2026-06-22): time-based group split with purge + embargo.

    Returns (train_mask, val_mask) as boolean Series aligned with train_df.index.

    Guarantees (with a hard assertion):
      - No date appears in both train and val (no cross-sectional leakage).
      - A `horizon`-day embargo gap is purged between train end and val start,
        so sliding-window labels (lookback=90, overlap 89/90) cannot span the
        split — otherwise val labels are near-copies of train labels and IC is
        severely inflated.

    Original code split by date but let same-day samples of different stocks
    fall into both sets, with no gap → train IC was meaningless.
    """
    dates = sorted(train_df["date"].unique())
    if len(dates) < 4:
        raise ValueError(f"M06 group split: too few unique dates ({len(dates)})")
    split_idx = int(len(dates) * (1 - test_size))
    split_idx = max(1, min(split_idx, len(dates) - 2))
    split_date = dates[split_idx]
    # embargo: val 起点在 split 之后再隔 horizon 个交易日, purge 掉标签重叠区间
    embargo_idx = min(split_idx + max(horizon, 1), len(dates) - 1)
    val_start_date = dates[embargo_idx]
    train_mask = train_df["date"] < split_date
    val_mask = train_df["date"] >= val_start_date

    train_dates = set(train_df.loc[train_mask, "date"].unique())
    val_dates = set(train_df.loc[val_mask, "date"].unique())
    overlap = train_dates & val_dates
    if overlap:
        raise RuntimeError(
            f"M06 group split 断言失败: train/val 存在 {len(overlap)} 个重叠日期, "
            f"示例: {sorted(overlap)[:5]}. 横截面泄露必须修复."
        )
    return train_mask, val_mask


def _build_features_from_kline(
    df_ohlcv: pd.DataFrame,
    lookback: int = 90,
    predict: int = 10,
    sym: str = "000001",
) -> pd.DataFrame:
    """Compute model features from OHLCV history using existing scoring functions.

    Mirrors the feature engineering in Kronos/tools/train_lgbm_ranker.py.

    M14: `sym` is the stock code of df_ohlcv; passed to score_fundamental(sym)
    so fund_score reflects THIS stock's fundamentals (not a hardcoded 000001
    constant for the entire sample). Default kept 000001 only for legacy
    callers without a symbol context; production caller (training_engine train)
    always passes the real sym.
    """
    try:
        from webui.services.screener_service import score_five_factor, score_fundamental
        from webui.services.advanced_models import (
            score_money_flow, score_mean_reversion,
            score_trend_strength, score_reversal, score_liquidity,
        )
    except ImportError:
        logger.warning("Kronos scoring functions not available — using stub features")
        return pd.DataFrame()

    if len(df_ohlcv) < lookback + predict + 30:
        return pd.DataFrame()

    windows = len(df_ohlcv) - lookback - predict
    if windows <= 0:
        return pd.DataFrame()

    step = max(1, windows // 500)
    sample_indices = list(range(0, windows, step))[:500]

    rows = []
    features_cols = ["open", "high", "low", "close", "vol", "amt"]

    for i in sample_indices:
        context = df_ohlcv.iloc[i:i + lookback]
        future = df_ohlcv.iloc[i + lookback:i + lookback + predict]
        trade_date = str(context.index[-1])[:10]

        if len(context) < lookback:
            continue

        kline_df = context[features_cols].rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "vol": "volume", "amt": "amount",
        }).copy()

        try:
            ff = score_five_factor(kline_df)
            fund = score_fundamental(sym)
            mf = score_money_flow(kline_df)
            mr = score_mean_reversion(kline_df)
            ts_ = score_trend_strength(kline_df)
            rev = score_reversal(kline_df)
            liq = score_liquidity(kline_df)
        except Exception:
            continue

        base_price = future["close"].iloc[0]
        rets = {}
        for h in [5, 10, 20, 30]:
            if h <= len(future) and base_price > 0:
                target_price = future["close"].iloc[min(h - 1, len(future) - 1)]
                rets[h] = (target_price / base_price - 1) * 100
            else:
                rets[h] = np.nan

        five_factor_norm = ff["score"] / 25 * 10

        row = {
            "date": trade_date,
            "momentum": ff["momentum"],
            "volume_factor": ff["volume_factor"],
            "technical": ff["technical"],
            "quality": ff["quality"],
            "risk": ff["risk"],
            "five_factor_norm": five_factor_norm,
            "money_flow_score": mf["score"],
            "mean_reversion_score": mr["score"],
            "trend_strength_score": ts_["score"],
            "reversal_score": rev["score"],
            "liquidity_score": liq["score"],
            "fund_score": fund,
            "buy_vote_ratio": sum([
                five_factor_norm > 6, mf["score"] > 6, mr["score"] > 6,
                ts_["score"] > 6, rev["score"] > 6, liq["score"] > 6,
                fund > 6, False, False, False, False, False,
            ]) / 12,
            "price": context["close"].iloc[-1],
            "ret_5d": rets.get(5, np.nan),
            "ret_10d": rets.get(10, np.nan),
            "ret_20d": rets.get(20, np.nan),
            "ret_30d": rets.get(30, np.nan),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def _train_lightgbm_sync(
    df: pd.DataFrame,
    params: TrainingParams,
    progress_callback: Callable[[TrainingMetrics], None],
) -> Dict[str, Any]:
    """Synchronous LightGBM LambdaRank training with fixed hyperparameters.

    Uses Optuna for hyperparameter search when n_trials > 1.
    """
    import lightgbm as lgb

    feature_cols = [
        "momentum", "volume_factor", "technical", "quality", "risk",
        "five_factor_norm",
        "money_flow_score", "mean_reversion_score",
        "trend_strength_score", "reversal_score", "liquidity_score",
        "fund_score", "buy_vote_ratio",
    ]

    target = f"ret_{params.horizon}d"
    valid = df[target].notna()
    train_df = df[valid].copy()

    if len(train_df) < 100:
        raise ValueError(f"Not enough valid samples: {len(train_df)}")

    # M06 (audit-model-2026-06-22): group split with purge/embargo.
    # val 必须是 train 之后连续日期段 + horizon 天 embargo gap, 防止 sliding window
    # 跨 train/val 边界 (原实现同日样本横跨两集 + 无 gap, val 标签与 train 高度相关,
    # IC 严重高估). 详见 _group_split_masks docstring.
    train_mask, val_mask = _group_split_masks(train_df, params.test_size, params.horizon)

    X_train = train_df.loc[train_mask, feature_cols].fillna(0)
    y_train_raw = train_df.loc[train_mask, target]
    X_val = train_df.loc[val_mask, feature_cols].fillna(0)
    y_val_raw = train_df.loc[val_mask, target]

    # Binarize: positive return = 1
    y_train = (y_train_raw > 0).astype(int)
    y_val = (y_val_raw > 0).astype(int)

    # Base params (always defined)
    base_params = {
        "objective": "binary",
        "metric": "auc",
        "boosting_type": "gbdt",
        "num_leaves": params.num_leaves or 63,
        "learning_rate": params.learning_rate or 0.03,
        "feature_fraction": params.colsample_bytree or 0.7,
        "bagging_fraction": params.subsample or 0.7,
        "bagging_freq": 10,
        "min_data_in_leaf": 100,
        "verbose": -1,
        "num_threads": TRAINING_NUM_THREADS,
        "seed": 42,
        "is_unbalance": True,
    }
    if params.max_depth is not None:
        base_params["max_depth"] = params.max_depth

    # Optuna hyperparameter search
    best_params = {}
    best_score = -float("inf")
    use_optuna = params.n_trials > 1

    if use_optuna:
        try:
            import optuna

            def _objective(trial):
                trial_params = {
                    **base_params,
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                    "num_leaves": trial.suggest_int("num_leaves", 15, 127),
                    "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
                    "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
                    "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 200),
                }
                if params.max_depth is not None:
                    trial_params["max_depth"] = params.max_depth
                else:
                    trial_params["max_depth"] = trial.suggest_int("max_depth", 3, 15)

                dtrain = lgb.Dataset(X_train, label=y_train)
                dval = lgb.Dataset(X_val, label=y_val)
                model = lgb.train(
                    trial_params, dtrain,
                    num_boost_round=200,
                    valid_sets=[dval],
                    callbacks=[
                        lgb.early_stopping(params.early_stopping_rounds),
                        lgb.log_evaluation(0),
                    ],
                )
                y_pred = model.predict(X_val)
                from scipy import stats
                ic, _ = stats.spearmanr(y_pred, y_val)
                return 0.0 if np.isnan(ic) else float(ic)

            study = optuna.create_study(direction="maximize")
            n_trials = min(params.n_trials, 20)
            study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)

            # Train final model with best params
            best_trial_params = {**base_params, **study.best_params}
            dtrain = lgb.Dataset(X_train, label=y_train)
            dval = lgb.Dataset(X_val, label=y_val)
            best_model = lgb.train(
                best_trial_params, dtrain,
                num_boost_round=200,
                valid_sets=[dval],
                callbacks=[lgb.early_stopping(params.early_stopping_rounds), lgb.log_evaluation(0)],
            )
            best_params = {
                "learning_rate": best_trial_params["learning_rate"],
                "num_leaves": best_trial_params["num_leaves"],
                "max_depth": best_trial_params.get("max_depth", -1),
                "feature_fraction": best_trial_params["feature_fraction"],
                "best_iteration": best_model.current_iteration(),
                "best_score": study.best_value,
                "optuna_trials": n_trials,
            }

            # Single metric for progress
            y_pred = best_model.predict(X_val)
            from scipy import stats
            ic, _ = stats.spearmanr(y_pred, y_val)
            ic = 0.0 if np.isnan(ic) else float(ic)
            metrics = TrainingMetrics(
                trial=1, epoch=best_model.current_iteration(),
                train_loss=0.0, valid_loss=0.0, best_valid_loss=0.0,
                ic=round(ic, 4), icir=round(ic / max(np.std(y_pred), 0.001), 4),
                feature_importance={}, elapsed_seconds=0.0,
            )
            if progress_callback:
                progress_callback(metrics)

            model = best_model
        except ImportError:
            use_optuna = False
            logger.warning("Optuna not installed — using manual trial loop")

    if not use_optuna:
        t0 = time.time()

        # Manual trial loop (Optuna not available or n_trials=1)
        n_effective_trials = min(params.n_trials, 10)
        params_dict = base_params

        for trial_num in range(max(1, n_effective_trials)):
            trial_params = {**params_dict}
            if n_effective_trials > 1:
                trial_params["learning_rate"] = params_dict["learning_rate"] * (0.5 + 0.5 * (trial_num + 1) / n_effective_trials)
                trial_params["num_leaves"] = max(15, params_dict["num_leaves"] - trial_num * 5)

                dtrain = lgb.Dataset(X_train, label=y_train)
                dval = lgb.Dataset(X_val, label=y_val)

                model = lgb.train(
                    trial_params,
                    dtrain,
                    num_boost_round=200,
                    valid_sets=[dval],
                    callbacks=[
                        lgb.early_stopping(params.early_stopping_rounds),
                        lgb.log_evaluation(0),
                    ],
                )

                # Evaluate
                y_pred = model.predict(X_val)
                from scipy import stats
                ic, _ = stats.spearmanr(y_pred, y_val)
                ic = 0.0 if np.isnan(ic) else float(ic)

                valid_mask = y_val.notna()
                if valid_mask.sum() >= 20:
                    pred_std = np.std(y_pred[valid_mask]) if np.std(y_pred[valid_mask]) > 0 else 1
                    icir = ic / pred_std
                else:
                    icir = 0.0

                best_score_auc = model.best_score["valid_0"]["auc"]
                train_loss = 1.0 - best_score_auc
                valid_loss = 1.0 - best_score_auc

                # Feature importance
                importance = model.feature_importance(importance_type="gain")
                imp_dict = {
                    feature_cols[i]: float(importance[i])
                    for i in np.argsort(importance)[::-1][:10]
                    if i < len(feature_cols)
                }

                elapsed = time.time() - t0

                metrics = TrainingMetrics(
                    trial=trial_num + 1,
                    epoch=model.current_iteration(),
                    train_loss=round(train_loss, 4),
                    valid_loss=round(valid_loss, 4),
                    best_valid_loss=round(valid_loss, 4),
                    ic=round(ic, 4),
                    icir=round(icir, 4),
                    feature_importance=imp_dict,
                    elapsed_seconds=round(elapsed, 1),
                )

                if progress_callback:
                    progress_callback(metrics)

                if ic > best_score:
                    best_score = ic
                    best_params = {
                        "learning_rate": trial_params["learning_rate"],
                        "num_leaves": trial_params["num_leaves"],
                        "max_depth": trial_params.get("max_depth", -1),
                        "feature_fraction": trial_params.get("feature_fraction", 0.7),
                        "best_iteration": model.current_iteration(),
                        "best_score": best_score_auc,
                    }
                    best_model = model

    # Save model
    model_dir = os.path.join(TRAINING_OUTPUT_DIR, "lgbm_ranker")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"model_{params.horizon}d.txt")
    best_model.save_model(model_path)

    return {
        "model": best_model,
        "model_path": model_path,
        "feature_cols": feature_cols,
        "best_params": best_params,
        "n_samples": len(train_df),
        "n_features": len(feature_cols),
    }


def _train_catboost_sync(
    df: pd.DataFrame,
    params: TrainingParams,
    progress_callback: Callable[[TrainingMetrics], None],
) -> Dict[str, Any]:
    """Synchronous CatBoost ranking training."""
    feature_cols = [
        "momentum", "volume_factor", "technical", "quality", "risk",
        "five_factor_norm",
        "money_flow_score", "mean_reversion_score",
        "trend_strength_score", "reversal_score", "liquidity_score",
        "fund_score", "buy_vote_ratio",
    ]

    target = f"ret_{params.horizon}d"
    valid = df[target].notna()
    train_df = df[valid].copy()

    if len(train_df) < 100:
        raise ValueError(f"Not enough valid samples: {len(train_df)}")

    # M06: group split with purge/embargo (同 lightgbm, 详见 _group_split_masks).
    train_mask, val_mask = _group_split_masks(train_df, params.test_size, params.horizon)

    X_train = train_df.loc[train_mask, feature_cols].fillna(0).values.astype(np.float32)
    y_train = train_df.loc[train_mask, target].values.astype(np.float32)
    X_val = train_df.loc[val_mask, feature_cols].fillna(0).values.astype(np.float32)
    y_val = train_df.loc[val_mask, target].values.astype(np.float32)

    t0 = time.time()

    try:
        from catboost import CatBoostRegressor
    except ImportError:
        # Fallback to LightGBM regression if CatBoost not installed
        logger.warning("CatBoost not installed, using LightGBM fallback")
        import lightgbm as lgb

        model = lgb.LGBMRegressor(
            n_estimators=200,
            learning_rate=params.learning_rate or 0.05,
            max_depth=params.max_depth or 6,
            num_leaves=params.num_leaves or 31,
            subsample=params.subsample or 0.8,
            colsample_bytree=params.colsample_bytree or 0.8,
            n_jobs=TRAINING_NUM_THREADS,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)

        # Report as CatBoost
        n_trees = model.booster_.num_trees()
        importance = model.feature_importances_
    else:
        model = CatBoostRegressor(
            iterations=200,
            learning_rate=params.learning_rate or 0.05,
            depth=params.max_depth or 6,
            loss_function="RMSE",
            random_seed=42,
            thread_count=TRAINING_NUM_THREADS,
            verbose=False,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        n_trees = model.tree_count_
        importance = model.get_feature_importance()

    # Metrics
    from scipy import stats
    ic_raw = np.corrcoef(y_pred, y_val)[0, 1]
    ic = 0.0 if np.isnan(ic_raw) else float(ic_raw)
    icir = ic / max(float(np.std(y_pred)), 1e-6)
    train_loss = float(np.sqrt(((y_pred - y_val) ** 2).mean()))

    imp_dict = {
        feature_cols[i]: float(importance[i])
        for i in np.argsort(importance)[::-1][:10]
        if i < len(feature_cols)
    }

    elapsed = time.time() - t0

    metrics = TrainingMetrics(
        trial=1,
        epoch=n_trees,
        train_loss=round(train_loss, 4),
        valid_loss=round(train_loss, 4),
        best_valid_loss=round(train_loss, 4),
        ic=round(ic, 4),
        icir=round(icir, 4),
        feature_importance=imp_dict,
        elapsed_seconds=round(elapsed, 1),
    )

    if progress_callback:
        progress_callback(metrics)

    # Save model
    model_dir = os.path.join(TRAINING_OUTPUT_DIR, "catboost_ranker")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"model_{params.horizon}d")
    if hasattr(model, "save_model"):
        model.save_model(model_path + ".cbm")
    else:
        import joblib
        joblib.dump(model, model_path + ".pkl")

    return {
        "model": model,
        "model_path": model_path,
        "feature_cols": feature_cols,
        "best_params": {
            "iterations": n_trees,
            "learning_rate": params.learning_rate or 0.05,
            "depth": params.max_depth or 6,
        },
        "n_samples": len(train_df),
        "n_features": len(feature_cols),
    }


def _train_kronos_sync(
    params: TrainingParams,
    progress_callback: Callable[[TrainingMetrics], None],
) -> Dict[str, Any]:
    """Kronos fine-tune training — DISABLED (M04, audit-model-2026-06-22).

    Kronos 自研 fine-tune 未实现: 原实现是 time.sleep(0.5) + 假 loss 数列的
    placeholder, 产出的"模型"会被 auto-deploy 盲目上线. 在 GPU 训练链路 +
    真实数据集就绪前, 该分支必须显式失败, 不得静默产出假指标.

    生产 prediction-service 当前基于公开 Kronos-mini 托管推理 (见 ADR-005 /
    M05), 自研训练另立项.
    """
    raise NotImplementedError(
        "Kronos fine-tune training is not implemented (M04). "
        "原实现为 placeholder (time.sleep + 假 loss), 已禁用. "
        "生产 prediction-service 使用公开 Kronos-mini 托管推理, "
        "自研训练需 GPU 集群 + 真实数据集另立项."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main training entry point
# ═══════════════════════════════════════════════════════════════════════════

async def run_training(
    params: TrainingParams,
    created_by: str,
    auto_deploy: bool = False,
) -> str:
    """Start an asynchronous training job.

    Returns job_id immediately. Training runs in background thread pool.
    Progress is published to Redis Pub/Sub channel `training:{job_id}`.

    Args:
        params: Training parameters
        created_by: Username who triggered the training
        auto_deploy: Auto-deploy if new model beats old production model

    Returns:
        job_id: UUID for tracking
    """
    # Check for conflicts
    active = await check_active_job(params.model_type.value)
    if active:
        raise ValueError(
            f"Training already running: {active.job_id} ({active.model_type.value}, status={active.status.value})"
        )

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    job = TrainingJob(
        job_id=job_id,
        model_type=params.model_type,
        status=JobStatus.PENDING,
        params=params,
        created_by=created_by,
        created_at=now,
    )

    await _save_job(job)
    logger.info("Training job created: %s (model=%s)", job_id, params.model_type.value)

    # Run training in background via asyncio.create_task (CPU-bound work uses run_in_executor)
    asyncio.create_task(_execute_training(job_id, params, auto_deploy))

    return job_id


async def _execute_training(job_id: str, params: TrainingParams, auto_deploy: bool):
    """Background training execution — runs in thread pool event loop."""
    try:
        # ── Status: PREPARING ──
        await _update_job_status(job_id, JobStatus.PREPARING)
        await _publish_progress(job_id, "status", {"status": "preparing", "message": "准备训练数据..."})

        # ── Prepare data ──
        df = _prepare_training_data(params)
        if df is None or df.empty:
            raise ValueError("No training data available")

        # ── Status: RUNNING ──
        await _update_job_status(job_id, JobStatus.RUNNING)
        await _publish_progress(job_id, "status", {"status": "running", "message": f"开始训练 ({params.model_type.value})..."})

        # ── Progress callback ──
        # 捕获主事件循环，供线程池中的 on_metric 回调安全调度协程
        _main_loop = asyncio.get_event_loop()

        def on_metric(metric: TrainingMetrics):
            # 从线程池线程安全调度协程到主事件循环
            _main_loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_on_training_metric(job_id, metric))
            )

        # ── Train ──
        train_fn = {
            "lightgbm": _train_lightgbm_sync,
            "catboost": _train_catboost_sync,
            "kronos_finetune": _train_kronos_sync,
        }.get(params.model_type.value)

        if train_fn is None:
            raise ValueError(f"Unknown model type: {params.model_type.value}")

        # Run in thread executor since training is CPU-bound sync code
        result = await _main_loop.run_in_executor(
            None,
            lambda: train_fn(df, params, on_metric)
        )

        # ── Status: EVALUATING ──
        await _update_job_status(job_id, JobStatus.EVALUATING)
        await _publish_progress(job_id, "evaluating", {"status": "evaluating", "message": "正在对比新旧模型回测表现..."})

        # ── MLflow logging ──
        mlflow_client = get_mlflow_client()
        model_name = f"{params.model_type.value}-ranker"
        experiment_name = f"training-{params.model_type.value}"

        run_id = mlflow_client.create_run(
            experiment_name=experiment_name,
            run_name=f"job-{job_id}",
        )

        # Get final metrics from the last callback
        final_metrics = None
        with _job_lock:
            job = _jobs.get(job_id)
            if job and job.metrics:
                final_metrics = job.metrics[-1]

        ml_metrics = {
            "ic": final_metrics.ic or 0 if final_metrics else 0,
            "icir": final_metrics.icir or 0 if final_metrics else 0,
            "train_loss": final_metrics.train_loss if final_metrics else 0,
            "valid_loss": final_metrics.valid_loss if final_metrics else 0,
            "n_samples": result.get("n_samples", 0),
            "n_features": result.get("n_features", 0),
        }

        log_model(mlflow_client, run_id, result.get("model"), params.model_dump(), ml_metrics, result.get("model_path"))

        # Register model
        version = register_model(mlflow_client, run_id, model_name)
        model_uri = f"models:/{model_name}/{version}"

        with _job_lock:
            job = _jobs.get(job_id)
            if job:
                job.model_uri = model_uri
                job.run_id = run_id
                job.experiment_id = experiment_name
                job.best_params = result.get("best_params")

        # ── Auto-evaluate vs old model ──
        comparison = await _evaluate_vs_production(job_id, params, mlflow_client)

        # ── Auto-deploy if applicable ──
        # M04: auto-deploy 仅在 live MLflow 模式下允许. mock MLflow + 合成数据下
        # IC≈1.0, comparison 必判 new_better, 会在假数据上盲目上线模型.
        if auto_deploy and MLFLOW_MODE != "live":
            logger.warning(
                "auto_deploy suppressed: MLFLOW_MODE=%s (非 live). "
                "mock MLflow 下 IC 不可信, 禁止自动上线 (M04).", MLFLOW_MODE)
            auto_deploy = False
            await _publish_progress(job_id, "auto_deploy_skipped", {
                "message": "auto-deploy 已跳过: 非 live MLflow 模式 (M04 安全门)",
            })
        if auto_deploy and comparison and comparison.get("verdict") == "new_better":
            mlflow_client.set_production_model(model_name, version)
            # Save model record to registry
            await _save_model_record(job_id, model_name, version, params, ml_metrics, mlflow_client, run_id)
            await _publish_progress(job_id, "auto_deploy", {
                "message": f"自动部署: {model_name} v{version} 优于旧模型，已上线",
            })

        # ── Status: COMPLETED ──
        await _update_job_status(job_id, JobStatus.COMPLETED, final_metrics=final_metrics)
        await _publish_progress(job_id, "complete", {
            "job_id": job_id,
            "status": "completed",
            "final_metrics": final_metrics.model_dump() if final_metrics else None,
            "model_uri": model_uri,
        })

        logger.info("Training job completed: %s (model=%s v%d)", job_id, model_name, version)

    except Exception as e:
        logger.error("Training job failed: %s — %s", job_id, str(e))
        logger.error(traceback.format_exc())

        await _update_job_status(job_id, JobStatus.FAILED, error_message=str(e))
        await _publish_progress(job_id, "error", {
            "job_id": job_id,
            "status": "failed",
            "error_message": str(e),
        })


async def _update_job_status(
    job_id: str,
    status: JobStatus,
    final_metrics: Optional[TrainingMetrics] = None,
    error_message: Optional[str] = None,
):
    """Update job status in memory and PostgreSQL."""
    job = None
    with _job_lock:
        job = _jobs.get(job_id)
        if job:
            job.status = status
            if status == JobStatus.RUNNING and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now(timezone.utc)
            if final_metrics:
                job.final_metrics = final_metrics
            if error_message:
                job.error_message = error_message
    # _save_job 内部有自己的 _job_lock，在锁外调用避免死锁
    if job:
        await _save_job(job)


async def _on_training_metric(job_id: str, metric: TrainingMetrics):
    """Handle a training metric callback — update job + publish to Redis."""
    with _job_lock:
        job = _jobs.get(job_id)
        if job:
            job.metrics.append(metric)

    await _publish_progress(job_id, "metric", metric.model_dump())


def _prepare_training_data(params: TrainingParams, allow_synthetic: bool = False) -> pd.DataFrame:
    """Prepare training data by loading from Kronos data store and building features.

    M04 (audit-model-2026-06-22): 找不到真实数据时 **抛异常**, 不再静默 fallback
    到合成数据. 原实现会让 auto-deploy 在 np.random 造的合成数据 (label 与特征
    完全相关, IC≈1.0) 上盲目上线模型. `allow_synthetic=True` 仅用于显式 dev/test
    入口, 主训练路径禁止.
    """
    from kronos.finetune.config import Config
    import pickle

    config = Config()
    data_path = f"{config.dataset_path}/train_data.pkl"

    if not os.path.exists(data_path):
        if allow_synthetic:
            logger.warning("Training data not found: %s — using synthetic (dev/test only)", data_path)
            return _generate_synthetic_data(params)
        raise FileNotFoundError(
            f"Training data not found: {data_path} (M04). "
            "主训练路径禁止 fallback 合成数据 (IC≈1.0 会让 auto-deploy 盲目上线). "
            "请准备真实数据集, 或在 dev/test 入口显式传 allow_synthetic=True."
        )

    with open(data_path, "rb") as f:
        train_data = pickle.load(f)

    max_stocks = min(len(train_data), 200)
    symbols = list(train_data.keys())[:max_stocks]

    all_dfs = []
    for sym in symbols:
        df_stock = train_data[sym]
        features = _build_features_from_kline(
            df_stock,
            lookback=params.lookback,
            predict=params.horizon,
            sym=sym,
        )
        if len(features) > 0:
            features["code"] = sym
            all_dfs.append(features)

    if not all_dfs:
        if allow_synthetic:
            logger.warning("No valid features extracted — using synthetic (dev/test only)")
            return _generate_synthetic_data(params)
        raise ValueError(
            "No valid features extracted from training data (M04). "
            "主训练路径禁止 fallback 合成数据."
        )

    result = pd.concat(all_dfs, ignore_index=True)
    logger.info("Training data: %d samples, %d stocks", len(result), len(all_dfs))
    return result


def _generate_synthetic_data(params: TrainingParams) -> pd.DataFrame:
    """Generate synthetic training data for development/testing."""
    np.random.seed(42)
    n_samples = 2000

    data = {
        "date": [f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n_samples)],
        "momentum": np.random.normal(5, 2, n_samples),
        "volume_factor": np.random.normal(5, 2, n_samples),
        "technical": np.random.normal(5, 2, n_samples),
        "quality": np.random.normal(5, 2, n_samples),
        "risk": np.random.normal(5, 2, n_samples),
        "five_factor_norm": np.random.normal(6, 2, n_samples),
        "money_flow_score": np.random.normal(5, 2, n_samples),
        "mean_reversion_score": np.random.normal(5, 2, n_samples),
        "trend_strength_score": np.random.normal(5, 2, n_samples),
        "reversal_score": np.random.normal(5, 2, n_samples),
        "liquidity_score": np.random.normal(5, 2, n_samples),
        "fund_score": np.random.normal(5, 2, n_samples),
        "buy_vote_ratio": np.random.uniform(0, 1, n_samples),
    }

    # Synthetic returns correlated with features
    signal = (
        data["momentum"] * 0.15
        + data["technical"] * 0.2
        + data["quality"] * 0.1
        + data["five_factor_norm"] * 0.2
        + data["trend_strength_score"] * 0.1
    )
    noise = np.random.normal(0, 3, n_samples)

    for h in [5, 10, 20, 30]:
        col = f"ret_{h}d"
        data[col] = signal * (h / 20) + noise + np.random.normal(0, 1, n_samples)

    df = pd.DataFrame(data)
    logger.info("Generated synthetic training data: %d samples", n_samples)
    return df


async def _evaluate_vs_production(
    job_id: str,
    params: TrainingParams,
    mlflow_client,
) -> Optional[Dict]:
    """Compare new model metrics against current production model."""
    model_name = f"{params.model_type.value}-ranker"
    production = mlflow_client.get_production_model(model_name)

    if not production:
        logger.info("No production model for %s — skipping comparison", model_name)
        return {"verdict": "new_better", "message": "No old model to compare"}

    # Get new model metrics
    with _job_lock:
        job = _jobs.get(job_id)

    if not job or not job.metrics:
        return None

    new_metrics = job.metrics[-1]
    new_ic = new_metrics.ic or 0
    new_icir = new_metrics.icir or 0

    # Get old model metrics (from its run)
    old_run = mlflow_client.get_run(production.get("run_id", ""))
    old_metrics = old_run.get("metrics", {}) if old_run else {}
    old_ic = old_metrics.get("ic", 0)
    old_icir = old_metrics.get("icir", 0)

    ic_delta_pct = ((new_ic - old_ic) / abs(old_ic) * 100) if old_ic != 0 else 0
    icir_delta_pct = ((new_icir - old_icir) / abs(old_icir) * 100) if old_icir != 0 else 0

    # M12 (audit-model-2026-06-22): 原 2% 点估计阈值在 mock MLflow + 合成数据下 IC≈1.0,
    # 容易误判 new_better 触发 auto-deploy. 真正的统计显著性检验 (Diebold-Mariano /
    # bootstrap IC 置信区间) 需要 per-batch IC 序列, 当前 job 只存 final_metrics 单点 —
    # 故本实现: (1) 非 live MLflow 已由 _execute_training 的 auto-deploy 安全门拦截 (M04);
    # (2) 加最小信号门 (|ic_delta_pct| < 5% 视为 inconclusive, 避免边界噪声触发部署);
    # (3) 显式标注 verdict 为点估计 (非 statistically significant), 待 per-batch IC 序列
    #     落库后升级为 bootstrap 检验 (TODO).
    logger.warning(
        "M12: _evaluate_vs_production 当前为点估计阈值 (非 statistically significant), "
        "需 per-batch IC 序列才能做 bootstrap/Diebold-Mariano 检验. "
        "auto-deploy 已由 M04 live-MLflow 安全门兜底."
    )
    verdict = "inconclusive"
    MIN_SIGNAL_PCT = 5  # M12: 最小信号门, 低于此视为噪声 (原 2% 太松)
    if abs(ic_delta_pct) >= MIN_SIGNAL_PCT and icir_delta_pct > 0:
        verdict = "new_better"
    elif ic_delta_pct <= -MIN_SIGNAL_PCT:
        verdict = "old_better"

    comparison = {
        "verdict": verdict,
        "new_ic": new_ic,
        "old_ic": old_ic,
        "new_icir": new_icir,
        "old_icir": old_icir,
        "ic_delta_pct": round(ic_delta_pct, 1),
        "icir_delta_pct": round(icir_delta_pct, 1),
        # M12: 显式标注 — 当前 verdict 基于点估计, 非 statistically significant.
        "significance_method": "point_estimate_threshold (NOT statistically significant)",
        "significance_todo": "upgrade to bootstrap IC CI / Diebold-Mariano once per-batch IC series persisted",
        "min_signal_pct": MIN_SIGNAL_PCT,
    }

    await _publish_progress(job_id, "comparison", comparison)
    return comparison


async def _save_model_record(
    job_id: str,
    model_name: str,
    version: int,
    params: TrainingParams,
    metrics: Dict[str, float],
    mlflow_client,
    run_id: str,
):
    """Save model record to model_registry table in PostgreSQL."""
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        import uuid as uuid_mod

        model_id = f"mdl-{uuid_mod.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        with _job_lock:
            job = _jobs.get(job_id)

        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_text(
                    "INSERT INTO model_registry (id, name, version, model_type, stage, "
                    "run_id, params, metrics, created_by, created_at) VALUES ("
                    ":id, :name, :version, :model_type, :stage, :run_id, :params, "
                    ":metrics, :created_by, :created_at)"
                ),
                {
                    "id": model_id,
                    "name": model_name,
                    "version": version,
                    "model_type": params.model_type.value,
                    "stage": "staging",
                    "run_id": run_id,
                    "params": json.dumps(params.model_dump(), default=str),
                    "metrics": json.dumps(metrics, default=str),
                    "created_by": job.created_by if job else "system",
                    "created_at": now,
                },
            )
            await db.commit()
            logger.info("Model record saved: %s %s v%d", model_id, model_name, version)
    except Exception as e:
        logger.warning("Failed to save model record: %s", e)
