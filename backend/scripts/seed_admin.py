#!/usr/bin/env python3
"""Seed admin user from environment variables.

Usage:
    ADMIN_EMAIL=admin@suying.ai ADMIN_PASSWORD=Admin123! python scripts/seed_admin.py
"""

import asyncio
import os
import sys

# Ensure backend/app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal
from app.models.user import User, Role
from app.services.auth_service import hash_password, seed_roles
from sqlalchemy import select


async def main():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@suying.ai")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    admin_name = os.environ.get("ADMIN_NAME", "admin")

    async with AsyncSessionLocal() as db:
        await seed_roles(db)

        result = await db.execute(select(User).where(User.email == admin_email))
        if result.scalar_one_or_none():
            print(f"Admin user '{admin_email}' already exists, skipping.")
            return

        role_result = await db.execute(select(Role).where(Role.name == "admin"))
        admin_role = role_result.scalar_one()

        admin_user = User(
            name=admin_name,
            email=admin_email,
            password_hash=hash_password(admin_password),
            role_id=admin_role.id,
        )
        db.add(admin_user)
        await db.commit()
        print(f"Admin user '{admin_email}' created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
