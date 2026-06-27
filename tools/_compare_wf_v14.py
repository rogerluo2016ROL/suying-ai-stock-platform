#!/usr/bin/env python3
"""对比 V14 样本外 walk-forward 与 V13/V5.9/ST 基线."""
import json, os
FILES = {
    "V13 基线":   "outputs/walk_forward_2024-2025.json",
    "V5.9 冻结":  "outputs/walk_forward_2024-2025_frozen_v59.json",
    "ST 过滤":    "outputs/walk_forward_2024-2025_st_filter.json",
    "V14 重测":   "outputs/walk_forward_2024-2025_v14.json",
}
print(f"{'版本':<12}{'月加权net均值':>14}{'正月数':>8}{'Sharpe年化':>12}{'符号':>6}")
print("-"*54)
rows={}
for name, f in FILES.items():
    if not os.path.exists(f):
        print(f"{name:<12}{'(未生成)':>14}")
        continue
    d=json.load(open(f))
    c=d.get("conclusion",{})
    mean=c.get("monthly_weighted_net_mean_avg")
    pos=c.get("monthly_pos_count")
    sh=c.get("sharpe_like_annualized")
    sign=c.get("weighted_net_sign_aggregate","")
    rows[name]=(mean,pos,sh,sign)
    print(f"{name:<12}{mean:>13.4f}%{pos:>6}/24{sh:>12.3f}{sign:>6}")
print("-"*54)
if "V14 重测" in rows and "V13 基线" in rows:
    v14=rows["V14 重测"]; v13=rows["V13 基线"]
    dmean=v14[0]-v13[0]; dsh=v14[2]-v13[2]
    print(f"\nV14 vs V13: 月均值 Δ={dmean:+.4f}pp, Sharpe Δ={dsh:+.3f}")
    if v14[0] > 0 and v14[2] > 0:
        print("✅ V14 样本外转正 — 罕见, 需复核数据可信度")
    elif dmean > 0.3:
        print("⚠️ V14 改善但仍需判断是否跨越可用阈值 (月均值>0)")
    else:
        print("❌ V14 样本外仍确定性亏损 — 印证 memory 结论 (策略逻辑本身无 alpha)")
