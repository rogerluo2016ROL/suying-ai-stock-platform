"""Add diagnosis tables — diagnosis_history, diagnosis_config

Revision ID: 004
Revises: 003
Create Date: 2026-06-10

Per AC-12.7 and docs/adr/005-stock-diagnosis.md Decision 4.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. diagnosis_history ──
    op.create_table(
        "diagnosis_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(8), nullable=False),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_diagnosis_history_code", "diagnosis_history", ["code"])
    op.create_index("idx_diagnosis_history_user_id", "diagnosis_history", ["user_id"])
    op.create_index("idx_diagnosis_history_code_date", "diagnosis_history", ["code", "created_at"])
    op.create_index("idx_diagnosis_history_created_at", "diagnosis_history", ["created_at"])

    # ── 2. diagnosis_config ──
    op.create_table(
        "diagnosis_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(64), nullable=True),
    )

    # Seed default grade thresholds (ADR-005 Decision 1)
    op.execute(
        "INSERT INTO diagnosis_config (key, value, description) VALUES "
        "('grade_threshold_strong_buy', '85', '强烈买入最低分'),"
        "('grade_threshold_buy', '70', '买入最低分'),"
        "('grade_threshold_hold', '50', '持有最低分'),"
        "('grade_threshold_reduce', '35', '减仓最低分'),"
        "('weight_technical', '0.40', '技术面权重'),"
        "('weight_capital_flow', '0.25', '资金面权重'),"
        "('weight_fundamental', '0.20', '基本面权重'),"
        "('weight_ai_predict', '0.10', 'AI预测权重'),"
        "('weight_sentiment', '0.05', '情绪面权重')"
    )


def downgrade() -> None:
    op.drop_table("diagnosis_config")
    op.drop_index("idx_diagnosis_history_created_at", "diagnosis_history")
    op.drop_index("idx_diagnosis_history_code_date", "diagnosis_history")
    op.drop_index("idx_diagnosis_history_user_id", "diagnosis_history")
    op.drop_index("idx_diagnosis_history_code", "diagnosis_history")
    op.drop_table("diagnosis_history")
