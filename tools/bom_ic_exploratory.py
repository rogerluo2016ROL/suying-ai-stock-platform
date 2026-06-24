#!/usr/bin/env python3
"""具身智能链 BOM — 路径1: 探索性截面 IC.

用已落的 V5 评分, 对几个有代表性的月末 cutoff 算 forward return,
看 V5 score 与 forward return 的 Spearman rank IC 方向是否成立.

⚠️ 严格诚实标注: V5 评分含 2026 全量证据/财务, 测 2025 cutoff 收益 = lookahead
   (用未来认知测过去收益). 本结果只能算"方向探索", 不能作 OOS 结论 (AC-8 不满足).
   方向成立才值得投入路径2 (cutoff-aware 严格 OOS).

复用 backtest/engine.py compute_ic + supply_chain_validation._forward_returns.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_ic_exploratory.py
"""
import os
import sys
from pathlib import Path

import numpy as np

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
for p in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    sys.path.insert(0, str(PROJ / p))
from kronos_factors.backtest.engine import compute_ic  # noqa: E402
from kronos_factors.backtest.supply_chain_validation import _forward_returns  # noqa: E402
from kronos_factors.scorer._db_stub import _get_db  # noqa: E402

CUTOFFS = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-13"]
HORIZONS = [5, 10, 20]


def load_scores():
    """从 PG 读 19 只 V5 评分: {code: total_score}."""
    scores = {}
    with _get_db(readonly=True) as db:
        rows = db.execute(
            "SELECT code, total_score FROM supply_chain_scores ORDER BY total_score DESC"
        ).fetchall()
        for r in rows:
            scores[r["code"]] = float(r["total_score"])
    return scores


def main():
    scores = load_scores()
    codes = list(scores.keys())
    score_arr = np.array([scores[c] for c in codes], dtype=np.float64)
    print("=" * 90)
    print("  BOM V5 评分 — 探索性截面 IC (⚠️ lookahead, 仅方向参考)")
    print("=" * 90)
    print(f"  样本: {len(codes)} 只 | 评分范围 {score_arr.min():.0f}~{score_arr.max():.0f}")
    print(f"  ⚠️ V5 含 2026 全量证据/财务, 测 2025 cutoff = 未来信息泄漏, 非 OOS\n")

    all_results = []
    for cutoff in CUTOFFS:
        print(f"  ▶ cutoff {cutoff}")
        for h in HORIZONS:
            rets, future_td = _forward_returns(codes, cutoff, h)
            valid = ~np.isnan(rets)
            n_valid = int(valid.sum())
            if n_valid < 5:
                print(f"     h={h:>2}d: 有效样本 {n_valid} < 5, 跳过 (可能 cutoff 后无数据)")
                continue
            ic = compute_ic(score_arr, rets)
            all_results.append({
                "cutoff": cutoff, "horizon": h, "future_td": future_td,
                "n": ic["n"], "ic": ic["ic"], "rank_ic": ic["rank_ic"],
                "hit_rate": ic["hit_rate"],
            })
            print(f"     h={h:>2}d → {future_td or '?'} | n={ic['n']:>2} "
                  f"IC={ic['ic']:+.3f} rankIC={ic['rank_ic']:+.3f} hit={ic['hit_rate']:.0%}")
        print()

    # 汇总
    if not all_results:
        print("  无有效结果"); return
    print("=" * 90)
    print("  汇总 (按 horizon 聚合)")
    print("=" * 90)
    print(f"  {'horizon':>8} {'n_cutoffs':>9} {'mean_IC':>9} {'mean_rankIC':>12} {'mean_hit':>9} {'正IC占比':>9}")
    print("  " + "-" * 64)
    for h in HORIZONS:
        sub = [r for r in all_results if r["horizon"] == h]
        if not sub: continue
        mean_ic = np.mean([r["ic"] for r in sub])
        mean_rank = np.mean([r["rank_ic"] for r in sub])
        mean_hit = np.mean([r["hit_rate"] for r in sub])
        pos = sum(1 for r in sub if r["rank_ic"] > 0)
        print(f"  {h:>7}d {len(sub):>9} {mean_ic:>+9.3f} {mean_rank:>+12.3f} {mean_hit:>9.0%} {pos}/{len(sub):>5}")

    # 方向判定
    print()
    rank_ics = [r["rank_ic"] for r in all_results]
    pos_rate = sum(1 for x in rank_ics if x > 0) / len(rank_ics)
    mean_rank = np.mean(rank_ics)
    print(f"  方向判定 (rank IC):")
    print(f"    全部 {len(rank_ics)} 个 cutoff×horizon 中, rank IC > 0 占比: {pos_rate:.0%}")
    print(f"    rank IC 均值: {mean_rank:+.3f}")
    if mean_rank > 0.05 and pos_rate >= 0.6:
        verdict = "✅ 方向成立 (评分高→收益高 倾向成立), 值得投入路径2 严格 OOS"
    elif mean_rank > 0:
        verdict = "⚪ 方向弱正 (信号微弱, 路径2 可能样本不足)"
    else:
        verdict = "❌ 方向不成立 (评分高→收益高 不成立), 路径2 不值得"
    print(f"    结论: {verdict}")
    print()
    print("  ⚠️ 再次强调: 本结果含 lookahead, 仅方向探索. 路径2 须 cutoff-aware 重算评分.")


if __name__ == "__main__":
    main()
