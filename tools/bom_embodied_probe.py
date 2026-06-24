#!/usr/bin/env python3
"""具身智能链 BOM 拆解 — 第1步: 概念池产品级过滤验证.

问题: 同花顺"人形机器人"概念 456 成员严重稀释 (含美的/长安/中国宝安等沾边股).
策略: 用 fina_mainbz_vip type='P' (产品级主营) 对概念池做产品锚定过滤,
      只有主营产品名命中 BOM 节点关键词的, 才保留为该节点候选.

本脚本验证: 对"减速器"概念(138)成员做产品扫描, 看产品级过滤后保留多少真标的,
以及它们锚定到哪些 BOM 节点 (减速器/丝杠/伺服/电机/控制器/传感器).

输出:
  - 各节点命中的公司 + 主营产品名 + 营收占比
  - 过滤前后对比 (138 -> N)
  - 验证"产品级锚定"是否比"概念成员卡"更精准

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_embodied_probe.py
"""
import os
import sys
import time
from collections import defaultdict

import tushare as ts
import pandas as pd

# BOM 节点 → 产品关键词 (具身智能链核心零部件)
BOM_NODES = {
    "reducer":      ["减速器", "谐波减速", "行星减速", "RV减速"],
    "leadscrew":    ["丝杠", "滚珠丝杠", "行星滚柱"],
    "servo":        ["伺服", "伺服系统", "伺服电机", "驱动器"],
    "motor":        ["电机", "空心杯", "无框电机", "步进电机"],
    "controller":   ["控制器", "运动控制", "控制系统"],
    "sensor":       ["传感器", "编码器", "力矩传感", "视觉"],
    "bearing":      ["轴承"],
}

CONCEPT = "886008.TI"  # 减速器概念 138 成员


def main():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    # 1) 概念成员池
    members = pro.ths_member(ts_code=CONCEPT)
    print(f"概念 {CONCEPT} (减速器) 成员: {len(members)}")
    codes = members["con_code"].tolist()
    print()

    # 2) 逐个查产品级主营, 锚定到 BOM 节点
    anchored = defaultdict(list)  # node -> [(code, name, bz_item, bz_sales, ratio)]
    scanned = 0
    no_mainbz = 0
    t0 = time.time()
    for i, code in enumerate(codes):
        try:
            df = pro.fina_mainbz_vip(ts_code=code, type="P")
            scanned += 1
        except Exception as e:
            no_mainbz += 1
            continue
        if df is None or len(df) == 0:
            no_mainbz += 1
            continue
        # 取最新一期 (end_date 最大)
        df = df.sort_values("end_date", ascending=False)
        latest_period = df["end_date"].iloc[0]
        df = df[df["end_date"] == latest_period].copy()
        total_sales = df["bz_sales"].sum()
        name = members.loc[members["con_code"] == code, "con_name"].iloc[0]
        matched_nodes = set()
        for _, r in df.iterrows():
            item = str(r["bz_item"]) if r["bz_item"] is not None else ""
            for node, kws in BOM_NODES.items():
                if any(kw in item for kw in kws):
                    ratio = (r["bz_sales"] / total_sales * 100) if total_sales > 0 else 0
                    anchored[node].append((code, name, item, r["bz_sales"], ratio))
                    matched_nodes.add(node)
        if (i + 1) % 20 == 0:
            print(f"  扫描 {i+1}/{len(codes)}... ({time.time()-t0:.0f}s)")
        time.sleep(0.25)  # 频控

    # 3) 汇总
    print()
    print("=" * 90)
    print(f"  产品级锚定结果 (扫描 {scanned} 只, 无主营数据 {no_mainbz} 只)")
    print("=" * 90)
    print(f"  {'BOM 节点':<12} {'命中公司数':<10} {'代表标的'}")
    print("  " + "-" * 86)
    all_anchored_codes = set()
    for node in BOM_NODES:
        items = anchored.get(node, [])
        # 去重 (同一公司多个产品命中同节点)
        seen = {}
        for code, name, item, sales, ratio in items:
            if code not in seen or sales > seen[code][3]:
                seen[code] = (code, name, item, sales, ratio)
        uniq = sorted(seen.values(), key=lambda x: -x[3])
        all_anchored_codes.update([c[0] for c in uniq])
        rep = ", ".join(f"{c[1]}({c[4]:.0f}%)" for c in uniq[:4]) if uniq else "—"
        print(f"  {node:<12} {len(uniq):<10} {rep}")

    print()
    print(f"  过滤前 (概念成员): {len(codes)} 只")
    print(f"  过滤后 (产品锚定命中): {len(all_anchored_codes)} 只")
    print(f"  稀释率: {(1 - len(all_anchored_codes)/len(codes))*100:.0f}% 成员被产品过滤剔除")

    # 4) 导出
    out = []
    for node in BOM_NODES:
        for code, name, item, sales, ratio in anchored.get(node, []):
            out.append({"node": node, "code": code, "name": name,
                        "bz_item": item, "bz_sales": sales, "ratio_pct": ratio})
    if out:
        df_out = pd.DataFrame(out).sort_values(["node", "bz_sales"], ascending=[True, False])
        path = "outputs/bom_embodied_reducer_anchored.csv"
        df_out.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n  导出: {path} ({len(df_out)} 行)")


if __name__ == "__main__":
    main()
