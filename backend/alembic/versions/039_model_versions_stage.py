"""Add stage column to model_versions for promotion governance.

Revision ID: 039
Revises: 038
Create Date: 2026-07-22

model_versions 此前没有 stage 概念,晋升(staging→production→archived)无从表达;
阶段三B 引入版本治理:历史版本保留、production 同时最多 1 个。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="staging"),
    )
    op.execute(
        """
        UPDATE model_versions
        SET stage = 'staging'
        WHERE stage IS NULL OR stage = ''
        """
    )


def downgrade() -> None:
    op.drop_column("model_versions", "stage")
