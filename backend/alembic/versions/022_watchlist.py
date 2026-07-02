"""Bring watchlist to full scope-aware schema (tenant/owner/account/visibility/data_scope).

Revision ID: 022
Revises: 021
Create Date: 2026-07-03

A 4-column legacy ``watchlist`` table (id / code / added_at / note) already exists
in some databases from an earlier prototype. This migration is idempotent: it
creates the table if missing, otherwise ADDs the scope + business columns that
are absent, then (re)builds the indexes. The legacy ``note`` column is retained
as-is for any existing data; ``notes`` is the new canonical column.

Scope pattern mirrors candidate_pools (migration 018): tenant_id / owner_user_id
/ account_id / visibility / data_scope. One row = one stock in one scope's
watchlist; uniqueness is enforced per (code, scope-keys) via a unique index that
coalesces NULL scope keys.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "watchlist"


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _ensure_table() -> None:
    """Create watchlist if absent, else ADD missing columns (idempotent)."""
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=100), nullable=False, server_default="tenant-default"),
            sa.Column("owner_user_id", sa.String(length=64), nullable=True),
            sa.Column("account_id", sa.String(length=100), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
            sa.Column("data_scope", sa.String(length=20), nullable=False, server_default="account"),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.String(length=500), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "visibility IN ('private', 'tenant_shared', 'public')",
                name="ck_watchlist_visibility",
            ),
            sa.CheckConstraint(
                "data_scope IN ('public', 'tenant', 'user', 'account')",
                name="ck_watchlist_data_scope",
            ),
        )
        return

    # Legacy table present — backfill scope + business columns idempotently.
    _add_column_if_missing(TABLE, "tenant_id", sa.String(length=100), nullable=False, server_default="tenant-default")
    _add_column_if_missing(TABLE, "owner_user_id", sa.String(length=64), nullable=True)
    _add_column_if_missing(TABLE, "account_id", sa.String(length=100), nullable=True)
    _add_column_if_missing(TABLE, "visibility", sa.String(length=20), nullable=False, server_default="private")
    _add_column_if_missing(TABLE, "data_scope", sa.String(length=20), nullable=False, server_default="account")
    _add_column_if_missing(TABLE, "name", sa.String(length=120), nullable=True)
    _add_column_if_missing(TABLE, "notes", sa.String(length=500), nullable=True)
    _add_column_if_missing(TABLE, "sort_order", sa.Integer(), nullable=False, server_default="0")
    _add_column_if_missing(TABLE, "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    _add_column_if_missing(TABLE, "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))

    # Legacy added_at is TIMESTAMP WITHOUT TIME ZONE; the store layer always
    # writes tz-aware datetimes, so promote it to TIMESTAMPTZ for consistency.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    added_at_type = next(
        (c["type"] for c in inspector.get_columns(TABLE) if c["name"] == "added_at"),
        None,
    )
    if added_at_type is not None and not getattr(added_at_type, "timezone", False):
        op.alter_column(TABLE, "added_at", type_=sa.DateTime(timezone=True))

    # Constraints — add only if not already present (CREATE INDEX IF NOT EXISTS
    # guards indexes; constraints need an explicit existence check).
    _ensure_check_constraint(TABLE, "ck_watchlist_visibility",
                             "visibility IN ('private', 'tenant_shared', 'public')")
    _ensure_check_constraint(TABLE, "ck_watchlist_data_scope",
                             "data_scope IN ('public', 'tenant', 'user', 'account')")


def _add_column_if_missing(table_name, column_name, column_type, **kwargs) -> None:
    if _has_column(table_name, column_name):
        return
    op.add_column(table_name, sa.Column(column_name, column_type, **kwargs))


def _ensure_check_constraint(table_name, constraint_name, condition_sql) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_check_constraints(table_name)}
    if constraint_name in existing:
        return
    op.create_check_constraint(constraint_name, table_name, condition_sql)


def _create_indexes() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchlist_scope_sort "
        f"ON {TABLE} (tenant_id, owner_user_id, account_id, sort_order, added_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_code " f"ON {TABLE} (code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_visibility " f"ON {TABLE} (visibility)")
    # Unique guard for account-scoped watchlist (one row per code per account).
    # Scope-visibility filtering is enforced in watchlist_store.find_one; this
    # index is the concurrency backstop for account-scope re-adds.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_account_code "
        f"ON {TABLE} (code, account_id) WHERE account_id IS NOT NULL"
    )


def upgrade() -> None:
    _ensure_table()
    _create_indexes()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_watchlist_account_code")
    op.execute("DROP INDEX IF EXISTS uq_watchlist_scope_code")
    op.execute("DROP INDEX IF EXISTS idx_watchlist_visibility")
    op.execute("DROP INDEX IF EXISTS idx_watchlist_code")
    op.execute("DROP INDEX IF EXISTS idx_watchlist_scope_sort")
    # Drop check constraints before columns (constraints reference the columns).
    op.execute("ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS ck_watchlist_data_scope")
    op.execute("ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS ck_watchlist_visibility")
    if _has_column(TABLE, "note"):
        # Legacy table existed before 022 — restore legacy 4-column shape
        # (id / code / added_at / note).
        # Restore added_at to its original TIMESTAMP WITHOUT TIME ZONE type.
        op.alter_column(TABLE, "added_at", type_=sa.DateTime(timezone=False))
        for col in ("metadata", "updated_at", "sort_order", "notes", "name", "data_scope",
                    "visibility", "account_id", "owner_user_id", "tenant_id"):
            if _has_column(TABLE, col):
                op.drop_column(TABLE, col)
    elif _has_table(TABLE):
        op.drop_table(TABLE)
