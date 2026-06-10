"""Extend 6 legacy application tables per refactoring plan §1.2

- screening_scores: add model_version, signal_source
- screening_batches: add signal_triggered
- predictions: add confidence, model_version
- prediction_versions: rename/expand to support model_registry
- prediction_details: add turning_point, risk_level
- backtest_records: add strategy_id, signal_source
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

def upgrade():
    # 1. screening_scores: 扩展字段适配新模式
    op.execute("""
        ALTER TABLE screening_scores 
        ADD COLUMN IF NOT EXISTS model_version VARCHAR(32),
        ADD COLUMN IF NOT EXISTS signal_source VARCHAR(50) DEFAULT 'factor'
    """)

    # 2. screening_batches: 增加 signal_triggered
    op.execute("""
        ALTER TABLE screening_batches 
        ADD COLUMN IF NOT EXISTS signal_triggered BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS signal_count INTEGER DEFAULT 0
    """)

    # 3. predictions: 增加 confidence/model_version
    op.execute("""
        ALTER TABLE predictions 
        ADD COLUMN IF NOT EXISTS confidence FLOAT,
        ADD COLUMN IF NOT EXISTS model_version VARCHAR(32),
        ADD COLUMN IF NOT EXISTS prediction_type VARCHAR(20) DEFAULT 'kronos'
    """)

    # 4. prediction_versions: 扩展为 model_registry 兼容
    op.execute("""
        ALTER TABLE prediction_versions 
        ADD COLUMN IF NOT EXISTS model_type VARCHAR(32) DEFAULT 'kronos',
        ADD COLUMN IF NOT EXISTS registry_uri TEXT,
        ADD COLUMN IF NOT EXISTS metrics JSONB,
        ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'
    """)

    # 5. prediction_details: 扩展拐点/风险字段
    op.execute("""
        ALTER TABLE prediction_details 
        ADD COLUMN IF NOT EXISTS turning_points JSONB,
        ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20),
        ADD COLUMN IF NOT EXISTS expected_return FLOAT,
        ADD COLUMN IF NOT EXISTS max_drawdown FLOAT
    """)

    # 6. backtest_records: 增加 strategy_id/信号来源
    op.execute("""
        ALTER TABLE backtest_records 
        ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64),
        ADD COLUMN IF NOT EXISTS signal_source VARCHAR(50),
        ADD COLUMN IF NOT EXISTS benchmark_return FLOAT
    """)

def downgrade():
    # 1
    op.execute("ALTER TABLE screening_scores DROP COLUMN IF EXISTS model_version, DROP COLUMN IF EXISTS signal_source")
    # 2
    op.execute("ALTER TABLE screening_batches DROP COLUMN IF EXISTS signal_triggered, DROP COLUMN IF EXISTS signal_count")
    # 3
    op.execute("ALTER TABLE predictions DROP COLUMN IF EXISTS confidence, DROP COLUMN IF EXISTS model_version, DROP COLUMN IF EXISTS prediction_type")
    # 4
    op.execute("ALTER TABLE prediction_versions DROP COLUMN IF EXISTS model_type, DROP COLUMN IF EXISTS registry_uri, DROP COLUMN IF EXISTS metrics, DROP COLUMN IF EXISTS status")
    # 5
    op.execute("ALTER TABLE prediction_details DROP COLUMN IF EXISTS turning_points, DROP COLUMN IF EXISTS risk_level, DROP COLUMN IF EXISTS expected_return, DROP COLUMN IF EXISTS max_drawdown")
    # 6
    op.execute("ALTER TABLE backtest_records DROP COLUMN IF EXISTS strategy_id, DROP COLUMN IF EXISTS signal_source, DROP COLUMN IF EXISTS benchmark_return")
