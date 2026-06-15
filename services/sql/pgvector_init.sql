-- pgvector 自学习系统 — 数据库迁移脚本
-- 执行: psql -h localhost -p 6432 -U kronos -d kronos -f services/sql/pgvector_init.sql

-- 1. 启用 pgvector 插件
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 模型注册表
CREATE TABLE IF NOT EXISTS model_registry (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL UNIQUE,
    display_name    VARCHAR(128),
    category        VARCHAR(32),
    factor_keys     TEXT[] NOT NULL,
    factor_dim      INTEGER NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);

-- 3. 因子快照表
CREATE TABLE IF NOT EXISTS factor_snapshots (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,
    trade_date      DATE NOT NULL,
    stock_code      VARCHAR(10) NOT NULL,
    time_slot       VARCHAR(5),
    factors         JSONB NOT NULL,
    factor_vector   vector(32),
    total_score     DOUBLE PRECISION,
    grade           VARCHAR(2),
    rank_in_day     INTEGER,
    next_day_return DOUBLE PRECISION,
    is_win          BOOLEAN,
    outcome_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_model FOREIGN KEY (model_name) REFERENCES model_registry(model_name)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_model_date ON factor_snapshots(model_name, trade_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_outcome ON factor_snapshots(model_name) WHERE next_day_return IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_snapshots_vector ON factor_snapshots USING ivfflat (factor_vector vector_cosine_ops) WITH (lists = 50);

-- 4. 每日结果汇总
CREATE TABLE IF NOT EXISTS daily_outcomes (
    id              SERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    model_name      VARCHAR(64) NOT NULL,
    total_picks     INTEGER,
    win_count       INTEGER,
    avg_return      DOUBLE PRECISION,
    cum_return      DOUBLE PRECISION,
    market_breadth  DOUBLE PRECISION,
    sh_index_change DOUBLE PRECISION,
    UNIQUE(model_name, trade_date)
);

-- 5. 模型版本演进
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,
    version_tag     VARCHAR(32) NOT NULL,
    snapshot_count  INTEGER,
    win_rate        DOUBLE PRECISION,
    mean_return     DOUBLE PRECISION,
    cum_return      DOUBLE PRECISION,
    is_current      BOOLEAN DEFAULT FALSE,
    deployed_at     TIMESTAMP DEFAULT NOW()
);

-- 6. 注册现有模型
INSERT INTO model_registry (model_name, display_name, category, factor_keys, factor_dim) VALUES
    ('leader_intraday_v7',  '秋神龙头战法-盘中 V7.0',  '秋神', ARRAY['gain_14','sector_leader_score','resonance_score','afternoon_score','seal_score','turnover_score','ma_score','volume_score','sector_momentum_score','gain_score','peer_count','leadership_bonus','dist_score','resonance_bonus','margin_bonus'], 32),
    ('leader_closing_v3',   '秋神龙头战法-尾盘 V3.0',  '秋神', ARRAY['gain_14','sector_leader_score','resonance_score','afternoon_score','seal_score','turnover_score','ma_score','volume_score','sector_momentum_score','gain_score','peer_count','leadership_bonus','resonance_bonus','margin_bonus','sector_resonance_bonus'], 32),
    ('leader_auction_v4',   '秋神龙头竞价超预期 V4.3','秋神', ARRAY['gap_z','sector_context','volume_surprise','amount_surprise','trap_reversal','fd_amount_yi'], 8),
    ('leader_scalp_v4',     '秋神龙头战法-盘后 V4.1',  '秋神', ARRAY['gain_quality','sector_leader','ma_trend','turnover','sector_resonance','capital_flow','sector_momentum','seal_quality','resilience'], 16),
    ('cb_auction_v1',       '秋神竞价概念选债 V1.0',   '秋神', ARRAY['premium_rate','scale_score','concept_strength','auction_strength','liquidity_score'], 8)
ON CONFLICT (model_name) DO NOTHING;

-- 7. 向量索引维护 (每小时自动)
-- REINDEX INDEX idx_snapshots_vector;
-- VACUUM ANALYZE factor_snapshots;
