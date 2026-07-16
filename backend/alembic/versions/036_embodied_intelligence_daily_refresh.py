"""Add persistence for the embodied-intelligence daily refresh pipeline."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "embodied_refresh_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('running','success','data_success_delivery_incomplete','failed')",
                name="ck_embodied_refresh_run_status",
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_unique_constraint(
        "uq_embodied_run_date_mode", "embodied_refresh_runs", ["run_date", "mode"]
    )

    op.create_table(
        "embodied_source_cursors",
        sa.Column("chain_id", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_embodied_cursor_source", "embodied_source_cursors", ["chain_id", "source_name"]
    )

    op.create_table(
        "embodied_evidence_changes",
        sa.Column("change_fingerprint", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id"), nullable=False),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_embodied_change_fingerprint", "embodied_evidence_changes", ["change_fingerprint"]
    )

    op.create_table(
        "embodied_leader_snapshots",
        sa.Column("snapshot_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id"), nullable=False),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_embodied_snapshot_rank", "embodied_leader_snapshots", ["run_id", "node_id", "rank"]
    )

    op.create_table(
        "embodied_delivery_records",
        sa.Column("delivery_id", sa.Text(), primary_key=True),
        sa.Column("change_batch_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id"), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('pending','confirmed','failed','unconfirmed')",
                name="ck_embodied_delivery_status",
            ),
            nullable=False,
        ),
        sa.Column("message_id", sa.Text()),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_embodied_delivery_target", "embodied_delivery_records", ["change_batch_id", "chat_id"]
    )

    op.create_table(
        "embodied_mapping_conflicts",
        sa.Column("conflict_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id")),
        sa.Column("mapping_id", sa.Text(), sa.ForeignKey("business_tag_mapping.mapping_id")),
        sa.Column("chain_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("existing_node_id", sa.Text()),
        sa.Column("proposed_node_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('pending_review','resolved','rejected')", name="ck_embodied_mapping_conflict_status"), nullable=False, server_default="pending_review"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "embodied_mapping_transitions",
        sa.Column("transition_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("embodied_refresh_runs.run_id")),
        sa.Column("mapping_id", sa.Text(), sa.ForeignKey("business_tag_mapping.mapping_id")),
        sa.Column("chain_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_name", sa.Text()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("embodied_mapping_transitions")
    op.drop_table("embodied_mapping_conflicts")
    op.drop_table("embodied_delivery_records")
    op.drop_table("embodied_leader_snapshots")
    op.drop_table("embodied_evidence_changes")
    op.drop_table("embodied_source_cursors")
    op.drop_table("embodied_refresh_runs")
