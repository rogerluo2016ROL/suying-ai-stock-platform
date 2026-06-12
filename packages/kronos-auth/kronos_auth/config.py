"""Kronos Auth configuration — environment-driven."""

import os

KRONOS_JWT_SECRET = os.environ.get(
    "JWT_SECRET_KEY",
    "dev-secret-change-in-production-min-32-chars!!",
)

KRONOS_SERVICE_SECRET = os.environ.get(
    "KRONOS_SERVICE_SECRET",
    "dev-service-secret-change-in-production",
)

JWT_ALGORITHM = "HS256"
