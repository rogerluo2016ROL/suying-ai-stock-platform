#!/usr/bin/env python3
"""Full-market screening with mode support: short/long/all.

Extracted from Kronos/tools/screening_top50.py
"""
import argparse, json, math, os, sys, time
from collections import Counter
from datetime import datetime
import numpy as np
import pandas as pd

os.environ.setdefault("TUSHARE_TOKEN", os.environ.get("TUSHARE_TOKEN", ""))

from kronos_factors.scorer._db_stub import _get_db, _get_market_data
from kronos_factors.scorer.five_factor import score_five_factor
from kronos_factors.scorer.advanced_factors import (
    score_money_flow, score_mean_reversion, score_trend_strength,
    score_reversal, score_liquidity, get_tushare_scores, score_hard_tech,
)

# ═══════════════════════════════════════════════════════════════
# Short-term technical scoring
# ═══════════════════════════════════════════════════════════════

def score_short_term(df) -> dict:
    """Short-term trading signals (0-10)."""
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values
    opens = df["open"].values

    if len(closes) < 60:
        return {"score": 5.0, "signals": []}

    s, signals = 5.0, []

    # MA多头排列：MA5 > MA10 > MA20 > MA60
    ma5 = closes[-5:].mean()
    ma10 = closes[-10:].mean()
    ma20 = closes[-20:].mean()
    ma60 = closes[-60:].mean()
    if ma5 > ma10 > ma20 > ma60:
        s += 2.5; signals.append("均线多头")

    # 不破十日线
    if closes[-1] > ma10 and lows[-5:].min() > ma10 * 0.98:
        s += 2.0; signals.append("不破十日线")

    # 放量突破
    avg_vol20 = volumes[-21:-1].mean() if len(volumes) > 21 else volumes.mean()
    if volumes[-1] > avg_vol20 * 1.5 and closes[-1] > opens[-1] * 1.02:
        s += 2.0; signals.append("放量突破")

    # MACD金叉 (3日内)
    ema12 = pd.Series(closes).ewm(span=12).mean().values
    ema26 = pd.Series(closes).ewm(span=26).mean().values
    dif = ema12 - ema26
    dea = pd.Series(dif).ewm(span=9).mean().values
    for j in range(-3, 0):
        if j >= -len(dif): break
        if dif[j-1] <= dea[j-1] and dif[j] > dea[j] and dif[j] > 0:
            s += 1.5; signals.append("MACD金叉")
            break

    # 缩量回调不破支撑
    if len(closes) > 5 and closes[-1] < closes[-3]:
        drop_pct = (closes[-1] / closes[-3] - 1) * 100
        vol_change = volumes[-1] / volumes[-4:-1].mean() - 1
        if -8 < drop_pct < 0 and vol_change < -0.3 and closes[-1] > ma20:
            s += 1.5; signals.append("缩量回调")

    # RSI健康
    delta = np.diff(closes[-15:])
    gain = np.where(delta > 0, delta, 0).mean()
    loss = abs(np.where(delta < 0, delta, 0)).mean()
    rsi = 100 - 100 / (1 + gain/loss) if loss > 0 else 50
    if 50 < rsi < 75:
        s += 1.0; signals.append(f"RSI={rsi:.0f}")

    # 创新高+回调不破10日线（新增量缩确认）
    if len(closes) >= 60:
        recent_high = highs[-10:].max()
        prior_60_high = highs[-60:-10].max()
        if recent_high >= prior_60_high:
            pullback_from_high = (closes[-1] - recent_high) / recent_high * 100
            if -10 < pullback_from_high < 0:
                if closes[-1] > ma10 and closes[-2] > ma10 and closes[-3] > ma10:
                    # Volume confirmation: pullback with non-expanding volume
                    avg_vol_10 = volumes[-11:-1].mean() if len(volumes) > 11 else volumes.mean()
                    if volumes[-1] < avg_vol_10:  # 回调日不放量
                        s += 2.5; signals.append(f"新高缩量回调(M10)")

    # 剔除拥挤
    ret20 = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0
    if ret20 > 50:
        s -= 2.0; signals.append("超买拥挤")

    score = round(max(0, min(10, s)), 1)
    return {"score": score, "signals": signals}


# ═══════════════════════════════════════════════════════════════
# Long-term fundamental scoring
# ═══════════════════════════════════════════════════════════════

