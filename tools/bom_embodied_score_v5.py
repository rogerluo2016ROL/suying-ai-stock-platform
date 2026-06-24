#!/usr/bin/env python3
"""具身智能链 BOM — 第5步: 补财务维度 + 修评分盲点.

改进:
  1. 接 fina_indicator 拉真实 growth (q_sales_yoy + netprofit_yoy) + profit (毛利率/净利率)
     替换 profit 全员中性6分 + growth 部分靠预告
  2. 修 chokepoint 多样性加权: 不同关键词命中 > 同关键词多次重复 (光洋降分)
  3. 低证据公司财务兜底: 证据少但财务强的好公司 (鸣志) 不被误判
  4. bom 主营占比 + 财务双驱动

评分规则 (V5):
  growth(15)  : max(q_sales_yoy, netprofit_yoy) 映射. 100%+→15, 50%→12, 20%→9, 0→6, 负→3
  profit(10)  : 毛利率映射. 50%+→10, 30%→7, 15%→4, <15%→2 (制造业毛利低, 阈值下调)
  chokepoint  : 多样性加权 = sum(min(命中次数,2)*权重), cap 20. 同关键词第3次起不加分
  其余维度同第4步

⚠️ 时点隔离: 本步用最新一期财务 (ann_date 最新的) 做评分验证. 回测时须按 trade_date
   卡 ann_date (PRD AC-8), 此处先不卡.

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_embodied_score_v5.py
"""
import ast
import os
import re
import sys
from pathlib import Path

import pandas as pd
import tushare as ts

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
sys.path.insert(0, str(PROJ / "packages" / "kronos-factors"))
from kronos_factors.engine.supply_chain_bom import (  # noqa: E402
    derive_rating, derive_trade_signal,
)
from kronos_factors.engine.supply_chain_bom_v5 import (  # noqa: E402
    DIM_WEIGHTS,
    score_bom_ratio,
    score_chokepoint_hits,
    score_commercialization as v5_score_commercialization,
    score_growth,
    score_market as v5_score_market,
    score_profit,
)

ANCHORED = pd.read_csv(PROJ / "outputs" / "bom_embodied_reducer_anchored.csv")
EV_ALL = pd.read_csv(PROJ / "outputs" / "bom_embodied_evidence_all.csv")
V4_SCORE = pd.read_csv(PROJ / "outputs" / "bom_embodied_score_all.csv")  # 第4步结果, 做对比

NODE_POLICY = {"reducer": 12, "motor": 12, "bearing": 11, "controller": 12}

def _pl(s):
    if isinstance(s, list): return s
    try:
        v = ast.literal_eval(str(s)); return v if isinstance(v, list) else []
    except Exception: return []


def fetch_fina(pro, code):
    """拉最新一期 fina_indicator. 返回 (q_sales_yoy, netprofit_yoy, gross_margin, net_margin, ann_date)."""
    try:
        df = pro.fina_indicator(ts_code=code, start_date="20240101", end_date="20260615")
        if df is None or len(df) == 0:
            return None
        df = df.sort_values("end_date", ascending=False)
        r = df.iloc[0]
        return {
            "q_sales_yoy": float(r.get("q_sales_yoy") or 0),
            "netprofit_yoy": float(r.get("netprofit_yoy") or 0),
            "gross_margin": float(r.get("grossprofit_margin") or r.get("gross_margin") or 0),
            "net_margin": float(r.get("netprofit_margin") or 0),
            "ann_date": str(r.get("ann_date") or ""),
            "end_date": str(r.get("end_date") or ""),
        }
    except Exception:
        return None


def score_policy(ev_df, node):
    base = float(NODE_POLICY.get(node, 11))
    if ev_df["text"].str.contains("人形机器人|量产元年|政策|战略卡位|具身智能", na=False).any():
        base += 3
    return min(base, DIM_WEIGHTS["policy"])


def score_bom(ratio):
    return score_bom_ratio(ratio)


def score_chokepoint_v5(ev_df):
    """多样性加权: 同关键词最多计2次命中, 鼓励不同维度证据."""
    kw_count = {}
    for _, r in ev_df.iterrows():
        for kw in _pl(r.get("chokepoint")):
            kw_count[kw] = kw_count.get(kw, 0) + 1
    return score_chokepoint_hits(kw_count), kw_count


def score_growth_v5(fina, ev_df):
    """财务增长优先, 预告兜底."""
    if fina:
        return score_growth(fina["q_sales_yoy"], fina["netprofit_yoy"])
    # 无财务, 用预告
    fc = ev_df[ev_df["source"] == "forecast"]
    for _, r in fc.iterrows():
        t = str(r.get("text", ""))
        if "预增" in t:
            m = re.search(r"预增\s*([\d.]+)~([\d.]+)", t)
            if m:
                hi = float(m.group(2))
                return score_growth(None, None, forecast_type="预增", forecast_max=hi)
    return score_growth(None, None)


def score_profit_v5(fina):
    """毛利率映射 (制造业阈值下调)."""
    if fina:
        return score_profit(fina["gross_margin"])
    return score_profit(None)


