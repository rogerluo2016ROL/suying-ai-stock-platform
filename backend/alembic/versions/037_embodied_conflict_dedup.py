"""Deduplicate embodied source conflicts and retain all proposed nodes."""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "embodied_mapping_conflicts",
        sa.Column("proposed_node_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("embodied_mapping_conflicts", "proposed_node_ids")