def score_long_term(code: str) -> dict:
    """Long-term value quality scoring (0-10)."""
    from kronos_factors.scorer._db_stub import _get_db
    try:
        with _get_db(readonly=True) as db:
            inds = db.execute(
                "SELECT * FROM financial_indicator WHERE code=? ORDER BY end_date DESC LIMIT 16",
                (code,)).fetchall()
            dbs = db.execute(
                "SELECT pe, pb FROM daily_basic WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (code,)).fetchone()
    except Exception:
        return {"score": 5.0, "signals": []}

    if len(inds) < 4:
        return {"score": 5.0, "signals": []}

    s, sigs = 5.0, []

    latest = dict(inds[0])
    roe = latest.get("roe") or 0
    debt = latest.get("debt_to_assets") or 0
    ocfps = latest.get("ocfps") or 0
    eps = latest.get("eps") or 0

    # ROE质量
    if roe > 15:
        roe_3y = all((dict(r).get("roe") or 0) > 10 for r in inds[:12] if r)
        if roe_3y: s += 2.5; sigs.append("ROE优质")
        else: s += 1.5; sigs.append("ROE良好")

    # 低估值
    pe = dbs["pe"] if dbs else 0
    pb = dbs["pb"] if dbs else 0
    if pe and 5 < pe < 20 and pb and pb < 3:
        s += 2.0; sigs.append(f"PE={pe:.0f}")

    # 现金流健康
    if ocfps and eps > 0 and ocfps > eps * 0.8:
        s += 1.5; sigs.append("现金流健康")

    # 低负债
    if 0 < debt < 40:
        s += 1.0; sigs.append(f"负债率={debt:.0f}%")

    # 营收CAGR
    if len(inds) >= 12:
        revs = [(dict(r).get("or_yoy") or 0) for r in inds[:12]]
        cagr = sum(revs) / len(revs) if revs else 0
        if cagr > 15: s += 1.5; sigs.append(f"增长={cagr:.0f}%")

    # 剔除价值陷阱
    if pe and 0 < pe < 5 and roe < 0:
        s -= 2.0; sigs.append("价值陷阱")

    return {"score": round(max(0, min(10, s)), 1), "signals": sigs}


# ═══════════════════════════════════════════════════════════════
# Industry trend factor
# ═══════════════════════════════════════════════════════════════

def score_growth(code: str) -> dict:
    """Revenue/profit growth scoring (0-10)."""
    from kronos_factors.scorer._db_stub import _get_db
    try:
        with _get_db(readonly=True) as db:
            incs = db.execute(
                "SELECT * FROM financial_income WHERE code=? ORDER BY end_date DESC LIMIT 8",
                (code,)).fetchall()
    except Exception:
        return {"score": 5.0, "signals": []}

    if len(incs) < 2:
        return {"score": 5.0, "signals": []}

    s, sigs = 5.0, []

    r0 = dict(incs[0]); r1 = dict(incs[1])
    rev0 = r0.get("total_revenue") or 0
    rev1 = r1.get("total_revenue") or 0
    profit0 = r0.get("n_income_attr_p") or 0
    profit1 = r1.get("n_income_attr_p") or 0

    # 营收爆发
    if rev1 > 0 and rev0 > 0:
        rev_yoy = (rev0 / rev1 - 1) * 100
        if rev_yoy > 50: s += 2.0; sigs.append(f"营收+{rev_yoy:.0f}%")

    # 利润爆发
    if profit1 > 0 and profit0 > 0:
        profit_yoy = (profit0 / profit1 - 1) * 100
        if profit_yoy > 50: s += 2.0; sigs.append(f"利润+{profit_yoy:.0f}%")
    elif profit1 <= 0 and profit0 > 0:
        s += 2.0; sigs.append("扭亏为盈")

    # SUE超预期 (using profit growth as proxy)
    if profit1 > 0 and profit_yoy > 20:
        s += 1.0; sigs.append("超预期")

    # 加速增长
    if len(incs) >= 4:
        r2 = dict(incs[2]); r3 = dict(incs[3])
        rev2 = r2.get("total_revenue") or 0; rev3 = r3.get("total_revenue") or 0
        if rev3 > 0 and rev2 > 0 and rev1 > 0:
            g1 = (rev1 / rev3 - 1) * 100
            g0 = (rev0 / rev2 - 1) * 100
            if g0 > g1 > 0: s += 1.5; sigs.append("加速增长")

    return {"score": round(max(0, min(10, s)), 1), "signals": sigs}


# ═══════════════════════════════════════════════════════════════
# Stock themes & catalysts (题材与催化剂)
# ═══════════════════════════════════════════════════════════════

def get_stock_themes(code: str, kline_df=None, ht: dict = None) -> dict:
    """Extract rich themes: research logic, hot topics, catalysts.

    Builds a narrative from multiple report titles + keyword matching against
    market hot topics. Returns detailed thesis for buy rationale.

    Returns:
        {"thesis": str, "hot_topics": str, "tracks": str, "surge_events": list[str]}
    """
    result = {"thesis": "", "hot_topics": "", "tracks": "", "surge_events": []}
    import re

    # ── Market hot topic keywords ──
    HOT_TOPICS = {
        "AI算力": ["AI", "算力", "服务器", "GPU", "光模块", "CPO", "PCB", "数据中心", "大模型", "DeepSeek"],
        "半导体国产替代": ["半导体", "芯片", "晶圆", "封装", "光刻", "EDA", "薄膜沉积", "刻蚀", "碳化硅", "国产替代"],
        "新能源": ["光伏", "风电", "储能", "锂电池", "固态电池", "氢能", "核能", "电力", "能源互联"],
        "机器人/智造": ["机器人", "人形", "伺服", "具身智能", "自动化", "工业AI", "智能制造", "机器视觉"],
        "低空经济": ["低空", "无人机", "eVTOL", "航天", "卫星", "航空"],
        "资源品涨价": ["涨价", "有色", "铜", "铝", "稀土", "化工", "煤炭", "石油", "天然气", "黄金"],
        "消费复苏": ["消费", "家电", "汽车", "旅游", "餐饮", "零售", "医药", "创新药"],
        "新材料": ["镍粉", "铜粉", "碳纤维", "复合材料", "电子化学品", "氟化", "薄膜"],
    }

    try:
        with _get_db(readonly=True) as db:
            # ── Research report analysis ──
            reps = db.execute(
                "SELECT trade_date, title, author FROM research_reports_tushare "
                "WHERE code=? AND code != 'nan' ORDER BY trade_date DESC LIMIT 6",
                (code,)
            ).fetchall()

            company_name = db.execute(
                "SELECT name, industry FROM stocks WHERE code=?", (code,)
            ).fetchone()

            all_keywords = []
            clean_theses = []
            if reps:
                for r in reps:
                    title = r["title"]
                    title = re.sub(r'\.pdf$', '', title)
                    title = re.sub(r'_\d{4}-\d{2}-\d{2}$', '', title)
                    title = re.sub(r'_\d{8}$', '', title)
                    title = re.sub(r'^[^\s_]+[_\s]', '', title)
                    title = re.sub(r'^(公司)?(动态)?研究(报告)?[：:]\s*', '', title)
                    title = re.sub(r'^(公司)?深度报告[：:]\s*', '', title)
                    title = re.sub(r'^\d{4}年?(年[报终度]|中报|Q\d|一[二三]?季[报度]?)\s*(点评|业绩点评|报告)?[：:．.]?\s*', '', title)
                    title = re.sub(r'^(公司)?(点评|业绩点评|信息更新报告|事件点评报告|首次覆盖报告)[：:．.]?\s*', '', title)
                    title = re.sub(r'^及\d{2}Q\d(季报)?(点评)?[：:]\s*', '', title)
                    title = re.sub(r'^年?(报|中报|季报).*?点评[：:]\s*', '', title)
                    title = re.sub(r'^[：:．.\s]+', '', title)
                    title = title.strip('_ -—')
                    if len(title) > 8:
                        clean_theses.append(title)
                        # Extract keywords from title
                        words = re.findall(r'[\w一-鿿]+', title)
                        all_keywords.extend(words)

            # ── Hot topic matching (from reports + hard_tech + industry) ──
            matched_topics = []
            industry = company_name["industry"] if company_name else ""
            name = company_name["name"] if company_name else ""
            text_to_match = " ".join(all_keywords) + " " + industry + " " + name

            for topic, keywords in HOT_TOPICS.items():
                if any(kw in text_to_match for kw in keywords):
                    matched_topics.append(topic)

            # Also from hard_tech tracks
            if ht and ht.get("tracks", "none") != "none":
                tracks_str = ht["tracks"]
                result["tracks"] = tracks_str
                for t in tracks_str.split(","):
                    t = t.strip()
                    if t and t not in matched_topics:
                        matched_topics.append(t)

            result["hot_topics"] = "、".join(matched_topics[:4]) if matched_topics else ""

            # ── Build rich thesis: prefer titles with hot topic keywords ──
            if clean_theses:
                hot_kw = ["AI", "半导体", "芯片", "机器人", "算力", "涨价", "新能源", "低空", "放量", "翻倍", "突破"]
                def thesis_score(t):
                    s = len(t) if len(t) > 15 else 0
                    s += sum(5 for kw in hot_kw if kw in t)  # bonus for hot keywords
                    return s
                best = max(clean_theses, key=thesis_score)
                result["thesis"] = best[:80]

                # Enrich with second perspective if available
                if len(clean_theses) >= 2:
                    others = [t for t in clean_theses if t[:30] != best[:30] and len(t) > 12]
                    if others:
                        result["thesis"] = best[:55] + "；" + others[0][:40]

    except Exception:
        pass

    # ── Historical surge events ──
    if kline_df is not None and len(kline_df) >= 20:
        try:
            import pandas as pd
            closes = kline_df["close"].values
            dates = kline_df["timestamps"] if "timestamps" in kline_df.columns else kline_df.index
            surges = []
            for i in range(1, len(closes)):
                daily_chg = (closes[i] - closes[i-1]) / closes[i-1] * 100 if closes[i-1] > 0 else 0
                if daily_chg > 7:
                    try:
                        d = pd.to_datetime(dates.iloc[i] if hasattr(dates, 'iloc') else dates[i])
                        surges.append(f"{d.strftime('%m/%d')}+{daily_chg:.0f}%")
                    except Exception:
                        surges.append(f"+{daily_chg:.0f}%")
            result["surge_events"] = surges[-5:]
        except Exception:
            pass

    return result


# ═══════════════════════════════════════════════════════════════
# Multi-timeframe trend filter (weekly + monthly)
# ═══════════════════════════════════════════════════════════════

def check_multi_timeframe_trend(code: str) -> dict:
    """Verify weekly and monthly K-line trends are bullish.

    Returns:
        {"weekly_ok": bool, "monthly_ok": bool,
         "w_ma5": float, "w_ma10": float, "w_ma20": float, "w_close": float,
         "m_ma5": float, "m_ma10": float, "m_close": float}
    """
    import numpy as np
    result = {"weekly_ok": False, "monthly_ok": False}
    try:
        with _get_db(readonly=True) as db:
            # ── Weekly ──
            wk_rows = db.execute(
                "SELECT open, high, low, close FROM weekly_kline "
                "WHERE code=? ORDER BY trade_date ASC", (code,)
            ).fetchall()
            if wk_rows and len(wk_rows) >= 20:
                wc = np.array([r["close"] for r in wk_rows], dtype=np.float64)
                w_ma5 = np.mean(wc[-5:])
                w_ma10 = np.mean(wc[-10:])
                w_ma20 = np.mean(wc[-20:])
                result.update(w_ma5=round(float(w_ma5), 2), w_ma10=round(float(w_ma10), 2),
                              w_ma20=round(float(w_ma20), 2), w_close=round(float(wc[-1]), 2))
                # MA5 > MA10 > MA20 AND price > MA20
                result["weekly_ok"] = bool(w_ma5 > w_ma10 > w_ma20 and wc[-1] > w_ma20)

            # ── Monthly ──
            mo_rows = db.execute(
                "SELECT open, high, low, close FROM monthly_kline "
                "WHERE code=? ORDER BY trade_date ASC", (code,)
            ).fetchall()
            if mo_rows and len(mo_rows) >= 6:
                mc = np.array([r["close"] for r in mo_rows], dtype=np.float64)
                m_ma5 = np.mean(mc[-5:]) if len(mc) >= 5 else np.mean(mc)
                m_ma10 = np.mean(mc[-6:]) if len(mc) >= 6 else m_ma5
                result.update(m_ma5=round(float(m_ma5), 2), m_ma10=round(float(m_ma10), 2),
                              m_close=round(float(mc[-1]), 2))
                # MA5 > MA10 AND price > MA5
                result["monthly_ok"] = bool(m_ma5 > m_ma10 and mc[-1] > m_ma5)
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════════════
# Identifiability scoring (辨识度)
# ═══════════════════════════════════════════════════════════════

def score_identifiability(code: str, kline_df=None) -> dict:
    """Score stock recognizability: market-cap, liquidity, analyst coverage,
    north-bound holdings, listing age, industry heat.  Returns 0-10.
    """
    s, sigs = 5.0, []
    try:
        with _get_db(readonly=True) as db:
            row = db.execute(
                "SELECT market_cap, float_mv, listed_date, industry FROM stocks WHERE code=?",
                (code,)).fetchone()
            if not row:
                return {"score": 5.0, "signals": ["无数据"]}

            mc = (row["market_cap"] or 0) / 1e4  # 万元 → 亿

            # ── Market cap ──
            if mc > 200:
                s += 3.0; sigs.append(f"市值{mc:.0f}亿")
            elif mc > 100:
                s += 2.0; sigs.append(f"市值{mc:.0f}亿")
            elif mc > 50:
                s += 1.0; sigs.append(f"市值{mc:.0f}亿")
            elif mc > 0 and mc < 20:
                s -= 3.0; sigs.append(f"微盘{mc:.0f}亿")

            # ── Liquidity (from daily_kline) ──
            if kline_df is not None and len(kline_df) >= 20:
                recent = kline_df.iloc[-20:]
                avg_amount = float(recent["amount"].mean()) / 1e8  # in 亿
                if avg_amount > 2:
                    s += 2.0; sigs.append(f"日均成交{avg_amount:.1f}亿")
                elif avg_amount > 1:
                    s += 1.0

            # ── Analyst coverage (last 90 days) ──
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y%m")
            br_count = db.execute(
                "SELECT COUNT(DISTINCT broker) as cnt FROM broker_recommend "
                "WHERE code=? AND month >= ?", (code, cutoff)
            ).fetchone()
            if br_count and br_count["cnt"] > 0:
                s += 2.0; sigs.append(f"{br_count['cnt']}家券商覆盖")

            # ── North-bound holdings ──
            hk = db.execute(
                "SELECT ratio FROM hk_holdings WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (code,)).fetchone()
            if hk and hk["ratio"]:
                ratio = float(hk["ratio"])
                if ratio > 3:
                    s += 2.0; sigs.append(f"北向{ratio:.1f}%")
                elif ratio > 1:
                    s += 1.0; sigs.append(f"北向{ratio:.1f}%")

            # ── Listed > 2 years ──
            ld = row["listed_date"]
            if ld:
                try:
                    ld_date = datetime.strptime(str(ld)[:10], "%Y%m%d")
                    if (datetime.now() - ld_date).days > 730:
                        s += 1.0
                except Exception:
                    pass

            # ── Hot industry ──
            hot_keywords = ["半导体", "AI", "人工智能", "机器人", "新能源", "低空",
                          "算力", "芯片", "创新药", "储能", "军工", "量子"]
            ind = row["industry"] or ""
            if any(kw in ind for kw in hot_keywords):
                s += 1.0; sigs.append(f"赛道:{ind}")

    except Exception:
        return {"score": 5.0, "signals": ["error"]}

    return {"score": round(max(0, min(10, s)), 1), "signals": sigs}


# ═══════════════════════════════════════════════════════════════
# Enhanced margin momentum scoring (融资盘动量)
# ═══════════════════════════════════════════════════════════════

def score_margin_momentum(code: str) -> dict:
    """Score margin buying momentum with acceleration detection. Returns 0-10.

    Goes beyond static balance/buy-ratio to measure:
    - 5/10/20-day balance growth acceleration
    - Consecutive buy amount increase (3+ days)
    - Leverage intensity (balance / float market cap)
    """
    s, sigs = 5.0, []
    try:
        with _get_db(readonly=True) as db:
            mg_rows = db.execute(
                "SELECT trade_date, rzye, rzmre, rzche FROM margin_detail "
                "WHERE code=? ORDER BY trade_date DESC LIMIT 20", (code,)
            ).fetchall()
            if not mg_rows or len(mg_rows) < 5:
                return {"score": 5.0, "signals": ["融资数据不足"]}

            balances = [float(r["rzye"] or 0) for r in mg_rows]
            buys = [float(r["rzmre"] or 0) for r in mg_rows]
            repays = [float(r["rzche"] or 0) for r in mg_rows]

            # ── Balance growth trends ──
            if balances[0] > 0:
                chg_5d = (balances[0] - balances[4]) / balances[4] * 100 if balances[4] > 0 else 0
                if chg_5d > 5:
                    s += 2.0; sigs.append(f"融余5日+{chg_5d:.0f}%")
                elif chg_5d > 2:
                    s += 1.0

                if len(balances) >= 10 and balances[9] > 0:
                    chg_10d = (balances[0] - balances[9]) / balances[9] * 100
                    if chg_10d > 8:
                        s += 1.5; sigs.append(f"融余10日+{chg_10d:.0f}%")
                    elif chg_10d > 5:
                        s += 0.5

            # ── Buy/repay ratio (recent 5 days) ──
            tb5, tr5 = sum(buys[:5]), sum(repays[:5])
            if tb5 + tr5 > 0:
                br5 = tb5 / (tb5 + tr5)
                if br5 > 0.55:
                    s += 2.0; sigs.append(f"买偿比{br5:.0%}")
                elif br5 > 0.50:
                    s += 1.0
                elif br5 < 0.45:
                    s -= 1.0

            # ── Buy amount acceleration (连续3日递增) ──
            if len(buys) >= 3 and buys[0] > buys[1] > buys[2] and buys[2] > 0:
                s += 1.5; sigs.append("买入连续加速")

            # ── Leverage intensity ──
            fv_row = db.execute(
                "SELECT float_mv FROM stocks WHERE code=?", (code,)
            ).fetchone()
            if fv_row and fv_row["float_mv"] and balances[0] > 0:
                float_mv = float(fv_row["float_mv"]) * 1e4  # 万元 → 元
                leverage = balances[0] / float_mv * 100 if float_mv > 0 else 0  # rzye(元) / float_mv(元)
                if leverage > 5:
                    s += 1.0; sigs.append(f"杠杆率{leverage:.1f}%")

            # ── Penalty: consecutive balance decline ──
            if len(balances) >= 5 and all(balances[i] < balances[i+1] for i in range(4)):
                s -= 2.0; sigs.append("融余连降")

    except Exception:
        return {"score": 5.0, "signals": ["error"]}

    return {"score": round(max(0, min(10, s)), 1), "signals": sigs}


# ═══════════════════════════════════════════════════════════════
# Social Security Fund check (社保基金)
# ═══════════════════════════════════════════════════════════════

# ── Institutional fund cache (avoid akshare rate limiting) ──
_INST_CACHE = {}


def check_institutional_funds(code: str) -> dict:
    """Check if institutional funds (社保/养老/年金/险资/QFII) are in top-10
    circulating shareholders. Compares latest two periods for new/increased positions.

    Fund types and bonuses:
    - 社保基金/养老金/QFII: new +2.0, increased +1.5, holding +0.5
    - 企业年金/险资:       new +1.5, increased +1.0, holding +0.3

    Returns:
        {"has_institutional": bool, "fund_types": [str], "status": str, "funds": [str], "score_bonus": float}
    """
    result = {"has_institutional": False, "fund_types": [], "status": "none",
              "funds": [], "score_bonus": 0.0}

    # Keywords → (bonus_new, bonus_increased, bonus_holding, type_label)
    FUND_PATTERNS = [
        ("社保", 2.0, 1.5, 0.5, "社保"),
        ("养老", 2.0, 1.5, 0.5, "养老金"),
        ("QFII", 2.0, 1.5, 0.5, "QFII"),
        ("年金", 1.5, 1.0, 0.3, "企业年金"),
        ("保险", 1.5, 1.0, 0.3, "险资"),
        ("UBS|摩根|高盛|花旗|汇丰|瑞银|美林|大和|野村|法兴|巴克莱|摩根士丹利", 2.0, 1.5, 0.5, "外资"),
    ]

    # Check cache first
    if code in _INST_CACHE:
        return _INST_CACHE[code]

    df = None
    # Try akshare with retry
    for attempt in range(3):
        try:
            import akshare as ak
            df = ak.stock_circulate_stock_holder(symbol=code)
            break
        except Exception:
            if attempt < 2:
                import time as _t; _t.sleep(0.5 * (attempt + 1))
            continue

    # Fallback: tushare top10_floatholders
    if df is None:
        try:
            import tushare as ts
            pro = ts.pro_api()
            ts_code = f"{code}.SZ" if code.startswith(('0','3')) else f"{code}.SH"
            df = pro.top10_floatholders(ts_code=ts_code)
            if df is not None and len(df) > 0:
                df = df.rename(columns={'holder_name':'股东名称','hold_num':'持股数量','hold_ratio':'占流通股比例','end_date':'截止日期'})
        except Exception:
            pass

    if df is None or len(df) == 0:
        _INST_CACHE[code] = result
        return result

    periods = df['截止日期'].drop_duplicates().sort_values(ascending=False).tolist()
    if len(periods) < 2:
        _INST_CACHE[code] = result
        return result

    latest = periods[0]
    previous = periods[1]
    latest_df = df[df['截止日期'] == latest]
    prev_df = df[df['截止日期'] == previous]

    best_bonus = 0.0
    best_status = "none"
    all_funds = []
    all_types = []

    for keyword, bonus_new, bonus_inc, bonus_hold, type_label in FUND_PATTERNS:
        matches = latest_df[latest_df['股东名称'].astype(str).str.contains(keyword, na=False)]
        if len(matches) == 0:
            continue

        all_types.append(type_label)
        result["has_institutional"] = True
        funds = matches['股东名称'].unique().tolist()
        all_funds.extend(funds[:2])

        is_new = False
        is_increased = False
        for _, row in matches.iterrows():
            name = row['股东名称']
            shares = float(row['持股数量']) if row['持股数量'] else 0
            prev_match = prev_df[prev_df['股东名称'] == name]
            if len(prev_match) == 0:
                is_new = True
            else:
                prev_shares = float(prev_match.iloc[0]['持股数量']) if prev_match.iloc[0]['持股数量'] else 0
                if shares > prev_shares * 1.01:
                    is_increased = True

        if is_new:
            if bonus_new > best_bonus:
                best_bonus = bonus_new; best_status = "new"
        elif is_increased:
            if bonus_inc > best_bonus:
                best_bonus = bonus_inc; best_status = "increased"
        else:
            if bonus_hold > best_bonus:
                best_bonus = bonus_hold; best_status = "holding"

    result["funds"] = all_funds[:4]
    result["fund_types"] = all_types
    result["score_bonus"] = best_bonus
    result["status"] = best_status

    _INST_CACHE[code] = result  # cache result
    return result


# Backward compatibility alias
check_social_security_fund = check_institutional_funds


# ═══════════════════════════════════════════════════════════════
# Filters
# ═══════════════════════════════════════════════════════════════

def should_exclude(code: str, kline_df) -> bool:
    """Exclude micro-cap and overbought stocks."""
    from kronos_factors.scorer._db_stub import _get_db
    try:
        with _get_db(readonly=True) as db:
            row = db.execute(
                "SELECT market_cap FROM stocks WHERE code=?", (code,)
            ).fetchone()
            if row and row["market_cap"] and row["market_cap"] < 100000:
                return True  # market cap < 10亿 → 仙股
    except: pass

    closes = kline_df["close"].values
    if len(closes) >= 20:
        ret20 = (closes[-1] / closes[-20] - 1) * 100
        if ret20 > 50:
            return True  # 近20日涨幅 > 50%

    return False


# ═══════════════════════════════════════════════════════════════
# Buy/Sell price alerts
# ═══════════════════════════════════════════════════════════════

def compute_trade_levels(df, mode="short") -> dict:
    """Compute entry, stop-loss, and target prices from K-line data.

    Short mode: MA10 support entry, MA20 stop, recent-high target
    Long mode:  MA60 support entry, MA120 stop, fair-value target
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values
    current = closes[-1]

    ma10 = closes[-10:].mean()
    ma20 = closes[-20:].mean()
    ma60 = closes[-60:].mean() if len(closes) >= 60 else ma20
    ma120 = closes[-120:].mean() if len(closes) >= 120 else ma60
    recent_high = highs[-20:].max()
    recent_low = lows[-20:].min()
    atr = np.mean(highs[-14:] - lows[-14:]) if len(highs) >= 14 else (highs[-1] - lows[-1])

    if mode == "short":
        entry = round(ma10, 2)
        stop_loss = round(ma20 - atr * 0.5, 2)
        target_1 = round(current + atr * 2, 2)
        target_2 = round(recent_high * 1.05, 2)
        support = round(ma20, 2)
        resistance = round(recent_high, 2)
    else:
        # Long mode: use nearest support level, cap at 2x current price
        entry_candidates = [v for v in [ma20, ma60] if v < current * 2]
        entry = round(min(entry_candidates) if entry_candidates else current * 0.95, 2)
        stop_candidates = [v for v in [ma60, ma120] if v < entry]
        stop_loss = round(max(stop_candidates) if stop_candidates else entry * 0.93, 2)
        target_1 = round(current * 1.15, 2)
        target_2 = round(current * 1.30, 2)
        support = round(ma20, 2)
        resistance = round(recent_high, 2)

    risk = max(current - stop_loss, 0.01)
    reward = target_1 - current
    rr = round(reward / risk, 1) if risk > 0 else 0

    return {
        "current": round(current, 2),
        "entry": entry, "stop_loss": stop_loss,
        "target_1": target_1, "target_2": target_2,
        "support": support, "resistance": resistance,
        "atr": round(atr, 2),
        "risk_reward": rr,
    }


def build_rationale(code, name, df, scores, mode, levels) -> str:
    """Build comprehensive selection rationale with themes, catalysts, and technicals."""
    parts = []

    # 0. Theme & Catalyst (题材与催化剂)
    th = scores.get("themes", {})
    if th.get("hot_topics"):
        parts.append(f"【热点】{th['hot_topics']}")
    if th.get("thesis"):
        parts.append(f"【逻辑】{th['thesis']}")
    if th.get("surge_events"):
        parts.append(f"【异动】{', '.join(th['surge_events'][-3:])}")
    if th.get("tracks"):
        parts.append(f"【赛道】{th['tracks']}")

    # 1. Price and technical position
    if mode == "short":
        if levels["current"] > levels["entry"]:
            parts.append(f"当前价{levels['current']}高于MA10入场点{levels['entry']}，等待回调至{levels['entry']}附近介入")
        else:
            parts.append(f"当前价{levels['current']}接近MA10支撑{levels['entry']}，可现价入场")
        parts.append(f"止损{levels['stop_loss']}（MA20-0.5ATR），目标{levels['target_1']}（+{((levels['target_1']/levels['current']-1)*100):.0f}%）")
        parts.append(f"盈亏比{levels['risk_reward']}:1")
    else:
        parts.append(f"MA60支撑位{levels['entry']}，当前价{levels['current']}")
        parts.append(f"止损{levels['stop_loss']}，目标{levels['target_1']}（+15%）/{levels['target_2']}（+30%）")

    # 2. Technical strengths
    st = scores.get("short_term", {})
    if st.get("signals"):
        parts.append("技术面：" + "、".join(st["signals"][:3]))

    # 3. Social Security Fund (社保基金) — LONG mode
    inst = scores.get("institutional", {})
    if inst.get("has_institutional"):
        types = inst.get("fund_types", [])
        type_str = f"({','.join(types)})" if types else ""
        status_map = {"new": f"🔥机构新进{type_str}", "increased": f"📈机构增持{type_str}", "holding": f"💼机构持有{type_str}"}
        parts.append(status_map.get(inst.get("status"), "机构持有"))

    # 4. Fundamental strengths
    lt = scores.get("long_term", {})
    if lt.get("signals"):
        parts.append("基本面：" + "、".join(lt["signals"][:3]))

    # 4. Growth / industry
    gr = scores.get("growth", {})
    if gr.get("signals"):
        parts.append("成长性：" + "、".join(gr["signals"][:2]))

    ht = scores.get("hard_tech", {})
    tracks = ht.get("tracks", "none")
    if tracks != "none":
        parts.append(f"产业赛道：{tracks}")

    # 5. Margin momentum & money flow
    ts_scores = scores.get("tushare", {})
    mg = scores.get("margin_momentum", {})
    if mg.get("score", 5) >= 7:
        parts.append("融资面：" + "、".join(mg.get("signals", [])[:2]))
    mf = ts_scores.get("tushare_moneyflow", {})
    if mf.get("score", 5) >= 7:
        parts.append(f"资金面：机构净流入")

    # 6. Multi-timeframe confirmation
    mtf = scores.get("multi_timeframe", {})
    if mtf.get("weekly_ok"):
        parts.append("周线多头确认")
    if mtf.get("monthly_ok"):
        parts.append("月线趋势向上")

    # 7. Identifiability
    idf = scores.get("identifiability", {})
    if idf.get("score", 5) >= 7:
        parts.append("辨识度：" + "、".join(idf.get("signals", [])[:1]))

    # 8. Broker consensus
    if ht.get("broker_consensus", 0) >= 2:
        parts.append(f"券商共识：近3月{ht['broker_consensus']}家推荐")

    return " | ".join(parts) if parts else "因子共振不足"


# ═══════════════════════════════════════════════════════════════
# Main screening
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Risk assessment (风险评估)
# ═══════════════════════════════════════════════════════════════

def assess_risk(code: str, df, scores: dict, mode: str) -> dict:
    """Compute risk score 0-10 (0=safest, 10=riskiest).

    Dimensions:
    - Volatility (近期波动率): 20d annualized
    - Drawdown (最大回撤): 60d max drawdown
    - Factor divergence (因子分歧): std of sub-scores
    - Concentration (集中度): single factor dominance
    """
    risk_score = 5.0
    details = []

    closes = df['close'].values if df is not None and len(df) >= 20 else None

    # ── 1. Volatility (20d) ──
    if closes is not None and len(closes) >= 20:
        returns = np.diff(closes[-20:]) / closes[-20:-1]
        vol_20d = np.std(returns) * np.sqrt(252) * 100  # annualized %
        if vol_20d > 60:
            risk_score += 2.0; details.append(f"极高波动{vol_20d:.0f}%")
        elif vol_20d > 40:
            risk_score += 1.0; details.append(f"高波动{vol_20d:.0f}%")
        elif vol_20d < 15:
            risk_score -= 1.0; details.append(f"低波动{vol_20d:.0f}%")

    # ── 2. Drawdown (60d) ──
    if closes is not None and len(closes) >= 60:
        peak = np.maximum.accumulate(closes[-60:])
        maxdd = float(np.min((closes[-60:] / peak - 1) * 100))
        if maxdd < -30:
            risk_score += 2.0; details.append(f"深回撤{maxdd:.0f}%")
        elif maxdd < -20:
            risk_score += 1.0; details.append(f"回撤{maxdd:.0f}%")

    # ── 3. Recent momentum extreme ──
    if closes is not None and len(closes) >= 20:
        ret_20 = (closes[-1] / closes[-20] - 1) * 100
        if ret_20 > 40:
            risk_score += 1.5; details.append(f"超买{ret_20:.0f}%")
        elif ret_20 > 25:
            risk_score += 0.5

    # ── 4. Factor concentration ──
    if mode == "short":
        st = scores.get("short_term", {})
        mg = scores.get("margin_momentum", {})
        if st.get("score", 5) > 9 and mg.get("score", 5) < 4:
            risk_score += 1.0; details.append("技术面独大")
    elif mode in ("long", "all"):
        inst = scores.get("institutional", {})
        if not inst.get("has_institutional"):
            risk_score += 0.5  # No institutional backing

    risk_score = round(max(0, min(10, risk_score)), 1)

    # Dynamic thresholds: relax in bull, tighten in bear
    regime = get_market_regime()
    if regime["regime"] == "bull":
        hi, mid = 8, 6  # relaxed
    elif regime["regime"] == "bear":
        hi, mid = 6, 4  # tightened
    else:
        hi, mid = 7, 5  # neutral

    if risk_score >= hi: level = "🔴 高风险"
    elif risk_score >= mid: level = "🟡 中风险"
    else: level = "🟢 低风险"

    if risk_score >= hi: position = "≤5%"
    elif risk_score >= mid: position = "5-10%"
    else: position = "10-15%"

    return {"score": risk_score, "level": level, "position": position,
            "details": details}


# ═══════════════════════════════════════════════════════════════
# Chokepoint scoring (供应链卡脖子 — Serenity方法论)
# ═══════════════════════════════════════════════════════════════

def score_chokepoint(code: str) -> dict:
    """Bottom-Up supply chain chokepoint scoring (0-10).

    Identifies micro-monopolies: stocks that are irreplaceable nodes
    in the AI/semiconductor supply chain, inspired by Serenity's method.

    Dimensions:
    - Industry monopoly (0-3): how many A-share peers in same industry?
    - Chokepoint keywords (0-3): "独家/唯一/卡脖子" in research reports
    - Hard-tech track (0-2): semiconductor/AI/robotics positioning
    - Institutional attention (0-2): analyst coverage + smart money
    """
    s, sigs = 5.0, []

    try:
        with _get_db(readonly=True) as db:
            # ── 1. Industry monopoly (同行业上市公司数) ──
            row = db.execute(
                "SELECT industry, market_cap, name FROM stocks WHERE code=?", (code,)
            ).fetchone()
            if not row or not row["industry"]:
                return {"score": 0, "signals": ["无行业数据"]}

            industry = row["industry"]
            mc = (row["market_cap"] or 0) / 1e4  # 亿

            # ── Hard-tech gate: only semiconductor/AI/robotics/new-energy/materials ──
            hard_tech_kw = [
                "半导体", "芯片", "集成电路", "光刻", "晶圆", "封装", "EDA",
                "电子", "通信", "计算机", "软件",
                "机器人", "自动化", "航天", "航空", "军工",
                "新能源", "光伏", "风电", "储能", "电池", "锂电",
                "新材料", "稀土", "特种", "精密", "仪器",
                "医药", "生物", "创新药", "医疗器械",
                "算力", "数据", "网络", "安全",
            ]
            is_hard_tech = any(kw in industry for kw in hard_tech_kw)
            if not is_hard_tech:
                return {"score": 0, "signals": [f"非硬科技({industry})"]}

            peer_count = db.execute(
                "SELECT COUNT(*) as cnt FROM stocks WHERE industry=? AND is_st=0",
                (industry,)
            ).fetchone()["cnt"]

            if peer_count <= 2:
                s += 3.0; sigs.append(f"行业仅{peer_count}家(绝对稀缺)")
            elif peer_count <= 5:
                s += 2.0; sigs.append(f"行业仅{peer_count}家(寡头)")
            elif peer_count <= 10:
                s += 1.0; sigs.append(f"行业{peer_count}家(有限竞争)")

            # ── 2. Semantic chokepoint matching (sentence-transformer) ──
            reps = db.execute(
                "SELECT title FROM research_reports_tushare "
                "WHERE code=? AND code != 'nan' ORDER BY trade_date DESC LIMIT 5",
                (code,)
            ).fetchall()

            # Try semantic matching first (P1 upgrade, model loaded once)
            semantic_score = 0.0
            try:
                if '_ST_MODEL' not in globals():
                    from sentence_transformers import SentenceTransformer
                    global _ST_MODEL, _CP_EMB
                    _ST_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                    _CP_EMB = _ST_MODEL.encode("不可替代的核心供应商 技术壁垒 国产替代 唯一供应商 卡脖子 打破垄断 自主可控")
                _st_model = _ST_MODEL
                cp_emb = _CP_EMB
                cp_query = "不可替代的核心供应商 技术壁垒 国产替代 唯一供应商 卡脖子 打破垄断 自主可控"
                cp_emb = _st_model.encode(cp_query)
                for r in reps:
                    t_emb = _st_model.encode(r["title"])
                    sim = float(np.dot(cp_emb, t_emb) / (np.linalg.norm(cp_emb) * np.linalg.norm(t_emb)))
                    semantic_score = max(semantic_score, sim)
                if semantic_score > 0.3:
                    s += min(3.0, semantic_score * 6)  # 0.3→1.8, 0.5→3.0
                    sigs.append(f"语义卡脖子({semantic_score:.2f})")
            except Exception:
                # Fallback to regex keywords
                chokepoint_kw = {
                    "唯一供应商|独家供应|仅此一家|不可替代|稀缺性": 3.0,
                    "国产替代|打破垄断|自主可控|填补空白|进口替代": 2.0,
                    "核心专利|技术壁垒|护城河|全球龙头|国内第一|市占率": 2.0,
                    "卡脖子|关键环节|核心材料|核心设备": 2.5,
                }
                import re
                kw_matched = set()
                for r in reps:
                    for kw_pattern, bonus in chokepoint_kw.items():
                        if re.search(kw_pattern, r["title"]) and kw_pattern not in kw_matched:
                            kw_matched.add(kw_pattern)
                            s += bonus * 0.5
                if kw_matched:
                    sigs.append(f"研报卡脖子关键词")

            # ── 3. Hard-tech track ──
            ht = score_hard_tech(code)
            tracks = ht.get("tracks", "none")
            if tracks != "none":
                track_bonus = 0
                if any(t in tracks for t in ["半导体"]):
                    track_bonus += 2.0
                if any(t in tracks for t in ["AI算力", "机器人"]):
                    track_bonus += 1.0
                if track_bonus == 0:
                    track_bonus = 0.5
                s += track_bonus
                sigs.append(f"赛道:{tracks}")

            # ── 4. Institutional attention ──
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y%m")
            br_count = db.execute(
                "SELECT COUNT(DISTINCT broker) as cnt FROM broker_recommend "
                "WHERE code=? AND month >= ?", (code, cutoff)
            ).fetchone()["cnt"]

            if br_count >= 3:
                s += 2.0; sigs.append(f"{br_count}家券商覆盖")
            elif br_count >= 1:
                s += 1.0; sigs.append(f"{br_count}家券商覆盖")

            # Smart money check (社保/北向)
            hk = db.execute(
                "SELECT ratio FROM hk_holdings WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (code,)
            ).fetchone()
            if hk and hk["ratio"] and float(hk["ratio"]) > 1:
                s += 1.0; sigs.append("北向持仓")

    except Exception:
        return {"score": 5.0, "signals": ["error"]}

    return {"score": round(max(0, min(10, s)), 1), "signals": sigs, "industry": industry}


def generate_devils_advocate(code: str, chkp_score: dict, kline_df=None) -> list[str]:
    """Generate risk counter-arguments (魔鬼代言人)."""
    risks = []
    try:
        with _get_db(readonly=True) as db:
            row = db.execute(
                "SELECT market_cap, industry FROM stocks WHERE code=?", (code,)
            ).fetchone()
            if not row: return risks

            mc = (row["market_cap"] or 0) / 1e4

            # Liquidity risk
            if kline_df is not None and len(kline_df) >= 20:
                avg_amt = float(kline_df['amount'].iloc[-20:].mean()) / 1e8
                if avg_amt < 0.5:
                    risks.append(f"日均成交仅{avg_amt:.1f}亿，流动性极低")
                elif avg_amt < 1:
                    risks.append(f"日均成交{avg_amt:.1f}亿，流动性偏低")

            # Market cap risk
            if mc < 20:
                risks.append(f"市值仅{mc:.0f}亿，微盘股波动剧烈")
            elif mc < 50:
                risks.append(f"市值{mc:.0f}亿，小盘股风险较高")

            # Concentration risk
            ind = chkp_score.get("industry", row.get("industry", ""))
            if ind:
                peer_cnt = db.execute(
                    "SELECT COUNT(*) FROM stocks WHERE industry=? AND is_st=0",
                    (ind,)
                ).fetchone()[0]
                if peer_cnt <= 3:
                    risks.append(f"行业仅{peer_cnt}家可比公司，信息不充分")

            # Recent run-up risk
            if kline_df is not None and len(kline_df) >= 20:
                closes = kline_df['close'].values
                ret20 = (closes[-1] / closes[-20] - 1) * 100
                if ret20 > 30:
                    risks.append(f"近20日涨幅{ret20:.0f}%，短期已大幅定价")

            # Assumption risk
            chkp_keywords_found = chkp_score.get("signals", [])
            if any("卡脖子" in s or "替代" in s for s in chkp_keywords_found):
                risks.append("核心假设:技术路线不可替代(若替代方案出现则逻辑崩塌)")

    except Exception:
        pass
    return risks


def get_market_regime() -> dict:
    """P2: Enhanced market regime detection with multi-index + volume confirmation.

    Returns regime info + factor-weight adjustment hints.
    """
    try:
        import numpy as np
        with _get_db(readonly=True) as db:
            # Multi-index cross-check: 沪深300 + 创业板 + 中证500
            regime_votes = {"bull": 0, "bear": 0, "neutral": 0}
            for idx_code in ["000300.SH", "399006.SZ", "000905.SH"]:
                rows = db.execute(
                    "SELECT close, vol FROM index_daily WHERE ts_code=? "
                    "ORDER BY trade_date DESC LIMIT 60", (idx_code,)
                ).fetchall()
                if not rows or len(rows) < 20:
                    continue
                closes = np.array([r['close'] for r in reversed(rows)], dtype=np.float64)
                vols = np.array([r['vol'] or 0 for r in reversed(rows)], dtype=np.float64)
                ma20 = np.mean(closes[-20:])
                ma60 = np.mean(closes) if len(closes) >= 60 else ma20
                vol_ma20 = np.mean(vols[-20:]) if len(vols) >= 20 else 0
                vol_ratio = vols[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
                ret_20d = (closes[-1] / closes[-20] - 1) * 100 if closes[-20] > 0 else 0

                # P2: Volume-confirmed regime
                if ret_20d > 3 and closes[-1] > ma20 > ma60 and vol_ratio > 0.8:
                    regime_votes["bull"] += 1
                elif ret_20d < -3 and closes[-1] < ma20 and vol_ratio > 1.1:
                    regime_votes["bear"] += 1
                else:
                    regime_votes["neutral"] += 1

            # Determine consensus regime
            regime = max(regime_votes, key=regime_votes.get)
            confidence = regime_votes[regime] / sum(regime_votes.values())

            if regime == "bull":
                bonus = 0.3 + (confidence - 0.5) * 0.2  # 0.3~0.4 for high confidence
                return {
                    "regime": "bull", "bonus": round(bonus, 2),
                    "label": f"市场强势({regime_votes['bull']}/{sum(regime_votes.values())}指数)",
                    "factor_hint": "momentum_weighted",
                }
            elif regime == "bear":
                bonus = -0.3 - (confidence - 0.5) * 0.2
                return {
                    "regime": "bear", "bonus": round(bonus, 2),
                    "label": f"市场弱势({regime_votes['bear']}/{sum(regime_votes.values())}指数)",
                    "factor_hint": "quality_defensive",
                }
            else:
                return {
                    "regime": "neutral", "bonus": 0.0,
                    "label": f"市场震荡({regime_votes['neutral']}/{sum(regime_votes.values())}指数)",
                    "factor_hint": "technical_weighted",
                }
    except:
        pass
    return {"regime": "neutral", "bonus": 0.0, "label": "未知", "factor_hint": "equal_weighted"}


def get_sector_momentum(code: str) -> float:
    """P2: Calculate sector/industry rotation score using SW industry indices.

    Returns 0-10 score where higher = sector is outperforming.
    """
    try:
        with _get_db(readonly=True) as db:
            # Get stock's SW industry code
            row = db.execute(
                "SELECT industry FROM stocks WHERE code=?", (code,)
            ).fetchone()
            if not row or not row['industry']:
                return 5.0

            industry = row['industry']
            # Find matching SW daily data
            sw_row = db.execute(
                "SELECT ts_code FROM sw_daily WHERE name LIKE ? LIMIT 1",
                (f"%{industry}%",)
            ).fetchone()

            if not sw_row:
                return 5.0

            sw_code = sw_row['ts_code']
            rows = db.execute(
                "SELECT close, pct_change FROM sw_daily WHERE ts_code=? "
                "ORDER BY trade_date DESC LIMIT 20", (sw_code,)
            ).fetchall()

            if not rows or len(rows) < 10:
                return 5.0

            import numpy as np
            changes = np.array([r['pct_change'] or 0 for r in rows], dtype=np.float64)
            ret_5d = sum(changes[:5])
            ret_10d = sum(changes[:10])
            ret_20d = sum(changes[:20]) if len(changes) >= 20 else ret_10d * 2

            # Score: momentum + consistency
            score = 5.0
            if ret_5d > 0: score += min(2.0, ret_5d / 5)
            if ret_10d > 0: score += min(2.0, ret_10d / 10)
            if ret_20d > 0: score += min(1.5, ret_20d / 20)
            # Consistency bonus: positive every day in last 5
            if all(c > 0 for c in changes[:5]):
                score += 0.5

            return max(0, min(10, round(score, 1)))
    except:
        return 5.0


def run_screening(mode="all", top_n=50, method="linear", lgbm_model=None, lgbm_cols=None):
    t0 = time.time()
    use_fusion = method == "fusion" and lgbm_model is not None

    # ── P2: Market regime (enhanced multi-index + volume) ──
    regime = get_market_regime()
    if regime.get("bonus", 0) != 0:
        print(f"  市场环境: {regime['label']} (评分调整 {regime['bonus']:+.1f}) [{regime.get('factor_hint','')}]")

    with _get_db(readonly=True) as db:
        codes = [r["code"] for r in db.execute(
            "SELECT code FROM stocks WHERE is_st=0 ORDER BY code").fetchall()]
        names = {r["code"]: r["name"] for r in db.execute(
            "SELECT code, name FROM stocks").fetchall()}

    all_scores = []
    excluded = 0
    for i, code in enumerate(codes):
        try:
            df = _get_market_data().get_kline_df(code, lookback=400)
            if df is None or len(df) < 30:
                continue
            if should_exclude(code, df):
                excluded += 1; continue

            price = float(df["close"].values[-1])
            ff = score_five_factor(df)
            fund = score_fundamental(code)
            mf = score_money_flow(df); mr = score_mean_reversion(df)
            ts_ = score_trend_strength(df); rev = score_reversal(df); liq = score_liquidity(df)
            ts_scores = get_tushare_scores(code) if os.environ.get("TUSHARE_TOKEN") else {}
            ht = score_hard_tech(code)
            st = score_short_term(df)
            lt = score_long_term(code)
            gr = score_growth(code)
            th = get_stock_themes(code, df, ht)  # themes & catalysts

            # ── Fusion score (LGBM + Linear) ──
            fusion_score = None
            if use_fusion:
                try:
                    feat = compute_fusion_features(ff, fund, mf, mr, ts_, rev, liq, st, lt, gr, ht)
                    fusion_score = compute_fusion_score(lgbm_model, lgbm_cols, feat, 5.0)
                except: pass

            # Mode-specific composite
            if mode == "chokepoint":
                # ── Chokepoint scoring ──
                cp = score_chokepoint(code)
                if cp["score"] < 6.0:
                    excluded += 1; continue  # raise threshold 5→6

                price = float(df["close"].values[-1])
                cp_score = cp["score"]
                # Bonus from identifiability
                idf = score_identifiability(code, df)

                models = [(cp_score, 1.0)]
                tw = 1.0
                composite = cp_score / 2.5  # scale to display range
                score_25 = max(0, min(25, composite * 2.5))

                # Devil's advocate
                devils = generate_devils_advocate(code, cp, df)

                # Store for display
                score_data = {"chokepoint": cp, "devils_advocate": devils,
                              "identifiability": idf, "themes": th}
                all_scores.append({
                    "code": code, "name": names.get(code, "?"),
                    "price": round(price, 2), "score": round(score_25, 1),
                    "grade": cp_score > 8 and "S" or (cp_score > 6 and "A" or "B"),
                    "cp_score": cp_score, "devils": devils,
                    "cp_signals": cp.get("signals", []),
                    "_df": df, "_scores": score_data,
                })
                continue  # skip normal model building

            if mode == "short":
                # ── Multi-timeframe pre-filter ──
                mtf = check_multi_timeframe_trend(code)
                if not mtf.get("weekly_ok") or not mtf.get("monthly_ok"):
                    excluded += 1; continue

                mg = score_margin_momentum(code)
                idf = score_identifiability(code, df)

                # P1: ICIR-weighted (backtest-verified 2026-06-08)
                # Removed: Tushare-资金流向(ICIR=-0.12), Tushare-融资融券(ICIR=-0.05), 均值回归(ICIR=-0.88)
                models = [
                    # Core technical (ICIR=+20.86, boosted 30%)
                    (st["score"], 0.30),
                    (ff["volume_factor"], 0.10),     # ICIR=+4.18
                    (ts_["score"], 0.08),             # ICIR=+0.88
                    (ff["score"]/25*10, 0.07),        # ICIR=+6.45 composite
                    # Momentum: inverted (ICIR=-7.49, contrarian signal)
                    ((8.0 - ff["momentum"]), 0.06),
                    # Money flow (ICIR=+0.88)
                    (mf["score"], 0.05),
                    # Margin momentum
                    (mg["score"], 0.07),
                    # Dragon/Tiger + Institutional (keep verified)
                    (ts_scores.get("tushare_top_list",{}).get("score",5), 0.08),
                    (ts_scores.get("tushare_top_inst",{}).get("score",5), 0.06),
                    # Analyst + North-bound
                    (ts_scores.get("tushare_analyst",{}).get("score",5), 0.03),
                    (ts_scores.get("tushare_hk_hold",{}).get("score",5), 0.03),
                    # Identifiability
                    (idf["score"], 0.07),
                ]
            elif mode == "long":
                models = [
                    (lt["score"], 0.40), (gr["score"], 0.35),  # growth up to 35%
                    (ht["score"]*2, 0.10),
                    (ts_scores.get("tushare_financial",{}).get("score",5), 0.08),
                    (ts_scores.get("tushare_daily_basic",{}).get("score",5), 0.05),
                    (ts_scores.get("tushare_por",{}).get("score",5), 0.02),  # NEW
                ]
            else:  # all — streamlined: removed ICIR≈0 factors
                idf_all = score_identifiability(code, df)
                # P1: Removed Tushare-资金流向(ICIR=-0.122) & 融资融券(ICIR=-0.046)
                # Momentum inverted (ICIR=-7.49), Technical amplified (ICIR=+20.86)
                models = [
                    (ff["technical"], 0.040),       # P1: ICIR=+20.86, amplified ×2
                    (ff["volume_factor"], 0.028),    # ICIR=+4.18
                    (ff["score"]/25*10, 0.027),      # ICIR=+6.45 composite
                    ((8.0 - ff["momentum"]), 0.025), # P1: momentum inverted (ICIR=-7.49)
                    (ff["quality"], 0.025),           # ICIR=+1.05
                    (ts_scores.get("tushare_daily_basic",{}).get("score",5), 0.020),
                    (ts_scores.get("tushare_financial",{}).get("score",5), 0.010),
                    (ht["score"]*2, 0.012), (gr["score"], 0.018),
                    (st["score"], 0.005), (lt["score"], 0.005),
                    (ts_scores.get("tushare_por",{}).get("score",5), 0.010),
                    (idf_all["score"], 0.008),
                ]

            # ── P2: Regime-adaptive weight adjustment ──
            hint = regime.get("factor_hint", "")
            if hint == "quality_defensive" and mode == "short":
                # Bear market: shift weight from momentum to quality + risk control
                models = [(s, w * 0.7 if i == 0 else w) for i, (s, w) in enumerate(models)]  # reduce short-term
                models.append((ff["quality"], 0.03))  # boost quality
                models.append((abs(ff["risk"]), 0.02))  # reward low risk
            elif hint == "momentum_weighted" and mode == "short":
                # Bull market: ride momentum harder
                models = [(s, w * 1.15 if i < 3 else w) for i, (s, w) in enumerate(models)]  # boost top 3

            # ── P2: Multi-timeframe bonus (周线+月线确认) ──
            mtf_bonus = 0.0
            if mode == "short":
                mtf = check_multi_timeframe_trend(code)
                if mtf.get("weekly_ok"):
                    mtf_bonus += 0.3  # 周线多头排列
                if mtf.get("monthly_ok"):
                    mtf_bonus += 0.2  # 月线多头排列

            # ── P2: Sector rotation factor ──
            sector_score = get_sector_momentum(code)

            tw = sum(w for _, w in models) + 0.03  # +3% for sector factor
            composite = sum(s * w for s, w in models) / tw if tw else 5.0
            composite += regime["bonus"] + mtf_bonus + sector_score * 0.03 / tw

            # ── Fusion override: LGBM score replaces linear composite ──
            if use_fusion and fusion_score is not None:
                composite = fusion_score / 100
                composite += regime["bonus"] + mtf_bonus + sector_score * 0.03 / max(tw, 0.01)
                # P2: Keep multi-timeframe + sector bonuses in fusion mode

            score_25 = max(0, min(25, composite * 2.5))

            # Build reason string
            reasons = []
            # ── Theme (all modes) ──
            if th.get("hot_topics"):
                reasons.append(th["hot_topics"])
            if th.get("thesis"):
                reasons.append(th["thesis"][:50])
            if th.get("tracks"):
                reasons.append(th["tracks"])

            if mode == "short":
                reasons.extend(st.get("signals", []))
                # Add margin momentum signals
                if mg["score"] >= 7:
                    reasons.extend(mg.get("signals", [])[:2])
                # Add identifiability highlights
                if idf["score"] >= 7:
                    reasons.extend(idf.get("signals", [])[:1])
                # Add multi-timeframe confirmation
                if mtf.get("weekly_ok"):
                    reasons.append(f"周线多头")
                if mtf.get("monthly_ok"):
                    reasons.append(f"月线向上")
            elif mode == "long":
                reasons = lt.get("signals", []) + gr.get("signals", [])
                tracks = ht.get("tracks", "none")
                if tracks != "none": reasons.append(tracks)
            else:
                sub = {"动量": ff["momentum"], "量能": ff["volume_factor"],
                       "技术": ff["technical"], "质量": ff["quality"],
                       "均值回归": mr["score"], "MFI": mf["score"], "趋势": ts_["score"],
                       "融资": ts_scores.get("tushare_margin",{}).get("score",5),
                       "资金流": ts_scores.get("tushare_moneyflow",{}).get("score",5),
                       "日指": ts_scores.get("tushare_daily_basic",{}).get("score",5),
                       "财报": ts_scores.get("tushare_financial",{}).get("score",5),
                       "硬科技": ht["score"]*2, "增长": gr["score"],
                       "短线": st["score"], "长线": lt["score"]}
                top4 = sorted(sub.items(), key=lambda x: x[1], reverse=True)[:4]
                reasons = [f"{k}={v:.1f}" for k, v in top4 if v > 5.5]

            reason_str = " | ".join(reasons) if reasons else "因子共振不足"

            # Store scores for later rationale building
            score_data = {
                "short_term": st, "long_term": lt, "growth": gr,
                "hard_tech": ht, "tushare": ts_scores, "themes": th,
                "margin_momentum": mg if mode == "short" else {},
                "identifiability": idf if mode == "short" else {},
                "multi_timeframe": mtf if mode == "short" else {},
            }

            all_scores.append({
                "code": code, "name": names.get(code, "?"),
                "price": round(price, 2), "score": round(score_25, 1),
                "grade": ff["grade"], "mode": mode,
                "reasons": reason_str,
                "_df": df, "_scores": score_data,  # kept for post-processing
            })
        except Exception:
            pass
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{len(codes)} ({time.time()-t0:.0f}s)")

    all_scores.sort(key=lambda x: x["score"], reverse=True)

    # ── Industry diversification: penalize over-concentration ──
    if mode in ("long", "all") and all_scores:
        industry_count = {}
        for s in all_scores:
            ind = names.get(s["code"], s["code"])
            # Get actual industry from stocks
            try:
                row = db.execute("SELECT industry FROM stocks WHERE code=?", (s["code"],)).fetchone()
                ind = row["industry"] if row and row["industry"] else "其他"
            except:
                ind = "其他"
            industry_count[ind] = industry_count.get(ind, 0) + 1
            # Stricter penalty: 资源品/同质化行业 ≥3 只开始，其他 ≥5 只
            heavy_ind = ("资源品涨价" in str(ind) or "有色" in str(ind) or "煤炭" in str(ind) or "化工" in str(ind))
            threshold = 2 if heavy_ind else 4  # tightened: 3→2, 5→4
            if industry_count[ind] > threshold:
                penalty = (industry_count[ind] - threshold) * 0.25  # 0.20→0.25
                s["score"] = round(max(0, s["score"] - penalty), 1)
        # Re-sort after penalty
        all_scores.sort(key=lambda x: x["score"], reverse=True)

    # ── LONG/ALL mode: 机构资金二次确认 (top 500 candidates) ──
    if mode in ("long", "all") and all_scores:
        ss_check_n = min(500, len(all_scores))
        print(f"\n  🔍 机构资金确认中 (社保/养老/年金/险资/QFII) Top {ss_check_n}...")
        ss_t0 = time.time()
        ss_checked = 0; ss_hits = 0
        for s in all_scores[:ss_check_n]:
            try:
                ss = check_institutional_funds(s["code"])
                s["institutional"] = ss
                if ss["score_bonus"] > 0:
                    s["score"] = round(s["score"] + ss["score_bonus"], 1)
                    s["ss_bonus"] = ss["score_bonus"]
                    s["ss_status"] = ss["status"]
                    s["ss_funds"] = ss["funds"]
                    s["ss_fund_types"] = ss.get("fund_types", [])
                    if "_scores" in s:
                        s["_scores"]["institutional"] = ss
                    ss_hits += 1
                ss_checked += 1
                if ss_checked % 50 == 0:
                    print(f"    机构检查: {ss_checked}/{ss_check_n} ({time.time()-ss_t0:.0f}s), 命中: {ss_hits}")
            except Exception:
                pass
        if ss_checked > 0:
            print(f"  机构检查完成: {ss_checked}只, 命中 {ss_hits}只 ({ss_hits/max(1,ss_checked)*100:.0f}%), 耗时 {time.time()-ss_t0:.0f}s")
            # Re-sort with bonuses
            all_scores[:ss_check_n] = sorted(all_scores[:ss_check_n], key=lambda x: x["score"], reverse=True)
            # Update ranks
            for i, s in enumerate(all_scores):
                s["rank"] = i + 1

    gc = Counter(s["grade"] for s in all_scores)
    print(f"\n[{mode.upper()}模式] {len(all_scores)} scored, {excluded} excluded ({time.time()-t0:.0f}s)")
    print(f"Dist: S={gc.get('S',0)} A={gc.get('A',0)} B={gc.get('B',0)} C={gc.get('C',0)}")

    # Print Top N with full details
    header = f"Top {top_n} ({mode}模式)"
    print("\n" + "=" * 120)
    print(f"  {header}")
    print("=" * 120)

    for i, s in enumerate(all_scores[:top_n]):
        code = s["code"]; name = s["name"]; price = s["price"]
        df = s.pop("_df", None)
        score_data = s.pop("_scores", {})
        levels = compute_trade_levels(df, mode) if df is not None else {}
        rationale = build_rationale(code, name, df, score_data, mode, levels)
        risk = assess_risk(code, df, score_data, mode)
        devils = s.get("devils", [])

        # 社保基金标记
        ss_tag = ""
        if mode in ("long", "all") and s.get("ss_status"):
            status_map = {"new": "🔥机构新进", "increased": "📈机构增持", "holding": "💼机构持有"}
            ss_tag = f"  |  {status_map.get(s['ss_status'], '')}"
            if s.get("ss_funds"):
                ss_tag += f" ({', '.join(s['ss_funds'][:2])})"
            if s.get("ss_fund_types"):
                ss_tag += f" [{','.join(s['ss_fund_types'])}]"

        cp_tag = ""
        if mode == "chokepoint" and s.get("cp_signals"):
            cp_tag = f"  |  {' · '.join(s['cp_signals'][:3])}"
        print(f'\n  [{i+1}] {code} {name}  |  评分: {s["score"]:.1f} ({s["grade"]}级)  |  现价: {price:.2f}{ss_tag}{cp_tag}  |  {risk["level"]} 仓位{risk["position"]}')
        if devils:
            for d in devils[:3]:
                print(f'      ⚠️ {d}')
        if levels:
            print(f'      入场: {levels["entry"]:.2f}  |  止损: {levels["stop_loss"]:.2f}  |  '
                  f'目标1: {levels["target_1"]:.2f}  |  目标2: {levels["target_2"]:.2f}  |  '
                  f'盈亏比: {levels["risk_reward"]:.1f}:1')
        print(f'      上涨理由: {rationale}')
        s["rationale"] = rationale
        if levels:
            s["levels"] = {k: v for k, v in levels.items() if not isinstance(v, (np.ndarray,))}

    out_path = f"outputs/screening_{mode}_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    with open(out_path, "w") as f:
        clean = [{k: v for k, v in s.items() if not k.startswith("_")} for s in all_scores[:top_n]]
        json.dump(clean, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {out_path}")
    return all_scores[:top_n]


def get_fusion_scorer():
    """Load CatBoost model for fusion scoring (replaces LGBM, no OpenMP conflict).
    Returns (model, feature_cols) or (None, None)."""
    try:
        from catboost import CatBoostRegressor
        with open('outputs/models/catboost_ranker/meta.json') as f:
            meta = json.load(f)
        model = CatBoostRegressor()
        model.load_model('outputs/models/catboost_ranker/model.cbm')
        return model, meta['feature_cols']
    except Exception:
        return None, None


def compute_fusion_features(ff, fund, mf, mr, ts_, rev, liq, st, lt, gr, ht):
    """Compute 19-feature vector for CatBoost fusion."""
    return {
        'momentum': ff['momentum'], 'volume_factor': ff['volume_factor'],
        'technical': ff['technical'], 'quality': ff['quality'], 'risk': ff['risk'],
        'five_factor_composite': ff['score'] / 25 * 10,
        'money_flow': mf['score'], 'mean_reversion': mr['score'],
        'trend_strength': ts_['score'], 'reversal': rev['score'],
        'liquidity': liq['score'], 'fundamental': fund,
        'growth': gr['score'], 'hard_tech': ht['score'] * 2,
        'short_term': st['score'], 'long_term': lt['score'],
        'q_m_ratio': ff['quality'] / max(ff['momentum'], 0.1),
        't_v_interact': ts_['score'] * ff['volume_factor'] / 10,
        'r_l_interact': rev['score'] * liq['score'] / 10,
    }


def compute_fusion_score(fusion_model, feat_cols, features, linear_score):
    """CatBoost × 6 + Linear × 0.4 — fusion scoring."""
    import numpy as np
    vec = np.array([[features.get(c, 0) for c in feat_cols]], dtype=np.float32)
    cb_s = float(fusion_model.predict(vec)[0])
    return cb_s * 6 + linear_score * 0.4


if __name__ == "__main__":
    import pandas as pd, numpy as np
    parser = argparse.ArgumentParser(description="Kronos screening")
    parser.add_argument("--mode", default="all", choices=["short", "long", "all", "chokepoint"])
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--method", default="linear", choices=["linear", "fusion"],
                        help="Scoring method: linear weights or LGBM+Linear fusion")
    args = parser.parse_args()

    # Pre-load CatBoost if fusion method
    fusion_model, fusion_cols = None, None
    if args.method == "fusion":
        fusion_model, fusion_cols = get_fusion_scorer()
        if fusion_model:
            print(f"  CatBoost Fusion: {fusion_model.tree_count_} trees loaded")
        else:
            print("  ⚠️ CatBoost not available, falling back to linear")
            args.method = "linear"

    run_screening(mode=args.mode, top_n=args.top_n, method=args.method,
                  lgbm_model=fusion_model, lgbm_cols=fusion_cols)
