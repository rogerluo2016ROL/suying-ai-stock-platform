#!/usr/bin/env python3
"""具身智能链 BOM — 第4步: 全节点七维评分 (reducer+motor+bearing+controller).

对 19 只公司 (4 节点) 跑 BOM 七维评分, 复用第3步规则, 验证跨节点分层是否合理.
输出全节点评分表 + 按节点分组 + 跨节点 Top 排名.

Usage:
    python tools/bom_embodied_score_all.py
"""
import ast
import re
import sys
from pathlib import Path

import pandas as pd

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
sys.path.insert(0, str(PROJ / "packages" / "kronos-factors"))
from kronos_factors.engine.supply_chain_bom import (  # noqa: E402
    DIM_WEIGHTS, derive_rating, derive_trade_signal,
)

ANCHORED = pd.read_csv(PROJ / "outputs" / "bom_embodied_reducer_anchored.csv")
EV_ALL = pd.read_csv(PROJ / "outputs" / "bom_embodied_evidence_all.csv")

# 节点 → policy 基础分 (都属具身智能链=未来产业主攻方向)
NODE_POLICY = {"reducer": 12, "motor": 12, "bearing": 11, "controller": 12}

CHOKEPOINT_WEIGHTS = {
    "垄断": 5, "独家": 5, "首家": 5, "稀缺": 5, "寡头": 5, "唯一": 5,
    "国产替代": 4, "进口替代": 4, "自主可控": 4, "打破垄断": 5, "卡脖子": 4,
    "客户验证": 3, "认证": 3, "供应商": 3, "定点": 3, "进入供应链": 3,
}


def _parse_list(s):
    if isinstance(s, list): return s
    try:
        v = ast.literal_eval(str(s)); return v if isinstance(v, list) else []
    except Exception: return []


def score_policy(ev_df, node):
    base = float(NODE_POLICY.get(node, 11))
    if ev_df["text"].str.contains("人形机器人|量产元年|政策|战略卡位|具身智能", na=False).any():
        base += 3
    return min(base, DIM_WEIGHTS["policy"])


def score_bom(ratio):
    r = float(ratio)
    if r >= 80: return 15.0
    if r >= 50: return 12.0
    if r >= 25: return 8.0
    if r >= 10: return 4.0
    return 2.0


def score_chokepoint(ev_df):
    total = 0.0; hits = {}
    for _, r in ev_df.iterrows():
        for kw in _parse_list(r.get("chokepoint")):
            w = CHOKEPOINT_WEIGHTS.get(kw, 2)
            total += w; hits[kw] = hits.get(kw, 0) + w
    return min(total, DIM_WEIGHTS["chokepoint"]), hits


def score_growth(ev_df):
    fc = ev_df[ev_df["source"] == "forecast"]
    max_g = None; is_reduce = False
    for _, r in fc.iterrows():
        t = str(r.get("text", ""))
        if "预增" in t:
            m = re.search(r"预增\s*([\d.]+)~([\d.]+)", t)
            if m: max_g = max(max_g or 0, float(m.group(2)))
        if "预减" in t: is_reduce = True
    if is_reduce and max_g is None: return 3.0, "预减"
    if max_g is not None:
        if max_g >= 100: return 15.0, f"预增{max_g:.0f}%"
        if max_g >= 50: return 12.0, f"预增{max_g:.0f}%"
        return 9.0, f"预增{max_g:.0f}%"
    return 6.0, "中性(待财务)"


def score_commercialization(ev_df):
    stage_order = ["放量/订单", "量产", "小批量", "样品/研发"]
    hits = set()
    for _, r in ev_df.iterrows():
        for s in _parse_list(r.get("stage")): hits.add(s)
    top = next((s for s in stage_order if s in hits), "未识别")
    fc = ev_df[ev_df["source"] == "forecast"]
    has_increase = any("预增" in str(r.get("text", "")) for _, r in fc.iterrows())
    base = {"放量/订单": 12.0, "量产": 9.0, "小批量": 6.0, "样品/研发": 3.0, "未识别": 2.0}[top]
    note = top
    if has_increase and base >= 9:
        base = min(base + 3, DIM_WEIGHTS["commercialization"]); note = f"{top}+业绩兑现"
    return base, note


