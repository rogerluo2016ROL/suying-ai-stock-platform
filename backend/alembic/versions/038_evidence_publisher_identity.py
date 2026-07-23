"""Persist trusted publisher identities for cross-batch evidence evaluation."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("business_tag_evidence_events", sa.Column("publisher_id", sa.Text(), nullable=True))
    op.add_column("business_tag_evidence_events", sa.Column("canonical_source_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_tag_evidence_events", "canonical_source_id")
    op.drop_column("business_tag_evidence_events", "publisher_id")
