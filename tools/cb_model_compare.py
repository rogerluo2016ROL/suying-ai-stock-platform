#!/usr/bin/env python3
"""可转债 ML 模型对比 — LightGBM vs CatBoost vs RF vs Ensemble.

用法:
  python3 tools/cb_model_compare.py --days 35 --top-n 30
"""

import argparse, json, os, sys, time, pickle
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))
sys.path.insert(0, _PROJ)

import numpy as np
import psycopg2
import lightgbm as lgb
from catboost import CatBoostRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error
from scipy.stats import spearmanr

from tools.cb_intraday_exit import (estimate_cb_exit_price, find_exit_info,
    find_stop_loss, find_take_profit, check_entry_quality, find_trailing_stop,
    adaptive_take_profit_target)
from tools.cb_backtest_intraday import (get_trade_dates, load_stock_mins,
    get_cb_open_and_stock, get_stock_atr_pct)

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
FEATURE_COLS = [
    "sector_score", "premium_score", "momentum_score", "liquidity_score",
    "rev_bonus", "call_penalty",
    "premium_rate_raw", "yesterday_pct_raw", "amount_wan_raw",
    "remain_size_yi", "stock_atr_pct",
    # Interaction features
    "liq_x_mom",      # liquidity × momentum
    "prem_x_sector",  # premium × sector
    "liq_x_atr",      # liquidity × volatility
    "mom_x_yest",     # momentum score × raw yesterday pct
]
FEATURE_NAMES = ["板块", "溢价率", "动量", "流动性", "下修加分", "强赎惩罚",
                 "溢价率%", "昨涨跌幅%", "成交额(万)", "剩余规模", "ATR%",
                 "流动×动量", "溢价×板块", "流动×波动", "动量×昨涨"]


def collect_data(days_back: int, top_n: int) -> tuple:
    """收集特征和标签."""
    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)
    print(f"采集 {len(trade_dates)} 天数据...")

    X_list, y_list, meta = [], [], []
    for ti, td in enumerate(trade_dates):
        # V6: use_ml=False to get raw linear picks (ML re-rank happens in this script)
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(trade_date=td, top_n=top_n, use_ml=False)
        engine.close()
        if not picks:
            continue
        for p in picks:
            try:
                price_info = get_cb_open_and_stock(conn, p["code"], p["stk_code"], td)
            except Exception:
                try: conn.rollback()
                except: pass
                continue
            cb_open = price_info["cb_open"]
            stock_open = price_info["stock_open"]
            if not cb_open or cb_open <= 0:
                continue

            bars = load_stock_mins(conn, p["stk_code"], td)
            if len(bars) < 10 or not check_entry_quality(bars, min_bars=3):
                try: conn.rollback()
                except: pass
                continue

            atr_pct = get_stock_atr_pct(conn, p["stk_code"], td)
            try: conn.rollback()
            except: pass

            tp_target = adaptive_take_profit_target(atr_pct)
            take_profit = find_take_profit(bars, cb_open, stock_open or 0, tp_target, skip_bars=3) if stock_open else None
            trailing_stop = find_trailing_stop(bars, pct_from_high=2.0, skip_bars=6)
            stop_loss = find_stop_loss(bars, below_vwap_minutes=45, skip_bars=6, min_pct_below=0.5)
            exit_info = find_exit_info(bars)
            if exit_info["signal"] and exit_info["signal"]["kdj_j"] <= 95:
                exit_info["signal"] = None

            if take_profit: sig = take_profit
            elif trailing_stop: sig = trailing_stop
            elif stop_loss: sig = stop_loss
            else: sig = exit_info["signal"]

            if sig:
                cb_exit = estimate_cb_exit_price(cb_open, stock_open or 0, sig["close"], p.get("premium_rate"))
            else:
                cur = conn.cursor()
                cur.execute("SELECT close FROM cb_daily WHERE ts_code=%s AND trade_date=%s", (p["code"], td))
                row = cur.fetchone(); cur.close()
                cb_exit = float(row[0]) if row and row[0] else cb_open

            d = p.get("details", {})
            liq = d.get("liquidity_score", 50)
            mom = d.get("momentum_score", 50)
            sec = d.get("sector_score", 50)
            prem = d.get("premium_score", 50)
            ypct = p.get("yesterday_pct") or 0
            features = [
                sec, prem, mom, liq,
                d.get("rev_bonus", 0), d.get("call_penalty", 0),
                p.get("premium_rate") or 0, ypct,
                p.get("cb_amount_wan") or 0, 0, atr_pct or 0,
                liq * mom / 100,          # liquidity × momentum interaction
                prem * sec / 100,         # premium × sector interaction
                liq * (atr_pct or 0) / 100,  # liquidity × volatility
                mom * ypct / 100,         # momentum × yesterday pct
            ]
            X_list.append(features)
            y_list.append((cb_exit - cb_open) / cb_open * 100)
            meta.append({"date": td, "code": p["code"]})

        if (ti + 1) % 10 == 0:
            print(f"  {ti+1}/{len(trade_dates)}, {len(X_list)} 样本")

    conn.close()
    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.float32)
    # Remove extreme outliers
    mask = np.abs(y - y.mean()) < 5 * y.std()
    print(f"采集完成: {X.shape[0]} 样本 (过滤 {sum(~mask)} 异常值), y mean={y[mask].mean():.2f}%")
    return X[mask], y[mask], [meta[i] for i in range(len(meta)) if mask[i]]


