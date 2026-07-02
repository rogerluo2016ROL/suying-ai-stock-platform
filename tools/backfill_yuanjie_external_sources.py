#!/usr/bin/env python3
"""Fetch Yuanjie 688498 source data from Tushare and persist it locally.

This script complements tools/backfill_yuanjie_ai_compute_10y.py:
1. Pulls single-stock near-10Y source data from Tushare.
2. Writes source tables used by the business-tag extractor.
3. Re-runs the structured L8/business-tag backfill.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import tushare as ts


PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()
CODE = "688498"
TS_CODE = "688498.SH"
START = "20160101"
END = "20260702"


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def parse_datetime(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    for fmt in ("%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def to_float(value):
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return float(text)
    except Exception:
        return None


def code_from_ts(value):
    text = str(value or "").strip()
    return text.split(".")[0][:6] if "." in text else text[:6]


def main() -> None:
    if not TOKEN:
        raise SystemExit("TUSHARE_TOKEN is not set")

    ts.set_token(TOKEN)
    pro = ts.pro_api()

    results = {}
    with psycopg2.connect(DSN) as conn:
        cur = conn.cursor()

        # 行情：模型交易信号、趋势/波动、资金确认使用。
        daily_rows = []
        try:
            daily = pro.daily(ts_code=TS_CODE, start_date=START, end_date=END)
            results["daily"] = 0 if daily is None else len(daily)
            if daily is not None:
                for _, row in daily.iterrows():
                    trade_date = parse_date(row.get("trade_date"))
                    if not trade_date:
                        continue
                    daily_rows.append(
                        (
                            CODE,
                            trade_date,
                            to_float(row.get("open")),
                            to_float(row.get("high")),
                            to_float(row.get("low")),
                            to_float(row.get("close")),
                            to_float(row.get("vol")),
                            to_float(row.get("amount")),
                            to_float(row.get("turnover_rate")),
                            to_float(row.get("pct_chg")),
                            to_float(row.get("amplitude")),
                        )
                    )
        except Exception as exc:
            results["daily"] = f"error:{str(exc)[:120]}"
        if daily_rows:
            cur.executemany(
                """
                INSERT INTO daily_kline(
                    code, trade_date, open, high, low, close, volume, amount,
                    turnover_rate, change_pct, amplitude
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    turnover_rate = COALESCE(EXCLUDED.turnover_rate, daily_kline.turnover_rate),
                    change_pct = COALESCE(EXCLUDED.change_pct, daily_kline.change_pct),
                    amplitude = COALESCE(EXCLUDED.amplitude, daily_kline.amplitude)
                """,
                daily_rows,
            )

        # 资金流：用于交易信号和预期热度，不直接当产业链证据。
        moneyflow_rows = []
        try:
            moneyflow = pro.moneyflow(ts_code=TS_CODE, start_date=START, end_date=END)
            results["moneyflow"] = 0 if moneyflow is None else len(moneyflow)
            if moneyflow is not None:
                for _, row in moneyflow.iterrows():
                    trade_date = parse_date(row.get("trade_date"))
                    if not trade_date:
                        continue
                    moneyflow_rows.append(
                        (
                            CODE,
                            trade_date,
                            to_float(row.get("buy_sm_amount")),
                            to_float(row.get("sell_sm_amount")),
                            to_float(row.get("buy_md_amount")),
                            to_float(row.get("sell_md_amount")),
                            to_float(row.get("buy_lg_amount")),
                            to_float(row.get("sell_lg_amount")),
                            to_float(row.get("buy_elg_amount")),
                            to_float(row.get("sell_elg_amount")),
                            to_float(row.get("net_mf_amount")),
                        )
                    )
        except Exception as exc:
            results["moneyflow"] = f"error:{str(exc)[:120]}"
        if moneyflow_rows:
            cur.executemany(
                """
                INSERT INTO moneyflow(
                    code, trade_date, buy_sm_amount, sell_sm_amount, buy_md_amount,
                    sell_md_amount, buy_lg_amount, sell_lg_amount, buy_elg_amount,
                    sell_elg_amount, net_mf_amount
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    buy_sm_amount = EXCLUDED.buy_sm_amount,
                    sell_sm_amount = EXCLUDED.sell_sm_amount,
                    buy_md_amount = EXCLUDED.buy_md_amount,
                    sell_md_amount = EXCLUDED.sell_md_amount,
                    buy_lg_amount = EXCLUDED.buy_lg_amount,
                    sell_lg_amount = EXCLUDED.sell_lg_amount,
                    buy_elg_amount = EXCLUDED.buy_elg_amount,
                    sell_elg_amount = EXCLUDED.sell_elg_amount,
                    net_mf_amount = EXCLUDED.net_mf_amount
                """,
                moneyflow_rows,
            )

        # 财务：增长、盈利评分的主数据源。
        income_rows = []
        try:
            income = pro.income(ts_code=TS_CODE, start_date=START, end_date=END)
            results["income"] = 0 if income is None else len(income)
            if income is not None:
                for _, row in income.iterrows():
                    end_date = parse_date(row.get("end_date"))
                    report_type = str(row.get("report_type") or row.get("comp_type") or "1")[:16]
                    if not end_date:
                        continue
                    income_rows.append(
                        (
                            CODE,
                            end_date,
                            report_type,
                            to_float(row.get("total_revenue") or row.get("revenue")),
                            to_float(row.get("operate_profit") or row.get("operating_profit")),
                            to_float(row.get("n_income") or row.get("net_profit")),
                            to_float(row.get("n_income_attr_p") or row.get("net_profit_parent")),
                        )
                    )
        except Exception as exc:
            results["income"] = f"error:{str(exc)[:120]}"
        if income_rows:
            cur.executemany(
                """
                INSERT INTO financial_income(
                    code, end_date, report_type, total_revenue, operating_profit,
                    net_profit, net_profit_parent
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code, end_date, report_type) DO UPDATE SET
                    total_revenue = COALESCE(EXCLUDED.total_revenue, financial_income.total_revenue),
                    operating_profit = COALESCE(EXCLUDED.operating_profit, financial_income.operating_profit),
                    net_profit = COALESCE(EXCLUDED.net_profit, financial_income.net_profit),
                    net_profit_parent = COALESCE(EXCLUDED.net_profit_parent, financial_income.net_profit_parent)
                """,
                income_rows,
            )

        indicator_rows = []
        try:
            indicator = pro.fina_indicator(ts_code=TS_CODE, start_date=START, end_date=END)
            results["fina_indicator"] = 0 if indicator is None else len(indicator)
            if indicator is not None:
                for _, row in indicator.iterrows():
                    end_date = parse_date(row.get("end_date"))
                    if not end_date:
                        continue
                    indicator_rows.append(
                        (
                            CODE,
                            end_date,
                            to_float(row.get("roe") or row.get("roe_dt")),
                            to_float(row.get("roa") or row.get("roa2_dt")),
                            to_float(row.get("grossprofit_margin") or row.get("gross_margin")),
                            to_float(row.get("netprofit_margin") or row.get("net_margin")),
                            to_float(row.get("debt_to_assets") or row.get("debt_ratio")),
                            to_float(row.get("current_ratio")),
                            to_float(row.get("eps") or row.get("basic_eps")),
                            to_float(row.get("bps")),
                            to_float(row.get("q_gr_yoy") or row.get("revenue_growth")),
                            to_float(row.get("q_netprofit_yoy") or row.get("profit_growth")),
                        )
                    )
        except Exception as exc:
            results["fina_indicator"] = f"error:{str(exc)[:120]}"
        if indicator_rows:
            cur.executemany(
                """
                INSERT INTO financial_indicator(
                    code, end_date, roe, roa, gross_margin, net_margin, debt_ratio,
                    current_ratio, eps, bps, revenue_growth, profit_growth
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code, end_date) DO UPDATE SET
                    roe = COALESCE(EXCLUDED.roe, financial_indicator.roe),
                    roa = COALESCE(EXCLUDED.roa, financial_indicator.roa),
                    gross_margin = COALESCE(EXCLUDED.gross_margin, financial_indicator.gross_margin),
                    net_margin = COALESCE(EXCLUDED.net_margin, financial_indicator.net_margin),
                    debt_ratio = COALESCE(EXCLUDED.debt_ratio, financial_indicator.debt_ratio),
                    current_ratio = COALESCE(EXCLUDED.current_ratio, financial_indicator.current_ratio),
                    eps = COALESCE(EXCLUDED.eps, financial_indicator.eps),
                    bps = COALESCE(EXCLUDED.bps, financial_indicator.bps),
                    revenue_growth = COALESCE(EXCLUDED.revenue_growth, financial_indicator.revenue_growth),
                    profit_growth = COALESCE(EXCLUDED.profit_growth, financial_indicator.profit_growth)
                """,
                indicator_rows,
            )

        forecast_rows = []
        try:
            forecast = pro.forecast(ts_code=TS_CODE, start_date=START, end_date=END)
            results["forecast"] = 0 if forecast is None else len(forecast)
            if forecast is not None:
                for _, row in forecast.iterrows():
                    end_date = parse_date(row.get("end_date"))
                    ftype = str(row.get("type") or row.get("forecast_type") or "").strip()
                    if not end_date or not ftype:
                        continue
                    net_profit = to_float(row.get("net_profit_max") or row.get("net_profit_min") or row.get("forecast_net_profit"))
                    forecast_rows.append((CODE, end_date, ftype, net_profit))
        except Exception as exc:
            results["forecast"] = f"error:{str(exc)[:120]}"
        if forecast_rows:
            cur.executemany(
                """
                INSERT INTO forecast_data(code, end_date, forecast_type, forecast_net_profit)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (code, end_date, forecast_type) DO UPDATE SET
                    forecast_net_profit = COALESCE(EXCLUDED.forecast_net_profit, forecast_data.forecast_net_profit)
                """,
                forecast_rows,
            )

        # 主营构成：普通接口能按单股返回历史多期，vip 补最近期。
        mainbz_rows = []
        for api_name, kwargs in [
            ("fina_mainbz", {"ts_code": TS_CODE}),
            ("fina_mainbz_vip", {"ts_code": TS_CODE, "type": "P"}),
            ("fina_mainbz_vip", {"ts_code": TS_CODE, "type": "D"}),
            ("fina_mainbz_vip", {"ts_code": TS_CODE, "type": "I"}),
        ]:
            try:
                df = getattr(pro, api_name)(**kwargs)
            except Exception as exc:
                results[f"{api_name}_{kwargs.get('type','all')}"] = f"error:{str(exc)[:120]}"
                continue
            if df is None or len(df) == 0:
                results[f"{api_name}_{kwargs.get('type','all')}"] = 0
                continue
            results[f"{api_name}_{kwargs.get('type','all')}"] = len(df)
            for _, row in df.iterrows():
                end_date = parse_date(row.get("end_date"))
                item = str(row.get("bz_item") or "").strip()
                if not end_date or not item:
                    continue
                biz_type = str(row.get("type") or kwargs.get("type") or "P")[:8]
                income = to_float(row.get("bz_sales"))
                ratio = to_float(row.get("bz_sales_ratio") or row.get("bz_ratio") or row.get("bz_profit_ratio"))
                mainbz_rows.append((CODE, end_date, item, income, ratio, biz_type))
        if mainbz_rows:
            cur.executemany(
                """
                INSERT INTO fina_mainbz(code, end_date, biz_item, biz_income, biz_ratio, biz_type)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code,end_date,biz_item) DO UPDATE SET
                    biz_income = COALESCE(EXCLUDED.biz_income, fina_mainbz.biz_income),
                    biz_ratio = COALESCE(EXCLUDED.biz_ratio, fina_mainbz.biz_ratio),
                    biz_type = COALESCE(EXCLUDED.biz_type, fina_mainbz.biz_type)
                """,
                mainbz_rows,
            )

        # 互动问答：源杰是沪市。
        qa_rows = []
        try:
            qa = pro.irm_qa_sh(ts_code=TS_CODE, start_date=START, end_date=END)
            results["irm_qa_sh"] = 0 if qa is None else len(qa)
            if qa is not None:
                for _, row in qa.iterrows():
                    pub_date = parse_date(row.get("trade_date") or row.get("pub_date"))
                    q = str(row.get("q") or row.get("question") or "").strip()
                    a = str(row.get("a") or row.get("answer") or "").strip()
                    if pub_date and q:
                        qa_rows.append((CODE, pub_date, q, a, parse_datetime(row.get("pub_time")), "sse_irm_qa"))
        except Exception as exc:
            results["irm_qa_sh"] = f"error:{str(exc)[:120]}"
        if qa_rows:
            cur.executemany(
                """
                INSERT INTO interact_qa(code, pub_date, question, answer, pub_time, source)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code,pub_date,question) DO UPDATE SET
                    answer = EXCLUDED.answer,
                    pub_time = COALESCE(EXCLUDED.pub_time, interact_qa.pub_time),
                    source = EXCLUDED.source
                """,
                qa_rows,
            )

        # 研报：写标题、作者/机构、评级、目标价。
        report_rows = []
        try:
            reports = pro.research_report(ts_code=TS_CODE, start_date=START, end_date=END)
            results["research_report"] = 0 if reports is None else len(reports)
            if reports is not None:
                for _, row in reports.iterrows():
                    pub_date = parse_date(row.get("trade_date") or row.get("report_date"))
                    title = str(row.get("title") or row.get("report_title") or "").strip()
                    if not pub_date or not title:
                        continue
                    broker = str(row.get("org_name") or row.get("author") or row.get("name") or "").strip()
                    rating = str(row.get("rating") or "").strip()
                    target_price = to_float(row.get("tp") or row.get("target_price") or row.get("max_price"))
                    report_rows.append((CODE, pub_date, title, broker, rating, target_price))
        except Exception as exc:
            results["research_report"] = f"error:{str(exc)[:120]}"
        if report_rows:
            cur.execute("DELETE FROM research_reports_tushare WHERE code=%s", (CODE,))
            cur.executemany(
                """
                INSERT INTO research_reports_tushare(code, pub_date, title, broker, rating, target_price)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                report_rows,
            )

        # 公告接口 probe 对该区间为空；这里仍按区间调用一次并落有标题的行。
        ann_rows = []
        try:
            anns = pro.anns_d(ts_code=CODE, start_date=START, end_date=END)
            results["anns_d"] = 0 if anns is None else len(anns)
            if anns is not None:
                for _, row in anns.iterrows():
                    ann_date = parse_date(row.get("ann_date"))
                    title = str(row.get("title") or "").strip()
                    if ann_date and title:
                        ann_rows.append((CODE, ann_date, title, None, str(row.get("url") or "")))
        except Exception as exc:
            results["anns_d"] = f"error:{str(exc)[:120]}"
        if ann_rows:
            cur.executemany(
                """
                INSERT INTO announcements(code, ann_date, title, ann_type, content)
                VALUES (%s,%s,%s,%s,%s)
                """,
                ann_rows,
            )

        conn.commit()

    subprocess.run([sys.executable, str(PROJ / "tools/backfill_yuanjie_ai_compute_10y.py")], cwd=PROJ, check=True)

    with psycopg2.connect(DSN) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM fina_mainbz WHERE code=%s", (CODE,))
        mainbz_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM interact_qa WHERE code=%s", (CODE,))
        qa_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM research_reports_tushare WHERE code=%s", (CODE,))
        report_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM announcements WHERE code=%s", (CODE,))
        ann_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_kline WHERE code=%s", (CODE,))
        daily_count = cur.fetchone()[0]
        cur.execute("SELECT min(trade_date), max(trade_date) FROM daily_kline WHERE code=%s", (CODE,))
        daily_range = cur.fetchone()
        cur.execute("SELECT count(*) FROM moneyflow WHERE code=%s", (CODE,))
        moneyflow_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM forecast_data WHERE code=%s", (CODE,))
        forecast_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM financial_income WHERE code=%s", (CODE,))
        income_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM financial_indicator WHERE code=%s", (CODE,))
        indicator_count = cur.fetchone()[0]
        print(
            {
                "source_fetch": results,
                "source_table_counts": {
                    "daily_kline": daily_count,
                    "daily_range": [str(daily_range[0]), str(daily_range[1])] if daily_range and daily_range[0] else [],
                    "moneyflow": moneyflow_count,
                    "forecast_data": forecast_count,
                    "financial_income": income_count,
                    "financial_indicator": indicator_count,
                    "fina_mainbz": mainbz_count,
                    "interact_qa": qa_count,
                    "research_reports_tushare": report_count,
                    "announcements": ann_count,
                },
            }
        )


if __name__ == "__main__":
    main()
