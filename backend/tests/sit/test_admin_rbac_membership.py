"""SIT tests for admin RBAC permissions and membership management."""

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

os.environ["DATABASE_TEST_NULLPOOL"] = "1"

from app.main import _run_migrations, app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth_service import create_access_token, create_user, seed_roles


TEST_EMAIL_PREFIX = "rbac_"
BACKEND_DIR = Path(__file__).resolve().parents[2]


async def _run_backend_migrations() -> None:
    cwd = os.getcwd()
    try:
        os.chdir(BACKEND_DIR)
        await asyncio.to_thread(_run_migrations)
    finally:
        os.chdir(cwd)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def migrate_and_cleanup():
    await _run_backend_migrations()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email.like(f"{TEST_EMAIL_PREFIX}%@test.com")))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email.like(f"{TEST_EMAIL_PREFIX}%@test.com")))
        await db.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_users():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email.like(f"{TEST_EMAIL_PREFIX}%@test.com")))
        await db.commit()
        await seed_roles(db)
        admin = await create_user(
            db,
            name="rbac_admin",
            email="rbac_admin@test.com",
            password="Abc12345",
            role_name="admin",
        )
        member = await create_user(
            db,
            name="rbac_member",
            email="rbac_member@test.com",
            password="Abc12345",
            role_name="user",
        )
        return {
            "admin": admin,
            "member": member,
            "admin_headers": {"Authorization": f"Bearer {create_access_token(admin)}"},
            "member_headers": {"Authorization": f"Bearer {create_access_token(member)}"},
        }


def _enabled_permissions(role_payload: dict) -> set[str]:
    return {
        item["key"]
        for item in role_payload["permissions"]
        if item.get("enabled") is True
    }


def _find_role(payload: dict, role_name: str) -> dict:
    return next(role for role in payload["roles"] if role["role"] == role_name)


@pytest.mark.asyncio
async def test_non_admin_cannot_access_permission_endpoint(client, seeded_users):
    resp = await client.get(
        "/api/v1/admin/permissions/roles",
        headers=seeded_users["member_headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_default_role_permissions(client, seeded_users):
    resp = await client.get(
        "/api/v1/admin/permissions/roles",
        headers=seeded_users["admin_headers"],
    )
    assert resp.status_code == 200

    body = resp.json()
    admin_permissions = _enabled_permissions(_find_role(body, "admin"))
    user_permissions = _enabled_permissions(_find_role(body, "user"))

    assert "dashboard" in user_permissions
    assert "trade" in user_permissions
    assert "admin_permissions" in admin_permissions
    assert "admin_memberships" in admin_permissions
    assert "admin_permissions" not in user_permissions
    assert "admin_memberships" not in user_permissions


@pytest.mark.asyncio
async def test_admin_can_update_role_permissions(client, seeded_users):
    list_resp = await client.get(
        "/api/v1/admin/permissions/roles",
        headers=seeded_users["admin_headers"],
    )
    assert list_resp.status_code == 200
    original = _enabled_permissions(_find_role(list_resp.json(), "external_analyst"))

    try:
        resp = await client.put(
            "/api/v1/admin/permissions/roles/external_analyst",
            json={"permission_keys": ["dashboard", "screener"]},
            headers=seeded_users["admin_headers"],
        )
        assert resp.status_code == 200
        updated = _enabled_permissions(resp.json())
        assert updated == {"dashboard", "screener"}
    finally:
        await client.put(
            "/api/v1/admin/permissions/roles/external_analyst",
            json={"permission_keys": sorted(original)},
            headers=seeded_users["admin_headers"],
        )


@pytest.mark.asyncio
async def test_admin_can_update_user_authorization_and_membership(client, seeded_users):
    member = seeded_users["member"]
    resp = await client.put(
        f"/api/v1/admin/users/{member.id}/authorization",
        json={
            "role": "internal_analyst",
            "is_active": True,
            "membership": {
                "status": "active",
                "plan": "pro",
                "starts_at": "2026-06-01T00:00:00+08:00",
                "ends_at": "2026-07-01T23:59:59+08:00",
                "note": "SIT membership update",
            },
        },
        headers=seeded_users["admin_headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "internal_analyst"
    assert body["membership"]["status"] == "active"
    assert body["membership"]["plan"] == "pro"
    assert body["membership"]["is_member"] is True

    list_resp = await client.get(
        "/api/v1/admin/memberships?q=rbac_member",
        headers=seeded_users["admin_headers"],
    )
    assert list_resp.status_code == 200
    members = list_resp.json()["members"]
    row = next(item for item in members if item["email"] == "rbac_member@test.com")
    assert row["membership"]["status"] == "active"
    assert row["membership"]["plan"] == "pro"


@pytest.mark.asyncio
async def test_auth_me_returns_permissions_and_membership(client, seeded_users):
    member = seeded_users["member"]
    update_resp = await client.put(
        f"/api/v1/admin/users/{member.id}/authorization",
        json={
            "role": "user",
            "membership": {
                "status": "active",
                "plan": "basic",
                "starts_at": "2026-06-01T00:00:00+08:00",
                "ends_at": "2026-12-31T23:59:59+08:00",
            },
        },
        headers=seeded_users["admin_headers"],
    )
    assert update_resp.status_code == 200

    resp = await client.get(
        "/api/v1/auth/me",
        headers=seeded_users["member_headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "dashboard" in body["permissions"]
    assert "admin_permissions" not in body["permissions"]
    assert body["membership"]["status"] == "active"
    assert body["membership"]["plan"] == "basic"
    assert body["membership"]["is_member"] is True
