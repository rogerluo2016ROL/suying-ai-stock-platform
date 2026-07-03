#!/usr/bin/env python3
"""龙头短线战法 — Leading Stock Short-term Strategy.

7-factor weighted scoring for identifying sector-leading stocks
with 7-12% daily gains and strong institutional follow-through.

Usage:
    python tools/leader_scalp.py --date 2026-06-05 --top-n 20
    python tools/leader_scalp.py --date 2026-06-05 --backtest 5  # last 5 days
    python tools/leader_scalp.py --date 2026-06-05 --db-write --top-n 20  # persist to DB
"""
import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime
from enum import Enum

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TUSHARE_TOKEN", os.environ.get("TUSHARE_TOKEN", ""))

from kronos_factors.scorer._db_stub import _get_db, _get_market_data

# Stub: DB write function — inject real implementation in production
_write_screening_scores = None


# ── V4.0: 市场环境枚举 ──
class MarketEnv(Enum):
    BULL = "bull"       # 做多环境：正常选股+满仓 (max 20% per stock)
    NEUTRAL = "neutral" # 中性偏弱：选股+半仓 (max 10% per stock)
    BEAR = "bear"       # 观望：选股但不交易（仅记录观察）
    CRASH = "crash"     # 熔断：不选股，直接跳过


def assess_market_env(db, trade_date):
    """V4.0 模块A: 市场环境评估 — 预判当日选股风险等级。

    根据上证指数表现、跌停家数、全市场涨跌比判定市场环境。
    返回 (MarketEnv, env_detail_dict)。

    数据来源:
      - index_daily: 上证指数 000001.SH
      - limit_list_d: 跌停统计 (limit_type='D')
      - daily_kline: 全市场涨跌比
    """
    detail = {"sh_pct": 0, "limit_down_count": 0, "breadth": 0,
              "consecutive_drops": 0, "reason": ""}

    # 1. 上证指数表现
    # NOTE: PG index_daily.code stores bare '000001' (no .SH suffix); the inline literal
    # is NOT routed through pg_adapter._translate_params (only bound params are), so the
    # historical '000001.SH' literal never matched and sh_pct silently returned 0.
    sh_row = db.execute(
        "SELECT pct_chg FROM index_daily WHERE ts_code='000001' AND trade_date=?",
        (trade_date,)
    ).fetchone()
    sh_pct = float(sh_row["pct_chg"]) if sh_row and sh_row["pct_chg"] is not None else 0
    detail["sh_pct"] = round(sh_pct, 2)

    # CRASH: 上证跌 > 2%
    if sh_pct < -2:
        detail["reason"] = f"上证暴跌{sh_pct:.1f}%, 触发熔断"
        return MarketEnv.CRASH, detail

    # 2. 跌停家数（limit_list_d 中 pct_chg < 0 即跌停）
    td = trade_date.replace('-', '')
    ld_row = db.execute(
        "SELECT COUNT(*) as cnt FROM limit_list_d "
        "WHERE trade_date=? AND pct_chg < 0",
        (td,)
    ).fetchone()
    ld_count = ld_row["cnt"] if ld_row else 0
    detail["limit_down_count"] = ld_count

    # CRASH: 跌停 > 50
    if ld_count > 50:
        detail["reason"] = f"跌停{ld_count}家, 市场恐慌, 触发熔断"
        return MarketEnv.CRASH, detail

    # 3. 全市场涨跌比（breadth）
    breadth_row = db.execute(
        "SELECT "
        "SUM(CASE WHEN b.close > 0 AND a.close > b.close THEN 1 ELSE 0 END) as up, "
        "SUM(CASE WHEN b.close > 0 AND a.close < b.close THEN 1 ELSE 0 END) as down "
        "FROM daily_kline a "
        "JOIN daily_kline b ON a.code=b.code AND b.trade_date < a.trade_date "
        "JOIN stocks s ON a.code=s.code "
        "WHERE a.trade_date=? AND s.is_st=0 AND s.name NOT LIKE '%ST%'",
        (trade_date,)
    ).fetchone()
    up_count = breadth_row["up"] if breadth_row else 1
    down_count = breadth_row["down"] if breadth_row else 1
    total_count = up_count + down_count
    breadth = up_count / max(1, total_count) * 100
    detail["breadth"] = round(breadth, 1)

    # BEAR: 涨跌比 < 1:3 (75%+ 下跌)
    if breadth < 25:
        detail["reason"] = f"全市场仅{breadth:.0f}%上涨({up_count}/{total_count}), 极度弱势"
        return MarketEnv.BEAR, detail

    # 4. 连续下跌检测
    prev_dates = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 4",
        (trade_date,)
    ).fetchall()
    if len(prev_dates) >= 3:
        prev_sh = []
        for i, pd_row in enumerate(prev_dates[1:4]):  # last 3 days before today
            pr = db.execute(
                "SELECT pct_chg FROM index_daily WHERE ts_code='000001' AND trade_date=?",
                (pd_row["trade_date"],)
            ).fetchone()
            prev_sh.append(float(pr["pct_chg"]) if pr and pr["pct_chg"] is not None else 0)

        # Count consecutive down days (including today)
        consecutive = 0
        for chg in [sh_pct] + prev_sh:
            if chg < -0.5:
                consecutive += 1
            else:
                break
        detail["consecutive_drops"] = consecutive

        # BEAR: 连续2日跌 > 0.5%
        if consecutive >= 2:
            detail["reason"] = f"上证连续{consecutive}日下跌>0.5%, 弱势延续"
            return MarketEnv.BEAR, detail

    # NEUTRAL: 上证跌 0.5%-1%, 或 breadth 25-40%
    if sh_pct < -0.5 or breadth < 40:
        detail["reason"] = f"市场偏弱(上证{sh_pct:+.1f}%, 上涨占比{breadth:.0f}%), 半仓运行"
        return MarketEnv.NEUTRAL, detail

    # BULL: 正常环境
    detail["reason"] = f"市场正常(上证{sh_pct:+.1f}%, 上涨占比{breadth:.0f}%), 全仓运行"
    return MarketEnv.BULL, detail


# ── Scoring weights (v3: 5-6月404样本 IC校准, P0优化A+B+D) ──
WEIGHTS = {
    "gain_quality": 20,       # 涨幅质量 (V4 IC=+0.04, 温和正向)
    "sector_leader": 28,      # 板块龙头 (V4 IC=+0.02, 温和正向)
    "ma_trend": 3,            # 均线趋势 (V4 IC=-0.07, 持续负向→降权)
    "turnover": 10,           # 成交额 (V4 IC=+0.10, 倒U型有效)
    "sector_resonance": 8,    # 板块共振 (V4 IC=+0.09, 稳定正向)
    "capital_flow": 22,       # 主力资金 (V4 IC=+0.08, 强信号→升权)
    "sector_momentum": 15,    # V4.1: 板块动量 IC=+0.126, 最强信号→升权从10到15
    "seal_quality": 5,        # 封板质量bonus (V4 IC=+0.07, 稳定)
    "resilience": 5,          # V4.1: 分歧不死 IC=+0.109, 重加回总分 (V3误判为负)
}
TOTAL_WEIGHT = sum(WEIGHTS.values())  # 116


def detect_extreme_loss_risk(db, trade_date, market_env):
    """V4.1 E1: 极端亏损日风险检测。

    检测三种历史回测中导致大幅亏损的模式：
      1. 长假/周末缺口风险 — 3+天无交易后首个交易日
      2. 前日大涨后的获利回吐 — 前日Top选股均值>5%时次日衰竭
      3. 板块轮动崩塌 — 前日最强板块今日逆转>2%

    Returns: (risk_level, risk_detail)
      risk_level: 0=安全, 1=警告(降仓), 2=危险(仅观察), 3=极高(暂停)
    """
    risk_detail = {"gap_days": 0, "prev_rally": False, "sector_reversal": False,
                   "risk_score": 0, "reasons": []}

    # 1. 缺口风险: 检查与上一个交易日的间隔
    prev_date_row = db.execute(
        "SELECT trade_date FROM daily_kline WHERE trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (trade_date,)
    ).fetchone()
    if prev_date_row:
        prev_date = str(prev_date_row["trade_date"])[:10]  # PG may return datetime.date
        from datetime import datetime, timedelta
        try:
            td_dt = datetime.strptime(str(trade_date)[:10], "%Y-%m-%d")
            pd_dt = datetime.strptime(prev_date, "%Y-%m-%d")
            gap_days = (td_dt - pd_dt).days
            risk_detail["gap_days"] = gap_days

            if gap_days >= 4:
                risk_detail["risk_score"] += 3
                risk_detail["reasons"].append(f"{gap_days}天长假缺口(周末+节日), 不确定性高")
            elif gap_days >= 3:
                risk_detail["risk_score"] += 2
                risk_detail["reasons"].append(f"{gap_days}天周末缺口, 适度谨慎")
        except ValueError:
            pass

    # 2. 前日大涨衰竭: 检查前日选股结果
    # Check if previous day had extreme returns (suggesting profit-taking)
    if prev_date_row:
        prev_top_ret = db.execute(
            "SELECT AVG((a.close/NULLIF(b.close,0)-1)*100) as avg_gain "
            "FROM daily_kline a "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date < a.trade_date "
            "WHERE a.trade_date=? AND a.amount/1e5 >= 10 "
            "AND b.close > 0 "
            "AND (a.close/NULLIF(b.close,0)-1)*100 BETWEEN 7 AND 12",
            (prev_date,)
        ).fetchone()
        if prev_top_ret and prev_top_ret["avg_gain"] and prev_top_ret["avg_gain"] > 8.5:
            risk_detail["prev_rally"] = True
            risk_detail["risk_score"] += 2
            risk_detail["reasons"].append(f"前日强势股均值{prev_top_ret['avg_gain']:.1f}%, 获利回吐压力大")

    # 3. 板块轮动崩塌: 昨日最强板块今日是否逆转
    if prev_date_row:
        prev_top_sector = db.execute(
            "SELECT s.industry FROM daily_kline a "
            "JOIN stocks s ON a.code=s.code "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date < a.trade_date "
            "WHERE a.trade_date=? AND (a.close/NULLIF(b.close,0)-1)*100 >= 9.5 "
            "GROUP BY s.industry ORDER BY COUNT(*) DESC LIMIT 1",
            (prev_date,)
        ).fetchone()
        if prev_top_sector:
            ind = prev_top_sector["industry"]
            kw = ind[-2:] if len(ind) >= 2 else ind
            sector_today = db.execute(
                "SELECT d.pct_chg FROM index_daily d "
                "JOIN index_basic b ON d.code=b.code "
                "WHERE b.name LIKE ? AND d.trade_date=? "
                "ORDER BY ABS(d.pct_chg) DESC LIMIT 1",
                (f"%{kw}%", trade_date)
            ).fetchone()
            if sector_today and sector_today["pct_chg"] and float(sector_today["pct_chg"]) < -1.5:
                risk_detail["sector_reversal"] = True
                risk_detail["risk_score"] += 2
                risk_detail["reasons"].append(f"前日最强板块{ind}今日逆转{float(sector_today['pct_chg']):+.1f}%")

    # Determine risk level
    risk_score = risk_detail["risk_score"]
    if risk_score >= 4:
        risk_level = 3  # 极高
    elif risk_score >= 3:
        risk_level = 2  # 危险
    elif risk_score >= 2:
        risk_level = 1  # 警告
    else:
        risk_level = 0  # 安全

    return risk_level, risk_detail


