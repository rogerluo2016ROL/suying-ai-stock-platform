#!/usr/bin/env python3
"""具身智能链 BOM — 第4步: 横扩 motor/bearing/controller 节点证据采集.

对 motor/bearing/controller 三节点各取主营占比 Top5 龙头, 批量拉证据
(research_report + irm_qa + forecast), 复用第2步的抽取规则.
reducer 节点已采过的公司 (昊志机电等) 跳过, 直接复用 bom_reducer_evidence.csv.

输出合并证据 CSV (含 reducer), 供第4步评分脚本消费.

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_expand_evidence.py
"""
import os
import sys
import time
import ast
from collections import defaultdict

import tushare as ts
import pandas as pd

PROJ = "/Users/rogerluo/程序目录/K线大模型"
ANCHORED = pd.read_csv(f"{PROJ}/outputs/bom_embodied_reducer_anchored.csv")
EXISTING_EV = pd.read_csv(f"{PROJ}/outputs/bom_reducer_evidence.csv")
EXISTING_CODES = set(EXISTING_EV["code"].unique())

START, END = "20240101", "20260615"

CHOKEPOINT_KW = [
    "国产替代", "进口替代", "打破垄断", "自主可控", "突破封锁", "卡脖子",
    "唯一", "独家", "首家", "稀缺", "寡头", "垄断",
    "定点", "认证", "进入供应链", "客户验证", "供应商", "合格供方",
    "替代进口", "海外替代", "国产化率",
]
COMMERCIALIZATION_KW = {
    "样品/研发": ["样品", "试制", "研发中", "预研", "开发中", "送样", "打样"],
    "小批量": ["小批量", "小批", "试产", "中试", "初步交付"],
    "量产": ["量产", "批量生产", "规模化", "批量交付", "规模交付", "稳定出货"],
    "放量/订单": ["订单", "产能释放", "扩产", "放量", "满产", "需求旺盛", "供不应求"],
}


def hit_kw(text, kws):
    text = str(text) if text else ""
    return [kw for kw in kws if kw in text]


def stage_hits(text):
    text = str(text) if text else ""
    return [s for s, kws in COMMERCIALIZATION_KW.items() if any(kw in text for kw in kws)]


def collect_one(pro, code, name):
    """单只公司证据采集, 返回 evidence list."""
    ev = []
    # 研报
    try:
        rr = pro.research_report(ts_code=code, start_date=START, end_date=END)
        if rr is None: rr = pd.DataFrame()
    except Exception:
        rr = pd.DataFrame()
    for _, r in (rr.head(30) if len(rr) else pd.DataFrame()).iterrows():
        title = str(r.get("title", ""))
        ch, st = hit_kw(title, CHOKEPOINT_KW), stage_hits(title)
        if ch or st:
            ev.append({"code": code, "name": name, "source": "research_report",
                       "date": str(r.get("trade_date", "")), "text": title[:120],
                       "chokepoint": ch, "stage": st})
    # 互动问答
    for api in ["irm_qa_sz", "irm_qa_sh"]:
        if (api == "irm_qa_sz" and not code.endswith(".SZ")) or \
           (api == "irm_qa_sh" and not code.endswith(".SH")):
            continue
        try:
            qa = getattr(pro, api)(ts_code=code, start_date=START, end_date=END)
            if qa is None: qa = pd.DataFrame()
        except Exception:
            qa = pd.DataFrame()
        for _, r in (qa.head(50) if len(qa) else pd.DataFrame()).iterrows():
            q = str(r.get("q", "")) + " " + str(r.get("a", ""))
            ch, st = hit_kw(q, CHOKEPOINT_KW), stage_hits(q)
            if ch or st:
                ev.append({"code": code, "name": name, "source": api,
                           "date": str(r.get("trade_date", "")),
                           "text": (str(r.get("q", ""))[:80] + " | " + str(r.get("a", ""))[:80]),
                           "chokepoint": ch, "stage": st})
    # 业绩预告
    try:
        fc = pro.forecast(ts_code=code, start_date=START, end_date=END)
        if fc is None: fc = pd.DataFrame()
    except Exception:
        fc = pd.DataFrame()
    for _, r in (fc.head(3) if len(fc) else pd.DataFrame()).iterrows():
        ev.append({"code": code, "name": name, "source": "forecast",
                   "date": str(r.get("ann_date", "")),
                   "text": f"业绩预告 {r.get('type','')} {r.get('p_change_min','')}~{r.get('p_change_max','')}%",
                   "chokepoint": [], "stage": []})
    return ev


