-- 因子快照自学习系统 — 轻量方案 (无需 pgvector)
-- psql -h localhost -p 6432 -U kronos -d kronos -f services/sql/self_learning_init.sql

-- 1. 模型注册表
CREATE TABLE IF NOT EXISTS model_registry (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL UNIQUE,
    display_name    VARCHAR(128),
    category        VARCHAR(32),
    factor_keys     TEXT[] NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 2. 因子快照表 (核心)
CREATE TABLE IF NOT EXISTS factor_snapshots (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,
    trade_date      DATE NOT NULL,
    stock_code      VARCHAR(10) NOT NULL,
    time_slot       VARCHAR(5),
    factors         JSONB NOT NULL,
    total_score     DOUBLE PRECISION,
    grade           VARCHAR(2),
    rank_in_day     INTEGER,
    next_day_return DOUBLE PRECISION,
    is_win          BOOLEAN,
    created_at      TIMESTAMP DEFAULT NOW(),
    outcome_at      TIMESTAMP,
    CONSTRAINT fk_snap_model FOREIGN KEY (model_name) REFERENCES model_registry(model_name)
);

CREATE INDEX idx_snap_model_date ON factor_snapshots(model_name, trade_date);
CREATE INDEX idx_snap_outcome ON factor_snapshots(model_name) WHERE next_day_return IS NOT NULL;

-- 3. 模型版本演进
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,
    version_tag     VARCHAR(32) NOT NULL,
    snapshot_count  INTEGER,
    win_rate        DOUBLE PRECISION,
    mean_return     DOUBLE PRECISION,
    is_current      BOOLEAN DEFAULT FALSE,
    deployed_at     TIMESTAMP DEFAULT NOW()
);

-- 4. 注册现有模型
INSERT INTO model_registry (model_name, display_name, category, factor_keys) VALUES
    ('leader_intraday_v7',  '秋神龙头战法-盘中 V7.0',    '秋神', ARRAY['gain_14','sector_leader_score','resonance_score','afternoon_score','gain_score','seal_score','turnover_score','ma_score','volume_score','sector_momentum_score','leadership_bonus','peer_count']),
    ('leader_closing_v3',   '秋神龙头战法-尾盘 V3.0',    '秋神', ARRAY['gain_14','sector_leader_score','resonance_score','afternoon_score','gain_score','seal_score','turnover_score','ma_score','volume_score','sector_momentum_score','leadership_bonus','peer_count']),
    ('leader_auction_v4',   '秋神龙头竞价超预期 V4.3',   '秋神', ARRAY['gap_pct','gap_z','sector_context','volume_surprise','trap_reversal','fd_amount_yi']),
    ('leader_scalp_v4',     '秋神龙头战法-盘后 V4.1',    '秋神', ARRAY['gain_pct','sector_leader_score','ma_score','turnover_score','capital_score','resonance_score','sector_momentum_score']),
    ('cb_auction_v1',       '秋神竞价概念选债 V1.0',     '秋神', ARRAY['premium_rate','scale_score','concept_strength','auction_strength'])
ON CONFLICT (model_name) DO NOTHING;