def score_commercialization(ev_df):
    stage_order = ["放量/订单", "量产", "小批量", "样品/研发"]
    hits = set()
    for _, r in ev_df.iterrows():
        for s in _pl(r.get("stage")): hits.add(s)
    top = next((s for s in stage_order if s in hits), "未识别")
    fc = ev_df[ev_df["source"] == "forecast"]
    has_inc = any("预增" in str(r.get("text", "")) for _, r in fc.iterrows())
    return v5_score_commercialization({top}, "预增" if has_inc else None)


def score_market(ev_df):
    return v5_score_market(len(ev_df))


def main():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    anchored = ANCHORED.sort_values("bz_sales", ascending=False).drop_duplicates("code")
    code_meta = {r["code"]: (r["node"], r["name"], r["bz_item"], r["ratio_pct"])
                 for _, r in anchored.iterrows()}
    codes = sorted(EV_ALL["code"].unique(), key=lambda c: -float(code_meta.get(c, ("?","?",0,0))[3]))

    results = []
    print("拉财务数据...")
    for i, code in enumerate(codes):
        if code not in code_meta: continue
        node, name, product, ratio = code_meta[code]
        ev_df = EV_ALL[EV_ALL["code"] == code].copy()
        fina = fetch_fina(pro, code)
        if (i + 1) % 5 == 0: print(f"  {i+1}/{len(codes)}")
        import time; time.sleep(0.25)

        policy = score_policy(ev_df, node)
        bom = score_bom(ratio)
        chokepoint, ch_hits = score_chokepoint_v5(ev_df)
        growth, g_note = score_growth_v5(fina, ev_df)
        profit, p_note = score_profit_v5(fina)
        commercialization, c_note = score_commercialization(ev_df)
        market = score_market(ev_df)
        risk = 0.0
        dims = {"policy": policy, "bom": bom, "chokepoint": chokepoint,
                "growth": growth, "profit": profit,
                "commercialization": commercialization, "market": market, "risk": risk}
        total = round(sum(dims[k] for k in DIM_WEIGHTS), 1)
        total = min(total, 100)
        results.append({
            "code": code, "name": name, "node": node, "main_pct": ratio,
            "policy": policy, "bom": bom, "chokepoint": chokepoint,
            "growth": growth, "profit": profit, "comm": commercialization, "market": market,
            "total": total, "rating": derive_rating(total),
            "trade_signal": derive_trade_signal(total, dims),
            "n_ev": len(ev_df), "growth_note": g_note, "profit_note": p_note, "comm_note": c_note,
            "fina_end": fina["end_date"] if fina else "",
        })

    df = pd.DataFrame(results).sort_values("total", ascending=False)

    # 对比第4步
    v4 = V4_SCORE.set_index("code")["total"].to_dict()
    df["v4_total"] = df["code"].map(v4)
    df["delta"] = df["total"] - df["v4_total"]

    print()
    print("=" * 125)
    print("  具身智能链 BOM V5 — 补财务 + 修规则 (全节点)")
    print("=" * 125)
    print(f"  {'名称':<8} {'节点':<10} {'主营%':>5} {'pol':>4} {'bom':>4} {'chk':>5} {'grw':>5} {'prf':>4} {'com':>4} {'mkt':>4} {'V5':>6} {'V4':>6} {'Δ':>5} {'级':>3} {'信号':<6}")
    print("  " + "-" * 121)
    for _, r in df.iterrows():
        print(f"  {r['name']:<8} {r['node']:<10} {r['main_pct']:>5.1f} {r['policy']:>4.0f} {r['bom']:>4.0f} "
              f"{r['chokepoint']:>5.0f} {r['growth']:>5.0f} {r['profit']:>4.0f} {r['comm']:>4.0f} {r['market']:>4.0f} "
              f"{r['total']:>6.1f} {r['v4_total']:>6.1f} {r['delta']:>+5.1f} {r['rating']:>3} {r['trade_signal']:<6}")
    print()
    print("  V5 关键修正:")
    # 光洋 (多样性加权降分)
    gy = df[df["name"] == "光洋股份"]
    if len(gy):
        r = gy.iloc[0]
        print(f"    光洋股份: V4 92 → V5 {r['total']:.0f} (多样性加权降 chokepoint; profit={r['profit_note']})")
    # 鸣志 (财务兜底升分)
    mz = df[df["name"] == "鸣志电器"]
    if len(mz):
        r = mz.iloc[0]
        print(f"    鸣志电器: V4 50 → V5 {r['total']:.0f} (财务兜底; growth={r['growth_note']} profit={r['profit_note']})")
    print()
    print("  跨节点分层 (V5):")
    for rating in ["S", "A", "B", "C", "D"]:
        g = df[df["rating"] == rating]
        if len(g):
            print(f"    {rating}级 ({len(g)}只): " + ", ".join(g["name"].tolist()))
    print()
    print("  整体 Top5 (V5):")
    for i, (_, r) in enumerate(df.head(5).iterrows()):
        print(f"    {i+1}. {r['name']:<8} [{r['node']}] {r['total']:.0f}分 {r['rating']}级 {r['trade_signal']} | {r['growth_note']} | {r['profit_note']} | {r['comm_note']}")

    out = PROJ / "outputs" / "bom_embodied_score_v5.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  导出: {out}")


if __name__ == "__main__":
    main()
