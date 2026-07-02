# Schema Drift Audit Report — 2026-07-01
**ADR-014 | UAT PG(16432) read-only**

## §1 审计范围

- DB 309张 | init_sql 73张 | 审计 96张 | 排除 22张
- P1-4 已纳入审计的数据管道表 (原 EXCLUDED): sw_daily, pledge_detail, rt_sw_k, top_list, cyq_chips
- ADR-008~011 已修仍排除表 (不重复扫): ths_daily, top_inst (top_inst 索引见 §6)
- 应用层排除表 (auth/training/diagnosis/screening/prediction/backtest/factor): 20 张
- high=5 medium=18 low=73
- MONITORED双缺(DB+init均无): 无
### 审计表清单 (96张)

|#|表|DB列|init列|严重|状态|MON|
|---|---|---|---|---|---|---|
|1|`adj_factor`|3|3|medium|=|y|
|2|`announcements`|5|5|low|=|y|
|3|`apscheduler_jobs`|3|0|low|init||
|4|`auto_trading_strategies`|0|16|low|DB||
|5|`block_trade_data`|7|7|medium|=|y|
|6|`broker_accounts`|12|0|low|init||
|7|`broker_recommend`|3|3|low|=|y|
|8|`candidate_pools`|14|14|high|=||
|9|`cb_basic`|38|38|low|=||
|10|`cb_call`|12|12|low|=||
|11|`cb_concept`|4|4|low|=||
|12|`cb_daily`|16|16|low|=||
|13|`cb_factor`|23|23|low|=||
|14|`cb_price_chg`|8|8|low|=||
|15|`cb_sector`|3|0|low|init||
|16|`cctv_news`|5|5|low|=|y|
|17|`chain_nodes`|10|0|low|init||
|18|`company_bom_mapping`|9|0|low|init||
|19|`company_chain_mapping`|12|0|low|init||
|20|`company_evidence`|10|0|low|init||
|21|`cyq_chips`|4|4|medium|=|y|
|22|`daily_basic`|8|8|medium|=|y|
|23|`daily_kline`|12|12|medium|=|y|
|24|`daily_kline_intraday`|11|11|low|=||
|25|`decision_contexts`|12|0|low|init||
|26|`dividend_data`|5|5|low|=|y|
|27|`experiments`|4|0|low|init||
|28|`fina_audit`|7|7|low|=|y|
|29|`fina_mainbz`|6|6|low|=|y|
|30|`financial_abstracts`|3|3|low|=||
|31|`financial_balance`|6|6|low|=|y|
|32|`financial_cashflow`|6|6|low|=|y|
|33|`financial_income`|7|7|low|=|y|
|34|`financial_indicator`|12|12|low|=|y|
|35|`forecast_data`|4|4|low|=|y|
|36|`hk_holdings`|4|4|medium|=|y|
|37|`index_basic`|4|4|low|=||
|38|`index_daily`|9|9|medium|=|y|
|39|`industry_themes`|7|0|low|init||
|40|`interact_qa`|7|7|low|=|y|
|41|`limit_list_d`|24|24|high|=|y|
|42|`limit_list_d_2026_null_backup_20260630`|24|0|low|init||
|43|`manual_overrides`|6|0|low|init||
|44|`margin_detail`|8|8|medium|=|y|
|45|`margin_summary`|3|3|medium|=|y|
|46|`membership_events`|11|0|low|init||
|47|`memberships`|13|0|low|init||
|48|`metrics`|4|0|low|init||
|49|`model_versions`|8|0|low|init||
|50|`moneyflow`|11|11|medium|=|y|
|51|`moneyflow_hsgt`|9|9|medium|=|y|
|52|`monthly_kline`|9|9|low|=|y|
|53|`mp_report`|6|6|low|=|y|
|54|`params`|3|0|low|init||
|55|`pledge_detail`|6|6|low|=|y|
|56|`policy_interpretations`|8|0|low|init||
|57|`policy_law`|8|8|low|=|y|
|58|`policy_sources`|8|0|low|init||
|59|`policy_themes`|5|0|low|init||
|60|`profit_forecasts`|5|5|low|=||
|61|`repurchase`|4|4|low|=|y|
|62|`research_reports`|6|6|low|=||
|63|`research_reports_tushare`|6|6|low|=|y|
|64|`risk_verdicts`|15|0|low|init||
|65|`role_permissions`|6|0|low|init||
|66|`rt_k`|12|12|medium|=|y|
|67|`rt_sw_k`|11|11|medium|=|y|
|68|`runs`|13|0|low|init||
|69|`screening_models`|7|0|low|init||
|70|`share_float`|4|4|low|=|y|
|71|`st_history`|5|5|low|=||
|72|`stk_auction_o`|11|10|medium|=||
|73|`stk_factor_pro`|21|21|medium|=|y|
|74|`stk_holdernumber`|3|3|low|=|y|
|75|`stk_holdertrade`|7|7|low|=|y|
|76|`stk_limit`|6|6|medium|=|y|
|77|`stk_mins`|10|10|high|=|y|
|78|`stock_news`|5|5|low|=||
|79|`stock_news_tushare`|5|5|low|=|y|
|80|`stock_profiles`|16|16|low|=|y|
|81|`stocks`|11|11|low|=|y|
|82|`strategy_plans`|16|16|high|=||
|83|`supply_chain_bom_edges`|4|0|low|init||
|84|`supply_chain_bom_nodes`|9|0|low|init||
|85|`supply_chain_scores`|9|0|low|init||
|86|`sw_daily`|15|15|medium|=|y|
|87|`sync_schedules`|10|0|low|init||
|88|`tags`|3|0|low|init||
|89|`tenants`|6|0|low|init||
|90|`ths_concept_map`|4|5|high|=||
|91|`ths_index`|6|0|low|init||
|92|`ths_member`|8|0|low|init||
|93|`top_list`|11|11|medium|=|y|
|94|`trade_cal`|3|3|low|=|y|
|95|`trade_orders`|17|0|low|init||
|96|`weekly_kline`|9|9|low|=|y|

