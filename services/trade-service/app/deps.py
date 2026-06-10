"""Auth deps for trade-service — JWT verification."""
import os, jwt
from fastapi import Header, HTTPException, Request, Depends

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production-min-32-chars!!")

async def require_auth(request: Request):
    """Verify JWT Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    try:
        token = auth.split(" ", 1)[1]
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
