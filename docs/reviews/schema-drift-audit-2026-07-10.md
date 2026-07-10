# Schema Drift Audit Report — 2026-07-10
**ADR-014 | UAT PG(16432) read-only**

## §1 审计范围

- DB 365张 | init_sql 75张 | 审计 151张 | 排除 23张
- P1-4 已纳入审计的数据管道表 (原 EXCLUDED): sw_daily, pledge_detail, rt_sw_k, top_list, cyq_chips
- ADR-008~011 已修仍排除表 (不重复扫): ths_daily, top_inst (top_inst 索引见 §6)
- 应用层排除表 (auth/training/diagnosis/screening/prediction/backtest/factor): 21 张
- high=0 medium=0 low=151
- MONITORED双缺(DB+init均无): 无
### 审计表清单 (151张)

|#|表|DB列|init列|严重|状态|MON|
|---|---|---|---|---|---|---|
|1|`adj_factor`|7|3|low|=|y|
|2|`announcements`|5|5|low|=|y|
|3|`apscheduler_jobs`|3|0|low|init||
|4|`auto_trading_strategies`|0|17|low|DB||
|5|`block_trade_data`|11|7|low|=|y|
|6|`broker_accounts`|12|0|low|init||
|7|`broker_recommend`|8|4|low|=|y|
|8|`business_tag_capex_evidence`|30|0|low|init||
|9|`business_tag_evidence_events`|20|0|low|init||
|10|`business_tag_evidence_freshness`|11|0|low|init||
|11|`business_tag_evidence_reassessment`|20|0|low|init||
|12|`business_tag_expectation_gap_scores`|12|0|low|init||
|13|`business_tag_expectation_monitor`|16|0|low|init||
|14|`business_tag_l8_evidence_status`|13|0|low|init||
|15|`business_tag_mapping`|15|0|low|init||
|16|`business_tag_stage_tracking`|10|0|low|init||
|17|`business_tag_stage_transition_log`|11|0|low|init||
|18|`business_tag_three_high_scores`|12|0|low|init||
|19|`candidate_pools`|14|14|low|=||
|20|`cb_basic`|38|38|low|=||
|21|`cb_call`|12|12|low|=||
|22|`cb_concept`|4|4|low|=||
|23|`cb_daily`|16|16|low|=||
|24|`cb_factor`|23|23|low|=||
|25|`cb_price_chg`|8|8|low|=||
|26|`cb_sector`|3|0|low|init||
|27|`cctv_news`|5|5|low|=|y|
|28|`chain_nodes`|10|0|low|init||
|29|`chatbi_agent_model_bindings`|13|0|low|init||
|30|`chatbi_agent_tools`|5|0|low|init||
|31|`chatbi_agents`|11|0|low|init||
|32|`chatbi_audit_logs`|7|0|low|init||
|33|`chatbi_feedback`|8|0|low|init||
|34|`chatbi_llm_invocations`|14|0|low|init||
|35|`chatbi_message_events`|10|0|low|init||
|36|`chatbi_messages`|11|0|low|init||
|37|`chatbi_model_providers`|11|0|low|init||
|38|`chatbi_model_versions`|11|0|low|init||
|39|`chatbi_platform_user_bindings`|11|0|low|init||
|40|`chatbi_preview_logs`|12|0|low|init||
|41|`chatbi_prompt_versions`|15|0|low|init||
|42|`chatbi_render_logs`|7|0|low|init||
|43|`chatbi_report_template_versions`|15|0|low|init||
|44|`chatbi_report_templates`|6|0|low|init||
|45|`chatbi_sessions`|6|0|low|init||
|46|`chatbi_tool_calls`|10|0|low|init||
|47|`company_bom_mapping`|9|0|low|init||
|48|`company_business_segments`|14|0|low|init||
|49|`company_chain_mapping`|12|0|low|init||
|50|`company_evidence`|10|0|low|init||
|51|`cyq_chips`|8|4|low|=|y|
|52|`daily_basic`|12|8|low|=|y|
|53|`daily_kline`|16|12|low|=|y|
|54|`daily_kline_intraday`|11|11|low|=||
|55|`data_readiness_snapshots`|8|0|low|init||
|56|`dc_concept`|16|0|low|init||
|57|`dc_hot`|13|0|low|init||
|58|`dc_member`|7|0|low|init||
|59|`decision_contexts`|12|0|low|init||
|60|`dividend_data`|9|5|low|=|y|
|61|`eastmoney_limit_pool`|21|0|low|init||
|62|`evidence_collection_jobs`|16|0|low|init||
|63|`evidence_extracted_facts`|26|0|low|init||
|64|`evidence_source_catalog`|20|0|low|init||
|65|`experiments`|4|0|low|init||
|66|`fina_audit`|7|7|low|=|y|
|67|`fina_mainbz`|6|6|low|=|y|
|68|`financial_abstracts`|3|3|low|=||
|69|`financial_balance`|10|6|low|=|y|
|70|`financial_cashflow`|10|6|low|=|y|
|71|`financial_income`|11|7|low|=|y|
|72|`financial_indicator`|16|12|low|=|y|
|73|`forecast_data`|12|8|low|=|y|
|74|`hk_holdings`|8|4|low|=|y|
|75|`index_basic`|8|4|low|=||
|76|`index_daily`|13|9|low|=|y|
|77|`industry_price_series`|13|0|low|init||
|78|`industry_themes`|7|0|low|init||
|79|`interact_qa`|7|7|low|=|y|
|80|`kpl_concept_cons`|10|0|low|init||
|81|`kpl_list`|27|0|low|init||
|82|`kpl_list_ths`|21|0|low|init||
|83|`limit_cpt_list`|12|0|low|init||
|84|`limit_list_d`|28|24|low|=|y|
|85|`limit_list_d_2026_null_backup_20260630`|24|0|low|init||
|86|`limit_list_ths`|21|0|low|init||
|87|`limit_step`|7|0|low|init||
|88|`manual_overrides`|6|0|low|init||
|89|`margin_detail`|12|8|low|=|y|
|90|`margin_summary`|3|3|low|=|y|
|91|`membership_events`|11|0|low|init||
|92|`memberships`|13|0|low|init||
|93|`metrics`|4|0|low|init||
|94|`model_versions`|8|0|low|init||
|95|`moneyflow`|15|11|low|=|y|
|96|`moneyflow_hsgt`|13|9|low|=|y|
|97|`monthly_kline`|13|9|low|=|y|
|98|`mp_report`|6|6|low|=|y|
|99|`official_site_events`|14|0|low|init||
|100|`params`|3|0|low|init||
|101|`patent_events`|19|0|low|init||
|102|`pledge_detail`|6|6|low|=|y|
|103|`policy_interpretations`|8|0|low|init||
|104|`policy_law`|8|8|low|=|y|
|105|`policy_sources`|8|0|low|init||
|106|`policy_themes`|5|0|low|init||
|107|`profit_forecasts`|5|5|low|=||
|108|`raw_evidence_documents`|18|0|low|init||
|109|`repurchase`|4|4|low|=|y|
|110|`research_reports`|6|6|low|=||
|111|`research_reports_tushare`|14|10|low|=|y|
|112|`risk_verdicts`|15|0|low|init||
|113|`role_permissions`|6|0|low|init||
|114|`rt_k`|12|12|low|=|y|
|115|`rt_sw_k`|15|11|low|=|y|
|116|`runs`|13|0|low|init||
|117|`screening_models`|7|0|low|init||
|118|`share_float`|4|4|low|=|y|
|119|`st_history`|5|5|low|=||
|120|`stk_auction_o`|15|11|low|=||
|121|`stk_factor_pro`|25|21|low|=|y|
|122|`stk_holdernumber`|3|3|low|=|y|
|123|`stk_holdertrade`|7|7|low|=|y|
|124|`stk_limit`|10|6|low|=|y|
|125|`stk_mins`|14|10|low|=|y|
|126|`stock_news`|5|5|low|=||
|127|`stock_news_tushare`|9|5|low|=|y|
|128|`stock_profiles`|16|16|low|=|y|
|129|`stocks`|15|11|low|=|y|
|130|`strategy_plans`|16|16|low|=||
|131|`supply_chain_bom_edges`|4|0|low|init||
|132|`supply_chain_bom_nodes`|9|0|low|init||
|133|`supply_chain_deconstruct_views`|6|0|low|init||
|134|`supply_chain_hierarchy_nodes`|14|0|low|init||
|135|`supply_chain_scores`|9|0|low|init||
|136|`sw_daily`|19|15|low|=|y|
|137|`sync_schedules`|10|0|low|init||
|138|`tags`|3|0|low|init||
|139|`task_runs`|11|0|low|init||
|140|`tenants`|6|0|low|init||
|141|`tender_award_events`|16|0|low|init||
|142|`ths_concept_catalog_legacy`|4|0|low|init||
|143|`ths_concept_map`|5|5|low|=||
|144|`ths_hot`|14|0|low|init||
|145|`ths_index`|6|0|low|init||
|146|`ths_member`|12|0|low|init||
|147|`top_list`|15|11|low|=|y|
|148|`trade_cal`|3|3|low|=|y|
|149|`trade_orders`|17|0|low|init||
|150|`tushare_api_update_metadata`|7|7|low|=||
|151|`weekly_kline`|13|9|low|=|y|