## §2 严重度详情

### `candidate_pools` — high MON=no

- 类型(11): owner_user_id(character varying/varchar(64));pool_id(character varying/varchar(100));source_mode(character varying/varchar(60));account_id(character varying/varchar(100));visibility(character varying/varchar(20));source_module(character varying/varchar(40));created_at(timestamp with time zone/timestamptz);name(character varying/varchar(120));updated_at(timestamp with time zone/timestamptz);tenant_id(character varying/varchar(100));data_scope(character varying/varchar(20))

### `limit_list_d` — high MON=yes

- 仅DB[1]: limit
- 仅init[1]: "limit"
- PK差: DB=[] init=['id']
- UQ差: DB+[['trade_date', 'ts_code', 'up_stat']] init+[]
- legacy索引: idx_limit_list_d_date

### `stk_mins` — high MON=yes

- 类型(1): trade_time(text/timestamp)
- legacy索引: idx_stk_mins_code_time
- 缺索引: idx_stk_mins_code

### `strategy_plans` — high MON=no

- 类型(13): plan_id(character varying/varchar(100));owner_user_id(character varying/varchar(64));account_id(character varying/varchar(100));capital(numeric/numeric(18,2));visibility(character varying/varchar(20));single_max_pct(numeric/numeric(8,4));model_name(character varying/varchar(80));created_at(timestamp with time zone/timestamptz);name(character varying/varchar(120));updated_at(timestamp with time zone/timestamptz);tenant_id(character varying/varchar(100));data_scope(character varying/varchar(20));status(character varying/varchar(30))

### `ths_concept_map` — high MON=no

- 仅DB[3]: list_date,name,type
- 仅init[4]: concept_code,concept_name,id,trade_date
- PK差: DB=['ts_code'] init=['id']
- UQ差: DB+[] init+[['concept_name', 'ts_code']]
- 缺索引: idx_ths_concept_map_code,idx_ths_concept_map_concept

### `adj_factor` — medium MON=yes

- legacy索引: idx_adj_factor_date

### `block_trade_data` — medium MON=yes

- legacy索引: idx_block_trade_date

### `cyq_chips` — medium MON=yes

- legacy索引: idx_cyq_chips_date

