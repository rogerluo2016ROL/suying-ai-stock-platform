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
    ('leader_afternoon_v1', '秋神龙头战法-午后 V1.0',  '秋神', ARRAY['gain_pct','gain_score','seal_score','ma_score','turnover_score','volume_score','capital_score','resonance_score','sector_momentum_score','sector_leader_score','resilience_score','peer_count','dist_to_limit','seal_weakness','atr_pct'], 16),
    ('leader_afternoon_trend_full_v1', '秋神趋势启动午后全量版选股 V1.0', '秋神', ARRAY['gain_pct','gain_score','seal_score','ma_score','turnover_score','volume_score','capital_score','resonance_score','sector_momentum_score','sector_leader_score','resilience_score','peer_count','dist_to_limit','is_at_limit','sector_resonance'], 16),
    ('short_v1',            '匪爷短线多因子选股模型 V1.0', '匪爷', ARRAY['short_term','volume_factor','trend_strength','five_factor_composite','momentum_inverted','money_flow','margin_momentum','top_list','top_inst','analyst','hk_hold','tushare_events','identifiability','kronos_prediction'], 16),
    ('chokepoint_v1',       '大葱卡脖子选股模型 V1.0', '大葱', ARRAY['cp_score','identifiability','hard_tech_score','theme_heat','devils_risk'], 8),
    ('bi_trend_launch_v13', '毕师傅硬核科技趋势启动 V13', '毕师傅', ARRAY['obv_score','wr_score','vol_score','ma_score','adx_score','sm_score','startup_quality_score','ignition_power_score','hard_tech_conviction','chokepoint_score','checklist_score','freshness_bonus','rebound_strength_bonus','obv_accel_score'], 16),
    ('bi_trend_full_market_v1', '毕师傅全市场趋势启动 V1.0', '毕师傅', ARRAY['obv_score','wr_score','vol_score','ma_score','adx_score','sm_score','startup_quality_score','ignition_power_score','hard_tech_conviction','chokepoint_score','checklist_score','freshness_bonus','rebound_strength_bonus','obv_accel_score'], 16),
    ('supply_chain_bom_v5', '大葱产业链解构选股模型 V5', '大葱', ARRAY['moat_score','growth_score','profit_score','rating_score','consensus_score','revenue_growth','profit_growth','roe','gross_margin','report_count'], 16),
    ('cb_auction_v1',       '秋神竞价概念选债 V1.0',   '秋神', ARRAY['premium_rate','scale_score','concept_strength','auction_strength','liquidity_score'], 8),
    ('cb_auction_t0_v1',    '竞价选债 T+0 模型 V1.0', '竞价', ARRAY['fd_amount_yi','auction_strength','concept_strength','theme_score','matched_concept_count','trigger_stock_count','risk_notes'], 8),
    ('cb_floor_v1',         '匪爷可转债底价选债模型 V1.0', '匪爷', ARRAY['premium_score','rsi_score','ytm_score','macd_score','revision_score','theme_score','boll_score','history_score','size_score','volume_score','sector_bonus','rating_penalty','call_penalty'], 16),
    ('cb_floor_v3',         '匪爷可转债底价安全垫选债模型 V3.0', '匪爷', ARRAY['price_gap_score','floor_safety_score','premium_score','revision_countdown_score','revision_history_score','theme_hot_score','liquidity_score','governance_score','pledge_score','maturity_score','size_score','ytm_score','call_risk','bank_industry_filter','state_control_filter','no_revision_signal'], 16),
    ('cb_intraday_v1',      '匪爷可转债日内投机博弈模型 V1.0', '匪爷', ARRAY['sector_score','premium_score','momentum_score','liquidity_score','rev_bonus','call_penalty','premium_rate','yesterday_pct','cb_amount_wan'], 16)
ON CONFLICT (model_name) DO NOTHING;

-- 7. 向量索引维护 (每小时自动)
-- REINDEX INDEX idx_snapshots_vector;
-- VACUUM ANALYZE factor_snapshots;
