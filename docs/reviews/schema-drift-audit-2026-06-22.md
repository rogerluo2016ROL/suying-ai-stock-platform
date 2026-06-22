# Schema Drift Audit Report — 2026-06-22
**ADR-014 | UAT PG(16432) read-only**

## §1 审计范围

- DB 93张 | init_sql 68张 | 审计 71张 | 排除 22张
- P1-4 已纳入审计的数据管道表 (原 EXCLUDED): sw_daily, pledge_detail, rt_sw_k, top_list, cyq_chips
- ADR-008~011 已修仍排除表 (不重复扫): ths_daily, top_inst (top_inst 索引见 §6)
- 应用层排除表 (auth/training/diagnosis/screening/prediction/backtest/factor): 20 张
- high=4 medium=17 low=50
- MONITORED双缺(DB+init均无): 无
### 审计表清单 (71张)

|#|表|DB列|init列|严重|状态|MON|
|---|---|---|---|---|---|---|
|1|`adj_factor`|3|3|medium|=|y|
|2|`announcements`|5|5|low|=|y|
|3|`apscheduler_jobs`|3|0|low|init||
|4|`block_trade_data`|7|7|medium|=|y|
|5|`broker_recommend`|3|3|low|=|y|
|6|`cb_basic`|38|38|low|=||
|7|`cb_call`|12|12|low|=||
|8|`cb_concept`|4|4|low|=||
|9|`cb_daily`|16|16|low|=||
|10|`cb_factor`|23|23|low|=||
|11|`cb_price_chg`|8|8|low|=||
|12|`cb_sector`|3|0|low|init||
|13|`cctv_news`|5|5|low|=|y|
|14|`cyq_chips`|4|4|medium|=|y|
|15|`daily_basic`|8|8|medium|=|y|
|16|`daily_kline`|12|12|medium|=|y|
|17|`dividend_data`|5|5|low|=|y|
|18|`experiments`|4|0|low|init||
|19|`fina_audit`|7|7|low|=|y|
|20|`fina_mainbz`|6|6|low|=|y|
|21|`financial_abstracts`|3|3|low|=||
|22|`financial_balance`|6|6|low|=|y|
|23|`financial_cashflow`|6|6|low|=|y|
|24|`financial_income`|7|7|low|=|y|
|25|`financial_indicator`|12|12|low|=|y|
|26|`forecast_data`|4|4|low|=|y|
|27|`hk_holdings`|4|4|medium|=|y|
|28|`index_basic`|4|4|low|=||
|29|`index_daily`|9|9|medium|=|y|
|30|`interact_qa`|7|7|low|=|y|
|31|`limit_list_d`|24|15|high|=|y|
|32|`margin_detail`|8|8|medium|=|y|
|33|`margin_summary`|3|3|medium|=|y|
|34|`metrics`|4|0|low|init||
|35|`model_versions`|8|0|low|init||
|36|`moneyflow`|11|11|medium|=|y|
|37|`moneyflow_hsgt`|9|3|high|=|y|
|38|`monthly_kline`|9|9|low|=|y|
|39|`mp_report`|6|6|low|=|y|
|40|`params`|3|0|low|init||
|41|`pledge_detail`|6|6|low|=|y|
|42|`policy_law`|8|8|low|=|y|
|43|`profit_forecasts`|5|5|low|=||
|44|`repurchase`|4|4|low|=|y|
|45|`research_reports`|6|6|low|=||
|46|`research_reports_tushare`|6|6|low|=|y|
|47|`rt_k`|12|12|medium|=|y|
|48|`rt_sw_k`|11|11|medium|=|y|
|49|`runs`|13|0|low|init||
|50|`screening_models`|7|0|low|init||
|51|`share_float`|4|4|low|=|y|
|52|`st_history`|5|5|low|=||
|53|`stk_auction_o`|11|10|medium|=||
|54|`stk_factor_pro`|21|21|medium|=|y|
|55|`stk_holdernumber`|3|3|low|=|y|
|56|`stk_holdertrade`|7|7|low|=|y|
|57|`stk_limit`|6|6|medium|=|y|
|58|`stk_mins`|10|10|high|=|y|
|59|`stock_news`|5|5|low|=||
|60|`stock_news_tushare`|5|5|low|=|y|
|61|`stock_profiles`|16|16|low|=|y|
|62|`stocks`|11|11|low|=|y|
|63|`sw_daily`|15|15|medium|=|y|
|64|`sync_schedules`|10|0|low|init||
|65|`tags`|3|0|low|init||
|66|`ths_concept_map`|4|5|high|=||
|67|`ths_index`|6|0|low|init||
|68|`ths_member`|8|0|low|init||
|69|`top_list`|11|11|medium|=|y|
|70|`trade_cal`|3|3|low|=|y|
|71|`weekly_kline`|9|9|low|=|y|