### `daily_basic` — medium MON=yes

- legacy索引: idx_daily_basic_date

### `daily_kline` — medium MON=yes

- legacy索引: idx_dk_code_date_ohlcv

### `hk_holdings` — medium MON=yes

- legacy索引: idx_hk_holdings_date

### `index_daily` — medium MON=yes

- legacy索引: idx_index_daily_date

### `margin_detail` — medium MON=yes

- legacy索引: idx_margin_detail_date

### `margin_summary` — medium MON=yes

- legacy索引: idx_margin_summary_date

### `moneyflow` — medium MON=yes

- legacy索引: idx_moneyflow_date

### `moneyflow_hsgt` — medium MON=yes

- legacy索引: idx_moneyflow_hsgt_date

### `rt_k` — medium MON=yes

- 仅DB[1]: code
- 仅init[1]: ts_code
- UQ差: DB+[['code', 'trade_date']] init+[['trade_date', 'ts_code']]
- legacy索引: idx_rt_k_code,idx_rt_k_date

### `rt_sw_k` — medium MON=yes

- legacy索引: idx_rt_sw_k_date

### `stk_auction_o` — medium MON=no

- 仅DB[1]: updated_at
- legacy索引: idx_stk_auction_o_code,idx_stk_auction_o_date

### `stk_factor_pro` — medium MON=yes

- UQ差: DB+[['trade_date', 'ts_code']] init+[]

### `stk_limit` — medium MON=yes

- legacy索引: idx_stk_limit_date

### `sw_daily` — medium MON=yes

- legacy索引: idx_sw_daily_date

### `top_list` — medium MON=yes

- legacy索引: idx_top_list_date

## §3 子ADR建议

按ADR-014§决策4(列差≥3/PK/类型/下游):

### ADR-14.1: `candidate_pools`
- DB列14 vs init_sql14 | 涉及下游(MONITORED): no
- 关键 diff: 类型(11): owner_user_id(character varying/varchar(64));pool_id(character varying/varchar(100));source_mode(character varying/varchar(60));account_id(character varying/varchar(100));visibility(character varying/varchar(20));source_module(character varying/varchar(40));created_at(timestamp with time zone/timestamptz);name(character varying/varchar(120));updated_at(timestamp with time zone/timestamptz);tenant_id(character varying/varchar(100));data_scope(character varying/varchar(20))
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.2: `limit_list_d`
- DB列24 vs init_sql24 | 涉及下游(MONITORED): yes
- 关键 diff: 仅DB[1]: limit
- 关键 diff: 仅init[1]: "limit"
- 关键 diff: PK差: DB=[] init=['id']
- 关键 diff: UQ差: DB+[['trade_date', 'ts_code', 'up_stat']] init+[]
- 关键 diff: legacy索引: idx_limit_list_d_date
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.3: `stk_mins`
- DB列10 vs init_sql10 | 涉及下游(MONITORED): yes
- 关键 diff: 类型(1): trade_time(text/timestamp)
- 关键 diff: legacy索引: idx_stk_mins_code_time
- 关键 diff: 缺索引: idx_stk_mins_code
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.4: `strategy_plans`
- DB列16 vs init_sql16 | 涉及下游(MONITORED): no
- 关键 diff: 类型(13): plan_id(character varying/varchar(100));owner_user_id(character varying/varchar(64));account_id(character varying/varchar(100));capital(numeric/numeric(18,2));visibility(character varying/varchar(20));single_max_pct(numeric/numeric(8,4));model_name(character varying/varchar(80));created_at(timestamp with time zone/timestamptz);name(character varying/varchar(120));updated_at(timestamp with time zone/timestamptz);tenant_id(character varying/varchar(100));data_scope(character varying/varchar(20));status(character varying/varchar(30))
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.5: `ths_concept_map`
- DB列4 vs init_sql5 | 涉及下游(MONITORED): no
- 关键 diff: 仅DB[3]: list_date,name,type
- 关键 diff: 仅init[4]: concept_code,concept_name,id,trade_date
- 关键 diff: PK差: DB=['ts_code'] init=['id']
- 关键 diff: UQ差: DB+[] init+[['concept_name', 'ts_code']]
- 关键 diff: 缺索引: idx_ths_concept_map_code,idx_ths_concept_map_concept
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