def get_last_trading_days(db, n=5):
    """Get the last N distinct trading days."""
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline ORDER BY trade_date DESC LIMIT ?", (n,)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_stock_universe(db, trade_date):
    """Get non-ST stocks with K-line data on the given date.

    Note: is_st field is unreliable (246 ST stocks have is_st=0).
    Name-based ST filter is the safety net.
    """
    rows = db.execute(
        "SELECT DISTINCT d.code, s.name, s.industry, s.float_mv "
        "FROM daily_kline d JOIN stocks s ON d.code=s.code "
        "WHERE d.trade_date=? AND s.is_st=0 "
        "AND s.name NOT LIKE '%ST%'"  # ST股名称过滤 (is_st字段不可靠)
        "AND (s.float_mv IS NULL OR s.float_mv >= 20)",  # NULL视为通过
        (trade_date,)
    ).fetchall()
    return {r["code"]: {"name": r["name"], "industry": r["industry"] or "其他",
                         "float_mv": r["float_mv"] or 30} for r in rows}


def get_kline_data(db, code, trade_date, lookback=60):
    """Get K-line data up to and including trade_date."""
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount, trade_date "
        "FROM daily_kline WHERE code=? AND trade_date<=? "
        "ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    return rows


def get_pre_close(db, code, trade_date):
    """Get previous close price — try stk_limit first (official), then daily_kline."""
    # stk_limit is the official exchange-provided pre_close
    row = db.execute(
        "SELECT pre_close FROM stk_limit WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if row and row["pre_close"] and row["pre_close"] > 0:
        return row["pre_close"]
    # Fallback: previous trading day close from daily_kline
    row = db.execute(
        "SELECT close, trade_date FROM daily_kline WHERE code=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    return row["close"] if row else None


def get_moneyflow(db, code, trade_date):
    """Get institutional money flow data."""
    row = db.execute(
        "SELECT buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount, "
        "net_mf_amount FROM moneyflow WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    return row


def get_sector_index(db, industry, trade_date, code=None):
    """Get sector index performance (V6.8: THS概念优先 → index_basic fallback).

    V6.8: 修复 ths_daily.code 格式不一致 (700001 vs 700001.TI),
    今日无数据时回退到最近交易日.
    """
    # 1. THS概念路径 (psycopg2 raw — 避免 adapter 把 m.ts_code 错译成 m.code)
    if code:
        raw_conn = None
        try:
            raw_conn = db._get_conn()
            cur = raw_conn.cursor()
            # V6.8: 修复 code 格式不一致, 今日无数据回退最近交易日
            cur.execute(
                "SELECT d.change_pct, i.name FROM ths_daily d "
                "JOIN ths_member m ON (m.ts_code = d.code OR m.ts_code = d.code || '.TI') "
                "JOIN ths_index i ON m.ts_code = i.ts_code "
                "WHERE m.con_code LIKE %s AND d.trade_date = %s "
                "ORDER BY ABS(d.change_pct) DESC LIMIT 1",
                (f"{code}%", trade_date)
            )
            r = cur.fetchone()
            # Fallback: 今日无数据 → 最近交易日
            if not r:
                cur.execute(
                    "SELECT d.change_pct, i.name FROM ths_daily d "
                    "JOIN ths_member m ON (m.ts_code = d.code OR m.ts_code = d.code || '.TI') "
                    "JOIN ths_index i ON m.ts_code = i.ts_code "
                    "WHERE m.con_code LIKE %s "
                    "ORDER BY d.trade_date DESC, ABS(d.change_pct) DESC LIMIT 1",
                    (f"{code}%",)
                )
                r = cur.fetchone()
            if r and r[0] is not None:
                return {"pct_change": float(r[0]), "amount": 0,
                        "name": r[1] or "", "source": "ths"}
        except Exception:
            pass
        finally:
            if raw_conn:
                try:
                    db._put_conn(raw_conn)
                except Exception:
                    pass

    # 2. index_basic → index_daily fallback
    keyword = industry[-2:] if len(industry) >= 2 else industry
    row = db.execute(
        "SELECT d.pct_chg, b.name FROM index_daily d "
        "JOIN index_basic b ON d.code=b.code "
        "WHERE b.name LIKE ? AND d.trade_date=? "
        "ORDER BY ABS(d.pct_chg) DESC LIMIT 1",
        (f"%{keyword}%", trade_date)
    ).fetchone()
    # Fallback: 今日无数据 → 最近交易日
    if (not row or row["pct_chg"] is None):
        row = db.execute(
            "SELECT d.pct_chg, b.name FROM index_daily d "
            "JOIN index_basic b ON d.code=b.code "
            "WHERE b.name LIKE ? "
            "ORDER BY d.trade_date DESC, ABS(d.pct_chg) DESC LIMIT 1",
            (f"%{keyword}%",)
        ).fetchone()
    if row and row["pct_chg"] is not None:
        return {"pct_change": float(row["pct_chg"]), "amount": 0,
                "name": row["name"], "source": "index"}

    return None


def get_shanghai_index(db, trade_date):
    """Get Shanghai Composite performance.

    PG index_daily.code stores bare '000001' (no .SH suffix). The inline literal is
    NOT routed through pg_adapter._translate_params (only bound params are), so it must
    match PG's stored value verbatim — the old '000001.SH' literal always returned 0.
    """
    row = db.execute(
        "SELECT pct_chg FROM index_daily WHERE ts_code='000001' AND trade_date=?",
        (trade_date,)
    ).fetchone()
    return row["pct_chg"] if row else 0


def compute_ma(closes, period):
    """Compute simple moving average."""
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def get_weak_sectors(db, trade_date, bottom_pct=20):
    """优化E: 板块动量过滤 — 返回近5日表现最差的板块集合。

    404样本: 矿物制品(-2.04%), 塑料(-0.66%)等弱势板块显著拖累胜率。
    计算各板块近5日平均收益，bottom percentile标记为弱势。
    """
    # 获取近5个交易日
    prev_dates = [r["trade_date"] for r in db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 6", (trade_date,)
    ).fetchall()]
    if len(prev_dates) < 6:
        return set()
    date_5d_ago = prev_dates[-1]  # 5 trading days ago

    # 获取所有行业
    industries = [r["industry"] for r in db.execute(
        "SELECT DISTINCT industry FROM stocks WHERE industry IS NOT NULL AND industry != ''"
    ).fetchall()]

    sector_5d = {}
    for ind in set(industries):
        # 计算该行业所有股票近5日平均涨幅
        row = db.execute(
            "SELECT AVG((a.close/NULLIF(b.close,0)-1)*100) as avg_5d "
            "FROM daily_kline a "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
            "JOIN stocks s ON a.code=s.code "
            "WHERE a.trade_date=? AND s.industry=? AND b.close>0 AND a.close>0",
            (date_5d_ago, trade_date, ind)
        ).fetchone()
        if row and row["avg_5d"] is not None:
            sector_5d[ind] = row["avg_5d"]
        else:
            sector_5d[ind] = 0

    if len(sector_5d) < 5:
        return set()

    # Bottom percentile = weak
    sorted_sectors = sorted(sector_5d.items(), key=lambda x: x[1])
    cutoff_idx = max(1, int(len(sorted_sectors) * bottom_pct / 100))
    weak = {ind for ind, _ in sorted_sectors[:cutoff_idx]}
    return weak


def score_sector_cycle(db, industry, trade_date):
    """F8: 板块周期阶段评分 (0-10) — 板块推演术启发 (V5.2 fix).

    优先"将成龙/主升初期"，避开"充分演绎"。
    """
    keyword = industry[-2:] if len(industry) >= 2 else industry
    score = 0

    # V5.2 fix: index_basic → index_daily (ths_daily empty, sw_daily columns wrong)
    rows = db.execute(
        "SELECT d.pct_chg, d.trade_date FROM index_daily d "
        "JOIN index_basic b ON d.code=b.code "
        "WHERE b.name LIKE ? AND d.trade_date <= ? "
        "ORDER BY d.trade_date DESC LIMIT 5",
        (f"%{keyword}%", trade_date)
    ).fetchall()

    if not rows or len(rows) < 3:
        return 5  # Insufficient data → neutral

    changes = [(float(r["pct_chg"]) if r["pct_chg"] is not None else 0) for r in rows]

    # Sector trend strength: recent 3-day cumulative return
    cum_3d = sum(changes[:3]) if len(changes) >= 3 else 0
    cum_5d = sum(changes[:5]) if len(changes) >= 5 else cum_3d

    # Count strong days (≥1%) in past 5
    strong_days = sum(1 for c in changes[:5] if c > 1)

    # Count consecutive up days
    up_streak = 0
    for c in changes:
        if c > 0: up_streak += 1
        else: break

    # Scoring
    if cum_3d > 5: score += 3      # 强趋势
    elif cum_3d > 2: score += 2
    elif cum_3d > 0: score += 1

    if strong_days >= 3: score += 3  # 持续走强
    elif strong_days >= 2: score += 2

    if up_streak >= 3: score += 2   # 连阳=主升
    elif up_streak >= 2: score += 1

    # Penalty: sector declining (充分演绎/衰退)
    if cum_5d < -3: score -= 2
    if cum_3d < 0 and cum_5d < 0: score -= 1

    return max(0, min(10, score))


def score_leader_role(db, code, industry, trade_date, gain_pct, amount_yi):
    """F9: 龙头角色识别 (0-10) — 板块推演术: 总龙>日内龙>中军>跟风。

    Within the same sector, identify the stock's role based on
    gain rank (总龙/日内龙) and volume rank (中军).
    """
    td = trade_date.replace('-', '')
    score = 0

    # Find all qualifying stocks in same sector
    peers = db.execute(
        "SELECT a.code, (a.close/NULLIF(b.close,0)-1)*100 as gain, a.amount/1e5 as amt, a.volume "
        "FROM daily_kline a "
        "JOIN daily_kline b ON a.code=b.code AND b.trade_date < ? "
        "JOIN stocks s ON a.code=s.code "
        "WHERE a.trade_date=? AND s.industry=? AND gain BETWEEN 7 AND 12",
        (trade_date, trade_date, industry)
    ).fetchall()

    if len(peers) <= 1:
        return 5  # Lone wolf — medium score

    # Rank by gain (总龙)
    peers_by_gain = sorted(peers, key=lambda x: -(x["gain"] or 0))
    gain_rank = next((i+1 for i, p in enumerate(peers_by_gain) if p["code"] == code), len(peers))

    # Rank by amount (中军)
    peers_by_amt = sorted(peers, key=lambda x: -(x["amt"] or 0))
    amt_rank = next((i+1 for i, p in enumerate(peers_by_amt) if p["code"] == code), len(peers))

    # Rank by volume (活跃度)
    peers_by_vol = sorted(peers, key=lambda x: -(x["volume"] or 0))
    vol_rank = next((i+1 for i, p in enumerate(peers_by_vol) if p["code"] == code), len(peers))

    if gain_rank == 1: score += 5      # 总龙: 板块涨幅第一
    elif gain_rank <= 3: score += 3    # 日内龙头
    elif gain_rank <= 5: score += 1

    if amt_rank == 1: score += 3       # 中军: 成交额最大
    elif amt_rank <= 3: score += 1

    if vol_rank == 1: score += 2       # 最活跃

    # Penalty: 跟风 (rank > 5 in all dimensions)
    if gain_rank > 5 and amt_rank > 5:
        score -= 2

    return max(0, min(10, score))


def check_board_rank(db, code, trade_date):
    """V4.0 模块D1: 判断涨停板是首板/二板/三板+。

    查询前5个交易日是否触及涨停价。

    Returns: (board_rank, board_score_bonus)
      - 首板(近5日无涨停): +4 bonus
      - 二板(前1日涨停): +2 bonus
      - 三板+(连续2日+涨停): -4 penalty (高位风险)
      - 隔日板(前2-3日涨停但昨日未涨停): 0 neutral
    """
    td = trade_date.replace('-', '')

    # Get today's limit price to check against
    today_limit_row = db.execute(
        "SELECT up_limit FROM stk_limit WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not today_limit_row or not today_limit_row["up_limit"]:
        return ("未知", 0)

    # Check previous 5 trading days for limit-up touches
    prev_dates = db.execute(
        "SELECT DISTINCT a.trade_date FROM daily_kline a "
        "WHERE a.code=? AND a.trade_date < ? "
        "ORDER BY a.trade_date DESC LIMIT 5",
        (code, trade_date)
    ).fetchall()

    if not prev_dates:
        return ("首板", 4)

    consecutive_boards = 0
    for i, pd_row in enumerate(prev_dates):
        pd = pd_row["trade_date"]
        # Get close and limit price for that day
        k_row = db.execute(
            "SELECT close, high FROM daily_kline WHERE code=? AND trade_date=?",
            (code, pd)
        ).fetchone()
        if not k_row:
            continue

        lim_row = db.execute(
            "SELECT up_limit FROM stk_limit WHERE code=? AND trade_date=?",
            (code, pd)
        ).fetchone()
        if not lim_row or not lim_row["up_limit"]:
            continue

        up_limit = lim_row["up_limit"]
        close_px = k_row["close"]

        # Check if close at or very near limit (within 0.5%)
        if up_limit > 0 and close_px >= up_limit * 0.995:
            consecutive_boards += 1
        else:
            break  # streak broken

    if consecutive_boards == 0:
        return ("首板", 4)
    elif consecutive_boards == 1:
        return ("二板", 2)
    elif consecutive_boards == 2:
        return ("三板", -2)
    else:
        return (f"{consecutive_boards+1}板", -4)


def score_resilience(kline_dict):
    """F10: 分歧不死验证 (0-5) — 低预期反而走强=真龙头。

    Args:
        kline_dict: {'open','high','low','close'} for today
    """
    score = 0
    tod_open = kline_dict.get('open', 0)
    tod_low = kline_dict.get('low', 0)
    tod_high = kline_dict.get('high', 0)
    tod_close = kline_dict.get('close', 0)

    if tod_open <= 0:
        return 0

    # Intraday drawdown
    intraday_drop = (tod_low / tod_open - 1) * 100

    # Close vs high (how close to the day's best price)
    high_ratio = tod_close / tod_high if tod_high > 0 else 0

    # All-day strength: never went below open
    if tod_low >= tod_open:
        score += 3  # 全天红盘, 无分歧
    elif intraday_drop > -2:
        score += 2  # 轻微分歧后回封
    elif intraday_drop > -4:
        score += 1  # 中度分歧

    # Close near high = strong finish
    if high_ratio >= 0.99:
        score += 2  # 光头阳线
    elif high_ratio >= 0.97:
        score += 1

    return min(5, score)


def get_intraday_leadership(db, code, trade_date, industry):
    """P0: Intraday leadership — who rose first in the sector?

    Uses stk_mins (5-min K-line) to find the stock with the earliest
    significant price surge within its concept/sector.

    Returns: (leader_score 0-5, earliest_surge_time_str)
    """
    try:
        # Get this stock's minute data
        rows = db.execute(
            "SELECT trade_time, close, pct_chg FROM stk_mins "
            "WHERE ts_code LIKE ? AND trade_time LIKE ? AND freq='5min' "
            "ORDER BY trade_time",
            (f"{code}%", f"{trade_date}%")
        ).fetchall()
        if not rows or len(rows) < 30:
            return (0, "")

        # Find when this stock first surged (涨速 > 0.3% per 5min 累计涨 > 2%)
        import numpy as np
        opens = [r["pct_chg"] or 0 for r in rows if r["pct_chg"] is not None]
        prices = [r["close"] for r in rows if r["close"] is not None]

        if not opens or not prices:
            return (0, "")

        # Find first significant surge time
        surge_time = ""
        cumulative = 0
        for r in rows:
            chg = r["pct_chg"] or 0
            cumulative += chg
            if cumulative >= 2.0 and not surge_time:
                surge_time = r["trade_time"][-8:-3] or r["trade_time"][-8:]  # HH:MM

        if not surge_time:
            return (0, "")

        # Compare with peer stocks in same industry
        peer_codes = db.execute(
            "SELECT DISTINCT ts_code FROM ths_member WHERE con_name LIKE ? LIMIT 10",
            (f"%{industry}%",)
        ).fetchall()

        earlier_count = 0
        total_peers = 0
        for (peer_ts,) in peer_codes:
            peer_code = peer_ts.split('.')[0]
            if peer_code == code:
                continue
            total_peers += 1
            peer_rows = db.execute(
                "SELECT trade_time, pct_chg FROM stk_mins "
                "WHERE ts_code=? AND trade_time LIKE ? AND freq='5min' ORDER BY trade_time",
                (peer_ts, f"{trade_date}%")
            ).fetchall()
            if not peer_rows:
                continue

            peer_cum = 0
            peer_surge = ""
            for pr in peer_rows:
                peer_cum += pr["pct_chg"] or 0
                if peer_cum >= 2.0 and not peer_surge:
                    peer_surge = pr["trade_time"][-8:-3] or pr["trade_time"][-8:]
                    break

            if peer_surge and surge_time <= peer_surge:
                earlier_count += 1

        if total_peers == 0:
            return (2, surge_time)  # No peers to compare, give medium score

        # Score: earlier than more peers = higher leader score
        ratio = earlier_count / total_peers if total_peers > 0 else 0
        if ratio >= 0.8:
            return (5, surge_time)  # Almost always the first to rise
        elif ratio >= 0.6:
            return (4, surge_time)
        elif ratio >= 0.4:
            return (3, surge_time)
        elif ratio >= 0.2:
            return (2, surge_time)
        else:
            return (1, surge_time)  # Late follower, not leader

    except Exception:
        return (0, "")  # No minute data available


def score_stock(code, info, db, trade_date):
    """Score a single stock with the 7-factor model.

    Returns dict with score breakdown, or None if eliminated.
    """
    klines = get_kline_data(db, code, trade_date, lookback=60)
    if len(klines) < 20:
        return None

    closes = np.array([r["close"] for r in klines], dtype=np.float64)
    volumes = np.array([r["volume"] for r in klines], dtype=np.float64)
    amounts = np.array([r["amount"] for r in klines], dtype=np.float64)
    highs = np.array([r["high"] for r in klines], dtype=np.float64)
    lows = np.array([r["low"] for r in klines], dtype=np.float64)
    opens = np.array([r["open"] for r in klines], dtype=np.float64)

    today_close = closes[-1]
    today_volume = volumes[-1]
    today_amount = amounts[-1]
    today_high = highs[-1]
    today_low = lows[-1]
    today_open = opens[-1]

    pre_close = get_pre_close(db, code, trade_date)
    if not pre_close or pre_close <= 0:
        return None

    # ═══════════════════════════════════════════════
    # 条件 1: 涨幅质量 (20分)
    # ═══════════════════════════════════════════════
    # ── 北交所排除: 920/830/870/4xx 开头 ──
    if code.startswith(('92', '83', '87', '4')):
        return None

    gain_pct = (today_close / pre_close - 1) * 100
    if gain_pct < 7.0 or gain_pct > 12.0:
        return None  # 淘汰

    # Initialize gain_score (max from WEIGHTS["gain_quality"]) before F15-F18 checks
    gain_score = 20

    # ── F15: 主升浪确认 (近10日阳线占比≥50%) ──
    kline_10d = db.execute(
        "SELECT close, LAG(close) OVER (ORDER BY trade_date) as prev_close "
        "FROM daily_kline WHERE code=? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 11",
        (code, trade_date)
    ).fetchall()
    up_days = sum(1 for r in kline_10d if r["prev_close"] and r["prev_close"] > 0
                  and (r["close"] / r["prev_close"] - 1) * 100 > 0)
    up_ratio = up_days / max(1, len(kline_10d) - 1)
    if up_ratio < 0.5:
        gain_score -= 3  # F15: 近期弱势, 非主升浪

    # ── F16: 趋势通道 (近20日高低点方向) ──
    kline_20d = db.execute(
        "SELECT high, low FROM daily_kline WHERE code=? AND trade_date <= ? "
        "ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    if len(kline_20d) >= 20:
        highs_20 = np.array([r["high"] for r in kline_20d[-20:]])
        lows_20 = np.array([r["low"] for r in kline_20d[-20:]])
        hh_up = highs_20[-1] > highs_20[0]   # 高点抬升
        ll_up = lows_20[-1] > lows_20[0]      # 低点抬升
        if not hh_up and not ll_up:
            gain_score -= 4  # F16: 下降通道扣4分 (高点低点都下移)
        elif not hh_up or not ll_up:
            gain_score -= 1  # 震荡通道扣1分

    # ── F17: 突破确认 (收盘接近近20日最高价) ──
    pre_high_20 = max(float(r["high"]) for r in kline_20d[-21:-1]) if len(kline_20d) >= 21 else today_close
    if pre_high_20 > 0 and today_close < pre_high_20 * 0.85:
        gain_score -= 3  # F17: 收盘还在前高下方15%+, 反弹非突破

    # ── F18: 连阳确认 (近3日至少2日收阳, 非单日脉冲) ──
    kline_3d = db.execute(
        "SELECT close, LAG(close) OVER (ORDER BY trade_date) as prev_close "
        "FROM daily_kline WHERE code=? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 4",
        (code, trade_date)
    ).fetchall()
    up_3d = sum(1 for r in kline_3d if r["prev_close"] and r["prev_close"] > 0
                and (r["close"] / r["prev_close"] - 1) * 100 > 0)
    if up_3d < 2:
        gain_score -= 4  # F18: 近3日阳线<2天, 单日脉冲反弹

    # ── 封板质量评分 (从limit_list_d获取) ──
    seal_score = 0
    seal_weakness = ""  # initialized; may be overwritten by limit_detail or yizi checks
    limit_row = db.execute(
        "SELECT first_time, open_times, fd_amount, up_stat FROM limit_list_d "
        "WHERE ts_code LIKE ? AND trade_date=?",
        (f"{code}%", trade_date.replace('-', ''))
    ).fetchone()

    is_limit_up = False
    stk_limit_row = db.execute(
        "SELECT up_limit FROM stk_limit WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if stk_limit_row and stk_limit_row["up_limit"] and stk_limit_row["up_limit"] > 0:
        if today_close >= stk_limit_row["up_limit"] * 0.995:
            is_limit_up = True

    # ── G1: 排除7-9%非涨停票 (1-6月数据: 286只, 胜率仅42%) ──
    if gain_pct < 9.5 and not is_limit_up:
        return None  # 非涨停+涨幅不足9.5%=次日弱势, 淘汰

    if limit_row and is_limit_up:
        # 有涨停板详细数据 → 精细评分
        first_time = limit_row["first_time"] or ""
        open_times = limit_row["open_times"] or 0
        fd_amount = (limit_row["fd_amount"] or 0) / 1e8  # 封单量(亿)
        up_stat = limit_row["up_stat"] or ""

        # 封板时间: 越早越强
        if first_time and first_time <= "100000":   # 10:00前封板
            seal_score += 8
        elif first_time and first_time <= "103000":  # 10:30前
            seal_score += 6
        elif first_time and first_time <= "113000":  # 11:30前
            seal_score += 4
        elif first_time and first_time <= "140000":  # 14:00前
            seal_score += 2
        else:
            seal_score += 1  # 尾盘涨停, 质量差

        # ── V4.0 D3: 尾盘涨停降权 ──
        if first_time and first_time >= "143000":
            seal_score = int(seal_score * 0.5)  # 14:30后封板 → 五折
            seal_weakness = "尾盘涨停"
        elif first_time and first_time >= "140000":
            seal_score = int(seal_score * 0.7)  # 14:00后封板 → 七折
            seal_weakness = "午后涨停"
        else:
            seal_weakness = ""

        # 开板次数: 0=完美, 越少越好
        if open_times == 0:
            seal_score += 5  # 一字板/封死
        elif open_times == 1:
            seal_score += 3
        elif open_times <= 3:
            seal_score += 1

        # ── V4.0 D4: 炸板率惩罚 ──
        if open_times >= 3:
            seal_score = int(seal_score * 0.6)

        # 封单量: 越大越强
        if fd_amount >= 5:
            seal_score += 3  # 大封单
        elif fd_amount >= 2:
            seal_score += 2
        elif fd_amount >= 0.5:
            seal_score += 1

        # 封板状态: 1/1=一次封死
        if up_stat in ("1/1",):
            seal_score += 2

    elif is_limit_up:
        # 涨停但无详细数据 → 基础分
        seal_score = 5

    # ── V4.0 D1: 首板/连板评分 ──
    board_rank, board_bonus = "未知", 0
    if is_limit_up:
        board_rank, board_bonus = check_board_rank(db, code, trade_date)
        seal_score += board_bonus

    # ── V4.0 D2: 一字板检测 (买不到→降分) ──
    is_yizi = False
    if is_limit_up and today_open >= today_high * 0.999 and today_low >= today_high * 0.999:
        # open=high=low → 一字板
        is_yizi = True
        seal_score -= 5
        seal_weakness = "一字板(买不到)"
    elif is_limit_up and today_low < today_open * 0.995:
        # T字板: 开板后回封 → 正常
        seal_weakness = seal_weakness if seal_weakness else "T字回封"

    seal_score = max(0, seal_score)  # Floor at 0

    # 未涨停: seal_score=0, 不影响

    if gain_pct >= 10.0:
        gain_score = 20
    elif gain_pct >= 9.5:
        gain_score = 18
    elif gain_pct >= 9.0:
        gain_score = 16
    elif gain_pct >= 8.5:
        gain_score = 14
    elif gain_pct >= 8.0:
        gain_score = 12
    elif gain_pct >= 7.5:
        gain_score = 10
    else:
        gain_score = 8

    # Bonus: 光头阳线
    if today_close >= today_high * 0.995:
        gain_score += 2
    # Bonus: 全天红盘
    if today_low >= today_open:
        gain_score += 1
    gain_score = min(20, gain_score)

    # ═══════════════════════════════════════════════
    # 条件 3: 均线趋势 (10分) — 先算，因为MA5≤MA10直接淘汰
    # ═══════════════════════════════════════════════
    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)

    # Try stk_factor_pro first (pre-computed on Tushare)
    factor_row = db.execute(
        "SELECT ma5, ma10, ma20, macd_dif, macd_dea, rsi_12 "
        "FROM stk_factor_pro WHERE ts_code LIKE ? AND trade_date=?",
        (f"{code}%", trade_date.replace('-', ''))
    ).fetchone()

    if factor_row and factor_row["ma5"] and factor_row["ma10"]:
        ma5 = factor_row["ma5"]
        ma10 = factor_row["ma10"]
        ma20 = factor_row["ma20"] or ma20
        macd_dif = factor_row["macd_dif"]
        macd_dea = factor_row["macd_dea"]
        rsi12 = factor_row["rsi_12"]
    else:
        macd_dif = None
        macd_dea = None
        rsi12 = None

    if ma5 is None or ma10 is None:
        return None

    # MA trend: soft scoring
    if ma20 and ma5 > ma10 > ma20 and today_close > ma20:
        ma_score = 10
    elif ma5 > ma10 and today_close > ma20:
        ma_score = 8
    elif ma5 > ma10:
        ma_score = 6
    elif today_close > ma20:
        ma_score = 3
    else:
        ma_score = 1
    # ── O4: MA多头收紧 ──
    if ma20 and ma20 > 0 and not (ma5 > ma10 > ma20):
        if ma5 > ma10:
            ma_score = min(ma_score, 3)
        else:
            ma_score = min(ma_score, 1)
    # 一票否决: 近1月跌幅>30%
    if len(closes) >= 20:
        month_ret = (closes[-1] / closes[-20] - 1) * 100
        if month_ret < -30:
            return None

    # ═══════════════════════════════════════════════
    # 条件 7: 集中放量 (10分) — 先算，供条件4参考
    # ═══════════════════════════════════════════════
    vol_ma5 = np.mean(volumes[-6:-1]) if len(volumes) >= 6 else np.mean(volumes[:-1])
    vol_ratio = today_volume / vol_ma5 if vol_ma5 > 0 else 1.0

    if vol_ratio >= 3.0:
        volume_score = 10
    elif vol_ratio >= 2.5:
        volume_score = 8
    elif vol_ratio >= 2.0:
        volume_score = 7
    elif vol_ratio >= 1.5:
        volume_score = 5
    else:
        volume_score = 3  # Soft: 不放量也给基础分（允许缩量涨停）

    # 换手率辅助
    turnover_rate = today_volume / (info.get("float_mv", 1e9) / today_close) * 100 if info.get("float_mv") else 10
    if 8 <= turnover_rate <= 15:
        volume_score += 2
    elif 5 <= turnover_rate <= 20:
        volume_score += 1
    elif turnover_rate > 25:
        volume_score -= 2
    volume_score = max(0, min(10, volume_score))

    # ═══════════════════════════════════════════════
    # 条件 4: 成交额 (10分) — v3: 倒U型 (IC=-0.11, 越大越差)
    # 404样本: 10-30亿胜率62%最优, >200亿胜率43%最差
    # ═══════════════════════════════════════════════
    amount_yi = (today_amount or 0) / 1e5  # Tushare amount is in 千元 → 亿
    if 10 <= amount_yi < 50:
        turnover_score = 10  # Sweet spot: 适中流动性
    elif 50 <= amount_yi < 80:
        turnover_score = 7   # 偏大, 冲高动能减弱
    elif 5 <= amount_yi < 10:
        turnover_score = 6   # 偏小但量比足则可用
    elif 80 <= amount_yi < 150:
        turnover_score = 4   # 大盘股, 次日难冲
    elif amount_yi >= 150:
        turnover_score = 2   # 巨盘股, 次日几乎不动
    elif amount_yi >= 3 and vol_ratio >= 3.0:
        turnover_score = 3   # 微盘爆发, 量比极高
    else:
        return None  # 淘汰: 成交额太小

    # ═══════════════════════════════════════════════
    # 条件 6: 主力资金 (10分)
    # ═══════════════════════════════════════════════
    mf = get_moneyflow(db, code, trade_date)
    if mf and mf["net_mf_amount"] is not None:
        net_inflow = mf["net_mf_amount"]
        lg_buy = mf["buy_lg_amount"] or 0
        lg_sell = mf["sell_lg_amount"] or 0
        elg_buy = mf["buy_elg_amount"] or 0
        elg_sell = mf["sell_elg_amount"] or 0
        total_inflow = lg_buy + elg_buy - lg_sell - elg_sell
        inflow_ratio = total_inflow / (today_amount + 1) * 100
    else:
        net_inflow = 0
        inflow_ratio = 0

    # ── 优化1: 主力资金强制过滤 ──
    # 回测数据: 主力流出组胜率仅9%, 强制排除
    if mf is not None and net_inflow < 0 and inflow_ratio < 0:
        return None  # 主力明确出货 → 淘汰 (胜率仅9%)

    if mf is None:
        capital_score = 10  # 无数据: 中性分 (weight=20)
    elif inflow_ratio > 10:
        capital_score = 20  # 主力大幅流入: 满分
    elif inflow_ratio > 5:
        capital_score = 17  # 主力明显流入
    elif inflow_ratio > 2:
        capital_score = 14  # 主力温和流入
    elif inflow_ratio >= 0:
        capital_score = 10  # 主力小幅流入/持平
    else:
        return None  # 主力净流出 → 淘汰 (胜率仅9%)

    # ═══════════════════════════════════════════════
    # 条件 2: 板块龙头 (25分) — 需要跨股票比较，先算已知部分
    # 板块内排名和涨停家数在后面 batch 计算
    # ═══════════════════════════════════════════════
    industry = info.get("industry", "其他")

    # ═══════════════════════════════════════════════
    # 条件 5: 板块共振 (15分)
    # ═══════════════════════════════════════════════
    sector_pct = get_sector_index(db, industry, trade_date, code)
    sh_pct = get_shanghai_index(db, trade_date)

    # ── F14: 板块支撑验证 (板块推演术核心) ──
    # F14: Count peer stocks with ≥7% gain in same sector
    # Must use the MOST RECENT previous trading day for pre_close
    prev_date_row = db.execute(
        "SELECT trade_date FROM daily_kline WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 1",
        (trade_date,)
    ).fetchone()
    prev_date = list(prev_date_row.values())[0] if prev_date_row else trade_date
    peer_count = db.execute(
        "SELECT COUNT(DISTINCT a.code) FROM daily_kline a "
        "JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
        "JOIN stocks s ON a.code=s.code "
        "WHERE a.trade_date=? AND s.industry=? "
        "AND b.close > 0 AND (a.close/NULLIF(b.close,0)-1)*100 >= 7",
        (prev_date, trade_date, industry)
    ).fetchone()
    peer_count = peer_count["count"] if peer_count else 0

    sector_change = sector_pct["pct_change"] if sector_pct and sector_pct["pct_change"] is not None else 0
    sector_amount = sector_pct["amount"] if sector_pct else 0

    # P0 fix (2026-07-03): 历史上 F14-1/F14-3/末支三处 `return None` 系统性淘汰了所有
    # 「板块弱 + 孤立涨停」个股。当 get_shanghai_index 因 '000001.SH' 硬编码 bug 返回 0 时，
    # 板块门的多条件 AND 几乎无人能通过 → leader_scalp 在 114 涨停日返回 0 候选。
    # 此处按 PL 授权改为「软降权」：保留候选（resonance_score 最低档）+ 标注 resonance_risk，
    # 让龙头至少进池供后续 ranking / 人工决策，而非被静默吞掉。
    # ⚠️ 注意：IC 校准的 peer_count/sector_change 数值阈值**未改动**——策略精调（阈值收紧/
    # 重校准）是独立 follow-up，须由 ml-engineer 跑 1-6 月样本外回测验证 IC 不漂移后再定
    # （参 memory bi-trend-net-backtest-finding / phase1-sample-out-conclusion：禁盲目基于6月调参）。
    resonance_score = 3  # 默认最低档（逆势/弱支撑）；下列分支覆盖提升
    resonance_risk = ""

    # F14-1: 孤立行情 — 同板块只有自己1只涨7%+, 且板块不涨
    # (原硬淘汰 → 软降权：留池 + 标 risk)
    if peer_count <= 1 and sector_change <= 0:
        resonance_score = 2  # 板块推演术: 没有板块支撑的独立行情=一日游风险
        resonance_risk = "孤立行情:无板块支撑,疑似一日游"

    # F14-2: 板块弱+个股唯一涨 → 淘汰
    elif peer_count <= 1 and sector_change < 1:
        resonance_score = 3  # 板块勉强, 非龙头

    elif sector_pct is None:
        # No sector data at all → treat as missing support
        if peer_count <= 2:
            resonance_score = 2  # F14-3: 无板块数据+少同伙=无法确认板块效应
            resonance_risk = "无板块数据:无法确认板块效应"
        else:
            resonance_score = 5  # 有多个同伙但无板块数据, 降级
    elif sector_change > 0 and sh_pct < 0:
        resonance_score = 15  # 独立行情!
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 3:
        resonance_score = 15  # 共振领涨
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 1:
        resonance_score = 12
    elif sector_change > 0 and sh_pct > 0:
        resonance_score = 10
    elif sector_change < 0 and sh_pct < 0 and sector_change > sh_pct:
        resonance_score = 8  # 抗跌
    elif sector_change < 0 and sh_pct > 0:
        resonance_score = 3  # 逆势
    else:
        # 板块更弱（原硬淘汰 → 软降权）
        resonance_score = 2
        resonance_risk = "板块更弱:逆势涨停风险"

    # ── 优化B: 板块涨幅因子 (IC=+0.14, 5-6月最强宏观信号) ──
    if sector_change > 3:
        sector_momentum_score = 10
    elif sector_change > 1:
        sector_momentum_score = 7
    elif sector_change > 0:
        sector_momentum_score = 5
    elif sector_change > -1:
        sector_momentum_score = 3
    else:
        sector_momentum_score = 0  # 板块下跌>1%, 逆水行舟

    # ═══════════════════════════════════════════════
    # F8: 板块周期阶段 (板块推演术, 0-10分)
    # ═══════════════════════════════════════════════
    cycle_score = score_sector_cycle(db, industry, trade_date)

    # ═══════════════════════════════════════════════
    # F9: 龙头角色识别 (板块推演术, 0-10分)
    # ═══════════════════════════════════════════════
    leader_role_score = score_leader_role(db, code, industry, trade_date, gain_pct, amount_yi)

    # ═══════════════════════════════════════════════
    # F10: 分歧不死验证 (0-5分)
    # ═══════════════════════════════════════════════
    resilience_score = score_resilience({
        'open': float(today_open), 'high': float(today_high),
        'low': float(today_low), 'close': float(today_close)
    })

    # ── P0: 日内分时带动性 (分钟线数据不可用时跳过) ──
    intraday_score, surge_time = 0, ""
    try:
        intraday_score, surge_time = get_intraday_leadership(db, code, trade_date, industry)
    except Exception:
        pass  # No minute data for this date → skip

    return {
        "code": code,
        "name": info["name"],
        "industry": industry,
        "float_mv": info.get("float_mv", 0),
        "gain_pct": round(gain_pct, 2),
        "close": round(float(today_close), 2),
        "pre_close": round(float(pre_close), 2),
        "amount_yi": round(amount_yi, 1),
        "vol_ratio": round(float(vol_ratio), 2),
        "turnover_rate": round(turnover_rate, 1),
        "inflow_ratio": round(inflow_ratio, 2),
        "net_inflow": round(float(net_inflow / 1e8), 2) if net_inflow else 0,
        "sector_change": round(sector_change, 2),
        "sh_change": round(sh_pct, 2),
        # Partial scores (sector_leader added later)
        "gain_score": gain_score,
        "ma_score": ma_score,
        "turnover_score": turnover_score,
        "volume_score": volume_score,
        "capital_score": capital_score,
        "resonance_score": resonance_score,
        "resonance_risk": resonance_risk,
        "seal_score": seal_score,
        "is_limit_up": is_limit_up,
        "board_rank": board_rank,
        "is_yizi": is_yizi,
        "seal_weakness": seal_weakness if is_limit_up else "",
        "cycle_score": cycle_score,
        "leader_role_score": leader_role_score,
        "resilience_score": resilience_score,
        "intraday_score": intraday_score,
        "surge_time": surge_time,
        # v3: 新增板块涨幅因子
        "sector_momentum_score": sector_momentum_score,
    }


def compute_sector_leader(scores, db, trade_date):
    """Post-process: compute sector leader scores across all qualified stocks."""
    # ── V4.0 B3: 板块风险标注 ──
    sector_risks = {}
    td = trade_date.replace('-', '')

    # Get all industries in play
    all_industries = set(s["industry"] for s in scores)

    for industry in all_industries:
        # V5.2 fix: index_basic → index_daily (ths_daily empty, sw_daily columns wrong)
        kw = industry[-2:] if len(industry) >= 2 else industry
        sector_row = db.execute(
            "SELECT d.pct_chg FROM index_daily d "
            "JOIN index_basic b ON d.code=b.code "
            "WHERE b.name LIKE ? AND d.trade_date=? "
            "ORDER BY ABS(d.pct_chg) DESC LIMIT 1",
            (f"%{kw}%", trade_date)
        ).fetchone()

        sector_pct = float(sector_row["pct_chg"]) if sector_row and sector_row["pct_chg"] is not None else 0

        # Count limit-down stocks in this sector (pct_chg < 0 = 跌停)
        ld_in_sector = db.execute(
            "SELECT COUNT(*) as cnt FROM limit_list_d ld "
            "JOIN stocks s ON s.code=SUBSTR(ld.ts_code, 1, 6) "
            "WHERE ld.trade_date=? AND ld.pct_chg < 0 AND s.industry=?",
            (td, industry)
        ).fetchone()
        ld_count = ld_in_sector["cnt"] if ld_in_sector else 0

        sector_risks[industry] = {
            "pct_change": sector_pct,
            "limit_down_count": ld_count,
            "is_crashing": sector_pct < -3 or ld_count >= 3,
            "is_weak": sector_pct < -1 or ld_count >= 1,
        }

    # Group by industry
    by_sector = defaultdict(list)
    for s in scores:
        by_sector[s["industry"]].append(s)

    for industry, stocks in by_sector.items():
        risk = sector_risks.get(industry, {})
        is_crashing = risk.get("is_crashing", False)
        is_weak = risk.get("is_weak", False)

        # B1: Sector meltdown → all stocks in this sector get penalty
        sector_penalty = 0
        if risk.get("limit_down_count", 0) >= 3:
            sector_penalty = -12  # Heavy penalty: sector has multiple limit-downs
        elif is_crashing:
            sector_penalty = -8   # Sector crashing >3%

        # V5.2 P0b: Sector overheat penalty (板块过热 → 次日分化)
        # 回测证据: 板块≥20只涨停 → 次日跟风股大幅回调
        n_total = len(stocks)
        if n_total >= 30:
            sector_overheat = -12   # 极度拥挤
        elif n_total >= 20:
            sector_overheat = -8    # 板块过热
        elif n_total >= 15:
            sector_overheat = -3    # 轻微过热警告
        else:
            sector_overheat = 0

        # Rank by gain within sector
        stocks.sort(key=lambda x: -x["gain_pct"])
        count_strong = n_total

        for rank, s in enumerate(stocks, 1):
            # Rank score
            if rank == 1:
                rank_score = 15
            elif rank <= 3:
                rank_score = 12
            elif rank <= 5:
                rank_score = 8
            elif rank <= 10:
                rank_score = 4
            else:
                rank_score = 0

            # Apply sector penalty to rank score
            if sector_penalty != 0:
                rank_score = max(0, rank_score + sector_penalty // 3)  # Distribute across all stocks

            # V5.2 P0b: 板块过热 → 后排跟风股罚更多, 前排龙头罚更少
            if sector_overheat != 0:
                if rank <= 3:
                    stock_overheat = sector_overheat // 2  # 龙头: 半罚
                elif rank <= 5:
                    stock_overheat = sector_overheat        # 前排: 全额
                else:
                    stock_overheat = int(sector_overheat * 1.5)  # 跟风: 1.5倍
            else:
                stock_overheat = 0

            # Sector breadth score
            if count_strong >= 5:
                breadth_score = 5
            elif count_strong >= 3:
                breadth_score = 4
            elif count_strong >= 2:
                breadth_score = 2
            else:
                breadth_score = 1

            # Concentration: individual / sector total
            sector_total_amount = sum(x["amount_yi"] for x in stocks)
            concentration = s["amount_yi"] / sector_total_amount * 100 if sector_total_amount > 0 else 0
            if concentration > 10:
                conc_score = 5
            elif concentration > 5:
                conc_score = 3
            elif concentration > 2:
                conc_score = 1
            else:
                conc_score = 0

            s["sector_leader_score"] = min(25, rank_score + breadth_score + conc_score + stock_overheat)
            s["sector_rank"] = rank
            s["sector_strong_count"] = count_strong
            s["concentration_pct"] = round(concentration, 1)
            s["_sector_risk"] = risk  # Attach sector risk info
            s["_sector_overheat"] = sector_overheat != 0
            s["_stock_overheat_penalty"] = stock_overheat

            # B3: Tag weak/crashing sectors
            if is_crashing:
                s["_sector_crashing"] = True
            elif is_weak:
                s["_sector_weak"] = True

    return scores


def run_leader_screening(trade_date, top_n=20, env_check=True):
    """Run full leader screening for a single trading day.

    Args:
        trade_date: YYYY-MM-DD
        top_n: number of top picks to return
        env_check: if True, run V4.0 market environment assessment
    """
    with _get_db(readonly=True) as db:
        # ── V4.0 模块A: 市场环境预检 ──
        market_env = MarketEnv.BULL
        env_detail = {}
        if env_check:
            market_env, env_detail = assess_market_env(db, trade_date)
            env_label = {"bull": "🟢做多", "neutral": "🟡中性", "bear": "🟠观望", "crash": "🔴熔断"}
            print(f"  市场环境: {env_label.get(market_env.value, '?')} — {env_detail.get('reason', '')}")

            # ── V4.1 E1: 极端亏损日检测 — 叠加风险判定 ──
            risk_level, risk_detail = detect_extreme_loss_risk(db, trade_date, market_env)
            if risk_level >= 2:
                # 风险升级: 危险/极高 → 提升 market_env 等级
                if market_env == MarketEnv.BULL and risk_level >= 3:
                    market_env = MarketEnv.BEAR
                    print(f"  ⚠️ 极端风险: {'; '.join(risk_detail['reasons'])} → 升级为🟠观望")
                elif market_env == MarketEnv.BULL and risk_level == 2:
                    market_env = MarketEnv.NEUTRAL
                    print(f"  ⚠️ 高风险: {'; '.join(risk_detail['reasons'])} → 升级为🟡半仓")
                elif market_env == MarketEnv.NEUTRAL and risk_level >= 2:
                    market_env = MarketEnv.BEAR
                    print(f"  ⚠️ 风险叠加: {'; '.join(risk_detail['reasons'])} → 升级为🟠观望")
            elif risk_level == 1:
                print(f"  ℹ️ 注意风险: {'; '.join(risk_detail['reasons'])}")

        # CRASH 熔断 → 不选股
        if market_env == MarketEnv.CRASH:
            print(f"  ⛔ 市场熔断, 跳过选股 (跌停{env_detail.get('limit_down_count', 0)}家)")
            return [], []

        universe = get_stock_universe(db, trade_date)
        print(f"  股票池: {len(universe)} 只 (非ST, 流通市值≥20亿)")

        scores = []
        for code, info in universe.items():
            try:
                result = score_stock(code, info, db, trade_date)
                if result:
                    scores.append(result)
            except Exception:
                continue

        print(f"  7条件筛选后: {len(scores)} 只")

        # Post-process: sector leader scores
        scores = compute_sector_leader(scores, db, trade_date)

        # ── 优化E: 板块动量过滤 — 弱势板块扣8分 ──
        weak_sectors = get_weak_sectors(db, trade_date, bottom_pct=20)
        if weak_sectors:
            weak_count = sum(1 for s in scores if s["industry"] in weak_sectors)
            print(f"  弱势板块({len(weak_sectors)}个): {', '.join(sorted(weak_sectors)[:5])}... → {weak_count}只受影响")

    # ── G2: 板块黑白名单 (1-6月1477样本) ──
    SECTOR_BONUS = {"火力发电":5,"黄金":5,"铅锌":3,"玻璃":3,"农药化肥":2}
    SECTOR_PENALTY = {"化纤":-10,"矿物制品":-10,"IT设备":-10,"汽车配件":-5,"航空":-5,"供气供热":-3}

    # Compute final score
    for s in scores:
        # ── V4.1 F0 total_score: 重校准因子权重 ──
        # ma_score 降权: 上限从10→6 (IC=-0.074, 持续负向)
        ma_adjusted = min(6, s["ma_score"])
        # sector_momentum 升权: 上限从10→15 (IC=+0.126, V4最强信号)
        sector_momentum_adjusted = min(15, s.get("sector_momentum_score", 0) * 1.5)
        # capital_score 调整为20分制 (IC=+0.079)
        capital_adjusted = min(22, s["capital_score"])
        # resilience 重加回: V4 IC=+0.109 (V3样本误判为负)
        resilience_adjusted = s.get("resilience_score", 0) * 2  # 0-5分制 → 0-10分制

        s["total_score"] = (
            s["gain_score"] + s["sector_leader_score"] + ma_adjusted +
            s["turnover_score"] + s["resonance_score"] + capital_adjusted +
            sector_momentum_adjusted +
            s.get("seal_score", 0) + s.get("intraday_score", 0) +
            s.get("cycle_score", 0) + s.get("leader_role_score", 0) +
            resilience_adjusted
            # volume_score removed: IC=+0.0003, zero predictive value
        )
        # ── seal_quality bonus (from WEIGHTS): 封板质量IC=+0.07 ──
        if s.get("is_limit_up") and s.get("seal_score", 0) >= 10:
            s["total_score"] += 5  # WEIGHTS["seal_quality"] → 升高门槛+升权
        # ── 优化4: 巨盘股降权 (成交额>80亿, 次日均值-0.07%) ──
        if s.get("amount_yi", 0) > 80:
            s["total_score"] -= 10
            s["_big_cap_penalty"] = True

        # ── G2: 板块黑白名单 (1-6月1477样本) ──
        ind = s.get("industry", "")
        if ind in SECTOR_PENALTY:
            s["total_score"] += SECTOR_PENALTY[ind]
            s["_sector_penalty"] = SECTOR_PENALTY[ind]
        if ind in SECTOR_BONUS:
            s["total_score"] += SECTOR_BONUS[ind]
            s["_sector_bonus"] = SECTOR_BONUS[ind]

        # ── 优化E: 弱势板块扣分 (bottom 20%板块: 矿物制品-2.04%, 塑料-0.66%等) ──
        if s["industry"] in weak_sectors:
            s["total_score"] -= 8
            s["_weak_sector_penalty"] = True

        # ── V4.0 B1: 板块系统性风险罚分 ──
        if s.get("_sector_crashing"):
            s["total_score"] -= 15  # 板块暴跌>3%或板块内跌停≥3 → 大幅扣分
        elif s.get("_sector_weak"):
            s["total_score"] -= 5   # 板块偏弱 → 适度扣分
        # ── V4.0 D2: 一字板额外扣分 ──
        if s.get("is_yizi"):
            s["total_score"] -= 3   # 一字板无法买入, 降低吸引力

        # ── V5.2 E3: 连板溢价重校准 (6月回测: 二板-7.8%/-7.5%, 三板+5.4%) ──
        board_rank = s.get("board_rank", "")
        if board_rank == "首板":
            s["total_score"] += 3   # 首板确定性最高
        elif board_rank == "二板":
            s["total_score"] -= 2   # V5.2: 回测数据二板风险大 (万通-7.8%, 双星-7.5%)
        elif "三板" in str(board_rank) or board_rank == "三板":
            s["total_score"] += 2   # 三板惯性尚可, 适度加分
        elif "4板" in str(board_rank) or "5板" in str(board_rank):
            s["total_score"] -= 5   # 高位风险, 加大惩罚

        # ── V4.1 F0 阈值重校准 (S=95→100修复A级倒挂) ──
        if s["total_score"] >= 100:
            s["grade"] = "S"
        elif s["total_score"] >= 82:
            s["grade"] = "A"
        elif s["total_score"] >= 68:
            s["grade"] = "B"
        else:
            s["grade"] = "C"

    scores.sort(key=lambda x: -x["total_score"])

    # ── V4.1 E2+模块B2: 板块集中度控制 (依市场环境动态调整) ──
    if market_env == MarketEnv.BULL:
        max_per_sector = 3    # V5.2: 4→3, 板块集中度控制
        min_grade = "B"
    elif market_env == MarketEnv.NEUTRAL:
        max_per_sector = 2    # V5.2: 3→2
        min_grade = "A"
    else:
        max_per_sector = 1    # V5.2: 2→1, BEAR只看最强
        min_grade = "S"

    top = []
    sector_counts = {}
    neut_filtered = 0
    for s in scores:
        ind = s.get("industry", "其他")
        cnt = sector_counts.get(ind, 0)

        # ── V4.1 E2: NEUTRAL环境额外过滤 ──
        if market_env == MarketEnv.NEUTRAL:
            # 排除负动量板块
            if s.get("sector_change", 0) <= 0 and s.get("sector_momentum_score", 0) < 3:
                neut_filtered += 1
                continue

        # Grade filter
        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        if grade_order.get(s.get("grade", "C"), 3) > grade_order.get(min_grade, 2):
            continue

        if cnt < max_per_sector:
            top.append(s)
            sector_counts[ind] = cnt + 1
        if len(top) >= top_n:
            break

    if neut_filtered > 0:
        print(f"  🟡 NEUTRAL收紧: {neut_filtered}只负动量板块标被排除")

    # ── V4.0 模块B1: 标记板块跌幅>3%的为高风险 ──
    for s in scores:
        if s.get("sector_change", 0) < -3:
            s["_high_risk_sector"] = True
            # 降一档
            if s.get("grade") == "S":
                s["grade"] = "A"
            elif s.get("grade") == "A":
                s["grade"] = "B"
            elif s.get("grade") == "B":
                s["grade"] = "C"

    # ── V4.0: 根据市场环境调整仓位建议 ──
    for s in top:
        s["market_env"] = market_env.value
        if market_env == MarketEnv.NEUTRAL:
            s["_env_halved"] = True  # 标记半仓
        elif market_env == MarketEnv.BEAR:
            s["_no_trade"] = True    # 标记不交易

    return top, scores


def generate_execution_plan(picks, market_env=MarketEnv.BULL):
    """V4.0 模块C: 生成次日执行计划。

    为每只入选股票生成可操作的次日交易计划，包括：
    - 入场价、止损价、止盈目标
    - 开盘动作建议
    - 仓位建议（受市场环境影响）
    - 风险提示

    Returns: list of execution plan dicts
    """
    plans = []
    for s in picks:
        close = s.get("close", 0)
        if close <= 0:
            continue

        grade = s.get("grade", "C")
        is_limit_up = s.get("is_limit_up", False)
        seal_score = s.get("seal_score", 0)
        board_rank = s.get("board_rank", "")
        is_yizi = s.get("is_yizi", False)
        sector_change = s.get("sector_change", 0)

        # ── 入场价: 昨日收盘 × 1.02 限价（不超过3%）──
        entry_limit = round(close * 1.02, 2)

        # ── 止损价: 硬止损 -3% ──
        stop_loss = round(close * 0.97, 2)

        # ── 止盈目标 ──
        tp1 = round(close * 1.05, 2)  # +5% 卖半仓
        tp2 = round(close * 1.10, 2)  # +10% 全卖

        # ── 仓位建议 ──
        base_pct = 0
        if s.get("_no_trade"):
            position_pct = 0
        elif grade == "S":
            base_pct = 20 if not s.get("_env_halved") else 10
        elif grade == "A":
            base_pct = 15 if not s.get("_env_halved") else 8
        elif grade == "B":
            base_pct = 10 if not s.get("_env_halved") else 5
        else:
            base_pct = 0
        position_pct = base_pct

        # ── 开盘动作 ──
        risk_warnings = []

        if is_yizi:
            open_action = "⛔ 一字板无法买入"
            risk_warnings.append("一字板: 散户买不到, 即使排到也风险极高")
            position_pct = 0
        elif s.get("_no_trade"):
            open_action = "🔴 市场弱市, 观望不买入"
            risk_warnings.append(f"市场环境: {s.get('market_env', 'bear')}")
            position_pct = 0
        elif seal_score >= 10 and board_rank == "首板":
            open_action = "🟢 竞价买入"
            risk_warnings.append("高封板质量首板, 竞价阶段介入")
        elif is_limit_up and seal_score >= 8:
            open_action = "🟡 开盘5分钟内买入"
        elif sector_change < -1:
            open_action = "🟠 等板块企稳再介入"
            risk_warnings.append(f"板块当日跌{sector_change:+.1f}%, 等确认企稳")
            position_pct = max(0, position_pct - 5)
        else:
            open_action = "🟡 开盘15分钟内买入"

        # ── 额外风险提示 ──
        if s.get("_sector_crashing"):
            risk_warnings.append("板块暴跌, 建议降低仓位")
            position_pct = max(0, position_pct - 5)
        if s.get("_big_cap_penalty"):
            risk_warnings.append("大盘股(>80亿), 次日冲高动能有限")
        if s.get("seal_weakness"):
            risk_warnings.append(s["seal_weakness"])
        if board_rank and "3板" in str(board_rank):
            risk_warnings.append(f"高位{board_rank}, 追高风险大")
            position_pct = max(0, position_pct - 5)

        # ── 止损规则 ──
        stop_rules = []
        if position_pct > 0:
            stop_rules.append(f"开盘跌>2%: 15分钟内不翻红→止损{stop_loss}")
            stop_rules.append(f"盘中跌至{stop_loss}: 无条件止损")
            stop_rules.append(f"冲高{tp1}(+5%): 卖半仓锁定利润")
            stop_rules.append(f"冲高{tp2}(+10%): 全部卖出")

        plans.append({
            "code": s["code"],
            "name": s["name"],
            "grade": grade,
            "total_score": s["total_score"],
            "entry_limit": entry_limit,
            "stop_loss": stop_loss,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "open_action": open_action,
            "position_pct": position_pct,
            "risk_warnings": risk_warnings,
            "stop_rules": stop_rules,
            "board_rank": board_rank,
            "is_limit_up": is_limit_up,
            "seal_score": seal_score,
        })

    return plans


def print_execution_plan(plans):
    """Print execution plan in a trader-friendly format."""
    print(f"\n{'=' * 90}")
    print(f"  📋 次日执行计划 (Execution Plan)")
    print(f"{'=' * 90}")
    print(f"\n  {'代码':<8} {'名称':<8} {'级':<3} {'开盘动作':<24} {'仓位':<6} {'止损':<8} {'止盈1':<8} {'止盈2':<8}")
    print(f"  {'-' * 80}")

    for p in plans:
        pos = f"{p['position_pct']}%" if p["position_pct"] > 0 else "不参与"
        print(f"  {p['code']:<8} {p['name']:<8} {p['grade']:<3} {p['open_action']:<24} "
              f"{pos:<6} {p['stop_loss']:<8} {p['take_profit_1']:<8} {p['take_profit_2']:<8}")

    # 风险提示汇总
    warnings = [(p["code"], p["name"], w) for p in plans for w in p["risk_warnings"]]
    if warnings:
        print(f"\n  ⚠️ 风险提示:")
        for code, name, w in warnings:
            print(f"    {code} {name}: {w}")

    # 止损规则
    actionable = [p for p in plans if p["position_pct"] > 0]
    if actionable:
        print(f"\n  🛑 止损规则 (通用):")
        rules = actionable[0]["stop_rules"]
        for r in rules:
            print(f"    • {r}")


def print_results(top, trade_date):
    """Print top picks in readable format."""
    env_label = {"bull": "🟢做多", "neutral": "🟡中性", "bear": "🟠观望", "crash": "🔴熔断"}
    # Determine the dominant market env from top picks
    market_env = top[0].get("market_env", "bull") if top else "bull"
    env_str = env_label.get(market_env, "?")

    print(f"\n{'=' * 90}")
    print(f"  龙头短线战法 V4.0 — {trade_date} Top {len(top)} | 市场: {env_str}")
    print(f"{'=' * 90}")
    print(f"\n  评分V4.1: 涨幅({WEIGHTS['gain_quality']})+龙头({WEIGHTS['sector_leader']})+均线({WEIGHTS['ma_trend']})+成交({WEIGHTS['turnover']})")
    print(f"        +共振({WEIGHTS['sector_resonance']})+资金({WEIGHTS['capital_flow']})+板块动量({WEIGHTS['sector_momentum']})")
    print(f"        +封板({WEIGHTS['seal_quality']})+分歧({WEIGHTS['resilience']}) | 成交量/均线降权, 板块动量+分歧升权")
    print(f"{'#':<3} {'代码':<8} {'名称':<8} {'总分':<5} {'级':<3} {'涨':<6} {'成交':<7} {'封板':<6} {'连板':<4} {'板块冲':<6} {'建仓':<6} {'板块/行业'}")
    print(f"{'-'*110}")

    for i, s in enumerate(top, 1):
        # Seal quality display
        if s.get('is_limit_up'):
            seal_info = str(s.get('seal_score', 0))
            if s.get('is_yizi'):
                seal_info += "一"
            if s.get('seal_weakness'):
                seal_info = seal_info  # keep concise
        else:
            seal_info = "—"

        # Board rank display
        board_info = s.get('board_rank', '-') if s.get('is_limit_up') else "-"
        if s.get('is_yizi'):
            board_info += "一"

        # Position sizing with market env adjustment
        ts = s['total_score']
        if s.get('_no_trade'):
            position = "0% ⛔"
        elif s.get('_env_halved'):
            position = "5%🔒"
        elif s['grade'] == 'S':
            if ts >= 95: position = "20%🔒"
            else: position = "15%🔒"
        elif s['grade'] == 'A':
            position = "10%"
        elif s['grade'] == 'B':
            position = "5%"
        else:
            position = "0% ⛔"

        print(f"{i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<5.0f} {s['grade']:<3} "
              f"{s['gain_pct']:>+5.1f}% {s['amount_yi']:<6.0f}亿 {seal_info:<6} {board_info:<4} "
              f"{s.get('sector_momentum_score',0):>5} "
              f"{position:<6} {s.get('sector_change',0):>+5.1f}% {s['industry']}")

    print(f"\n  S级={sum(1 for s in top if s['grade']=='S')} "
          f"A级={sum(1 for s in top if s['grade']=='A')} "
          f"B级={sum(1 for s in top if s['grade']=='B')}")


def run_backtest(dates, top_n=20):
    """Run leader screening on multiple dates for backtest analysis."""
    all_results = {}
    for trade_date in dates:
        print(f"\n{'─' * 60}")
        print(f"  📅 {trade_date}")
        print(f"{'─' * 60}")
        try:
            top, all_scores = run_leader_screening(trade_date, top_n)
            print_results(top, trade_date)
            all_results[trade_date] = {
                "top": top,
                "total_qualified": len(all_scores),
                "s_count": sum(1 for s in all_scores if s.get("grade") == "S"),
                "a_count": sum(1 for s in all_scores if s.get("grade") == "A"),
                "b_count": sum(1 for s in all_scores if s.get("grade") == "B"),
            }
        except Exception as e:
            print(f"  ❌ Error: {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  回测汇总 ({len(all_results)} 个交易日)")
    print(f"{'=' * 60}")
    for dt, r in all_results.items():
        # Include market env if available
        env_str = ""
        if r.get("top"):
            env_val = r["top"][0].get("market_env", "")
            env_emoji = {"bull": "🟢", "neutral": "🟡", "bear": "🟠", "crash": "🔴"}
            env_str = f" {env_emoji.get(env_val, '')}"
        print(f"  {dt}{env_str}: {r['total_qualified']}只入选 | S={r['s_count']} A={r['a_count']} B={r['b_count']}")

    return all_results


def _write_to_db(all_scores, trade_date, top_n):
    """Write leader_scalp scores to screening_scores table."""
    # Assign ranks
    for i, s in enumerate(all_scores, 1):
        s["rank"] = i
    rows = _to_screening_format(all_scores, trade_date)
    batch_id = f"leader_scalp_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    with get_db() as db:
        _write_screening_scores and _write_screening_scores(
            db, rows, batch_id,
            engine_name="leader_scalp",
            strategy_label="龙头短线战法",
            top_n=top_n,
        )
    print(f"\n  ✅ 已写入数据库: {len(rows)} 条 (batch_id={batch_id})")


def _to_screening_format(scores, trade_date):
    """Convert leader_scalp score dicts to screening_scores row dicts."""
    rows = []
    for s in scores:
        total_score = s.get("total_score", 0)
        grade = s.get("grade", "C")

        # Signal based on grade
        if grade == "S":
            signal = "可积极建仓，分批介入，止损5%"
        elif grade == "A":
            signal = "适量买入，控制仓位"
        elif grade == "B":
            signal = "等待回调企稳后轻仓参与"
        else:
            signal = "不建议参与"

        # Build reason string with key metrics
        reason_parts = [
            f"涨幅{s.get('gain_pct', 0):+.1f}%",
            f"成交{s.get('amount_yi', 0):.0f}亿",
        ]
        if s.get("is_limit_up"):
            reason_parts.append("涨停")
        if s.get("seal_score", 0) > 0:
            reason_parts.append(f"封板{s['seal_score']}分")
        if s.get("leader_role_score", 0) > 0:
            reason_parts.append(f"龙头{s['leader_role_score']}分")
        if s.get("intraday_score", 0) > 0:
            reason_parts.append(f"日内{s['intraday_score']}分")

        row = {
            "code": s["code"],
            "score": total_score,
            "grade": grade,
            "momentum": s.get("gain_score", 0),
            "volume_factor": s.get("volume_score", 0),
            "technical": s.get("ma_score", 0),
            "quality": s.get("cycle_score", 0),
            "risk": 0,  # resilience_score removed (IC=-0.08)
            "kronos_trend_score": 0,
            "kronos_pred_return": 0,
            "fund_score": 0,
            "target_price": None,
            "stop_loss": round(s["close"] * 0.95, 2) if s.get("close") else None,
            "nlp_score": 0,
            "nlp_sentiment": 0,
            "nlp_risk": 0,
            "nlp_event": "",
            "money_flow_score": s.get("inflow_ratio", 5.0),
            "mean_reversion_score": 5.0,
            "trend_strength_score": 5.0,
            "reversal_score": 5.0,
            "liquidity_score": s.get("turnover_score", 5.0),
            "analyst_score": 5.0,
            "target_upside_pct": 0,
            "eps_growth_pct": 0,
            "report_count_3m": 0,
            "institutional_consensus": "",
            "event_score": 0,
            "event_risk_flag": 0,
            "event_risk_reason": "",
            "quality_score": s.get("cycle_score", 5.0),
            "roe": 0,
            "revenue_growth_pct": 0,
            "profit_growth_pct": 0,
            "gross_margin_pct": 0,
            "debt_ratio_pct": 0,
            "cf_positive": 0,
            "fundamental_grade": "",
            "f10_score": 5.0,
            "sector_score": s.get("resonance_score", 5.0),
            "dividend_yield_pct": 0,
            "shareholder_signal": "",
            "capital_score": s.get("capital_score", 5.0),
            "north_bound_signal": "",
            "level2_signal": "",
            "buy_votes": 0,
            "total_votes": 12,
            "vote_ratio": 0.5,
            "signal": signal,
            "reason": " | ".join(reason_parts),
            "strategy": f"龙头短线战法",
            "rank": s.get("rank", 0),
            "leader_score": s.get("sector_leader_score", 0),
            "seal_score": s.get("seal_score", 0),
        }
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="龙头短线战法 V4.0")
    parser.add_argument("--date", type=str, help="Single trading date (YYYY-MM-DD)")
    parser.add_argument("--backtest", type=int, default=0, help="Run on last N trading days")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--db-write", action="store_true",
                        help="Persist scores to screening_scores table")
    parser.add_argument("--env-check", action="store_true", default=True,
                        help="Enable V4.0 market environment check (default: on)")
    parser.add_argument("--no-env-check", dest="env_check", action="store_false",
                        help="Disable market environment check")
    parser.add_argument("--execution-plan", action="store_true",
                        help="Generate and print next-day execution plan")
    parser.add_argument("--export-json", type=str, default=None,
                        help="Export results to JSON file path")
    args = parser.parse_args()

    if args.backtest > 0:
        with _get_db(readonly=True) as db:
            dates = get_last_trading_days(db, args.backtest)
        print(f"回测日期: {dates}")
        results = run_backtest(dates, args.top_n)

        # Save
        out_path = f"outputs/leader_scalp_backtest_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
        os.makedirs("outputs", exist_ok=True)
        # Convert to serializable
        serializable = {}
        for dt, r in results.items():
            serializable[dt] = {
                "total_qualified": r["total_qualified"],
                "s_count": r["s_count"], "a_count": r["a_count"], "b_count": r["b_count"],
                "top": [{k: v for k, v in s.items() if not k.startswith("_")}
                        for s in r["top"]]
            }
        with open(out_path, 'w') as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {out_path}")

    elif args.date:
        top, all_scores = run_leader_screening(args.date, args.top_n,
                                                env_check=args.env_check)
        print_results(top, args.date)

        # ── V4.0 模块C: 执行计划 ──
        if args.execution_plan and top:
            # Determine market env from top picks
            env = MarketEnv(top[0].get("market_env", "bull")) if top else MarketEnv.BULL
            plans = generate_execution_plan(top, env)
            print_execution_plan(plans)

        if args.db_write and all_scores:
            _write_to_db(all_scores, args.date, args.top_n)

        # Export JSON
        if args.export_json and top:
            os.makedirs(os.path.dirname(args.export_json) or "outputs", exist_ok=True)
            export_data = {
                "date": args.date,
                "top_n": len(top),
                "market_env": top[0].get("market_env", "bull") if top else "unknown",
                "picks": [{k: v for k, v in s.items() if not k.startswith("_")}
                          for s in top],
            }
            if args.execution_plan:
                export_data["execution_plan"] = generate_execution_plan(top)
            with open(args.export_json, 'w') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n  📁 JSON exported: {args.export_json}")

    else:
        # Default: latest trading day
        with _get_db(readonly=True) as db:
            dates = get_last_trading_days(db, 1)
        if dates:
            print(f"最新交易日: {dates[0]}")
            top, all_scores = run_leader_screening(dates[0], args.top_n,
                                                    env_check=args.env_check)
            print_results(top, dates[0])


# ── Service-layer engine wrapper ──


class LeaderScalpEngine:
    """V4.0 龙头短线战法引擎 — 收盘后选股.

    Wraps run_leader_screening + generate_execution_plan for screener-service.
    """

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute leader scalp screening.

        Returns: [{code, name, total_score, grade, ...}, ...]
        """
        if trade_date is None:
            with _get_db(readonly=True) as db:
                dates = get_last_trading_days(db, 1)
                trade_date = dates[0] if dates else None

        if not trade_date:
            return []

        top, all_scores = run_leader_screening(trade_date, top_n=top_n)
        return top if top else []


if __name__ == "__main__":
    main()