def train_evaluate(name: str, model, X, y, meta, predict_fn) -> dict:
    """训练+交叉验证."""
    tscv = TimeSeriesSplit(n_splits=5)
    scores = []
    t0 = time.time()

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        # Train
        try:
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        except TypeError:
            model.fit(X_train, y_train)

        y_pred = predict_fn(model, X_val)
        rmse = np.sqrt(mean_squared_error(y_val, y_pred))
        mae = mean_absolute_error(y_val, y_pred)
        rho, _ = spearmanr(y_val, y_pred)

        # Top-N ranking quality: re-rank within each date, compare returns
        fold_meta = [meta[i] for i in val_idx]
        date_groups = defaultdict(list)
        for j, m in enumerate(fold_meta):
            date_groups[m["date"]].append((y_pred[j], y_val[j]))

        top_returns = []
        for items in date_groups.values():
            if len(items) >= 10:
                ranked = sorted(items, key=lambda x: x[0], reverse=True)[:10]
                top_returns.extend(r[1] for r in ranked)

        top_mean = np.mean(top_returns) if top_returns else 0
        top_win = sum(1 for r in top_returns if r > 0) / len(top_returns) * 100 if top_returns else 0

        scores.append({"rmse": rmse, "mae": mae, "spearman_r": rho,
                       "top10_mean": top_mean, "top10_win": top_win})

    elapsed = time.time() - t0
    avg_rho = np.mean([s["spearman_r"] for s in scores])
    avg_top = np.mean([s["top10_mean"] for s in scores])
    avg_win = np.mean([s["top10_win"] for s in scores])

    print(f"  {name:<18} SpearmanR={avg_rho:.3f}  Top10均值={avg_top:+.2f}%  "
          f"胜率={avg_win:.0f}%  RMSE={np.mean([s['rmse'] for s in scores]):.2f}%  "
          f"耗时={elapsed:.1f}s")

    return {"name": name, "spearman_r": avg_rho, "top10_mean": avg_top,
            "top10_win": avg_win, "scores": scores, "elapsed": elapsed, "model": model}