## §2 严重度详情

### `limit_list_d` — high MON=yes

- 仅DB[10]: down_limit,id,industry,limit,limit_amount,limit_type,open,pre_close,total_mv,up_limit
- 仅init[1]: code
- 类型(1): trade_date(text/date)
- PK差: DB=[] init=['code', 'trade_date']
- UQ差: DB+[['limit_type', 'trade_date', 'ts_code'], ['trade_date', 'ts_code', 'up_stat']] init+[]
- legacy索引: idx_limit_list_d_date

### `moneyflow_hsgt` — high MON=yes

- 仅DB[6]: ggt_ss,ggt_sz,hgt,north_money,sgt,south_money
- legacy索引: idx_moneyflow_hsgt_date

### `stk_mins` — high MON=yes

- 类型(1): trade_time(text/timestamp)
- legacy索引: idx_stk_mins_code_time
- 缺索引: idx_stk_mins_code

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

### ADR-14.1: `limit_list_d`
- DB列24 vs init_sql15 | 涉及下游(MONITORED): yes
- 关键 diff: 仅DB[10]: down_limit,id,industry,limit,limit_amount,limit_type,open,pre_close,total_mv,up_limit
- 关键 diff: 仅init[1]: code
- 关键 diff: 类型(1): trade_date(text/date)
- 关键 diff: PK差: DB=[] init=['code', 'trade_date']
- 关键 diff: UQ差: DB+[['limit_type', 'trade_date', 'ts_code'], ['trade_date', 'ts_code', 'up_stat']] init+[]
- 关键 diff: legacy索引: idx_limit_list_d_date
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.2: `moneyflow_hsgt`
- DB列9 vs init_sql3 | 涉及下游(MONITORED): yes
- 关键 diff: 仅DB[6]: ggt_ss,ggt_sz,hgt,north_money,sgt,south_money
- 关键 diff: legacy索引: idx_moneyflow_hsgt_date
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.3: `stk_mins`
- DB列10 vs init_sql10 | 涉及下游(MONITORED): yes
- 关键 diff: 类型(1): trade_time(text/timestamp)
- 关键 diff: legacy索引: idx_stk_mins_code_time
- 关键 diff: 缺索引: idx_stk_mins_code
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.4: `ths_concept_map`
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
- `block_trade_data` (medium MON=yes): legacy索引: idx_block_trade_date
- `cb_call` (low MON=no): 缺索引: idx_cb_call_code,idx_cb_call_date
- `cb_daily` (low MON=no): 缺索引: idx_cb_daily_code,idx_cb_daily_date
- `cb_factor` (low MON=no): 缺索引: idx_cb_factor_code,idx_cb_factor_date
- `cb_price_chg` (low MON=no): 缺索引: idx_cb_price_chg_code
- `cb_sector` (low MON=no): init独有(DB缺)
- `cyq_chips` (medium MON=yes): legacy索引: idx_cyq_chips_date
- `daily_basic` (medium MON=yes): legacy索引: idx_daily_basic_date
- `daily_kline` (medium MON=yes): legacy索引: idx_dk_code_date_ohlcv
- `experiments` (low MON=no): init独有(DB缺)
- `fina_audit` (low MON=yes): 缺索引: idx_fina_audit_result
- `hk_holdings` (medium MON=yes): legacy索引: idx_hk_holdings_date
- `index_daily` (medium MON=yes): legacy索引: idx_index_daily_date
- `margin_detail` (medium MON=yes): legacy索引: idx_margin_detail_date
- `margin_summary` (medium MON=yes): legacy索引: idx_margin_summary_date
- `metrics` (low MON=no): init独有(DB缺)
- `model_versions` (low MON=no): init独有(DB缺)
- `moneyflow` (medium MON=yes): legacy索引: idx_moneyflow_date
- `params` (low MON=no): init独有(DB缺)
- `rt_k` (medium MON=yes): 仅DB[1]: code; 仅init[1]: ts_code; UQ差: DB+[['code', 'trade_date']] init+[['trade_date', 'ts_code']]; legacy索引: idx_rt_k_code,idx_rt_k_date
- `rt_sw_k` (medium MON=yes): legacy索引: idx_rt_sw_k_date
- `runs` (low MON=no): init独有(DB缺)
- `screening_models` (low MON=no): init独有(DB缺)
- `stk_auction_o` (medium MON=no): 仅DB[1]: updated_at; legacy索引: idx_stk_auction_o_code,idx_stk_auction_o_date
- `stk_factor_pro` (medium MON=yes): UQ差: DB+[['trade_date', 'ts_code']] init+[]
- `stk_limit` (medium MON=yes): legacy索引: idx_stk_limit_date
- `stock_profiles` (low MON=yes): 缺索引: idx_stock_profiles_province
- `sw_daily` (medium MON=yes): legacy索引: idx_sw_daily_date
- `sync_schedules` (low MON=no): init独有(DB缺)
- `tags` (low MON=no): init独有(DB缺)
- `ths_index` (low MON=no): init独有(DB缺)
- `ths_member` (low MON=no): init独有(DB缺)
- `top_list` (medium MON=yes): legacy索引: idx_top_list_date

