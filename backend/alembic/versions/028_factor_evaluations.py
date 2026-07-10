"""Persist immutable observed-factor evaluations.

Revision ID: 028
Revises: 027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factor_evaluations",
        sa.Column("evaluation_id", sa.String(64), primary_key=True),
        sa.Column("model_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_factor_evaluations_model_created", "factor_evaluations", ["model_key", "created_at"])


def downgrade():
    op.drop_index("idx_factor_evaluations_model_created", table_name="factor_evaluations")
    op.drop_table("factor_evaluations")
