"""Add role permissions and membership period fields.

Revision ID: 019
Revises: 018
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_key", name="uq_role_permissions_role_key"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_key", "role_permissions", ["permission_key"])

    op.add_column(
        "memberships",
        sa.Column(
            "membership_status",
            sa.String(length=20),
            nullable=False,
            server_default="inactive",
        ),
    )
    op.add_column("memberships", sa.Column("membership_plan", sa.String(length=40), nullable=True))
    op.add_column(
        "memberships",
        sa.Column("membership_starts_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memberships",
        sa.Column("membership_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("memberships", sa.Column("membership_source", sa.String(length=40), nullable=True))
    op.add_column("memberships", sa.Column("membership_note", sa.Text(), nullable=True))
    op.add_column(
        "memberships",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "membership_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=True),
        sa.Column("old_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_membership_events_membership_id", "membership_events", ["membership_id"])
    op.create_index("ix_membership_events_user_id", "membership_events", ["user_id"])
    op.create_index(
        "ix_membership_events_created_by_user_id",
        "membership_events",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_membership_events_created_by_user_id", table_name="membership_events")
    op.drop_index("ix_membership_events_user_id", table_name="membership_events")
    op.drop_index("ix_membership_events_membership_id", table_name="membership_events")
    op.drop_table("membership_events")

    op.drop_column("memberships", "updated_at")
    op.drop_column("memberships", "membership_note")
    op.drop_column("memberships", "membership_source")
    op.drop_column("memberships", "membership_ends_at")
    op.drop_column("memberships", "membership_starts_at")
    op.drop_column("memberships", "membership_plan")
    op.drop_column("memberships", "membership_status")

    op.drop_index("ix_role_permissions_permission_key", table_name="role_permissions")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