def main():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    # 取 motor/bearing/controller 各 Top5 (按主营占比, 去重)
    targets = {}  # code -> (node, name, product, ratio)
    for node in ["motor", "bearing", "controller"]:
        sub = ANCHORED[ANCHORED["node"] == node].sort_values("bz_sales", ascending=False).head(5)
        for _, r in sub.iterrows():
            # 同一公司可能跨节点, 记录主营占比最高的节点
            if r["code"] not in targets or r["ratio_pct"] > targets[r["code"]][3]:
                targets[r["code"]] = (node, r["name"], r["bz_item"], r["ratio_pct"])

    print(f"横扩目标: {len(targets)} 只 (motor/bearing/controller 各Top5, 去重)")
    print(f"  其中 {sum(1 for c in targets if c in EXISTING_CODES)} 只已在 reducer 采集, 复用")
    print()

    new_ev = []
    for code, (node, name, product, ratio) in targets.items():
        if code in EXISTING_CODES:
            print(f"  ✓ {code} {name} [{node}] — 复用 reducer 证据")
            continue
        print(f"  ▶ {code} {name} [{node}] 主营{ratio:.0f}% ...", end=" ", flush=True)
        ev = collect_one(pro, code, name)
        for e in ev:
            e["node"] = node
        new_ev.extend(ev)
        print(f"{len(ev)} 条证据")
        time.sleep(0.5)

    # 合并: 给 reducer 证据补 node 字段
    EXISTING_EV["node"] = EXISTING_EV["code"].map(
        lambda c: "reducer" if c in {x[0] for x in [
            ("002472.SZ","双环传动"),("688017.SH","绿的谐波"),("002896.SZ","中大力德"),
            ("605389.SH","长龄液压"),("300503.SZ","昊志机电"),("301368.SZ","丰立智能"),
            ("301596.SZ","瑞迪智驱")]} else None)
    # reducer 公司的 node 标注
    reducer_map = {"002472.SZ":"reducer","688017.SH":"reducer","002896.SZ":"reducer",
                   "605389.SH":"reducer","300503.SZ":"reducer","301368.SZ":"reducer",
                   "301596.SZ":"reducer"}
    EXISTING_EV["node"] = EXISTING_EV["code"].map(reducer_map)

    # 横扩公司也按主营最高节点标注 (已在 reducer 的公司, 其 motor/controller 锚定用 reducer)
    new_df = pd.DataFrame(new_ev) if new_ev else pd.DataFrame(columns=EXISTING_EV.columns)
    all_ev = pd.concat([EXISTING_EV, new_df], ignore_index=True)
    # 给横扩新公司的 node 用 targets 映射 (跨节点的归主营最高节点)
    tgt_map = {c: v[0] for c, v in targets.items()}
    all_ev["node"] = all_ev.apply(
        lambda r: r["node"] if pd.notna(r.get("node")) else tgt_map.get(r["code"], "?"), axis=1)

    out = f"{PROJ}/outputs/bom_embodied_evidence_all.csv"
    all_ev.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n合并证据: {len(all_ev)} 条 ({all_ev['code'].nunique()} 公司)")
    print(f"  按节点: {all_ev.groupby('node')['code'].nunique().to_dict()}")
    print(f"  导出: {out}")


if __name__ == "__main__":
    main()