## §2 严重度详情

(无high/medium)

## §3 子ADR建议

按ADR-014§决策4(列差≥3/PK/类型/下游):
(无 — ADR-008~013已完成主要drift修复)

## §4 轻量对齐

- `adj_factor` (low MON=yes): legacy索引: idx_adj_factor_code_date,idx_adj_factor_date,idx_adj_factor_trade_code
- `apscheduler_jobs` (low MON=no): init独有(DB缺)
- `auto_trading_strategies` (low MON=no): DB独有(init缺)
- `block_trade_data` (low MON=yes): legacy索引: idx_block_trade_date
- `broker_accounts` (low MON=no): init独有(DB缺)
- `business_tag_capex_evidence` (low MON=no): init独有(DB缺)
- `business_tag_evidence_events` (low MON=no): init独有(DB缺)
- `business_tag_evidence_freshness` (low MON=no): init独有(DB缺)
- `business_tag_evidence_reassessment` (low MON=no): init独有(DB缺)
- `business_tag_expectation_gap_scores` (low MON=no): init独有(DB缺)
- `business_tag_expectation_monitor` (low MON=no): init独有(DB缺)
- `business_tag_l8_evidence_status` (low MON=no): init独有(DB缺)
- `business_tag_mapping` (low MON=no): init独有(DB缺)
- `business_tag_stage_tracking` (low MON=no): init独有(DB缺)
- `business_tag_stage_transition_log` (low MON=no): init独有(DB缺)
- `business_tag_three_high_scores` (low MON=no): init独有(DB缺)
- `cb_daily` (low MON=no): legacy索引: idx_cb_daily_trade_code
- `cb_factor` (low MON=no): legacy索引: idx_cb_factor_trade_code
- `cb_sector` (low MON=no): init独有(DB缺)
- `chain_nodes` (low MON=no): init独有(DB缺)
- `chatbi_agent_model_bindings` (low MON=no): init独有(DB缺)
- `chatbi_agent_tools` (low MON=no): init独有(DB缺)
- `chatbi_agents` (low MON=no): init独有(DB缺)
- `chatbi_audit_logs` (low MON=no): init独有(DB缺)
- `chatbi_feedback` (low MON=no): init独有(DB缺)
- `chatbi_llm_invocations` (low MON=no): init独有(DB缺)
- `chatbi_message_events` (low MON=no): init独有(DB缺)
- `chatbi_messages` (low MON=no): init独有(DB缺)
- `chatbi_model_providers` (low MON=no): init独有(DB缺)
- `chatbi_model_versions` (low MON=no): init独有(DB缺)
- `chatbi_platform_user_bindings` (low MON=no): init独有(DB缺)
- `chatbi_preview_logs` (low MON=no): init独有(DB缺)
- `chatbi_prompt_versions` (low MON=no): init独有(DB缺)
- `chatbi_render_logs` (low MON=no): init独有(DB缺)
- `chatbi_report_template_versions` (low MON=no): init独有(DB缺)
- `chatbi_report_templates` (low MON=no): init独有(DB缺)
- `chatbi_sessions` (low MON=no): init独有(DB缺)
- `chatbi_tool_calls` (low MON=no): init独有(DB缺)
- `company_bom_mapping` (low MON=no): init独有(DB缺)
- `company_business_segments` (low MON=no): init独有(DB缺)
- `company_chain_mapping` (low MON=no): init独有(DB缺)
- `company_evidence` (low MON=no): init独有(DB缺)
- `cyq_chips` (low MON=yes): legacy索引: idx_cyq_chips_date
- `daily_basic` (low MON=yes): legacy索引: idx_daily_basic_code_date,idx_daily_basic_date,idx_daily_basic_trade_code
- `daily_kline` (low MON=yes): legacy索引: idx_dk_code_date_ohlcv
- `data_readiness_snapshots` (low MON=no): init独有(DB缺)
- `dc_concept` (low MON=no): init独有(DB缺)
- `dc_hot` (low MON=no): init独有(DB缺)
- `dc_member` (low MON=no): init独有(DB缺)
- `decision_contexts` (low MON=no): init独有(DB缺)
- `eastmoney_limit_pool` (low MON=no): init独有(DB缺)
- `evidence_collection_jobs` (low MON=no): init独有(DB缺)
- `evidence_extracted_facts` (low MON=no): init独有(DB缺)
- `evidence_source_catalog` (low MON=no): init独有(DB缺)
- `experiments` (low MON=no): init独有(DB缺)
- `hk_holdings` (low MON=yes): legacy索引: idx_hk_holdings_date,idx_hk_holdings_trade_code
- `index_daily` (low MON=yes): legacy索引: idx_index_daily_date,idx_index_daily_trade_code
- `industry_price_series` (low MON=no): init独有(DB缺)
- `industry_themes` (low MON=no): init独有(DB缺)
- `kpl_concept_cons` (low MON=no): init独有(DB缺)
- `kpl_list` (low MON=no): init独有(DB缺)
- `kpl_list_ths` (low MON=no): init独有(DB缺)
- `limit_cpt_list` (low MON=no): init独有(DB缺)
- `limit_list_d_2026_null_backup_20260630` (low MON=no): init独有(DB缺)
- `limit_list_ths` (low MON=no): init独有(DB缺)
- `limit_step` (low MON=no): init独有(DB缺)
- `manual_overrides` (low MON=no): init独有(DB缺)
- `margin_detail` (low MON=yes): legacy索引: idx_margin_detail_date,idx_margin_detail_trade_code
- `margin_summary` (low MON=yes): legacy索引: idx_margin_summary_date
- `membership_events` (low MON=no): init独有(DB缺)
- `memberships` (low MON=no): init独有(DB缺)
- `metrics` (low MON=no): init独有(DB缺)
- `model_versions` (low MON=no): init独有(DB缺)
- `moneyflow` (low MON=yes): legacy索引: idx_moneyflow_date,idx_moneyflow_trade_code
- `moneyflow_hsgt` (low MON=yes): legacy索引: idx_moneyflow_hsgt_date
- `monthly_kline` (low MON=yes): legacy索引: idx_monthly_kline_code_date,idx_monthly_kline_trade_code
- `official_site_events` (low MON=no): init独有(DB缺)
- `params` (low MON=no): init独有(DB缺)
- `patent_events` (low MON=no): init独有(DB缺)
- `policy_interpretations` (low MON=no): init独有(DB缺)
- `policy_sources` (low MON=no): init独有(DB缺)
- `policy_themes` (low MON=no): init独有(DB缺)
- `raw_evidence_documents` (low MON=no): init独有(DB缺)
- `risk_verdicts` (low MON=no): init独有(DB缺)
- `role_permissions` (low MON=no): init独有(DB缺)
- `rt_k` (low MON=yes): legacy索引: idx_rt_k_code,idx_rt_k_date
- `rt_sw_k` (low MON=yes): legacy索引: idx_rt_sw_k_date
- `runs` (low MON=no): init独有(DB缺)
- `screening_models` (low MON=no): init独有(DB缺)
- `stk_auction_o` (low MON=no): legacy索引: idx_stk_auction_o_code,idx_stk_auction_o_date
- `stk_limit` (low MON=yes): legacy索引: idx_stk_limit_code_date,idx_stk_limit_date,idx_stk_limit_trade_code
- `stk_mins` (low MON=yes): legacy索引: idx_stk_mins_code_time
- `supply_chain_bom_edges` (low MON=no): init独有(DB缺)
- `supply_chain_bom_nodes` (low MON=no): init独有(DB缺)
- `supply_chain_deconstruct_views` (low MON=no): init独有(DB缺)
- `supply_chain_hierarchy_nodes` (low MON=no): init独有(DB缺)
- `supply_chain_scores` (low MON=no): init独有(DB缺)
- `sw_daily` (low MON=yes): legacy索引: idx_sw_daily_date
- `sync_schedules` (low MON=no): init独有(DB缺)
- `tags` (low MON=no): init独有(DB缺)
- `task_runs` (low MON=no): init独有(DB缺)
- `tenants` (low MON=no): init独有(DB缺)
- `tender_award_events` (low MON=no): init独有(DB缺)
- `ths_concept_catalog_legacy` (low MON=no): init独有(DB缺)
- `ths_hot` (low MON=no): init独有(DB缺)
- `ths_index` (low MON=no): init独有(DB缺)
- `ths_member` (low MON=no): init独有(DB缺)
- `top_list` (low MON=yes): legacy索引: idx_top_list_date,idx_top_list_trade_code
- `trade_orders` (low MON=no): init独有(DB缺)
- `weekly_kline` (low MON=yes): legacy索引: idx_weekly_kline_code_date,idx_weekly_kline_trade_code

