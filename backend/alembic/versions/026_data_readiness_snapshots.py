from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='026'; down_revision='025'; branch_labels=None; depends_on=None
def upgrade():
    op.create_table('data_readiness_snapshots', sa.Column('snapshot_id',sa.String(64),primary_key=True), sa.Column('profile',sa.String(80),nullable=False), sa.Column('target_trade_date',sa.Date(),nullable=False), sa.Column('cutoff_time',sa.DateTime(timezone=True)), sa.Column('status',sa.String(20),nullable=False), sa.Column('sources',postgresql.JSONB(),nullable=False), sa.Column('checked_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()), sa.Column('expires_at',sa.DateTime(timezone=True)))
def downgrade(): op.drop_table('data_readiness_snapshots')
