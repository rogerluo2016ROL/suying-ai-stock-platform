"""Add transmission_layer column to chain_nodes.

Revision ID: 040
Revises: 039
Create Date: 2026-07-23

术语解耦: chain_nodes 旧的 layer (1-5, 原材料→终端应用) 是"上下游环节"编号,
而 template 路径的 8 层是产业"传导链 (transmission)"位置
(demand/task/core_product/foundation/integration/supporting/infrastructure/commercialization),
与 BOM 钻取链 (drilldown) L1-L8 (研究钻取深度) 是不同维度。

本迁移为 chain_nodes 新增 transmission_layer 列并回填旧 layer 映射:
  1(原材料)   → foundation
  2(核心零部件) → core_product
  3(制造)     → integration
  4(渠道)     → supporting
  5(终端应用)  → commercialization
无映射的 layer 值保持 NULL。映射与
packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py 的
LEGACY_LAYER_TO_TRANSMISSION 常量保持一致。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chain_nodes ADD COLUMN IF NOT EXISTS transmission_layer VARCHAR(32)"
    )
    op.execute(
        """
        UPDATE chain_nodes
        SET transmission_layer = CASE layer
            WHEN 1 THEN 'foundation'
            WHEN 2 THEN 'core_product'
            WHEN 3 THEN 'integration'
            WHEN 4 THEN 'supporting'
            WHEN 5 THEN 'commercialization'
            ELSE NULL
        END
        WHERE transmission_layer IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("chain_nodes", "transmission_layer")