## §5 索引登记

|表|索引|列|来源|状态|
|---|---|---|---|---|
|adj_factor|idx_adj_factor_date|(trade_date)|init:n/DB:y|i-miss|
|apscheduler_jobs|ix_apscheduler_jobs_next_run_time|(next_run_time)|init:n/DB:y|i-miss|
|block_trade_data|idx_block_trade_date|(trade_date)|init:n/DB:y|i-miss|
|cb_call|idx_cb_call_code|(ts_code)|init:y/DB:n|d-miss|
|cb_call|idx_cb_call_date|(call_date)|init:y/DB:n|d-miss|
|cb_concept|idx_cb_concept_code|(ts_code)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_name|(concept)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_code|(ts_code)|init:y/DB:n|d-miss|
|cb_daily|idx_cb_daily_date|(trade_date)|init:y/DB:n|d-miss|
|cb_factor|idx_cb_factor_code|(ts_code)|init:y/DB:n|d-miss|
|cb_factor|idx_cb_factor_date|(trade_date)|init:y/DB:n|d-miss|
|cb_price_chg|idx_cb_price_chg_code|(ts_code)|init:y/DB:n|d-miss|
|cyq_chips|idx_cyq_chips_date|(trade_date)|init:n/DB:y|i-miss|
|daily_basic|idx_daily_basic_date|(trade_date)|init:n/DB:y|i-miss|
|daily_kline|idx_daily_kline_code|(code)|init:y/DB:y|synced|
|daily_kline|idx_daily_kline_date|(trade_date)|init:y/DB:y|synced|
|daily_kline|idx_dk_code_date_ohlcv|(code,trade_date,open,volume,amount)|init:n/DB:y|i-miss|
|fina_audit|idx_fina_audit_result|(audit_result)|init:y/DB:n|d-miss|
|hk_holdings|idx_hk_holdings_date|(trade_date)|init:n/DB:y|i-miss|
|index_daily|idx_index_daily_date|(trade_date)|init:n/DB:y|i-miss|
|interact_qa|idx_interact_qa_code|(code)|init:y/DB:y|synced|
|interact_qa|idx_interact_qa_date|(pub_date)|init:y/DB:y|synced|
|limit_list_d|idx_limit_list_d_date|(trade_date)|init:n/DB:y|i-miss|
|margin_detail|idx_margin_detail_date|(trade_date)|init:n/DB:y|i-miss|
|margin_summary|idx_margin_summary_date|(trade_date)|init:n/DB:y|i-miss|
|moneyflow|idx_moneyflow_date|(trade_date)|init:n/DB:y|i-miss|
|moneyflow_hsgt|idx_moneyflow_hsgt_date|(trade_date)|init:n/DB:y|i-miss|
|policy_law|idx_policy_law_ptype|(ptype)|init:y/DB:y|synced|
|policy_law|idx_policy_law_puborg|(puborg)|init:y/DB:y|synced|
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
|sw_daily|idx_sw_daily_date|(trade_date)|init:n/DB:y|i-miss|
|ths_concept_map|idx_ths_concept_map_code|(ts_code)|init:y/DB:n|d-miss|
|ths_concept_map|idx_ths_concept_map_concept|(concept_name)|init:y/DB:n|d-miss|
|top_list|idx_top_list_date|(trade_date)|init:n/DB:y|i-miss|

## §6 ADR-010 F-1 收尾

**F-1 背景**: ADR-010 backlog `idx_cyq_chips_date` schema drift (init_sql 未声明, DB 实存); ADR-011 review §1.3 / S-5 升级合并入本 ADR-014。

**F-1 处置查证 (cyq_chips / top_inst 虽在 EXCLUDED, 此段单查索引现状)**:
- `cyq_chips.idx_cyq_chips_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)
- `top_inst.idx_top_inst_code_date`: DB=yes init_sql=yes → COMPLETED(synced)
- `top_inst.idx_top_inst_date`: DB=yes init_sql=no → OPEN(入轻量对齐: init_sql 补 CREATE INDEX)

**F-1 结论**: idx_cyq_chips_date / idx_top_inst_date 在 ADR-010/011 alembic 迁移后已清理 — F-1 跟踪项可关闭; §5 索引登记表覆盖全审计范围 drift 索引, F-1 合并至本 ADR-014, ADR-010 backlog F-1 关闭。