def score_market(ev_df):
    n = len(ev_df)
    if n >= 20: return 10.0
    if n >= 10: return 7.0
    if n >= 5: return 5.0
    if n >= 1: return 3.0
    return 1.0


def main():
    # 公司 → (node, name, product, ratio) 取每个 code 主营最高的锚定
    anchored = ANCHORED.sort_values("bz_sales", ascending=False).drop_duplicates("code")
    code_meta = {r["code"]: (r["node"], r["name"], r["bz_item"], r["ratio_pct"])
                 for _, r in anchored.iterrows()}
    # 评分只看有证据的公司 (EV_ALL 的 code)
    codes = sorted(EV_ALL["code"].unique(), key=lambda c: -float(code_meta.get(c, ("?","?",0,0))[3]))

    results = []
    for code in codes:
        if code not in code_meta:
            continue
        node, name, product, ratio = code_meta[code]
        ev_df = EV_ALL[EV_ALL["code"] == code].copy()
        policy = score_policy(ev_df, node)
        bom = score_bom(ratio)
        chokepoint, ch_hits = score_chokepoint(ev_df)
        growth, g_note = score_growth(ev_df)
        profit = 6.0
        commercialization, c_note = score_commercialization(ev_df)
        market = score_market(ev_df)
        risk = 0.0
        dims = {"policy": policy, "bom": bom, "chokepoint": chokepoint,
                "growth": growth, "profit": profit,
                "commercialization": commercialization, "market": market, "risk": risk}
        total = round(sum(dims[k] for k in DIM_WEIGHTS), 1)
        total = min(total, 100)
        results.append({
            "code": code, "name": name, "node": node, "product": product[:14],
            "main_pct": ratio, "policy": policy, "bom": bom, "chokepoint": chokepoint,
            "growth": growth, "profit": profit, "comm": commercialization, "market": market,
            "total": total, "rating": derive_rating(total),
            "trade_signal": derive_trade_signal(total, dims),
            "n_ev": len(ev_df), "chokepoint_hits": ch_hits,
            "growth_note": g_note, "comm_note": c_note,
        })

    df = pd.DataFrame(results).sort_values("total", ascending=False)

    print("=" * 120)
    print("  具身智能链 BOM — 全节点七维评分 (reducer + motor + bearing + controller)")
    print("=" * 120)
    print(f"  {'名称':<8} {'节点':<10} {'主营%':>5} {'pol':>4} {'bom':>4} {'chk':>5} {'grw':>5} {'prf':>4} {'com':>4} {'mkt':>4} {'total':>6} {'级':>3} {'信号':<6} {'证据':>3}")
    print("  " + "-" * 116)
    for _, r in df.iterrows():
        print(f"  {r['name']:<8} {r['node']:<10} {r['main_pct']:>5.1f} {r['policy']:>4.0f} {r['bom']:>4.0f} "
              f"{r['chokepoint']:>5.0f} {r['growth']:>5.0f} {r['profit']:>4.0f} {r['comm']:>4.0f} {r['market']:>4.0f} "
              f"{r['total']:>6.1f} {r['rating']:>3} {r['trade_signal']:<6} {r['n_ev']:>3}")
    print()
    # 按节点分组 Top
    print("  按节点 Top2:")
    for node in ["reducer", "motor", "bearing", "controller"]:
        sub = df[df["node"] == node].head(2)
        if len(sub):
            print(f"    {node:<10}: " + ", ".join(f"{r['name']}({r['rating']}{r['total']:.0f})" for _, r in sub.iterrows()))
    print()
    # 跨节点分层
    print("  跨节点分层:")
    for rating in ["S", "A", "B", "C", "D"]:
        g = df[df["rating"] == rating]
        if len(g):
            print(f"    {rating}级 ({len(g)}只): " + ", ".join(g["name"].tolist()))
    print()
    # Top5 整体排名
    print("  整体 Top5 (跨节点):")
    for i, (_, r) in enumerate(df.head(5).iterrows()):
        ch = ", ".join(f"{k}" for k in list(r["chokepoint_hits"])[:3]) or "—"
        print(f"    {i+1}. {r['name']:<8} [{r['node']}] {r['total']:.0f}分 {r['rating']}级 {r['trade_signal']} | chk:{ch} | {r['growth_note']} | {r['comm_note']}")

    out = PROJ / "outputs" / "bom_embodied_score_all.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  导出: {out}")


if __name__ == "__main__":
    main()
