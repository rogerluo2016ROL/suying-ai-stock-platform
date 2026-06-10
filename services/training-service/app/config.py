"""Training-service configuration — all environment-driven."""

import os

# ── Server ──
HOST = os.environ.get("TRAINING_HOST", "0.0.0.0")
PORT = int(os.environ.get("TRAINING_PORT", "8008"))
DEBUG = os.environ.get("TRAINING_DEBUG", "false").lower() in ("1", "true", "yes")

# ── Database (shared PostgreSQL with backend) ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kronos:kronos@localhost:6432/kronos",
)
DATABASE_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://kronos:kronos@localhost:6432/kronos",
)

# ── JWT (same secret as backend for token verification) ──
JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY", "dev-secret-change-in-production-min-32-chars!!"
)
JWT_ALGORITHM = "HS256"

# ── Redis (for training progress pub/sub) ──
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ── MLflow ──
MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://localhost:5010"
)
# Set to "mock" to use in-memory mock MLflow (no MLflow server needed)
MLFLOW_MODE = os.environ.get("MLFLOW_MODE", "mock")

# ── Training defaults ──
TRAINING_NUM_THREADS = int(os.environ.get("TRAINING_NUM_THREADS", "4"))
TRAINING_OUTPUT_DIR = os.environ.get(
    "TRAINING_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Kronos", "outputs", "models"),
)
