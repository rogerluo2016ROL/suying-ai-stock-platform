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
    ('leader_afternoon_v1', '秋神龙头战法-午后 V1.0',    '秋神', ARRAY['gain_pct','gain_score','seal_score','ma_score','turnover_score','volume_score','capital_score','resonance_score','sector_momentum_score','sector_leader_score','resilience_score','peer_count','dist_to_limit','seal_weakness','atr_pct']),
    ('leader_afternoon_trend_full_v1', '秋神趋势启动午后全量版选股 V1.0', '秋神', ARRAY['gain_pct','gain_score','seal_score','ma_score','turnover_score','volume_score','capital_score','resonance_score','sector_momentum_score','sector_leader_score','resilience_score','peer_count','dist_to_limit','is_at_limit','sector_resonance']),
    ('short_v1',            '匪爷短线多因子选股模型 V1.0', '匪爷', ARRAY['short_term','volume_factor','trend_strength','five_factor_composite','momentum_inverted','money_flow','margin_momentum','top_list','top_inst','analyst','hk_hold','tushare_events','identifiability','kronos_prediction']),
    ('chokepoint_v1',       '大葱卡脖子选股模型 V1.0',   '大葱', ARRAY['cp_score','identifiability','hard_tech_score','theme_heat','devils_risk']),
    ('bi_trend_launch_v13', '毕师傅硬核科技趋势启动 V13', '毕师傅', ARRAY['obv_score','wr_score','vol_score','ma_score','adx_score','sm_score','startup_quality_score','ignition_power_score','hard_tech_conviction','chokepoint_score','checklist_score','freshness_bonus','rebound_strength_bonus','obv_accel_score']),
    ('bi_trend_full_market_v1', '毕师傅全市场趋势启动 V1.0', '毕师傅', ARRAY['obv_score','wr_score','vol_score','ma_score','adx_score','sm_score','startup_quality_score','ignition_power_score','hard_tech_conviction','chokepoint_score','checklist_score','freshness_bonus','rebound_strength_bonus','obv_accel_score']),
    ('supply_chain_bom_v5', '大葱产业链解构选股模型 V5',  '大葱', ARRAY['moat_score','growth_score','profit_score','rating_score','consensus_score','revenue_growth','profit_growth','roe','gross_margin','report_count']),
    ('cb_auction_v1',       '秋神竞价概念选债 V1.0',     '秋神', ARRAY['premium_rate','scale_score','concept_strength','auction_strength']),
    ('cb_auction_t0_v1',    '竞价选债 T+0 模型 V1.0',   '竞价', ARRAY['fd_amount_yi','auction_strength','concept_strength','theme_score','matched_concept_count','trigger_stock_count','risk_notes']),
    ('cb_floor_v1',         '匪爷可转债底价选债模型 V1.0', '匪爷', ARRAY['premium_score','rsi_score','ytm_score','macd_score','revision_score','theme_score','boll_score','history_score','size_score','volume_score','sector_bonus','rating_penalty','call_penalty']),
    ('cb_intraday_v1',      '匪爷可转债日内投机博弈模型 V1.0', '匪爷', ARRAY['sector_score','premium_score','momentum_score','liquidity_score','rev_bonus','call_penalty','premium_rate','yesterday_pct','cb_amount_wan'])
ON CONFLICT (model_name) DO NOTHING;
