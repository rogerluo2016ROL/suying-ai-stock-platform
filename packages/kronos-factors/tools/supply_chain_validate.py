#!/usr/bin/env python
"""supply_chain 样本外验证 CLI (P5).

用法:
  PYTHONPATH=packages/kronos-factors python tools/supply_chain_validate.py \\
      --train-start 2020-03-31 --test-end 2026-06-30 --baseline random

可选 --weights calibrated_weights.json (P4 校准权重), 不传则用默认权重.
输出 verdict + train/test/baseline IC 统计, JSON 落到 --out.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 让 tools/ 脚本能 import kronos_factors (脚本在 packages/kronos-factors/tools/)
_PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG))


def main():
    ap = argparse.ArgumentParser(description="supply_chain 样本外验证 (P5 门禁)")
    ap.add_argument("--train-start", default="2020-03-31")
    ap.add_argument("--train-end", default="2023-12-31")
    ap.add_argument("--test-start", default="2024-01-31")
    ap.add_argument("--test-end", default="2026-06-30")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--n-seeds", type=int, default=5)
    ap.add_argument("--sample-size", type=int, default=300)
    ap.add_argument("--baseline", default="random", choices=["random", "chokepoint"])
    ap.add_argument("--weights", default=None, help="calibrated_weights.json (P4), 不传用默认")
    ap.add_argument("--out", default="supply_chain_oos_report.json")
    args = ap.parse_args()

    from kronos_factors.engine.supply_chain import SupplyChainEngine
    from kronos_factors.backtest.supply_chain_validation import run_supply_chain_oos_validation

    weights = None
    if args.weights and Path(args.weights).exists():
        data = json.loads(Path(args.weights).read_text(encoding="utf-8"))
        weights = data.get("weights") or data
        print(f"加载校准权重: {weights}", flush=True)
    else:
        print("用默认权重验证 (未传 --weights)", flush=True)

    print(f"\n{'='*60}\nsupply_chain 样本外验证 (P5)\n{'='*60}", flush=True)
    result = run_supply_chain_oos_validation(
        SupplyChainEngine, weights=weights,
        train_start=args.train_start, train_end=args.train_end,
        test_start=args.test_start, test_end=args.test_end,
        horizon=args.horizon, n_seeds=args.n_seeds,
        sample_size=args.sample_size, baseline=args.baseline)

    print(f"\n{'='*60}\n门禁判定: {result['verdict']}\n{'='*60}", flush=True)
    print(f"  ① test mean_ic > 0:          {result['criteria']['test_mean_ic_positive']}  ({result['test']['mean_ic']:+.4f})")
    print(f"  ② test p_value < 0.05:        {result['criteria']['test_p_lt_0.05']}  ({result['test']['p_value']:.4f})")
    print(f"  ③ 优于基线 +0.02:             {result['criteria']['beats_baseline_by_0.02']}  "
          f"(test {result['test']['mean_ic']:+.4f} vs base {result['baseline']['mean_ic']:+.4f})")
    print(f"  ④ 跨 seed std < 0.03:         {result['criteria']['seed_std_lt_0.03']}  ({result['test']['seed_std']:.4f})")
    print(f"\n  train: mean_ic={result['train']['mean_ic']:+.4f} ICIR={result['train']['icir']:+.4f} "
          f"n={result['train']['n_cutoffs']}")
    print(f"  test:  mean_ic={result['test']['mean_ic']:+.4f} ICIR={result['test']['icir']:+.4f} "
          f"n={result['test']['n_cutoffs']}")

    out_path = Path(args.out)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {out_path.resolve()}", flush=True)

    # 门禁 FAIL 提醒: 校准权重不得上线, 回退默认
    if result["verdict"] == "FAIL" and weights:
        print("\n⚠️ verdict=FAIL: 校准权重不得合并到 DEFAULT_WEIGHTS, 回退默认权重.", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