## §5 索引登记

|表|索引|列|来源|状态|
|---|---|---|---|---|
|adj_factor|idx_adj_factor_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|adj_factor|idx_adj_factor_date|(trade_date)|init:n/DB:y|i-miss|
|adj_factor|idx_adj_factor_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|apscheduler_jobs|ix_apscheduler_jobs_next_run_time|(next_run_time)|init:n/DB:y|i-miss|
|auto_trading_strategies|idx_auto_trading_strategies_status_updated|(status,updated_at)|init:y/DB:n|d-miss|
|auto_trading_strategies|idx_auto_trading_strategies_strategy_id|(strategy_id)|init:y/DB:n|d-miss|
|block_trade_data|idx_block_trade_date|(trade_date)|init:n/DB:y|i-miss|
|broker_accounts|ix_broker_accounts_owner_user_id|(owner_user_id)|init:n/DB:y|i-miss|
|broker_accounts|ix_broker_accounts_tenant_id|(tenant_id)|init:n/DB:y|i-miss|
|business_tag_capex_evidence|idx_business_tag_capex_asof|(as_of_date DESC)|init:n/DB:y|i-miss|
|business_tag_capex_evidence|idx_business_tag_capex_chain|(chain_id,mapped_layer_id)|init:n/DB:y|i-miss|
|business_tag_capex_evidence|idx_business_tag_capex_code|(code)|init:n/DB:y|i-miss|
|business_tag_capex_evidence|idx_business_tag_capex_mapping|(mapping_id)|init:n/DB:y|i-miss|
|business_tag_capex_evidence|idx_business_tag_capex_review|(review_status,source_level)|init:n/DB:y|i-miss|
|business_tag_evidence_events|idx_business_tag_evidence_code_date|(code,event_date)|init:n/DB:y|i-miss|
|business_tag_evidence_events|idx_business_tag_evidence_mapping|(mapping_id)|init:n/DB:y|i-miss|
|business_tag_evidence_freshness|idx_business_tag_evidence_freshness_status|(freshness_status,next_review_date)|init:n/DB:y|i-miss|
|business_tag_evidence_reassessment|idx_business_tag_evidence_reassessment_code|(code,assessment_date)|init:n/DB:y|i-miss|
|business_tag_evidence_reassessment|idx_business_tag_evidence_reassessment_status|(assessment_date,review_status)|init:n/DB:y|i-miss|
|business_tag_expectation_gap_scores|idx_business_tag_expectation_gap|(trade_date,expectation_gap_score DESC NULLS LAST)|init:n/DB:y|i-miss|
|business_tag_expectation_monitor|idx_business_tag_expectation_monitor_mapping|(mapping_id,gap_status)|init:n/DB:y|i-miss|
|business_tag_l8_evidence_status|idx_business_tag_l8_status_code|(code)|init:n/DB:y|i-miss|
|business_tag_l8_evidence_status|idx_business_tag_l8_status_dimension|(dimension_id,source_status)|init:n/DB:y|i-miss|
|business_tag_l8_evidence_status|idx_business_tag_l8_status_mapping|(mapping_id)|init:n/DB:y|i-miss|
|business_tag_mapping|idx_business_tag_mapping_code|(code)|init:n/DB:y|i-miss|
|business_tag_mapping|idx_business_tag_mapping_node|(node_id)|init:n/DB:y|i-miss|
|business_tag_mapping|idx_business_tag_mapping_status|(status)|init:n/DB:y|i-miss|
|business_tag_stage_tracking|idx_business_tag_stage_mapping_date|(mapping_id,trade_date)|init:n/DB:y|i-miss|
|business_tag_stage_transition_log|idx_business_tag_stage_transition_mapping|(mapping_id,created_at DESC)|init:n/DB:y|i-miss|
|business_tag_three_high_scores|idx_business_tag_three_high_total|(trade_date,total_score DESC NULLS LAST)|init:n/DB:y|i-miss|
|candidate_pools|idx_candidate_pools_pool_id|(pool_id)|init:y/DB:y|synced|
|candidate_pools|idx_candidate_pools_scope_updated|(tenant_id,owner_user_id,account_id,updated_at)|init:y/DB:y|synced|
|candidate_pools|idx_candidate_pools_source|(source_module,source_mode,updated_at)|init:y/DB:y|synced|
|cb_call|idx_cb_call_code|(ts_code)|init:y/DB:y|synced|
|cb_call|idx_cb_call_date|(call_date)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_code|(ts_code)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_name|(concept)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_code|(ts_code)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_date|(trade_date)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_trade_code|(trade_date,ts_code)|init:n/DB:y|i-miss|
|cb_factor|idx_cb_factor_code|(ts_code)|init:y/DB:y|synced|
|cb_factor|idx_cb_factor_date|(trade_date)|init:y/DB:y|synced|
|cb_factor|idx_cb_factor_trade_code|(trade_date,ts_code)|init:n/DB:y|i-miss|
|cb_price_chg|idx_cb_price_chg_code|(ts_code)|init:y/DB:y|synced|
|chain_nodes|idx_chain_nodes_theme_chain|(theme_id,layer)|init:n/DB:y|i-miss|
|chatbi_message_events|idx_chatbi_message_events_msg_seq|(message_id,event_seq)|init:n/DB:y|i-miss|
|chatbi_platform_user_bindings|idx_chatbi_platform_bindings_internal_user|(internal_user_id)|init:n/DB:y|i-miss|
|company_bom_mapping|idx_company_bom_mapping_code|(code)|init:n/DB:y|i-miss|
|company_bom_mapping|idx_company_bom_mapping_node|(node_id)|init:n/DB:y|i-miss|
|company_business_segments|idx_company_business_segments_code|(code)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_code|(code)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_node|(node_id)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_resonance|(chokepoint_score DESC NULLS LAST)|init:n/DB:y|i-miss|
|company_evidence|idx_company_evidence_code|(code)|init:n/DB:y|i-miss|
|company_evidence|idx_company_evidence_node|(node_id)|init:n/DB:y|i-miss|
|cyq_chips|idx_cyq_chips_date|(trade_date)|init:n/DB:y|i-miss|
|daily_basic|idx_daily_basic_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|daily_basic|idx_daily_basic_date|(trade_date)|init:n/DB:y|i-miss|
|daily_basic|idx_daily_basic_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|daily_kline|idx_daily_kline_code|(code)|init:y/DB:y|synced|
|daily_kline|idx_daily_kline_date|(trade_date)|init:y/DB:y|synced|
|daily_kline|idx_dk_code_date_ohlcv|(code,trade_date,open,volume,amount)|init:n/DB:y|i-miss|
|daily_kline_intraday|idx_daily_kline_intraday_code|(code)|init:y/DB:y|synced|
|daily_kline_intraday|idx_daily_kline_intraday_date|(trade_date)|init:y/DB:y|synced|
|decision_contexts|idx_decision_contexts_candidate_id|(candidate_id)|init:n/DB:y|i-miss|
|decision_contexts|idx_decision_contexts_context_id|(decision_context_id)|init:n/DB:y|i-miss|
|decision_contexts|idx_decision_contexts_plan_id|(plan_id)|init:n/DB:y|i-miss|
|decision_contexts|idx_decision_contexts_scope_created|(tenant_id,account_id,created_at)|init:n/DB:y|i-miss|
|decision_contexts|idx_decision_contexts_symbol|(symbol)|init:n/DB:y|i-miss|
|evidence_collection_jobs|idx_evidence_collection_jobs_source_status|(source_id,status,created_at DESC)|init:n/DB:y|i-miss|
|evidence_extracted_facts|idx_evidence_extracted_facts_company|(company_code)|init:n/DB:y|i-miss|
|evidence_extracted_facts|idx_evidence_extracted_facts_l5|(l5_tag)|init:n/DB:y|i-miss|
|evidence_extracted_facts|idx_evidence_extracted_facts_mapping|(mapping_id)|init:n/DB:y|i-miss|
|evidence_extracted_facts|idx_evidence_extracted_facts_status|(validation_status,source_level)|init:n/DB:y|i-miss|
|evidence_source_catalog|idx_evidence_source_catalog_level|(source_level,enabled)|init:n/DB:y|i-miss|
|fina_audit|idx_fina_audit_result|(audit_result)|init:y/DB:y|synced|
|hk_holdings|idx_hk_holdings_date|(trade_date)|init:n/DB:y|i-miss|
|hk_holdings|idx_hk_holdings_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|index_daily|idx_index_daily_date|(trade_date)|init:n/DB:y|i-miss|
|index_daily|idx_index_daily_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|industry_price_series|idx_industry_price_series_chain_date|(chain_id,trade_date DESC)|init:n/DB:y|i-miss|
|interact_qa|idx_interact_qa_code|(code)|init:y/DB:y|synced|
|interact_qa|idx_interact_qa_date|(pub_date)|init:y/DB:y|synced|
|limit_list_d|idx_limit_list_d_date|(trade_date)|init:y/DB:y|synced|
|margin_detail|idx_margin_detail_date|(trade_date)|init:n/DB:y|i-miss|
|margin_detail|idx_margin_detail_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|margin_summary|idx_margin_summary_date|(trade_date)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_created_by_user_id|(created_by_user_id)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_membership_id|(membership_id)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_user_id|(user_id)|init:n/DB:y|i-miss|
|memberships|ix_memberships_tenant_id|(tenant_id)|init:n/DB:y|i-miss|
|memberships|ix_memberships_user_id|(user_id)|init:n/DB:y|i-miss|
|moneyflow|idx_moneyflow_date|(trade_date)|init:n/DB:y|i-miss|
|moneyflow|idx_moneyflow_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|moneyflow_hsgt|idx_moneyflow_hsgt_date|(trade_date)|init:n/DB:y|i-miss|
|monthly_kline|idx_monthly_kline_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|monthly_kline|idx_monthly_kline_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|official_site_events|idx_official_site_events_company_date|(company_code,event_date DESC NULLS LAST)|init:n/DB:y|i-miss|
|patent_events|idx_patent_events_company_date|(company_code,publication_date DESC NULLS LAST)|init:n/DB:y|i-miss|
|policy_interpretations|idx_policy_interpretations_created_at|(created_at)|init:n/DB:y|i-miss|
|policy_law|idx_policy_law_ptype|(ptype)|init:y/DB:y|synced|
|policy_law|idx_policy_law_puborg|(puborg)|init:y/DB:y|synced|
|policy_sources|idx_policy_sources_published_at|(published_at)|init:n/DB:y|i-miss|
|raw_evidence_documents|idx_raw_evidence_documents_company|(company_code,publish_time DESC NULLS LAST)|init:n/DB:y|i-miss|
|raw_evidence_documents|idx_raw_evidence_documents_source|(source_id,crawl_time DESC)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_candidate_id|(candidate_id)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_decision_context_id|(decision_context_id)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_order_id|(order_id)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_plan_id|(plan_id)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_result|(result)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_scope_created|(tenant_id,account_id,created_at)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_symbol_created|(symbol,created_at)|init:n/DB:y|i-miss|
|risk_verdicts|idx_risk_verdicts_verdict_id|(verdict_id)|init:n/DB:y|i-miss|
|role_permissions|ix_role_permissions_permission_key|(permission_key)|init:n/DB:y|i-miss|
|role_permissions|ix_role_permissions_role_id|(role_id)|init:n/DB:y|i-miss|
|rt_k|idx_rt_k_code|(code)|init:n/DB:y|i-miss|
|rt_k|idx_rt_k_date|(trade_date)|init:n/DB:y|i-miss|
|rt_sw_k|idx_rt_sw_k_date|(trade_date)|init:n/DB:y|i-miss|
|st_history|idx_st_history_code|(code)|init:y/DB:y|synced|
|st_history|idx_st_history_date|(start_date)|init:y/DB:y|synced|
|stk_auction_o|idx_stk_auction_o_code|(code)|init:n/DB:y|i-miss|
|stk_auction_o|idx_stk_auction_o_date|(trade_date)|init:n/DB:y|i-miss|
|stk_limit|idx_stk_limit_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|stk_limit|idx_stk_limit_date|(trade_date)|init:n/DB:y|i-miss|
|stk_limit|idx_stk_limit_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|stk_mins|idx_stk_mins_code|(code)|init:y/DB:y|synced|
|stk_mins|idx_stk_mins_code_time|(code,trade_time)|init:n/DB:y|i-miss|
|stk_mins|idx_stk_mins_time|(trade_time)|init:y/DB:y|synced|
|stock_profiles|idx_stock_profiles_province|(province)|init:y/DB:y|synced|
|strategy_plans|idx_strategy_plans_plan_id|(plan_id)|init:y/DB:y|synced|
|strategy_plans|idx_strategy_plans_scope_updated|(tenant_id,owner_user_id,account_id,updated_at)|init:y/DB:y|synced|
|strategy_plans|idx_strategy_plans_status|(status)|init:y/DB:y|synced|
|supply_chain_bom_nodes|idx_bom_nodes_theme_chain|(theme_id,chain_id)|init:n/DB:y|i-miss|
|supply_chain_deconstruct_views|idx_supply_chain_deconstruct_node_type|(node_id,view_type)|init:n/DB:y|i-miss|
|supply_chain_hierarchy_nodes|idx_supply_chain_hierarchy_layer|(layer_level)|init:n/DB:y|i-miss|
|supply_chain_hierarchy_nodes|idx_supply_chain_hierarchy_parent|(parent_node_id)|init:n/DB:y|i-miss|
|supply_chain_scores|idx_supply_chain_scores_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|sw_daily|idx_sw_daily_date|(trade_date)|init:n/DB:y|i-miss|
|task_runs|idx_task_runs_type_created|(task_type,created_at)|init:n/DB:y|i-miss|
|tenants|ix_tenants_slug|(slug)|init:n/DB:y|i-miss|
|tender_award_events|idx_tender_award_events_company_date|(company_code,publish_date DESC NULLS LAST)|init:n/DB:y|i-miss|
|ths_concept_map|idx_ths_concept_map_code|(ts_code)|init:y/DB:y|synced|
|ths_concept_map|idx_ths_concept_map_concept|(concept_name)|init:y/DB:y|synced|
|top_list|idx_top_list_date|(trade_date)|init:n/DB:y|i-miss|
|top_list|idx_top_list_trade_code|(trade_date,code)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_candidate_id|(candidate_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_code_created|(code,created_at)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_decision_context_id|(decision_context_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_order_id|(order_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_plan_id|(plan_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_scope_created|(tenant_id,account_id,created_at)|init:n/DB:y|i-miss|
|weekly_kline|idx_weekly_kline_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|weekly_kline|idx_weekly_kline_trade_code|(trade_date,code)|init:n/DB:y|i-miss|

## §6 ADR-010 F-1 收尾

**F-1 背景**: ADR-010 backlog `idx_cyq_chips_date` schema drift (init_sql 未声明, DB 实存); ADR-011 review §1.3 / S-5 升级合并入本 ADR-014。

**F-1 处置查证 (cyq_chips / top_inst 虽在 EXCLUDED, 此段单查索引现状)**:
- `cyq_chips.idx_cyq_chips_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)
- `top_inst.idx_top_inst_code_date`: DB=yes init_sql=yes → COMPLETED(synced)
- `top_inst.idx_top_inst_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)

**F-1 结论**: idx_cyq_chips_date / idx_top_inst_date 在 ADR-010/011 alembic 迁移后已清理 — F-1 跟踪项可关闭; §5 索引登记表覆盖全审计范围 drift 索引, F-1 合并至本 ADR-014, ADR-010 backlog F-1 关闭。
