"""Add controlled asynchronous task run records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "027_task_runs"
down_revision = "026_data_readiness_snapshots"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "task_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB()),
        sa.Column("error_payload", postgresql.JSONB()),
        sa.Column("code_commit", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

def downgrade():
    op.drop_table("task_runs")