## §4 轻量对齐

- `adj_factor` (medium MON=yes): legacy索引: idx_adj_factor_date
- `apscheduler_jobs` (low MON=no): init独有(DB缺)
- `auto_trading_strategies` (low MON=no): DB独有(init缺)
- `block_trade_data` (medium MON=yes): legacy索引: idx_block_trade_date
- `broker_accounts` (low MON=no): init独有(DB缺)
- `cb_call` (low MON=no): 缺索引: idx_cb_call_code,idx_cb_call_date
- `cb_daily` (low MON=no): 缺索引: idx_cb_daily_code,idx_cb_daily_date
- `cb_factor` (low MON=no): 缺索引: idx_cb_factor_code,idx_cb_factor_date
- `cb_price_chg` (low MON=no): 缺索引: idx_cb_price_chg_code
- `cb_sector` (low MON=no): init独有(DB缺)
- `chain_nodes` (low MON=no): init独有(DB缺)
- `company_bom_mapping` (low MON=no): init独有(DB缺)
- `company_chain_mapping` (low MON=no): init独有(DB缺)
- `company_evidence` (low MON=no): init独有(DB缺)
- `cyq_chips` (medium MON=yes): legacy索引: idx_cyq_chips_date
- `daily_basic` (medium MON=yes): legacy索引: idx_daily_basic_date
- `daily_kline` (medium MON=yes): legacy索引: idx_dk_code_date_ohlcv
- `decision_contexts` (low MON=no): init独有(DB缺)
- `experiments` (low MON=no): init独有(DB缺)
- `fina_audit` (low MON=yes): 缺索引: idx_fina_audit_result
- `hk_holdings` (medium MON=yes): legacy索引: idx_hk_holdings_date
- `index_daily` (medium MON=yes): legacy索引: idx_index_daily_date
- `industry_themes` (low MON=no): init独有(DB缺)
- `limit_list_d_2026_null_backup_20260630` (low MON=no): init独有(DB缺)
- `manual_overrides` (low MON=no): init独有(DB缺)
- `margin_detail` (medium MON=yes): legacy索引: idx_margin_detail_date
- `margin_summary` (medium MON=yes): legacy索引: idx_margin_summary_date
- `membership_events` (low MON=no): init独有(DB缺)
- `memberships` (low MON=no): init独有(DB缺)
- `metrics` (low MON=no): init独有(DB缺)
- `model_versions` (low MON=no): init独有(DB缺)
- `moneyflow` (medium MON=yes): legacy索引: idx_moneyflow_date
- `moneyflow_hsgt` (medium MON=yes): legacy索引: idx_moneyflow_hsgt_date
- `params` (low MON=no): init独有(DB缺)
- `policy_interpretations` (low MON=no): init独有(DB缺)
- `policy_sources` (low MON=no): init独有(DB缺)
- `policy_themes` (low MON=no): init独有(DB缺)
- `risk_verdicts` (low MON=no): init独有(DB缺)
- `role_permissions` (low MON=no): init独有(DB缺)
- `rt_k` (medium MON=yes): 仅DB[1]: code; 仅init[1]: ts_code; UQ差: DB+[['code', 'trade_date']] init+[['trade_date', 'ts_code']]; legacy索引: idx_rt_k_code,idx_rt_k_date
- `rt_sw_k` (medium MON=yes): legacy索引: idx_rt_sw_k_date
- `runs` (low MON=no): init独有(DB缺)
- `screening_models` (low MON=no): init独有(DB缺)
- `stk_auction_o` (medium MON=no): 仅DB[1]: updated_at; legacy索引: idx_stk_auction_o_code,idx_stk_auction_o_date
- `stk_factor_pro` (medium MON=yes): UQ差: DB+[['trade_date', 'ts_code']] init+[]
- `stk_limit` (medium MON=yes): legacy索引: idx_stk_limit_date
- `stock_profiles` (low MON=yes): 缺索引: idx_stock_profiles_province
- `supply_chain_bom_edges` (low MON=no): init独有(DB缺)
- `supply_chain_bom_nodes` (low MON=no): init独有(DB缺)
- `supply_chain_scores` (low MON=no): init独有(DB缺)
- `sw_daily` (medium MON=yes): legacy索引: idx_sw_daily_date
- `sync_schedules` (low MON=no): init独有(DB缺)
- `tags` (low MON=no): init独有(DB缺)
- `tenants` (low MON=no): init独有(DB缺)
- `ths_index` (low MON=no): init独有(DB缺)
- `ths_member` (low MON=no): init独有(DB缺)
- `top_list` (medium MON=yes): legacy索引: idx_top_list_date
- `trade_orders` (low MON=no): init独有(DB缺)

