"""Kronos Auth — shared JWT + RBAC for microservices."""

from kronos_auth.deps import require_role, get_current_user_jwt, X_SERVICE_AUTH_HEADER
from kronos_auth.config import KRONOS_JWT_SECRET, KRONOS_SERVICE_SECRET
from kronos_auth.exceptions import UnauthorizedError, ForbiddenError

__all__ = [
    "require_role",
    "get_current_user_jwt",
    "X_SERVICE_AUTH_HEADER",
    "KRONOS_JWT_SECRET",
    "KRONOS_SERVICE_SECRET",
    "UnauthorizedError",
    "ForbiddenError",
]
