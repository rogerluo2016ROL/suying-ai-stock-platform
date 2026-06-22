# Schema Drift Audit Report — 2026-06-22
**ADR-014 | UAT PG(16432) read-only**

## §1 审计范围

- DB 79张 | init_sql 66张 | 审计 54张 | 排除 27张
- ADR-008~013 已修排除表 (本审计不重复扫): ths_daily, sw_daily, pledge_detail, rt_sw_k, top_list, cyq_chips, top_inst
- 应用层排除表 (auth/training/diagnosis/screening/prediction/backtest/factor): 20 张
- high=2 medium=0 low=52
- MONITORED双缺(DB+init均无): ['stk_factor_pro', 'trade_cal']
### 审计表清单 (54张)

|#|表|DB列|init列|严重|状态|MON|
|---|---|---|---|---|---|---|
|1|`adj_factor`|3|3|low|=|y|
|2|`announcements`|5|5|low|=|y|
|3|`block_trade_data`|7|7|low|=|y|
|4|`broker_recommend`|3|3|low|=|y|
|5|`cb_basic`|38|38|low|=||
|6|`cb_call`|12|12|low|=||
|7|`cb_concept`|4|4|low|=||
|8|`cb_daily`|16|16|low|=||
|9|`cb_factor`|23|23|low|=||
|10|`cb_price_chg`|8|8|low|=||
|11|`cctv_news`|5|5|low|=|y|
|12|`daily_basic`|8|8|low|=|y|
|13|`daily_kline`|12|12|low|=|y|
|14|`dividend_data`|5|5|low|=|y|
|15|`fina_audit`|7|7|low|=|y|
|16|`fina_mainbz`|6|6|low|=|y|
|17|`financial_abstracts`|3|3|low|=||
|18|`financial_balance`|6|6|low|=|y|
|19|`financial_cashflow`|6|6|low|=|y|
|20|`financial_income`|7|7|low|=|y|
|21|`financial_indicator`|12|12|low|=|y|
|22|`forecast_data`|4|4|low|=|y|
|23|`hk_holdings`|4|4|low|=|y|
|24|`index_basic`|4|4|low|=||
|25|`index_daily`|9|9|low|=|y|
|26|`interact_qa`|7|7|low|=|y|
|27|`limit_list_d`|15|15|low|=|y|
|28|`margin_detail`|8|8|low|=|y|
|29|`margin_summary`|3|3|low|=|y|
|30|`moneyflow`|11|11|low|=|y|
|31|`moneyflow_hsgt`|3|3|low|=|y|
|32|`monthly_kline`|9|9|low|=|y|
|33|`mp_report`|6|6|low|=|y|
|34|`policy_law`|8|8|low|=|y|
|35|`profit_forecasts`|5|5|low|=||
|36|`repurchase`|4|4|low|=|y|
|37|`research_reports`|6|6|low|=||
|38|`research_reports_tushare`|6|6|low|=|y|
|39|`rt_k`|12|12|low|=|y|
|40|`share_float`|4|4|low|=|y|
|41|`st_history`|5|5|low|=||
|42|`stk_auction_o`|10|10|low|=||
|43|`stk_factor_pro`|0|0|high|DB|y|
|44|`stk_holdernumber`|3|3|low|=|y|
|45|`stk_holdertrade`|7|7|low|=|y|
|46|`stk_limit`|6|6|low|=|y|
|47|`stk_mins`|10|10|low|=|y|
|48|`stock_news`|5|5|low|=||
|49|`stock_news_tushare`|5|5|low|=|y|
|50|`stock_profiles`|16|16|low|=|y|
|51|`stocks`|11|11|low|=|y|
|52|`ths_concept_map`|5|5|low|=||
|53|`trade_cal`|0|0|high|DB|y|
|54|`weekly_kline`|9|9|low|=|y|

## §2 严重度详情

### `stk_factor_pro` — high MON=yes

- MONITORED但DB+init双缺 — scheduler监控会报错

### `trade_cal` — high MON=yes

- MONITORED但DB+init双缺 — scheduler监控会报错

## §3 子ADR建议

按ADR-014§决策4(列差≥3/PK/类型/下游):

### ADR-14.1: `stk_factor_pro`
- DB列0 vs init_sql0 | 涉及下游(MONITORED): yes
- 关键 diff: MONITORED但DB+init双缺 — scheduler监控会报错
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

### ADR-14.2: `trade_cal`
- DB列0 vs init_sql0 | 涉及下游(MONITORED): yes
- 关键 diff: MONITORED但DB+init双缺 — scheduler监控会报错
- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)

## §4 轻量对齐

(无)

## §5 索引登记

|表|索引|列|来源|状态|
|---|---|---|---|---|
|cb_call|idx_cb_call_code|(ts_code)|init:y/DB:y|synced|
|cb_call|idx_cb_call_date|(call_date)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_code|(ts_code)|init:y/DB:y|synced|
|cb_concept|idx_cb_concept_name|(concept)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_code|(ts_code)|init:y/DB:y|synced|
|cb_daily|idx_cb_daily_date|(trade_date)|init:y/DB:y|synced|
|cb_factor|idx_cb_factor_code|(ts_code)|init:y/DB:y|synced|
|cb_factor|idx_cb_factor_date|(trade_date)|init:y/DB:y|synced|
|cb_price_chg|idx_cb_price_chg_code|(ts_code)|init:y/DB:y|synced|
|daily_kline|idx_daily_kline_code|(code)|init:y/DB:y|synced|
|daily_kline|idx_daily_kline_date|(trade_date)|init:y/DB:y|synced|
|fina_audit|idx_fina_audit_result|(audit_result)|init:y/DB:y|synced|
|interact_qa|idx_interact_qa_code|(code)|init:y/DB:y|synced|
|interact_qa|idx_interact_qa_date|(pub_date)|init:y/DB:y|synced|
|policy_law|idx_policy_law_ptype|(ptype)|init:y/DB:y|synced|
|policy_law|idx_policy_law_puborg|(puborg)|init:y/DB:y|synced|
|st_history|idx_st_history_code|(code)|init:y/DB:y|synced|
|st_history|idx_st_history_date|(start_date)|init:y/DB:y|synced|
|stk_mins|idx_stk_mins_code|(code)|init:y/DB:y|synced|
|stk_mins|idx_stk_mins_time|(trade_time)|init:y/DB:y|synced|
|stock_profiles|idx_stock_profiles_province|(province)|init:y/DB:y|synced|
|ths_concept_map|idx_ths_concept_map_code|(ts_code)|init:y/DB:y|synced|
|ths_concept_map|idx_ths_concept_map_concept|(concept_name)|init:y/DB:y|synced|

## §6 ADR-010 F-1 收尾

**F-1 背景**: ADR-010 backlog `idx_cyq_chips_date` schema drift (init_sql 未声明, DB 实存); ADR-011 review §1.3 / S-5 升级合并入本 ADR-014。

**F-1 处置查证 (cyq_chips / top_inst 虽在 EXCLUDED, 此段单查索引现状)**:
- `cyq_chips`: 无非PK/UNIQUE 索引 (DB=[] init_sql=[])
- `top_inst.idx_top_inst_code_date`: DB=yes init_sql=yes → COMPLETED(synced)

**F-1 结论**: idx_cyq_chips_date / idx_top_inst_date 在 ADR-010/011 alembic 迁移后已清理 — F-1 跟踪项可关闭; §5 索引登记表覆盖全审计范围 drift 索引, F-1 合并至本 ADR-014, ADR-010 backlog F-1 关闭。
