"""Add multi-horizon return columns to screening_snapshots.

- ret_3d/5d/10d/20d: forward return at 3/5/10/20 trading days
- is_win_3d/5d/10d: whether the return is positive
- ret_Xd_at: timestamp when the outcome was backfilled
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    for col, dtype in [
        ("ret_3d", sa.Double), ("ret_5d", sa.Double),
        ("ret_10d", sa.Double), ("ret_20d", sa.Double),
        ("is_win_3d", sa.Boolean), ("is_win_5d", sa.Boolean),
        ("is_win_10d", sa.Boolean),
        ("ret_3d_at", sa.DateTime), ("ret_5d_at", sa.DateTime),
        ("ret_10d_at", sa.DateTime), ("ret_20d_at", sa.DateTime),
    ]:
        op.execute(f"ALTER TABLE screening_snapshots ADD COLUMN IF NOT EXISTS {col} {dtype().compile(op.get_bind()) if hasattr(dtype(), 'compile') else ''}")


def downgrade():
    for col in ["ret_3d", "ret_5d", "ret_10d", "ret_20d",
                "is_win_3d", "is_win_5d", "is_win_10d",
                "ret_3d_at", "ret_5d_at", "ret_10d_at", "ret_20d_at"]:
        op.execute(f"ALTER TABLE screening_snapshots DROP COLUMN IF EXISTS {col}")