def run_comparison(days_back: int = 35, top_n: int = 30):
    """模型对比主流程."""
    # ── Collect data ──
    X, y, meta = collect_data(days_back, top_n)

    # ── Feature importance from LightGBM for reference ──
    print(f"\n{'='*80}")
    print(f"模型对比 ({X.shape[0]} 样本, {X.shape[1]} 特征, 5折时序交叉验证)")
    print(f"{'='*80}\n")

    results = []

    # 1. Random Forest (baseline)
    rf = RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=10,
                                random_state=42, n_jobs=-1)
    results.append(train_evaluate("RF (sklearn)", rf, X, y, meta,
                                  lambda m, x: m.predict(x)))

    # 2. LightGBM Regressor
    lgb_reg = lgb.LGBMRegressor(objective='regression', num_leaves=31, learning_rate=0.05,
                                 n_estimators=200, min_child_samples=20, subsample=0.8,
                                 colsample_bytree=0.8, random_state=42, verbose=-1)
    results.append(train_evaluate("LightGBM Regressor", lgb_reg, X, y, meta,
                                  lambda m, x: m.predict(x)))

    # 3. LightGBM Ranker
    lgb_rank = lgb.LGBMRanker(objective='lambdarank', num_leaves=31, learning_rate=0.05,
                               n_estimators=200, min_child_samples=20, subsample=0.8,
                               colsample_bytree=0.8, random_state=42, verbose=-1)
    # Ranker needs group info
    try:
        results.append(train_evaluate("LightGBM Ranker", lgb_rank, X, y, meta,
                                      lambda m, x: m.predict(x)))
    except Exception as e:
        print(f"  LightGBM Ranker: 跳过 ({e})")
        # Fallback to regressor with same params for features
        lgb_rank2 = lgb.LGBMRegressor(objective='regression', num_leaves=31, learning_rate=0.05,
                                       n_estimators=200, min_child_samples=20, random_state=42, verbose=-1)
        results.append(train_evaluate("LightGBM (rank fallback)", lgb_rank2, X, y, meta,
                                      lambda m, x: m.predict(x)))

    # 4. CatBoost Regressor
    cb = CatBoostRegressor(iterations=200, learning_rate=0.05, depth=6,
                           l2_leaf_reg=3, random_seed=42, verbose=False, allow_writing_files=False)
    results.append(train_evaluate("CatBoost", cb, X, y, meta,
                                  lambda m, x: m.predict(x)))

    # 5. Ensemble (average of RF + LGB + CatBoost)
    ensemble_models = [(r["name"], r["model"]) for r in results
                       if r["name"] in ("RF (sklearn)", "LightGBM Regressor", "CatBoost")]
    if len(ensemble_models) >= 2:
        def _ensemble_predict(x):
            preds = [m.predict(x) for _, m in ensemble_models]
            return np.mean(preds, axis=0)

        # Evaluate ensemble without training
        tscv = TimeSeriesSplit(n_splits=5)
        ens_scores = []
        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            y_pred = _ensemble_predict(X[val_idx])
            y_val = y[val_idx]
            rho, _ = spearmanr(y_val, y_pred)
            fold_meta = [meta[i] for i in val_idx]
            date_groups = defaultdict(list)
            for j, m in enumerate(fold_meta):
                date_groups[m["date"]].append((y_pred[j], y_val[j]))
            top_rets = []
            for items in date_groups.values():
                if len(items) >= 10:
                    ranked = sorted(items, key=lambda x: x[0], reverse=True)[:10]
                    top_rets.extend(r[1] for r in ranked)
            ens_scores.append({
                "spearman_r": rho, "top10_mean": np.mean(top_rets) if top_rets else 0,
                "top10_win": sum(1 for r in top_rets if r > 0) / len(top_rets) * 100 if top_rets else 0,
                "rmse": np.sqrt(mean_squared_error(y_val, y_pred)),
            })

        name_str = f"Ensemble ({'+'.join(n.split()[0] for n, _ in ensemble_models)})"
        avg_rho = np.mean([s["spearman_r"] for s in ens_scores])
        avg_top = np.mean([s["top10_mean"] for s in ens_scores])
        avg_win = np.mean([s["top10_win"] for s in ens_scores])
        print(f"  {name_str:<18} SpearmanR={avg_rho:.3f}  Top10均值={avg_top:+.2f}%  "
              f"胜率={avg_win:.0f}%  RMSE={np.mean([s['rmse'] for s in ens_scores]):.2f}%")
        results.append({"name": name_str, "spearman_r": avg_rho, "top10_mean": avg_top,
                        "top10_win": avg_win, "scores": ens_scores, "elapsed": 0,
                        "model": _ensemble_predict})  # store predict fn as model

    # ── Summary ──
    print(f"\n{'='*80}")
    print(f"综合排名 (按 Top10均值收益)")
    print(f"{'='*80}")
    results.sort(key=lambda r: r["top10_mean"], reverse=True)
    print(f"{'模型':<25} {'SpearmanR':<10} {'Top10均值':<12} {'Top10胜率':<10} {'RMSE':<10} {'耗时':<8}")
    print(f"{'-'*75}")
    for i, r in enumerate(results, 1):
        marker = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        print(f"{marker} {r['name']:<23} {r['spearman_r']:.3f}{'':<5} "
              f"{r['top10_mean']:+.2f}%{'':<6} {r['top10_win']:.0f}%{'':<6} "
              f"{np.mean([s['rmse'] for s in r['scores']]):.2f}%{'':<4} {r['elapsed']:.0f}s")

    # ── Best model feature importance ──
    best = results[0]
    print(f"\n🏆 最优模型: {best['name']} (Top10均值={best['top10_mean']:+.2f}%)")

    # Save best model(s)
    os.makedirs(os.path.join(_PROJ, "outputs"), exist_ok=True)
    if "Ensemble" in best["name"]:
        # Save individual models for ensemble
        for ens_name, ens_model in ensemble_models:
            path = os.path.join(_PROJ, "outputs", f"cb_ml_{ens_name.split()[0].lower()}.pkl")
            with open(path, "wb") as f:
                pickle.dump({"model": ens_model, "name": ens_name,
                             "feature_cols": FEATURE_COLS}, f)
        print(f"Ensemble 已保存: {len(ensemble_models)} 个子模型 → outputs/cb_ml_*.pkl")
    else:
        best_path = os.path.join(_PROJ, "outputs", "cb_ml_best.pkl")
        with open(best_path, "wb") as f:
            pickle.dump({"model": best["model"], "name": best["name"],
                         "feature_cols": FEATURE_COLS}, f)
        print(f"已保存: {best_path}")

    # Also save results summary
    summary = [{"name": r["name"], "spearman_r": round(r["spearman_r"], 3),
                "top10_mean": round(r["top10_mean"], 2),
                "top10_win": round(r["top10_win"], 1)} for r in results]
    print(f"\n对比结果: {json.dumps(summary, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=35)
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()
    run_comparison(args.days, args.top_n)
