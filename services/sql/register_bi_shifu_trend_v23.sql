-- 毕师傅趋势战法候选 V2.3：不替换正式 V2.1-score，仅注册为 candidate。
-- 开盘偏离过滤属于次日执行规则，不能作为收盘选股时的未来数据使用。
INSERT INTO screening_models (model_key, display_name, category, factor_keys, is_active)
VALUES (
    'bi_shifu_trend_v23',
    '毕师傅趋势战法候选 V2.3',
    '趋势',
    ARRAY['macd_golden_cross','macd_below_days','obv_golden_cross','ma20_ma60_trend','volume_ratio','candle_health','atr_stop_loss_pct'],
    TRUE
)
ON CONFLICT (model_key) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    factor_keys = EXCLUDED.factor_keys,
    is_active = EXCLUDED.is_active;

INSERT INTO model_registry (
    id, name, version, model_type, stage, run_id, params, metrics, artifact_uri, created_by, notes, created_at, updated_at
)
VALUES (
    'bi_shifu_trend_v23_candidate',
    'bi_shifu_trend',
    23,
    'screening',
    'candidate',
    'backtest_bi_shifu_trend_candidate_v23_2026_ytd_open_sequence',
    '{"mode_key":"bi_shifu_trend_v23","top_n":5,"macd_below_min_days":7,"entry_gap_min_pct":-2.0,"entry_gap_max_pct":0.5,"entry_rule":"next_open_only"}'::json,
    '{"period":"2026-01-05~2026-07-13","win_rate_pct":52.34,"total_return_pct":43.143,"max_drawdown_pct":-12.0934,"trades":107,"cost_bps_round_trip":14,"cohort_allocation_pct":50}'::json,
    'outputs/backtest_bi_shifu_trend_candidate_v23_2026_ytd_open_sequence.json',
    'codex',
    '候选版；收盘选 Top5，次日仅在开盘偏离[-2%,+0.5%]时执行。未自动升级生产版本。',
    NOW(), NOW()
)
ON CONFLICT (id) DO UPDATE
SET params = EXCLUDED.params,
    metrics = EXCLUDED.metrics,
    artifact_uri = EXCLUDED.artifact_uri,
    notes = EXCLUDED.notes,
    updated_at = NOW();
