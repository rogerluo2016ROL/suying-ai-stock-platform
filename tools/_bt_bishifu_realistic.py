#!/usr/bin/env python3
"""毕师傅趋势战法 — 真实资金模拟回测（修正版）。

相对 tools/backtest_bi_shifu_trend_1y.py 的修正：
  1. 先卖后买：T+2 卖出/止损回笼的现金当日即可用于新批次（A股资金 T+0 可用）。
  2. 资金约束选股：当日新批次用"买入前可用现金"等权分配，按评分降序买到现金用完
     —— 连续信号日持仓重叠、现金被占用时，低分票自然买不进（不再假设每批满仓）。
  3. T+1 涨停/停牌剔除：开盘涨停（主板≥9.5%、科创创业≥19.5%）或当日无行情 → 买不进。
  4. 滑点：买 open×(1+slip)，卖 close×(1-slip)，止损 stop×(1-slip)。
  5. 每日资金流水透明。

复用 outputs/bi_shifu_trend_signals_exact_*.json 已算信号（model_version=v2.1-score）。
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import psycopg2

ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="outputs/bi_shifu_trend_signals_exact_2025-07-15_2026-07-13.json")
    ap.add_argument("--start", default="2026-04-16")
    ap.add_argument("--end", default="2026-07-15")
    ap.add_argument("--initial-capital", type=float, default=1_000_000.0)
    ap.add_argument("--slippage-bps", type=float, default=20.0)
    ap.add_argument("--cost-bps", type=float, default=14.0)
    ap.add_argument("--no-limit-filter", action="store_true", help="不剔除开盘涨停")
    ap.add_argument("--max-pos-pct", type=float, default=1.0, help="单票占总资产上限，1.0=不限(满仓轮动)")
    ap.add_argument("--output", default="outputs/bt_bishifu_realistic_3m.json")
    return ap.parse_args()


def main():
    a = parse_args()
    slip = a.slippage_bps / 10000.0
    buy_cost = a.cost_bps / 20000.0
    sell_cost = a.cost_bps / 20000.0
    limit_filter = not a.no_limit_filter

    cache = json.loads((ROOT / a.cache).read_text())
    signals = cache["signals"]

    conn = psycopg2.connect("postgresql://kronos:kronos@localhost:6432/kronos")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
                (a.start, a.end))
    tdays = [str(r[0])[:10] for r in cur.fetchall()]
    tidx = {d: i for i, d in enumerate(tdays)}

    # 信号日：必须在 tdays 内且 entry/exit 都存在
    sig_days = sorted([d for d in signals if d in tidx and signals[d] and tidx[d] + 2 < len(tdays)])

    cur.execute("""SELECT k.code,k.trade_date,k.open,k.high,k.low,k.close,a.adj_factor
                   FROM daily_kline k LEFT JOIN adj_factor a ON a.code=k.code AND a.trade_date=k.trade_date
                   WHERE k.trade_date>=%s AND k.trade_date<=%s""", (tdays[0], tdays[-1]))
    raw = cur.fetchall()
    conn.close()

    # 收集原始行情 + 复权因子
    raw_map: dict[tuple, tuple] = {}
    bycode: dict[str, list] = defaultdict(list)
    for code, td, o, h, l, c, af in raw:
        td = str(td)[:10]
        raw_map[(code, td)] = (float(o), float(h), float(l), float(c), (float(af) if af is not None else None))
        bycode[code].append(td)

    # 前复权：每只股票以"窗口内最后一个非空 af"为基准(ref)，adj = raw*af/ref。
    # 同股所有日期基准一致，跨除权连续，根治 entry/exit af 不一致 / 持仓期 af 缺失导致的估值跳变。
    bars: dict[tuple, tuple] = {}  # (code,td) -> (adj_o, adj_h, adj_l, adj_c, raw_open)
    for code, tds in bycode.items():
        tds = sorted(set(tds))
        last = None
        for td in tds:  # af forward fill
            o, h, l, c, af = raw_map[(code, td)]
            if af is not None:
                last = af
            elif last is not None:
                af = last
            raw_map[(code, td)] = (o, h, l, c, af)
        nxt = None
        for td in reversed(tds):  # af backward fill
            o, h, l, c, af = raw_map[(code, td)]
            if af is not None:
                nxt = af
            elif nxt is not None:
                af = nxt
            raw_map[(code, td)] = (o, h, l, c, af)
        ref = next((raw_map[(code, td)][4] for td in reversed(tds) if raw_map[(code, td)][4] is not None), None)
        if not ref:
            continue  # 全程无复权因子，放弃该股
        for td in tds:
            o, h, l, c, af = raw_map[(code, td)]
            if af is None:
                continue
            f = af / ref
            bars[(code, td)] = (o * f, h * f, l * f, c * f, o)  # 前4=前复权价, 末=原始开盘(涨停判断)

    # picks 按 entry_date 索引
    entries: dict[str, list] = defaultdict(list)
    for sd in sig_days:
        entry = tdays[tidx[sd] + 1]
        exit_ = tdays[tidx[sd] + 2]
        for p in signals[sd]:
            entries[entry].append({**p, "signal_date": sd, "entry_date": entry, "exit_date": exit_})

    def limit_line(code: str) -> float:
        return 0.195 if code.startswith(("688", "30")) else 0.095

    cash = a.initial_capital
    positions: list[dict] = []
    trades: list[dict] = []
    daily: list[dict] = []

    def close_trade(pos, sell_price, reason):
        nonlocal cash
        proceeds = pos["shares"] * sell_price * (1 - sell_cost)
        cash += proceeds
        net = proceeds / pos["spend"] - 1
        trades.append({
            "signal_date": pos["signal_date"], "code": pos["code"], "name": pos["name"],
            "grade": pos["grade"], "score": pos["score"],
            "entry_date": pos["entry_date"], "exit_date": pos["exit_date"],
            "buy_price": round(pos["buy_price"], 3), "sell_price": round(sell_price, 3),
            "spend": round(pos["spend"], 0), "net_return_pct": round(net * 100, 3), "exit_reason": reason,
        })
        return proceeds

    for D in tdays:
        buys_n = sells_n = 0
        buys_spend = sells_proceeds = 0.0
        cash_open = cash  # 期初现金（含上一日结转）

        # a. 先卖：exit_date==D 的到期仓（昨天买的）
        for pos in [p for p in positions if p["exit_date"] <= D]:
            b = bars.get((pos["code"], D))
            if b is None:
                continue  # 停牌，继续持有；复牌日（exit<=D 且有 bar）补卖
            ao, ah, al, ac, ro = b
            stop = pos["stop"]
            if ao <= stop:              # 跳空低开越过止损
                sells_proceeds += close_trade(pos, ao * (1 - slip), "t2_gap_stop")
            elif al <= stop:            # 盘中触止损
                sells_proceeds += close_trade(pos, stop * (1 - slip), "t2_stop")
            else:                       # 正常收盘卖
                sells_proceeds += close_trade(pos, ac * (1 - slip), "t2_normal")
            positions.remove(pos)
            sells_n += 1

        # b. 后买：entry_date==D 的新批次
        cands = entries.get(D, [])
        eligible = []
        for p in cands:
            b = bars.get((p["code"], D))
            if b is None:
                continue  # 停牌买不进
            ao, ah, al, ac, ro = b
            sig_close = p.get("close")
            if limit_filter and sig_close and ro / sig_close - 1 >= limit_line(p["code"]):
                continue  # 开盘涨停买不进（用原始价判涨停板）
            eligible.append((p, ao))  # 前复权开盘作成交基准
        if eligible:
            eligible.sort(key=lambda x: -float(x[0].get("score", 0)))
            n = len(eligible)
            cash0 = cash
            cap_per = cash0 / n
            if a.max_pos_pct < 1.0:
                hold_val = sum(pp["shares"] * bars[(pp["code"], D)][3]
                               for pp in positions if (pp["code"], D) in bars)
                cap_per = min(cap_per, (cash0 + hold_val) * a.max_pos_pct)
            for p, buy_raw in eligible:
                if cap_per > cash + 1:
                    break  # 现金不足，剩余低分票放弃
                buy_price = buy_raw * (1 + slip)
                shares = cap_per / (buy_price * (1 + buy_cost))
                cash -= cap_per  # = shares*buy_price*(1+buy_cost)
                buys_spend += cap_per
                stop_pct = float(p.get("stop_loss_pct", 8.0)) / 100.0
                positions.append({
                    "code": p["code"], "name": p.get("name", ""), "signal_date": p["signal_date"],
                    "entry_date": D, "exit_date": p["exit_date"], "buy_price": buy_price,
                    "stop": buy_price * (1 - stop_pct), "shares": shares, "spend": cap_per,
                    "score": float(p.get("score", 0)), "grade": p.get("grade", ""),
                    "last_close": bars[(p["code"], D)][3],
                })
                buys_n += 1

        # c. T+1 当日止损：今天买入且当日 low 触止损
        for pos in [p for p in positions if p["entry_date"] == D]:
            b = bars.get((pos["code"], D))
            if b is None:
                continue
            ao, ah, al, ac, ro = b
            if al <= pos["stop"]:
                sells_proceeds += close_trade(pos, pos["stop"] * (1 - slip), "t1_stop")
                positions.remove(pos)  # 已止损，必须移除，否则 T+2 会被重复平仓
                sells_n += 1

        # d. 估值 + 流水（停牌股按上一收盘价估值，避免 hold_val 归零导致 equity 暴跌假象）
        hold_val = 0
        for pos in positions:
            b = bars.get((pos["code"], D))
            if b:
                pos["last_close"] = b[3]
                hold_val += pos["shares"] * b[3]
            elif pos.get("last_close"):
                hold_val += pos["shares"] * pos["last_close"]
        equity = cash + hold_val
        daily.append({
            "date": D, "cash_open": round(cash_open, 0), "cash": round(cash, 0),
            "holdings": len(positions), "hold_val": round(hold_val, 0), "equity": round(equity, 0),
            "position_pct": round(hold_val / equity * 100, 1) if equity else 0.0,
            "buys_n": buys_n, "buys_spend": round(buys_spend, 0),
            "sells_n": sells_n, "sell_proceeds": round(sells_proceeds, 0),
        })

    final_equity = daily[-1]["equity"] if daily else cash
    rets = [t["net_return_pct"] for t in trades]
    wins = sum(1 for r in rets if r > 0)
    peak = a.initial_capital
    mdd = 0.0
    for d in daily:
        peak = max(peak, d["equity"])
        mdd = min(mdd, d["equity"] / peak - 1)
    # 日收益做夏普
    eq = np.array([d["equity"] for d in daily], dtype=float)
    daily_ret = np.diff(eq) / eq[:-1]
    sharpe = float(np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)) if len(daily_ret) > 1 and np.std(daily_ret) > 0 else 0.0

    summary = {
        "口径": "真实模拟(先卖后买+满仓轮动+涨停剔除+滑点{:.0f}bp+成本{:.0f}bp)".format(a.slippage_bps, a.cost_bps),
        "initial_capital": a.initial_capital,
        "final_equity": round(final_equity, 0),
        "total_return_pct": round((final_equity / a.initial_capital - 1) * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "sharpe": round(sharpe, 2),
        "trades": len(trades),
        "win_rate_pct": round(wins / len(rets) * 100, 2) if rets else 0.0,
        "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
        "signal_days": len(sig_days),
    }
    out = ROOT / a.output
    out.write_text(json.dumps({"summary": summary, "trades": trades, "daily": daily}, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("输出:", out)


if __name__ == "__main__":
    main()
