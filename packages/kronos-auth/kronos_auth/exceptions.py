"""Kronos Auth exception classes."""

from fastapi import HTTPException, status


class UnauthorizedError(HTTPException):
    """401 — missing, expired, or invalid token."""

    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenError(HTTPException):
    """403 — valid token but insufficient role."""

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
