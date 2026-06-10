"""SIT integration tests for Auth API — PRD v1.1 compliant.

Requires: Postgres running (docker-compose), DATABASE_URL set or default.
Run: DATABASE_TEST_NULLPOOL=1 pytest tests/sit/test_auth_integration.py -v
"""

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["DATABASE_TEST_NULLPOOL"] = "1"

from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User


@pytest_asyncio.fixture(scope="module", autouse=True)
async def cleanup_test_users():
    """Remove test users before the module runs to avoid duplicate-key failures."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(User).where(User.email.like("sit_%@test.com")))
        await db.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestRegister:
    """AC-1, AC-2: Register endpoint — PRD v1.1: returns tokens + sets cookie."""

    async def test_register_returns_tokens_and_user(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "sit_test_user",
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert body["user"]["name"] == "sit_test_user"
        assert body["user"]["email"] == "sit_r@test.com"
        assert body["user"]["role"] == "user"
        # refresh_token should NOT be in body — in Set-Cookie
        assert "refresh_token" not in body

    async def test_register_sets_refresh_cookie(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "cookie_test",
            "email": "sit_cookie@test.com",
            "password": "Abc12345",
        })
        assert resp.status_code == 201
        cookies = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in cookies
        assert "HttpOnly" in cookies
        assert "SameSite=strict" in cookies

    async def test_duplicate_email_returns_409(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "dup_user2",
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "邮箱已注册"

    async def test_short_password_returns_422(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "shortpw",
            "email": "short@test.com",
            "password": "Abc1",
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLogin:
    """AC-3, AC-4: Login — no refresh_token in body, Set-Cookie instead."""

    async def test_login_returns_access_token_and_user(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert body["user"]["name"] == "sit_test_user"
        assert body["user"]["role"] == "user"
        # refresh_token must NOT be in response body
        assert "refresh_token" not in body

    async def test_login_sets_refresh_cookie(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        cookies = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in cookies
        assert "HttpOnly" in cookies

    async def test_wrong_password_returns_401(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401
        assert resp.json()["detail"] == "邮箱或密码错误"

    async def test_nonexistent_email_returns_401(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "noexist@test.com",
            "password": "Abc12345",
        })
        assert resp.status_code == 401
        assert resp.json()["detail"] == "邮箱或密码错误"


@pytest.mark.asyncio
class TestRefresh:
    """AC-6, AC-7: Token refresh — reads from cookie, rotation."""

    async def test_refresh_from_cookie(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        rt_cookie = login.headers.get("set-cookie", "")
        # Extract cookie value
        rt_val = rt_cookie.split("refresh_token=")[1].split(";")[0]

        resp = await client.post("/api/v1/auth/refresh", cookies={"refresh_token": rt_val})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        # refresh_token should NOT be in body (goes via new Set-Cookie)
        assert "refresh_token" not in body

    async def test_refresh_from_body_fallback(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        rt_val = login.headers.get("set-cookie", "").split("refresh_token=")[1].split(";")[0]

        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": rt_val})
        assert resp.status_code == 200

    async def test_reused_refresh_token_returns_401(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        rt_val = login.headers.get("set-cookie", "").split("refresh_token=")[1].split(";")[0]

        # Use once
        await client.post("/api/v1/auth/refresh", json={"refresh_token": rt_val})
        # Reuse should fail
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": rt_val})
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestMe:
    """AC-9, AC-10, AC-11: Current user endpoint."""

    async def test_me_returns_user_info(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        at = login.json()["access_token"]

        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {at}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "sit_test_user"
        assert body["email"] == "sit_r@test.com"

    async def test_no_auth_header_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_fake_jwt_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer fake.jwt.token.here",
        })
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestRBAC:
    """AC-12, AC-13: Role-based access control."""

    async def test_non_admin_cannot_access_admin_users(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "sit_r@test.com",
            "password": "Abc12345",
        })
        at = login.json()["access_token"]

        resp = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {at}"})
        assert resp.status_code == 403

    async def test_admin_can_access_admin_users(self, client):
        login = await client.post("/api/v1/auth/login", json={
            "email": "admin@suying.ai",
            "password": "Admin123!",
        })
        at = login.json()["access_token"]

        resp = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {at}"})
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        assert "total" in body
