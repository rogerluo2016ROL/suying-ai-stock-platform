#!/usr/bin/env python3
"""毕师傅 V15 信号源重设 — 阶段A 因子 IC 速测.

目的
----
bi_trend (OBV+WR+ADX) 样本外确定性亏 (Sharpe -3.18). 在投入完整策略实现前,
先用 IC 速测确认数据库中"已存在但未使用"的横截面因子是否真有 alpha.
只有通过门控的因子才进入阶段B (写成完整策略). 验证优先于实现 —— 避免重蹈
OBV+WR 覆辙 (花整个策略的成本实现一个没 alpha 的东西).

口径 (与 bi_trend / walk_forward 对齐)
--------------------------------------
- 股票池: 仅硬科技池 (复用 _is_hard_tech_stock), 排除 ST
- 截面: 2024-01 ~ 2025-12 每月末 (复用 month_end_cutoffs), 共 24 个
- 前向收益: 月末交易日收盘 → 20 交易日后收盘 (复用 _get_trading_day)
- 指标: RankIC 均值 / ICIR (mean/std) / 正IC月占比
- 复权: 用 adj_factor 后复权 (与 backtest 一致, 消除除权跳变)

因子 (聚焦估值/换手 + 资金流两类)
----------------------------------
估值/换手 (daily_basic, 反转方向 → 取负):
  - pe_inv:        -PE  (低PE→未来涨)
  - pb_inv:        -PB  (低PB→未来涨)
  - turnover_inv:  -换手率 (低换手→未来涨, 冷门反转)
  - small_mv:      -circ_mv (小市值因子)
资金流 (moneyflow + margin_detail, 动量方向 → 取正):
  - main_net_inflow:  (大单+超大单) 净流入 / 成交额 (主力动量)
  - margin_chg:       融资余额5日变化率 (杠杆资金流入)

门控判据: |ICIR| >= 0.3 且 正IC月占比 >= 55% → 进入阶段B.

Usage:
    KRONOS_PG_URL="postgresql://kronos:kronos@localhost:6432/kronos" \\
      PYTHONPATH=packages/kronos-factors .venv/bin/python tools/factor_ic_probe.py \\
      --start 2024-01 --end 2025-12 --export outputs/factor_ic_probe.json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.backtest.engine import compute_ic, _get_trading_day
from kronos_factors.backtest.supply_chain_ic import month_end_cutoffs, _resolve_trading_day
from kronos_factors.engine.bi_trend_launch import _is_hard_tech_stock

HORIZON = 20  # 前向收益 20 交易日 (与 supply_chain_ic 默认一致)

# 因子定义: name -> 说明. 已统一为"高分=预期涨"(反转因子取负, 动量/质量因子保持正向).
FACTORS = {
    "pe_inv": "低PE反转",
    "pb_inv": "低PB反转",
    "turnover_inv": "低换手反转",
    "small_mv": "小市值",
    "main_net_inflow": "主力净流入动量",
    "margin_chg": "融资余额5日变化",
    # 扩展因子池 (第二轮)
    "north_hold_chg": "北向持股占比20日变化",
    "holder_increase": "股东净增持(60日内)",
    "roe": "ROE(财报滞后90日)",
    "revenue_growth": "营收增长(财报滞后90日)",
}

# 财报发布滞后假设 (天): 截面日 T 只能看到 end_date <= T-90 的财报, 防前视.
FIN_PUBLISH_LAG_DAYS = 90
# 股东增减持事件回溯窗口 (天): 截面日前 N 天内的增减持累计 (用 ann_date, 公告即可见).
HOLDER_LOOKBACK_DAYS = 60
# 北向持股变化回溯 (交易日)
NORTH_LOOKBACK_TD = 20


def _hard_tech_codes(db) -> set:
    """硬科技池股票代码集合 (排除 ST), 复用 bi_trend 同口径."""
    rows = db.execute(
        "SELECT code, industry FROM stocks WHERE is_st=0 AND name NOT LIKE '%ST%'"
    ).fetchall()
    return {r["code"] for r in rows if _is_hard_tech_stock(r["industry"] or "")}


def _adj_close_on(db, trade_date: str) -> dict:
    """取某交易日全市场后复权收盘价 {code: adj_close}."""
    rows = db.execute(
        "SELECT d.code, d.close, "
        "COALESCE(a.adj_factor, "
        "  (SELECT a2.adj_factor FROM adj_factor a2 "
        "   WHERE a2.code=d.code AND a2.trade_date<=d.trade_date "
        "   ORDER BY a2.trade_date DESC LIMIT 1), 1.0) AS adj "
        "FROM daily_kline d "
        "LEFT JOIN adj_factor a ON a.code=d.code AND a.trade_date=d.trade_date "
        "WHERE d.trade_date=?",
        (trade_date,),
    ).fetchall()
    return {r["code"]: float(r["close"]) * float(r["adj"] or 1.0)
            for r in rows if r["close"]}


def _factor_values(db, trade_date: str, codes: set) -> dict:
    """取某交易日各因子的横截面原始值 {factor: {code: value}}.

    反转因子在此已取负 (低PE→高分), 动量因子保持正向, 统一为"高分=预期涨".
    """
    out = {f: {} for f in FACTORS}

    # daily_basic: pe/pb/turnover_rate/circ_mv
    for r in db.execute(
        "SELECT code, pe, pb, turnover_rate, circ_mv FROM daily_basic WHERE trade_date=?",
        (trade_date,),
    ).fetchall():
        c = r["code"]
        if c not in codes:
            continue
        # 反转因子取负; PE/PB<=0 (亏损/异常) 跳过
        if r["pe"] and r["pe"] > 0:
            out["pe_inv"][c] = -float(r["pe"])
        if r["pb"] and r["pb"] > 0:
            out["pb_inv"][c] = -float(r["pb"])
        if r["turnover_rate"] is not None:
            out["turnover_inv"][c] = -float(r["turnover_rate"])
        if r["circ_mv"] and r["circ_mv"] > 0:
            out["small_mv"][c] = -float(r["circ_mv"])  # 小市值=高分

    # moneyflow: 主力净流入 = (大单+超大单 买-卖) / 总成交额, 归一化
    for r in db.execute(
        "SELECT code, buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount, "
        "buy_sm_amount, sell_sm_amount, buy_md_amount, sell_md_amount "
        "FROM moneyflow WHERE trade_date=?",
        (trade_date,),
    ).fetchall():
        c = r["code"]
        if c not in codes:
            continue
        lg = (r["buy_lg_amount"] or 0) - (r["sell_lg_amount"] or 0)
        elg = (r["buy_elg_amount"] or 0) - (r["sell_elg_amount"] or 0)
        total = sum(abs(r[k] or 0) for k in (
            "buy_sm_amount", "sell_sm_amount", "buy_md_amount", "sell_md_amount",
            "buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount"))
        if total > 0:
            out["main_net_inflow"][c] = (lg + elg) / total  # 主力净流入占比

    # margin_detail: 融资余额 5 日变化率
    prev5 = db.execute(
        "SELECT MAX(trade_date) d FROM daily_kline WHERE trade_date < ?",
        (trade_date,),
    ).fetchone()
    # 取 5 交易日前的日期
    d5 = db.execute(
        "SELECT trade_date FROM (SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT 6) t "
        "ORDER BY trade_date ASC LIMIT 1",
        (trade_date,),
    ).fetchone()
    if d5 and d5["trade_date"]:
        rz_now = {r["code"]: float(r["rzye"] or 0) for r in db.execute(
            "SELECT code, rzye FROM margin_detail WHERE trade_date=?", (trade_date,)
        ).fetchall()}
        rz_old = {r["code"]: float(r["rzye"] or 0) for r in db.execute(
            "SELECT code, rzye FROM margin_detail WHERE trade_date=?", (d5["trade_date"],)
        ).fetchall()}
        for c in codes:
            n, o = rz_now.get(c), rz_old.get(c)
            if n is not None and o and o > 0:
                out["margin_chg"][c] = (n / o - 1)

    # 北向持股占比 20 交易日变化 (hk_holdings.ratio)
    dN = db.execute(
        "SELECT trade_date FROM (SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?) t "
        "ORDER BY trade_date ASC LIMIT 1",
        (trade_date, NORTH_LOOKBACK_TD + 1),
    ).fetchone()
    if dN and dN["trade_date"]:
        hk_now = {r["code"]: float(r["ratio"] or 0) for r in db.execute(
            "SELECT code, ratio FROM hk_holdings WHERE trade_date=?", (trade_date,)
        ).fetchall()}
        hk_old = {r["code"]: float(r["ratio"] or 0) for r in db.execute(
            "SELECT code, ratio FROM hk_holdings WHERE trade_date=?", (dN["trade_date"],)
        ).fetchall()}
        for c in codes:
            n, o = hk_now.get(c), hk_old.get(c)
            if n is not None and o is not None:
                out["north_hold_chg"][c] = n - o  # 占比变化 (pp), 加仓为正

    # 股东净增持: 截面日前 HOLDER_LOOKBACK_DAYS 天内 change_ratio 累计 (ann_date 公告即可见)
    import datetime
    td_dt = datetime.datetime.strptime(trade_date, "%Y-%m-%d").date()
    lb_start = (td_dt - datetime.timedelta(days=HOLDER_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    holder_acc = {}
    for r in db.execute(
        "SELECT code, change_ratio FROM stk_holdertrade "
        "WHERE ann_date > ? AND ann_date <= ?",
        (lb_start, trade_date),
    ).fetchall():
        c = r["code"]
        if c not in codes:
            continue
        holder_acc[c] = holder_acc.get(c, 0.0) + float(r["change_ratio"] or 0)
    for c, v in holder_acc.items():
        out["holder_increase"][c] = v  # 净增持比例累计, 增持为正

    # 财务因子 (financial_indicator): 防前视 — 只取 end_date <= T-90 的最近一期财报
    fin_cutoff = (td_dt - datetime.timedelta(days=FIN_PUBLISH_LAG_DAYS)).strftime("%Y-%m-%d")
    # 每只票取 end_date<=fin_cutoff 的最新一期
    fin_rows = db.execute(
        "SELECT DISTINCT ON (code) code, roe, revenue_growth FROM financial_indicator "
        "WHERE end_date <= ? ORDER BY code, end_date DESC",
        (fin_cutoff,),
    ).fetchall()
    for r in fin_rows:
        c = r["code"]
        if c not in codes:
            continue
        if r["roe"] is not None:
            out["roe"][c] = float(r["roe"])
        if r["revenue_growth"] is not None:
            out["revenue_growth"][c] = float(r["revenue_growth"])

    return out


def probe(start: str, end: str) -> dict:
    db = create_pg_adapter()
    codes = _hard_tech_codes(db)
    print(f"硬科技池: {len(codes)} 只", file=sys.stderr)

    cutoffs = month_end_cutoffs(start, end)
    print(f"截面: {len(cutoffs)} 个月末 ({cutoffs[0]} ~ {cutoffs[-1]})", file=sys.stderr)

    # 每因子每月的 RankIC 序列
    factor_ics = {f: [] for f in FACTORS}
    detail = []

    for cal in cutoffs:
        td = _resolve_trading_day(db, cal)
        if not td:
            continue
        future_td = _get_trading_day(db, td, HORIZON)
        if not future_td:
            continue
        c0 = _adj_close_on(db, td)
        c1 = _adj_close_on(db, future_td)
        fvals = _factor_values(db, td, codes)

        month_row = {"cutoff": td, "future": future_td}
        for f in FACTORS:
            fv = fvals[f]
            common = [c for c in fv if c in c0 and c in c1 and c0[c] > 0]
            if len(common) < 10:
                month_row[f] = None
                continue
            scores = np.array([fv[c] for c in common], dtype=np.float64)
            rets = np.array([c1[c] / c0[c] - 1 for c in common], dtype=np.float64)
            ic = compute_ic(scores, rets)
            factor_ics[f].append(ic["rank_ic"])
            month_row[f] = round(ic["rank_ic"], 4)
        detail.append(month_row)
        print(f"  {td} → {future_td}: " +
              " ".join(f"{f}={month_row[f]}" for f in FACTORS if month_row[f] is not None),
              file=sys.stderr)

    # 汇总统计 + 门控判定
    summary = {}
    for f, label in FACTORS.items():
        arr = np.array(factor_ics[f])
        if len(arr) == 0:
            summary[f] = {"label": label, "n": 0, "verdict": "no_data"}
            continue
        mean_ic = float(np.mean(arr))
        std_ic = float(np.std(arr)) or 1e-9
        icir = mean_ic / std_ic
        pos_ratio = float(np.mean(arr > 0))
        # 门控: |ICIR|>=0.3 且 (该因子方向上)正IC月占比>=55%
        # 注: 因子已统一为"高分=预期涨", 故期望 IC>0, 看 pos_ratio
        passed = abs(icir) >= 0.3 and pos_ratio >= 0.55
        summary[f] = {
            "label": label,
            "mean_rank_ic": round(mean_ic, 4),
            "std_ic": round(std_ic, 4),
            "icir": round(icir, 4),
            "pos_ic_month_ratio": round(pos_ratio, 3),
            "n_months": len(arr),
            "verdict": "PASS" if passed else "fail",
        }

    return {
        "horizon": HORIZON,
        "pool": "hard_tech",
        "start": start,
        "end": end,
        "n_cutoffs": len(detail),
        "summary": summary,
        "monthly_detail": detail,
    }


def main():
    ap = argparse.ArgumentParser(description="V15 阶段A 因子 IC 速测 (硬科技池)")
    ap.add_argument("--start", default="2024-01")
    ap.add_argument("--end", default="2025-12")
    ap.add_argument("--export", default=None)
    args = ap.parse_args()

    res = probe(args.start, args.end)

    print("\n" + "=" * 78)
    print("  毕师傅 V15 阶段A — 因子 IC 速测 (硬科技池, 20日前向, 2024-2025)")
    print("=" * 78)
    print(f"  {'因子':<18}{'mean RankIC':>13}{'ICIR':>9}{'正IC月占比':>11}{'月数':>6}  判定")
    print("-" * 78)
    any_pass = False
    for f, s in res["summary"].items():
        if s.get("n", -1) == 0:
            print(f"  {s['label']:<18}{'无数据':>13}")
            continue
        flag = "✅ PASS" if s["verdict"] == "PASS" else "❌"
        if s["verdict"] == "PASS":
            any_pass = True
        print(f"  {s['label']:<18}{s['mean_rank_ic']:>+13.4f}{s['icir']:>+9.3f}"
              f"{s['pos_ic_month_ratio']:>11.0%}{s['n_months']:>6}  {flag}")
    print("-" * 78)
    print(f"  门控: |ICIR|>=0.3 且 正IC月占比>=55%")
    print(f"  结论: {'有因子通过 → 进入阶段B' if any_pass else '全部不达标 → 停止, 评估扩池/换因子'}")

    if args.export:
        Path(args.export).write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已导出: {args.export}")


if __name__ == "__main__":
    main()
