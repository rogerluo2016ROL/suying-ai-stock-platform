"""Add training tables — training_jobs, model_registry, factor_weights, training_schedule

Revision ID: 003
Revises: 002
Create Date: 2026-06-10

Per AC-6.1~6.9 and docs/design/model-training/api-contract.md Section 8.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. training_jobs ──
    op.create_table(
        "training_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("model_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("best_params", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("final_metrics", sa.JSON(), nullable=True),
        sa.Column("model_uri", sa.String(512), nullable=True),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("experiment_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("idx_training_jobs_status", "training_jobs", ["status"])
    op.create_index("idx_training_jobs_model_type", "training_jobs", ["model_type"])
    op.create_index("idx_training_jobs_created_at", "training_jobs", ["created_at"])

    # ── 2. model_registry ──
    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("model_type", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="none"),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("experiment_id", sa.String(128), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("artifact_uri", sa.String(512), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_by", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_unique_constraint("uq_model_name_version", "model_registry", ["name", "version"])
    op.create_index("idx_model_registry_stage", "model_registry", ["stage"])
    op.create_index("idx_model_registry_name", "model_registry", ["name"])

    # ── 3. factor_weights ──
    op.create_table(
        "factor_weights",
        sa.Column("factor_name", sa.String(64), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("direction", sa.String(16), nullable=False, server_default="long"),
        sa.Column("ic", sa.Float(), nullable=True),
        sa.Column("icir", sa.Float(), nullable=True),
        sa.Column(
            "calibrated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("idx_factor_weights_calibrated", "factor_weights", ["calibrated_at"])

    # ── 4. factor_calibration_history ──
    op.create_table(
        "factor_calibration_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "calibrated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_calibration_history_date", "factor_calibration_history", ["calibrated_at"]
    )

    # ── 5. training_schedule ──
    op.create_table(
        "training_schedule",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cron", sa.String(64), nullable=False, server_default="0 2 * * 6"),
        sa.Column("model_type", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("auto_deploy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notify_on_complete", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "notify_channels",
            sa.JSON(),
            nullable=False,
            server_default='["email","wecom"]',
        ),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.String(36), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("training_schedule")
    op.drop_table("factor_calibration_history")
    op.drop_table("factor_weights")
    op.drop_index("idx_model_registry_name", "model_registry")
    op.drop_index("idx_model_registry_stage", "model_registry")
    op.drop_constraint("uq_model_name_version", "model_registry")
    op.drop_table("model_registry")
    op.drop_index("idx_training_jobs_created_at", "training_jobs")
    op.drop_index("idx_training_jobs_model_type", "training_jobs")
    op.drop_index("idx_training_jobs_status", "training_jobs")
    op.drop_table("training_jobs")
