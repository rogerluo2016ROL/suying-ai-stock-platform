"""Database layer — connection management + DDL for stock_screening.db."""
import os
import sqlite3
import logging
from contextlib import contextmanager

logger = logging.getLogger("kronos-webui.db")

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stock_screening.db",
)


@contextmanager
def get_db(readonly: bool = False):
    """Context manager for database connections (auto-commit/close)."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    if not readonly:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        if not readonly:
            db.commit()
    except Exception:
        if not readonly:
            db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    with get_db() as db:
        _create_tables(db)
        _create_indexes(db)
    logger.info("Database initialized: %s", DB_PATH)


def _create_tables(db: sqlite3.Connection) -> None:
    db.executescript("""
        -- 1. 股票基础信息
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            board TEXT NOT NULL,
            industry TEXT,
            market_cap REAL,
            float_mv REAL,
            pe_ratio REAL,
            pb_ratio REAL,
            listed_date TEXT,
            is_st INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 2. 日线行情
        CREATE TABLE IF NOT EXISTS daily_kline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL,
            amount REAL,
            turnover_rate REAL,
            change_pct REAL,
            amplitude REAL,
            UNIQUE(code, trade_date)
        );

        -- 3. 评分结果
        CREATE TABLE IF NOT EXISTS screening_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            code TEXT NOT NULL,
            score REAL NOT NULL,
            grade TEXT NOT NULL,
            momentum REAL,
            volume_factor REAL,
            technical REAL,
            quality REAL,
            risk REAL,
            kronos_trend_score REAL,
            kronos_pred_return REAL,
            fund_score REAL,
            signal TEXT,
            reason TEXT,
            strategy TEXT,
            target_price REAL,
            stop_loss REAL,
            rank INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 4. 批次记录
        CREATE TABLE IF NOT EXISTS screening_batches (
            batch_id TEXT PRIMARY KEY,
            total_stocks INTEGER,
            scored_stocks INTEGER,
            top40_codes TEXT,
            elapsed REAL,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 5. 预测结果
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            code TEXT NOT NULL,
            pred_len INTEGER,
            lookback INTEGER,
            last_close REAL,
            pred_last_close REAL,
            pred_return_pct REAL,
            pred_max REAL,
            pred_min REAL,
            pred_data_json TEXT,
            temperature REAL,
            top_p REAL,
            sample_count INTEGER,
            elapsed REAL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 5b. 预测版本 (batch predict sessions)
        CREATE TABLE IF NOT EXISTS prediction_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_tag TEXT NOT NULL UNIQUE,
            stock_count INTEGER,
            pred_len INTEGER,
            params_json TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 5c. 版本内股票每日预测明细
        CREATE TABLE IF NOT EXISTS prediction_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER REFERENCES prediction_versions(id),
            code TEXT NOT NULL,
            stock_name TEXT,
            last_close REAL,
            pred_return_pct REAL,
            pred_last_close REAL,
            pred_max REAL,
            pred_min REAL,
            daily_json TEXT,
            elapsed REAL,
            UNIQUE(version_id, code)
        );
        CREATE INDEX IF NOT EXISTS idx_pred_details_version ON prediction_details(version_id);

        -- 6. 历史回溯
        CREATE TABLE IF NOT EXISTS backtest_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            code TEXT NOT NULL,
            rank INTEGER,
            score REAL,
            signal TEXT,
            pred_return REAL,
            actual_return_5d REAL,
            actual_return_10d REAL,
            actual_return_20d REAL,
            actual_return_60d REAL,
            hit INTEGER,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 7. 自选股
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            added_at TEXT DEFAULT (datetime('now','localtime')),
            notes TEXT
        );

        -- 8. 机构研报
        CREATE TABLE IF NOT EXISTS research_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            title TEXT,
            org_name TEXT,
            rating TEXT,
            rating_score INTEGER DEFAULT 5,
            target_price REAL,
            report_date TEXT,
            author TEXT,
            UNIQUE(code, title, report_date)
        );

        -- 9. 个股新闻 (for NLP enrichment)
        CREATE TABLE IF NOT EXISTS stock_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            source TEXT,
            news_time TEXT,
            url TEXT,
            sentiment_score REAL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, title, news_time)
        );

        -- 10. 机构盈利预测缓存
        CREATE TABLE IF NOT EXISTS profit_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            eps_forecast REAL,
            pe_forecast REAL,
            growth_pct REAL,
            forecast_count INTEGER,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 11. 季报财务摘要
        CREATE TABLE IF NOT EXISTS financial_abstracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            report_period TEXT NOT NULL,
            roe REAL, revenue REAL, revenue_yoy REAL,
            net_profit REAL, net_profit_yoy REAL,
            gross_margin REAL, net_margin REAL,
            debt_ratio REAL, eps REAL, operating_cf REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, report_period)
        );

        -- 12. 公告事件
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, title TEXT,
            ann_type TEXT, ann_date TEXT,
            event_score INTEGER DEFAULT 0,
            event_type TEXT, url TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, title, ann_date)
        );

        -- 13. 公司概况 (F10)
        CREATE TABLE IF NOT EXISTS stock_profiles (
            code TEXT PRIMARY KEY,
            company_name TEXT, industry_csrc TEXT,
            listed_date TEXT, registered_capital TEXT,
            chairman TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 14. Tushare 个股资金流向 (moneyflow)
        CREATE TABLE IF NOT EXISTS moneyflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            buy_sm_amount REAL,
            sell_sm_amount REAL,
            buy_md_amount REAL,
            sell_md_amount REAL,
            buy_lg_amount REAL,
            sell_lg_amount REAL,
            buy_elg_amount REAL,
            sell_elg_amount REAL,
            net_mf_amount REAL,
            net_mf_vol REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 15. Tushare 北向资金持股 (hk_hold)
        CREATE TABLE IF NOT EXISTS hk_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            vol INTEGER,
            ratio REAL,
            hold_vol REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 16. Tushare 融资融券明细 (margin_detail)
        CREATE TABLE IF NOT EXISTS margin_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            rzye REAL,
            rqye REAL,
            rzmre REAL,
            rqyl INTEGER,
            rzche REAL,
            rqchl REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 17. Tushare 龙虎榜 (top_list)
        CREATE TABLE IF NOT EXISTS top_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            name TEXT,
            close REAL,
            pct_change REAL,
            turnover_rate REAL,
            amount REAL,
            l_sell REAL,
            l_buy REAL,
            net_amount REAL,
            reason TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 18. Tushare 每日指标 (daily_basic)
        CREATE TABLE IF NOT EXISTS daily_basic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            turnover_rate REAL,
            turnover_rate_f REAL,
            volume_ratio REAL,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            ps_ttm REAL,
            dv_ratio REAL,
            total_mv REAL,
            circ_mv REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 19. Tushare 涨跌停价格 (stk_limit)
        CREATE TABLE IF NOT EXISTS stk_limit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            up_limit REAL,
            down_limit REAL,
            pre_close REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 20. 周线行情
        CREATE TABLE IF NOT EXISTS weekly_kline (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 21. 月线行情
        CREATE TABLE IF NOT EXISTS monthly_kline (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 22. 复权因子 (用于计算前复权/后复权价格)
        CREATE TABLE IF NOT EXISTS adj_factor (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            adj_factor REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date)
        );

        -- 23. 指数基本信息
        CREATE TABLE IF NOT EXISTS index_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            market TEXT,
            publisher TEXT,
            category TEXT,
            base_date TEXT,
            base_point REAL,
            list_date TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 24. 指数日线行情
        CREATE TABLE IF NOT EXISTS index_daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            close REAL, open REAL, high REAL, low REAL,
            pre_close REAL, change REAL, pct_chg REAL,
            vol REAL, amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(ts_code, trade_date)
        );

        -- 25. 利润表 (Tushare income)
        CREATE TABLE IF NOT EXISTS financial_income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            report_type TEXT,
            basic_eps REAL,
            total_revenue REAL,
            revenue REAL,
            oper_cost REAL,
            sell_expense REAL,
            admin_expense REAL,
            fin_expense REAL,
            n_income REAL,
            n_income_attr_p REAL,
            operate_profit REAL,
            total_profit REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date, report_type)
        );

        -- 26. 资产负债表 (Tushare balancesheet)
        CREATE TABLE IF NOT EXISTS financial_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            report_type TEXT,
            total_assets REAL,
            total_cur_assets REAL,
            total_liab REAL,
            total_cur_liab REAL,
            total_hldr_eqy_exc_min_int REAL,
            total_share REAL,
            cap_rese REAL,
            undistr_porfit REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date, report_type)
        );

        -- 27. 现金流量表 (Tushare cashflow)
        CREATE TABLE IF NOT EXISTS financial_cashflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            report_type TEXT,
            n_cashflow_act REAL,
            n_cashflow_inv_act REAL,
            n_cashflow_fin_act REAL,
            c_fr_sale_sg REAL,
            net_profit REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date, report_type)
        );

        -- 28. 财务指标 (Tushare fina_indicator)
        CREATE TABLE IF NOT EXISTS financial_indicator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            roe REAL, roa REAL,
            grossprofit_margin REAL,
            netprofit_margin REAL,
            debt_to_assets REAL,
            eps REAL, ocfps REAL,
            current_ratio REAL,
            quick_ratio REAL,
            or_yoy REAL, profit_dedt REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date)
        );

        -- 29. 业绩预告 (Tushare forecast)
        CREATE TABLE IF NOT EXISTS forecast_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            end_date TEXT,
            forecast_type TEXT,
            net_profit_min REAL,
            net_profit_max REAL,
            change_reason TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, ann_date, end_date)
        );

        -- 30. 分红送股 (Tushare dividend)
        CREATE TABLE IF NOT EXISTS dividend_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            ann_date TEXT,
            cash_div REAL,
            stk_div REAL,
            stk_bo_rate REAL,
            record_date TEXT,
            ex_date TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date, ann_date)
        );

        -- 32. 龙虎榜机构席位 (Tushare top_inst)
        CREATE TABLE IF NOT EXISTS top_inst (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            exalter TEXT,
            buy REAL, buy_rate REAL,
            sell REAL, sell_rate REAL,
            net_buy REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, trade_date, exalter)
        );

        -- 33. 大宗交易 (Tushare block_trade)
        CREATE TABLE IF NOT EXISTS block_trade_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            price REAL, vol REAL, amount REAL,
            buyer TEXT, seller TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 34. 融资融券汇总 (Tushare margin)
        CREATE TABLE IF NOT EXISTS margin_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            rzye REAL, rzmre REAL, rzche REAL,
            rqye REAL, rqmcl REAL, rzrqye REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(trade_date)
        );

        -- 35. 沪深港通资金流向 (Tushare moneyflow_hsgt)
        CREATE TABLE IF NOT EXISTS moneyflow_hsgt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ggt_ss REAL, ggt_sz REAL,
            hgt REAL, sgt REAL,
            north_money REAL, south_money REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(trade_date)
        );

        -- 36. 股东增减持 (Tushare stk_holdertrade)
        CREATE TABLE IF NOT EXISTS stk_holdertrade (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            holder_name TEXT,
            holder_type TEXT,
            in_de TEXT,
            change_vol REAL,
            change_ratio REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 37. 股东人数 (Tushare stk_holdernumber)
        CREATE TABLE IF NOT EXISTS stk_holdernumber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            holder_num INTEGER,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date)
        );

        -- 38. 股权质押 (Tushare pledge_detail)
        CREATE TABLE IF NOT EXISTS pledge_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            pledgor TEXT,
            pledgee TEXT,
            pledge_amount REAL,
            pledge_total_ratio REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 39. 股票回购 (Tushare repurchase)
        CREATE TABLE IF NOT EXISTS repurchase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            end_date TEXT,
            proc TEXT,
            vol REAL,
            amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 40. 限售解禁 (Tushare share_float)
        CREATE TABLE IF NOT EXISTS share_float (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            ann_date TEXT NOT NULL,
            float_date TEXT,
            float_share REAL,
            float_ratio REAL,
            holder_name TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 41. 筹码分布原始数据 (Tushare cyq_chips, 6000pts)
        -- Returns per-price-level data: each row = price level + holding %
        CREATE TABLE IF NOT EXISTS cyq_chips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            price REAL,
            percent REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_cyq_chips_code_date ON cyq_chips(code, trade_date);

        -- 42. 券商每月金股 (Tushare broker_recommend, 6000pts)
        CREATE TABLE IF NOT EXISTS broker_recommend (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            broker TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(month, broker, code)
        );
        CREATE INDEX IF NOT EXISTS idx_broker_recommend_month ON broker_recommend(month, code);

        -- 31. 主营业务构成 (Tushare fina_mainbz)
        CREATE TABLE IF NOT EXISTS fina_mainbz (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            bz_item TEXT,
            bz_sales REAL,
            bz_profit REAL,
            bz_cost REAL,
            curr_type TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(code, end_date, bz_item)
        );

        -- 43. 券商研报 (Tushare research_report, 独立权限)
        CREATE TABLE IF NOT EXISTS research_reports_tushare (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            title TEXT,
            report_type TEXT,
            author TEXT,
            name TEXT,
            code TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_research_tushare_code ON research_reports_tushare(code, trade_date);

        -- 44. 新闻资讯 (Tushare news, 独立权限)
        CREATE TABLE IF NOT EXISTS stock_news_tushare (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pub_time TEXT NOT NULL,
            title TEXT,
            content TEXT,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 45. 申万实时行情 (Tushare rt_sw_k, 独立权限 — real-time snapshot)
        CREATE TABLE IF NOT EXISTS rt_sw_k (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_time TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            name TEXT,
            close REAL, pre_close REAL,
            open REAL, high REAL, low REAL,
            vol REAL, amount REAL,
            pct_change REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(trade_time, ts_code)
        );

        -- 47. 实时日K线 (Tushare rt_k, Level-2 权限 — same-day only)
        CREATE TABLE IF NOT EXISTS rt_k (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            pre_close REAL, change REAL, pct_chg REAL,
            vol REAL, amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(ts_code, trade_date)
        );

        -- 48. 开盘集合竞价 (Tushare stk_auction_o, 特色数据权限)
        CREATE TABLE IF NOT EXISTS stk_auction_o (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pre_close REAL, price REAL,
            volume REAL, amount REAL,
            bid_volume REAL, ask_volume REAL,
            bid_amount REAL, ask_amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(ts_code, trade_date)
        );


        -- 46. 申万行业日线 (Tushare sw_daily, 独立权限)
        CREATE TABLE IF NOT EXISTS sw_daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            name TEXT,
            open REAL, high REAL, low REAL, close REAL,
            change REAL, pct_change REAL,
            pe REAL, pb REAL,
            float_mv REAL, total_mv REAL,
            vol REAL, amount REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(ts_code, trade_date)
        );
    """)


def _create_indexes(db: sqlite3.Connection) -> None:
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_stocks_board ON stocks(board)",
        "CREATE INDEX IF NOT EXISTS idx_stocks_industry ON stocks(industry)",
        "CREATE INDEX IF NOT EXISTS idx_daily_kline_code ON daily_kline(code)",
        "CREATE INDEX IF NOT EXISTS idx_daily_kline_date ON daily_kline(trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_kline_code_date ON daily_kline(code, trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_scores_batch ON screening_scores(batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_scores_code ON screening_scores(code)",
        "CREATE INDEX IF NOT EXISTS idx_scores_rank ON screening_scores(batch_id, rank)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_batch ON predictions(batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_code ON predictions(code)",
        "CREATE INDEX IF NOT EXISTS idx_backtest_batch ON backtest_records(batch_id)",
    ]
    for idx in indexes:
        db.execute(idx)
    # Additional index for batch queries
    db.execute("CREATE INDEX IF NOT EXISTS idx_screening_batches_created ON screening_batches(created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_code ON research_reports(code)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_date ON research_reports(code, report_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stock_news_code ON stock_news(code)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stock_news_time ON stock_news(code, news_time)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_financial_code ON financial_abstracts(code, report_period)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ann_code ON announcements(code, ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ann_date ON announcements(ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_moneyflow_code_date ON moneyflow(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_hk_holdings_code_date ON hk_holdings(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_margin_detail_code_date ON margin_detail(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_top_list_code_date ON top_list(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_daily_basic_code_date ON daily_basic(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stk_limit_code_date ON stk_limit(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_weekly_kline_code_date ON weekly_kline(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_monthly_kline_code_date ON monthly_kline(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_adj_factor_code_date ON adj_factor(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_index_daily_code_date ON index_daily(ts_code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fin_income_code ON financial_income(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fin_balance_code ON financial_balance(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fin_cashflow_code ON financial_cashflow(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fin_indicator_code ON financial_indicator(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_forecast_data_code ON forecast_data(code, ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_dividend_data_code ON dividend_data(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fina_mainbz_code ON fina_mainbz(code, end_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_top_inst_code_date ON top_inst(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_block_trade_data_code_date ON block_trade_data(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_margin_summary_date ON margin_summary(trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_moneyflow_hsgt_date ON moneyflow_hsgt(trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stk_holdertrade_code ON stk_holdertrade(code, ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stk_holdernumber_code ON stk_holdernumber(code)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pledge_detail_code ON pledge_detail(code)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_repurchase_code ON repurchase(code, ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_share_float_code ON share_float(code, ann_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cyq_chips_code_date ON cyq_chips(code, trade_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_broker_recommend_month ON broker_recommend(month, code)")


def ensure_columns(db: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add column if not exists (safe migration)."""
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        logger.info("Migrated %s.%s (%s)", table, column, ddl)


def write_screening_scores(db, scores, batch_id, engine_name="full_screening",
                           strategy_label="", top_n=40):
    """Write screening results to screening_scores + screening_batches.

    Handles column migrations, batch lifecycle (INSERT + UPDATE),
    and score INSERTs for any engine.

    Args:
        db: writable sqlite3.Connection
        scores: list of dicts with at least {code, score, grade, rank}
        batch_id: unique batch identifier
        engine_name: engine key (e.g. 'full_screening', 'leader_scalp')
        strategy_label: human-readable strategy name
        top_n: number of top picks to record in batch
    """
    import json as _json

    # Ensure engine/leader/seal columns exist
    for col, ddl in [
        ("engine", "engine TEXT DEFAULT ''"),
        ("leader_score", "leader_score REAL DEFAULT 0"),
        ("seal_score", "seal_score REAL DEFAULT 0"),
    ]:
        ensure_columns(db, "screening_scores", col, ddl)
    ensure_columns(db, "screening_batches", "engine", "engine TEXT DEFAULT ''")

    # Insert or replace batch record
    existing = db.execute(
        "SELECT batch_id FROM screening_batches WHERE batch_id=?", (batch_id,)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE screening_batches SET status='running',engine=? WHERE batch_id=?",
            (engine_name, batch_id),
        )
    else:
        db.execute(
            "INSERT INTO screening_batches (batch_id, status, engine) VALUES (?, 'running', ?)",
            (batch_id, engine_name),
        )

    # Write scores
    top_codes = []
    for s in scores:
        rank = s.get("rank", 0)
        if rank <= top_n:
            top_codes.append(s["code"])

        db.execute(
            "INSERT INTO screening_scores"
            "(batch_id,code,score,grade,momentum,volume_factor,"
            "technical,quality,risk,kronos_trend_score,"
            "kronos_pred_return,fund_score,target_price,stop_loss,"
            "nlp_score,nlp_sentiment,nlp_risk,nlp_event,"
            "money_flow_score,mean_reversion_score,"
            "trend_strength_score,reversal_score,liquidity_score,"
            "analyst_score,target_upside_pct,eps_growth_pct,"
            "report_count_3m,institutional_consensus,"
            "event_score,event_risk_flag,event_risk_reason,"
            "quality_score,roe,revenue_growth_pct,"
            "profit_growth_pct,gross_margin_pct,debt_ratio_pct,"
            "cf_positive,fundamental_grade,"
            "f10_score,sector_score,dividend_yield_pct,"
            "shareholder_signal,capital_score,"
            "north_bound_signal,level2_signal,"
            "buy_votes,total_votes,vote_ratio,"
            "signal,reason,strategy,rank,engine,leader_score,seal_score)"
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                batch_id, s["code"], s["score"], s["grade"],
                s.get("momentum", 0), s.get("volume_factor", 0),
                s.get("technical", 0),
                s.get("quality", 0), s.get("risk", 0),
                s.get("kronos_trend_score", 0),
                s.get("kronos_pred_return", 0), s.get("fund_score", 0),
                s.get("target_price"), s.get("stop_loss"),
                s.get("nlp_score", 0), s.get("nlp_sentiment", 0),
                s.get("nlp_risk", 0), s.get("nlp_event", ""),
                s.get("money_flow_score", 5.0),
                s.get("mean_reversion_score", 5.0),
                s.get("trend_strength_score", 5.0),
                s.get("reversal_score", 5.0),
                s.get("liquidity_score", 5.0),
                s.get("analyst_score", 5.0),
                s.get("target_upside_pct", 0),
                s.get("eps_growth_pct", 0),
                s.get("report_count_3m", 0),
                s.get("institutional_consensus", ""),
                s.get("event_score", 0),
                s.get("event_risk_flag", 0),
                s.get("event_risk_reason", ""),
                s.get("quality_score", 5.0),
                s.get("roe", 0),
                s.get("revenue_growth_pct", 0),
                s.get("profit_growth_pct", 0),
                s.get("gross_margin_pct", 0),
                s.get("debt_ratio_pct", 0),
                s.get("cf_positive", 0),
                s.get("fundamental_grade", ""),
                s.get("f10_score", 5.0),
                s.get("sector_score", 5.0),
                s.get("dividend_yield_pct", 0),
                s.get("shareholder_signal", ""),
                s.get("capital_score", 5.0),
                s.get("north_bound_signal", ""),
                s.get("level2_signal", ""),
                s.get("buy_votes", 0), s.get("total_votes", 12),
                s.get("vote_ratio", 0.5),
                s["signal"], s["reason"], s["strategy"], rank,
                engine_name,
                s.get("leader_score", 0),
                s.get("seal_score", 0),
            ),
        )

    # Update batch status
    scored_count = len(scores)
    top_codes_json = _json.dumps(top_codes)
    db.execute(
        "UPDATE screening_batches SET total_stocks=?,scored_stocks=?,"
        "top40_codes=?,status='completed' WHERE batch_id=?",
        (scored_count, scored_count, top_codes_json, batch_id),
    )
    logger.info(
        "Wrote %d scores for engine=%s batch=%s", scored_count, engine_name, batch_id
    )