## §5 索引登记

|表|索引|列|来源|状态|
|---|---|---|---|---|
|adj_factor|idx_adj_factor_date|(trade_date)|init:n/DB:y|i-miss|
|apscheduler_jobs|ix_apscheduler_jobs_next_run_time|(next_run_time)|init:n/DB:y|i-miss|
|auto_trading_strategies|idx_auto_trading_strategies_status_updated|(status,updated_at)|init:y/DB:n|d-miss|
|auto_trading_strategies|idx_auto_trading_strategies_strategy_id|(strategy_id)|init:y/DB:n|d-miss|
|block_trade_data|idx_block_trade_date|(trade_date)|init:n/DB:y|i-miss|
|broker_accounts|ix_broker_accounts_owner_user_id|(owner_user_id)|init:n/DB:y|i-miss|
|broker_accounts|ix_broker_accounts_tenant_id|(tenant_id)|init:n/DB:y|i-miss|
|candidate_pools|idx_candidate_pools_pool_id|(pool_id)|init:y/DB:y|synced|
|candidate_pools|idx_candidate_pools_scope_updated|(tenant_id,owner_user_id,account_id,updated_at)|init:y/DB:y|synced|
|candidate_pools|idx_candidate_pools_source|(source_module,source_mode,updated_at)|init:y/DB:y|synced|
|cb_call|idx_cb_call_code|(ts_code)|init:y/DB:n|d-miss|
|cb_call|idx_cb_call_date|(call_date)|init:y/DB:n|d-miss|
|cb_concept|idx_cb_concept_code|(ts_code)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_name|(concept)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_code|(ts_code)|init:y/DB:n|d-miss|
|cb_daily|idx_cb_daily_date|(trade_date)|init:y/DB:n|d-miss|
|cb_factor|idx_cb_factor_code|(ts_code)|init:y/DB:n|d-miss|
|cb_factor|idx_cb_factor_date|(trade_date)|init:y/DB:n|d-miss|
|cb_price_chg|idx_cb_price_chg_code|(ts_code)|init:y/DB:n|d-miss|
|chain_nodes|idx_chain_nodes_theme_chain|(theme_id,layer)|init:n/DB:y|i-miss|
|company_bom_mapping|idx_company_bom_mapping_code|(code)|init:n/DB:y|i-miss|
|company_bom_mapping|idx_company_bom_mapping_node|(node_id)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_code|(code)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_node|(node_id)|init:n/DB:y|i-miss|
|company_chain_mapping|idx_company_chain_mapping_resonance|(chokepoint_score DESC NULLS LAST)|init:n/DB:y|i-miss|
|company_evidence|idx_company_evidence_code|(code)|init:n/DB:y|i-miss|
|company_evidence|idx_company_evidence_node|(node_id)|init:n/DB:y|i-miss|
|cyq_chips|idx_cyq_chips_date|(trade_date)|init:n/DB:y|i-miss|
|daily_basic|idx_daily_basic_date|(trade_date)|init:n/DB:y|i-miss|
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
|fina_audit|idx_fina_audit_result|(audit_result)|init:y/DB:n|d-miss|
|hk_holdings|idx_hk_holdings_date|(trade_date)|init:n/DB:y|i-miss|
|index_daily|idx_index_daily_date|(trade_date)|init:n/DB:y|i-miss|
|interact_qa|idx_interact_qa_code|(code)|init:y/DB:y|synced|
|interact_qa|idx_interact_qa_date|(pub_date)|init:y/DB:y|synced|
|limit_list_d|idx_limit_list_d_date|(trade_date)|init:n/DB:y|i-miss|
|margin_detail|idx_margin_detail_date|(trade_date)|init:n/DB:y|i-miss|
|margin_summary|idx_margin_summary_date|(trade_date)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_created_by_user_id|(created_by_user_id)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_membership_id|(membership_id)|init:n/DB:y|i-miss|
|membership_events|ix_membership_events_user_id|(user_id)|init:n/DB:y|i-miss|
|memberships|ix_memberships_tenant_id|(tenant_id)|init:n/DB:y|i-miss|
|memberships|ix_memberships_user_id|(user_id)|init:n/DB:y|i-miss|
|moneyflow|idx_moneyflow_date|(trade_date)|init:n/DB:y|i-miss|
|moneyflow_hsgt|idx_moneyflow_hsgt_date|(trade_date)|init:n/DB:y|i-miss|
|policy_interpretations|idx_policy_interpretations_created_at|(created_at)|init:n/DB:y|i-miss|
|policy_law|idx_policy_law_ptype|(ptype)|init:y/DB:y|synced|
|policy_law|idx_policy_law_puborg|(puborg)|init:y/DB:y|synced|
|policy_sources|idx_policy_sources_published_at|(published_at)|init:n/DB:y|i-miss|
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
|stk_limit|idx_stk_limit_date|(trade_date)|init:n/DB:y|i-miss|
|stk_mins|idx_stk_mins_code|(code)|init:y/DB:n|d-miss|
|stk_mins|idx_stk_mins_code_time|(code,trade_time)|init:n/DB:y|i-miss|
|stk_mins|idx_stk_mins_time|(trade_time)|init:y/DB:y|synced|
|stock_profiles|idx_stock_profiles_province|(province)|init:y/DB:n|d-miss|
|strategy_plans|idx_strategy_plans_plan_id|(plan_id)|init:y/DB:y|synced|
|strategy_plans|idx_strategy_plans_scope_updated|(tenant_id,owner_user_id,account_id,updated_at)|init:y/DB:y|synced|
|strategy_plans|idx_strategy_plans_status|(status)|init:y/DB:y|synced|
|supply_chain_bom_nodes|idx_bom_nodes_theme_chain|(theme_id,chain_id)|init:n/DB:y|i-miss|
|supply_chain_scores|idx_supply_chain_scores_code_date|(code,trade_date)|init:n/DB:y|i-miss|
|sw_daily|idx_sw_daily_date|(trade_date)|init:n/DB:y|i-miss|
|tenants|ix_tenants_slug|(slug)|init:n/DB:y|i-miss|
|ths_concept_map|idx_ths_concept_map_code|(ts_code)|init:y/DB:n|d-miss|
|ths_concept_map|idx_ths_concept_map_concept|(concept_name)|init:y/DB:n|d-miss|
|top_list|idx_top_list_date|(trade_date)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_candidate_id|(candidate_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_code_created|(code,created_at)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_decision_context_id|(decision_context_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_order_id|(order_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_plan_id|(plan_id)|init:n/DB:y|i-miss|
|trade_orders|idx_trade_orders_scope_created|(tenant_id,account_id,created_at)|init:n/DB:y|i-miss|

## §6 ADR-010 F-1 收尾

**F-1 背景**: ADR-010 backlog `idx_cyq_chips_date` schema drift (init_sql 未声明, DB 实存); ADR-011 review §1.3 / S-5 升级合并入本 ADR-014。

**F-1 处置查证 (cyq_chips / top_inst 虽在 EXCLUDED, 此段单查索引现状)**:
- `cyq_chips.idx_cyq_chips_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)
- `top_inst.idx_top_inst_code_date`: DB=yes init_sql=yes → COMPLETED(synced)
- `top_inst.idx_top_inst_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)

**F-1 结论**: idx_cyq_chips_date / idx_top_inst_date 在 ADR-010/011 alembic 迁移后已清理 — F-1 跟踪项可关闭; §5 索引登记表覆盖全审计范围 drift 索引, F-1 合并至本 ADR-014, ADR-010 backlog F-1 关闭。
