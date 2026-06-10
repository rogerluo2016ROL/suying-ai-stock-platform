"""MLflow integration — tracking, model registry, stage management.

Supports two modes:
- "mock": In-memory dict store for local dev (no MLflow server required)
- "live": Real MLflow tracking server via MLFLOW_TRACKING_URI

Per ADR-004 Decision 3: MLflow Tracking + Model Registry for model versioning.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import MLFLOW_MODE, MLFLOW_TRACKING_URI, TRAINING_OUTPUT_DIR

logger = logging.getLogger("training-service.mlflow")


class MockMlflowClient:
    """In-memory mock of MLflow client for local development.

    Stores runs, models, and artifacts in memory dicts.
    Serializes to JSON files in TRAINING_OUTPUT_DIR for persistence across restarts.
    """

    def __init__(self, storage_dir: str = TRAINING_OUTPUT_DIR):
        self._storage_dir = Path(storage_dir) / "mlflow_mock"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, Dict] = {}
        self._models: Dict[str, List[Dict]] = {}  # name -> [versions]
        self._load()

    def _load(self):
        runs_file = self._storage_dir / "runs.json"
        models_file = self._storage_dir / "models.json"
        if runs_file.exists():
            self._runs = json.loads(runs_file.read_text())
        if models_file.exists():
            self._models = json.loads(models_file.read_text())

    def _save(self):
        (self._storage_dir / "runs.json").write_text(json.dumps(self._runs, indent=2, default=str))
        (self._storage_dir / "models.json").write_text(json.dumps(self._models, indent=2, default=str))

    def create_run(self, experiment_name: str, run_name: str) -> str:
        run_id = str(uuid.uuid4())
        self._runs[run_id] = {
            "run_id": run_id,
            "experiment_name": experiment_name,
            "run_name": run_name,
            "params": {},
            "metrics": {},
            "tags": {},
            "artifacts": {},
            "status": "RUNNING",
            "created_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info("Mock MLflow: created run %s (%s)", run_id, run_name)
        return run_id

    def log_params(self, run_id: str, params: Dict[str, Any]):
        if run_id in self._runs:
            self._runs[run_id]["params"].update(params)
            self._save()

    def log_metrics(self, run_id: str, metrics: Dict[str, float]):
        if run_id in self._runs:
            self._runs[run_id]["metrics"].update(metrics)
            self._save()

    def log_param(self, run_id: str, key: str, value: Any):
        if run_id in self._runs:
            self._runs[run_id]["params"][key] = value
            self._save()

    def log_metric(self, run_id: str, key: str, value: float):
        if run_id in self._runs:
            self._runs[run_id]["metrics"][key] = value
            self._save()

    def set_tag(self, run_id: str, key: str, value: str):
        if run_id in self._runs:
            self._runs[run_id]["tags"][key] = value
            self._save()

    def log_artifact(self, run_id: str, local_path: str, artifact_path: Optional[str] = None):
        if run_id in self._runs:
            art_name = artifact_path or os.path.basename(local_path)
            self._runs[run_id]["artifacts"][art_name] = local_path
            self._save()

    def end_run(self, run_id: str, status: str = "FINISHED"):
        if run_id in self._runs:
            self._runs[run_id]["status"] = status
            self._runs[run_id]["ended_at"] = datetime.now().isoformat()
            self._save()

    def register_model(self, run_id: str, model_name: str) -> int:
        """Register model from a run, return version number."""
        if model_name not in self._models:
            self._models[model_name] = []

        version = len(self._models[model_name]) + 1
        model_version = {
            "name": model_name,
            "version": version,
            "run_id": run_id,
            "stage": "none",
            "created_at": datetime.now().isoformat(),
            "description": "",
        }
        self._models[model_name].append(model_version)
        self._save()
        logger.info("Mock MLflow: registered %s v%d from run %s", model_name, version, run_id)
        return version

    def get_model_version(self, name: str, version: int) -> Optional[Dict]:
        versions = self._models.get(name, [])
        for v in versions:
            if v["version"] == version:
                return v
        return None

    def get_latest_version(self, name: str) -> Optional[Dict]:
        versions = self._models.get(name, [])
        return versions[-1] if versions else None

    def transition_model_version_stage(self, name: str, version: int, stage: str):
        mv = self.get_model_version(name, version)
        if mv:
            mv["stage"] = stage
            self._save()
            logger.info("Mock MLflow: %s v%d stage -> %s", name, version, stage)

    def get_production_model(self, name: str) -> Optional[Dict]:
        """Get current production version of a registered model."""
        versions = self._models.get(name, [])
        for v in reversed(versions):
            if v["stage"] == "production":
                return v
        return None

    def set_production_model(self, name: str, version: int):
        """Set a specific version to production (demote old production)."""
        versions = self._models.get(name, [])
        for v in versions:
            if v["stage"] == "production":
                v["stage"] = "archived"
        mv = self.get_model_version(name, version)
        if mv:
            mv["stage"] = "production"
            mv["deployed_at"] = datetime.now().isoformat()
            self._save()
            logger.info("Mock MLflow: set %s v%d as production", name, version)

    def list_models(self, name: Optional[str] = None) -> List[Dict]:
        result = []
        for model_name, versions in self._models.items():
            if name and model_name != name:
                continue
            for v in versions:
                run = self._runs.get(v.get("run_id", ""), {})
                result.append({
                    **v,
                    "params": run.get("params", {}),
                    "metrics": run.get("metrics", {}),
                })
        return sorted(result, key=lambda x: x["version"], reverse=True)

    def get_run(self, run_id: str) -> Optional[Dict]:
        return self._runs.get(run_id)

    def search_runs(self, experiment_name: Optional[str] = None) -> List[Dict]:
        runs = list(self._runs.values())
        if experiment_name:
            runs = [r for r in runs if r.get("experiment_name") == experiment_name]
        return sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True)


class LiveMlflowClient:
    """Real MLflow client wrapper using mlflow.tracking.MlflowClient."""

    def __init__(self, tracking_uri: str = MLFLOW_TRACKING_URI):
        import mlflow
        self._tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self._client = mlflow.tracking.MlflowClient(tracking_uri)
        logger.info("MLflow live client connected to %s", tracking_uri)

    def create_run(self, experiment_name: str, run_name: str) -> str:
        import mlflow
        mlflow.set_experiment(experiment_name)
        run = mlflow.start_run(run_name=run_name)
        return run.info.run_id

    def log_params(self, run_id: str, params: Dict[str, Any]):
        for k, v in params.items():
            self._client.log_param(run_id, k, v)

    def log_metrics(self, run_id: str, metrics: Dict[str, float]):
        for k, v in metrics.items():
            self._client.log_metric(run_id, k, v)

    def log_param(self, run_id: str, key: str, value: Any):
        self._client.log_param(run_id, key, value)

    def log_metric(self, run_id: str, key: str, value: float):
        self._client.log_metric(run_id, key, value)

    def set_tag(self, run_id: str, key: str, value: str):
        self._client.set_tag(run_id, key, value)

    def log_artifact(self, run_id: str, local_path: str, artifact_path: Optional[str] = None):
        self._client.log_artifact(run_id, local_path, artifact_path)

    def end_run(self, run_id: str, status: str = "FINISHED"):
        self._client.set_terminated(run_id, status)

    def register_model(self, run_id: str, model_name: str) -> int:
        result = self._client.create_model_version(
            name=model_name,
            source=f"runs:/{run_id}/model",
        )
        return result.version

    def get_model_version(self, name: str, version: int) -> Optional[Dict]:
        try:
            mv = self._client.get_model_version(name, version)
            return {
                "name": mv.name,
                "version": int(mv.version),
                "run_id": mv.run_id,
                "stage": mv.current_stage.lower(),
                "created_at": datetime.fromtimestamp(mv.creation_timestamp / 1000.0),
                "description": mv.description or "",
            }
        except Exception as e:
            logger.warning("MLflow get_model_version failed: %s", e)
            return None

    def get_latest_version(self, name: str) -> Optional[Dict]:
        try:
            versions = self._client.get_latest_versions(name)
            if versions:
                v = versions[0]
                return {
                    "name": v.name,
                    "version": int(v.version),
                    "run_id": v.run_id,
                    "stage": v.current_stage.lower(),
                    "created_at": datetime.fromtimestamp(v.creation_timestamp / 1000.0),
                    "description": v.description or "",
                }
        except Exception as e:
            logger.warning("MLflow get_latest_version failed: %s", e)
        return None

    def transition_model_version_stage(self, name: str, version: int, stage: str):
        self._client.transition_model_version_stage(
            name=name, version=version, stage=stage
        )

    def get_production_model(self, name: str) -> Optional[Dict]:
        try:
            versions = self._client.get_latest_versions(name, stages=["Production"])
            if versions:
                v = versions[0]
                return {
                    "name": v.name,
                    "version": int(v.version),
                    "run_id": v.run_id,
                    "stage": "production",
                    "created_at": datetime.fromtimestamp(v.creation_timestamp / 1000.0),
                    "description": v.description or "",
                }
        except Exception:
            pass
        return None

    def set_production_model(self, name: str, version: int):
        # Demote old production to archived
        old = self.get_production_model(name)
        if old:
            self.transition_model_version_stage(name, old["version"], "Archived")
        self.transition_model_version_stage(name, version, "Production")

    def list_models(self, name: Optional[str] = None) -> List[Dict]:
        result = []
        try:
            if name:
                versions = self._client.search_model_versions(f"name='{name}'")
            else:
                reg_models = self._client.search_registered_models()
                versions = []
                for rm in reg_models:
                    versions.extend(
                        self._client.search_model_versions(f"name='{rm.name}'")
                    )
            for v in versions:
                run = self._client.get_run(v.run_id)
                result.append({
                    "name": v.name,
                    "version": int(v.version),
                    "run_id": v.run_id,
                    "stage": v.current_stage.lower(),
                    "created_at": datetime.fromtimestamp(v.creation_timestamp / 1000.0),
                    "description": v.description or "",
                    "params": run.data.params if run else {},
                    "metrics": run.data.metrics if run else {},
                })
        except Exception as e:
            logger.warning("MLflow list_models failed: %s", e)
        return sorted(result, key=lambda x: x["version"], reverse=True)

    def get_run(self, run_id: str) -> Optional[Dict]:
        try:
            run = self._client.get_run(run_id)
            return {
                "run_id": run.info.run_id,
                "experiment_name": self._client.get_experiment(run.info.experiment_id).name,
                "run_name": run.info.run_name,
                "params": run.data.params,
                "metrics": run.data.metrics,
                "tags": run.data.tags,
                "status": run.info.status,
            }
        except Exception:
            return None

    def search_runs(self, experiment_name: Optional[str] = None) -> List[Dict]:
        try:
            if experiment_name:
                exp = self._client.get_experiment_by_name(experiment_name)
                if exp:
                    runs = self._client.search_runs([exp.experiment_id])
                    return [
                        {
                            "run_id": r.info.run_id,
                            "experiment_name": experiment_name,
                            "run_name": r.info.run_name,
                            "params": r.data.params,
                            "metrics": r.data.metrics,
                            "tags": r.data.tags,
                            "status": r.info.status,
                            "created_at": datetime.fromtimestamp(r.info.start_time / 1000.0),
                        }
                        for r in runs
                    ]
        except Exception as e:
            logger.warning("MLflow search_runs failed: %s", e)
        return []


# ── Factory ──

_mlflow_client: Optional[Any] = None


def get_mlflow_client():
    """Return singleton MLflow client (mock or live based on config)."""
    global _mlflow_client
    if _mlflow_client is None:
        if MLFLOW_MODE == "live":
            try:
                _mlflow_client = LiveMlflowClient(MLFLOW_TRACKING_URI)
                logger.info("MLflow client: live mode at %s", MLFLOW_TRACKING_URI)
            except Exception as e:
                logger.warning("MLflow live failed (%s), falling back to mock", e)
                _mlflow_client = MockMlflowClient()
        else:
            _mlflow_client = MockMlflowClient()
            logger.info("MLflow client: mock mode (local dev)")
    return _mlflow_client


# ── High-level functions used by training engine ──

def log_model(
    mlflow_client,
    run_id: str,
    model: Any,
    params: Dict[str, Any],
    metrics: Dict[str, float],
    model_path: Optional[str] = None,
) -> str:
    """Log a trained model to MLflow tracking.

    Args:
        mlflow_client: MLflow client instance
        run_id: MLflow run ID
        model: The trained model object
        params: Training parameters
        metrics: Evaluation metrics (train_loss, valid_loss, ic, icir, sharpe, etc.)
        model_path: Optional local path to model file for artifact logging

    Returns:
        model_uri: MLflow model URI string
    """
    mlflow_client.log_params(run_id, params)
    mlflow_client.log_metrics(run_id, metrics)

    if model_path and os.path.exists(model_path):
        mlflow_client.log_artifact(run_id, model_path)

    mlflow_client.end_run(run_id, "FINISHED")
    logger.info("Model logged: run=%s metrics=%s", run_id, metrics)
    return f"runs:/{run_id}/model"


def register_model(
    mlflow_client,
    run_id: str,
    name: str,
) -> int:
    """Register a model from an MLflow run.

    Args:
        mlflow_client: MLflow client instance
        run_id: MLflow run ID
        name: Registered model name (e.g. 'lightgbm-ranker')

    Returns:
        version: Registered model version number
    """
    version = mlflow_client.register_model(run_id, name)
    logger.info("Model registered: %s v%d from run=%s", name, version, run_id)
    return version


def get_production_model(mlflow_client, name: str) -> Optional[Dict]:
    """Get current production model version.

    Args:
        mlflow_client: MLflow client instance
        name: Registered model name

    Returns:
        Model version dict or None if no production model
    """
    return mlflow_client.get_production_model(name)


def set_production_model(mlflow_client, name: str, version: int):
    """Set a model version as production (demotes old production to archived).

    Args:
        mlflow_client: MLflow client instance
        name: Registered model name
        version: Version number to promote
    """
    mlflow_client.set_production_model(name, version)
    logger.info("Production model set: %s v%d", name, version)
