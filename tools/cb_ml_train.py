#!/usr/bin/env python3
"""可转债日内 LightGBM 排序模型 — 替代线性加权评分.

用法:
  # 收集数据 + 训练 + 保存模型
  python3 tools/cb_ml_train.py --days 35 --top-n 30

  # 用已保存模型预测
  python3 tools/cb_ml_train.py --predict --top-n 10
"""

import argparse, os, sys, time, json, pickle
from collections import defaultdict
from datetime import date, datetime

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))
sys.path.insert(0, _PROJ)

import numpy as np
import psycopg2
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error

from tools.cb_intraday_exit import (estimate_cb_exit_price, find_exit_info,
    find_stop_loss, find_take_profit, check_entry_quality, find_trailing_stop,
    adaptive_take_profit_target)
from tools.cb_backtest_intraday import (get_trade_dates, load_stock_mins,
    get_cb_open_and_stock, get_stock_atr_pct)

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
MODEL_PATH = os.path.join(_PROJ, "outputs", "cb_ml_model.pkl")
FEATURE_COLS = [
    "sector_score", "premium_score", "momentum_score", "liquidity_score",
    "rev_bonus", "call_penalty",
    "premium_rate_raw", "yesterday_pct_raw", "amount_wan_raw",
    "remain_size_yi", "stock_atr_pct",
]


def collect_training_data(days_back: int = 35, top_n: int = 30) -> list[dict]:
    """收集特征和日内收益标签."""
    from kronos_factors.engine.cb_intraday import CbIntradayEngine

    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)
    print(f"采集 {len(trade_dates)} 个交易日数据...")

    all_samples = []

    for ti, td in enumerate(trade_dates):
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(trade_date=td, top_n=top_n)
        engine.close()
        if not picks:
            continue

        for p in picks:
            ts_code = p["code"]
            stk_code = p["stk_code"]
            d = p.get("details", {})

            # ── Get entry/exit data ──
            try:
                price_info = get_cb_open_and_stock(conn, ts_code, stk_code, td)
            except Exception:
                try: conn.rollback()
                except: pass
                continue

            cb_open = price_info["cb_open"]
            stock_open = price_info["stock_open"]
            if not cb_open or cb_open <= 0:
                continue

            bars = load_stock_mins(conn, stk_code, td)
            if len(bars) < 10:
                continue

            # Entry quality filter
            if not check_entry_quality(bars, min_bars=3):
                continue

            # Simulate exit
            stock_atr_pct = get_stock_atr_pct(conn, stk_code, td)
            try: conn.rollback()
            except: pass

            tp_target = adaptive_take_profit_target(stock_atr_pct)
            take_profit = find_take_profit(bars, cb_open, stock_open or 0, tp_target, skip_bars=3) if stock_open else None
            trailing_stop = find_trailing_stop(bars, pct_from_high=2.0, skip_bars=6)
            stop_loss = find_stop_loss(bars, below_vwap_minutes=45, skip_bars=6, min_pct_below=0.5)
            exit_info = find_exit_info(bars)
            if exit_info["signal"] and exit_info["signal"]["kdj_j"] <= 95:
                exit_info["signal"] = None

            if take_profit:
                sig = take_profit
            elif trailing_stop:
                sig = trailing_stop
            elif stop_loss:
                sig = stop_loss
            else:
                sig = exit_info["signal"]

            if sig:
                premium_rate = p.get("premium_rate")
                cb_exit = estimate_cb_exit_price(cb_open, stock_open or 0, sig["close"], premium_rate)
            else:
                cur = conn.cursor()
                cur.execute("SELECT close FROM cb_daily WHERE ts_code=%s AND trade_date=%s", (ts_code, td))
                row = cur.fetchone()
                cur.close()
                cb_exit = float(row[0]) if row and row[0] else cb_open

            intraday_ret = (cb_exit - cb_open) / cb_open * 100

            # ── Assemble features ──
            features = {
                "sector_score": d.get("sector_score", 50),
                "premium_score": d.get("premium_score", 50),
                "momentum_score": d.get("momentum_score", 50),
                "liquidity_score": d.get("liquidity_score", 50),
                "rev_bonus": d.get("rev_bonus", 0),
                "call_penalty": d.get("call_penalty", 0),
                "premium_rate_raw": p.get("premium_rate") or 0,
                "yesterday_pct_raw": p.get("yesterday_pct") or 0,
                "amount_wan_raw": (p.get("cb_amount_wan") or 0),
                "remain_size_yi": 0,  # not in current output, placeholder
                "stock_atr_pct": stock_atr_pct or 0,
            }

            all_samples.append({
                "date": td, "code": ts_code, "name": p.get("name"),
                "grade": p.get("grade"), "total_score": p.get("total_score"),
                "features": features,
                "intraday_return": round(intraday_ret, 4),
                "exit_method": sig.get("type", "close") if sig else "close",
            })

        if (ti + 1) % 10 == 0:
            print(f"  {ti+1}/{len(trade_dates)} dates, {len(all_samples)} samples")

    conn.close()
    print(f"采集完成: {len(all_samples)} 样本, {len(set(s['date'] for s in all_samples))} 天")
    return all_samples


def train_model(samples: list[dict]) -> dict:
    """训练 LightGBM 排序模型."""
    X = np.array([[s["features"][f] for f in FEATURE_COLS] for s in samples], dtype=np.float32)
    y = np.array([s["intraday_return"] for s in samples], dtype=np.float32)

    # Remove extreme outliers (>5 sigma)
    mean_y, std_y = y.mean(), y.std()
    mask = np.abs(y - mean_y) < 5 * std_y
    X, y = X[mask], y[mask]
    samples = [s for s, m in zip(samples, mask) if m]
    print(f"特征矩阵: {X.shape}, 标签均值={y.mean():.2f}% 标准差={y.std():.2f}%")

    # TimeSeriesSplit for realistic evaluation
    tscv = TimeSeriesSplit(n_splits=5)
    scores = []

    params = {
        'objective': 'regression',
        'metric': 'rmse',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'min_data_in_leaf': 20,
        'verbose': -1,
        'random_state': 42,
    }

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model = lgb.train(params, lgb.Dataset(X_train, y_train),
                          num_boost_round=200,
                          valid_sets=[lgb.Dataset(X_val, y_val)],
                          callbacks=[lgb.early_stopping(10), lgb.log_evaluation(0)])

        y_pred = model.predict(X_val)
        rmse = np.sqrt(mean_squared_error(y_val, y_pred))
        mae = mean_absolute_error(y_val, y_pred)
        # Spearman rank correlation (for ranking quality)
        from scipy.stats import spearmanr
        rho, _ = spearmanr(y_val, y_pred)
        scores.append({"rmse": rmse, "mae": mae, "spearman_r": rho})
        print(f"  Fold {fold+1}: RMSE={rmse:.2f}% MAE={mae:.2f}% SpearmanR={rho:.3f}")

    # ── Train final model on all data ──
    final_model = lgb.train(params, lgb.Dataset(X, y), num_boost_round=150)

    # Feature importance
    importance = dict(zip(FEATURE_COLS, final_model.feature_importance(importance_type='gain')))
    importance = {k: round(v / max(importance.values()) * 100, 1) for k, v in
                  sorted(importance.items(), key=lambda x: x[1], reverse=True)}

    print(f"\n特征重要性 (gain, normalized):")
    for feat, imp in importance.items():
        print(f"  {feat}: {imp}%")

    return {
        "model": final_model,
        "feature_cols": FEATURE_COLS,
        "importance": importance,
        "cv_scores": scores,
        "n_samples": len(samples),
    }


def predict_with_model(model_info: dict, picks: list[dict], atr_map: dict = None) -> list[dict]:
    """用 ML 模型对选股结果重新打分排序."""
    model = model_info["model"]
    feature_cols = model_info["feature_cols"]

    for p in picks:
        d = p.get("details", {})
        features = [
            d.get("sector_score", 50),
            d.get("premium_score", 50),
            d.get("momentum_score", 50),
            d.get("liquidity_score", 50),
            d.get("rev_bonus", 0),
            d.get("call_penalty", 0),
            p.get("premium_rate") or 0,
            p.get("yesterday_pct") or 0,
            p.get("cb_amount_wan") or 0,
            0,  # remain_size_yi placeholder
            (atr_map or {}).get(p.get("stk_code", "")) or 0,
        ]
        X = np.array([features], dtype=np.float32)
        p["ml_score"] = float(model.predict(X)[0])

    # Re-rank by ML score
    picks.sort(key=lambda x: x.get("ml_score", 0), reverse=True)
    return picks


def compare_linear_vs_ml(samples: list[dict], model_info: dict) -> dict:
    """对比线性评分 vs ML 评分的排序效果."""
    # Group by date, rank by each method, compare top-N returns
    date_groups = defaultdict(list)
    for s in samples:
        date_groups[s["date"]].append(s)

    linear_rets = []
    ml_rets = []
    X_all = np.array([[s["features"][f] for f in FEATURE_COLS] for s in samples], dtype=np.float32)
    ml_scores = model_info["model"].predict(X_all)
    for i, s in enumerate(samples):
        s["ml_score"] = float(ml_scores[i])

    for td, items in date_groups.items():
        if len(items) < 10:
            continue
        # Linear ranking (by total_score)
        linear_ranked = sorted(items, key=lambda x: x["total_score"] or 0, reverse=True)[:10]
        linear_rets.extend(s["intraday_return"] for s in linear_ranked)

        # ML ranking
        ml_ranked = sorted(items, key=lambda x: x.get("ml_score", 0), reverse=True)[:10]
        ml_rets.extend(s["intraday_return"] for s in ml_ranked)

    def _s(name, vals):
        return f"{name}: mean={np.mean(vals):+.2f}% win={sum(1 for v in vals if v>0)/len(vals)*100:.1f}% n={len(vals)}"

    print(f"\n线性 vs ML 排序对比 (Top 10 per day):")
    print(f"  {_s('线性评分', linear_rets)}")
    print(f"  {_s('ML 评分 ', ml_rets)}")
    improvement = (np.mean(ml_rets) - np.mean(linear_rets)) / abs(np.mean(linear_rets)) * 100 if np.mean(linear_rets) != 0 else 0
    print(f"  ML提升: {improvement:+.1f}%")

    return {"linear": linear_rets, "ml": ml_rets}


# ── CLI ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CB ML ranking model")
    parser.add_argument("--days", type=int, default=35, help="采集数据天数")
    parser.add_argument("--top-n", type=int, default=30, help="每期采集 pick 数")
    parser.add_argument("--predict", action="store_true", help="用已保存模型预测")
    parser.add_argument("--compare", action="store_true", help="对比线性 vs ML")
    args = parser.parse_args()

    if args.predict:
        # ── Live prediction ──
        if not os.path.exists(MODEL_PATH):
            print(f"模型不存在: {MODEL_PATH}, 请先训练")
            sys.exit(1)

        with open(MODEL_PATH, "rb") as f:
            model_info = pickle.load(f)

        from kronos_factors.engine.cb_intraday import CbIntradayEngine
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(top_n=args.top_n)
        engine.close()

        conn = psycopg2.connect(PG_URL)
        atr_map = {}
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM cb_daily")
        effective_date = str(cur.fetchone()[0])
        for p in picks:
            stk = p.get("stk_code", "")
            if stk:
                atr_map[stk] = get_stock_atr_pct(conn, stk, effective_date)
        conn.close()

        ranked = predict_with_model(model_info, picks, atr_map)
        print(f"\n{'='*80}")
        print(f"ML 排序结果 (Top {min(args.top_n, len(ranked))})")
        print(f"{'='*80}")
        print(f"{'#':<3} {'转债':<12} {'正股':<7} {'线性分':<6} {'ML分':<8} {'等级':<4}")
        for i, p in enumerate(ranked[:args.top_n], 1):
            print(f"{i:<3} {p['name']:<12} {p['stk_code']:<7} "
                  f"{p.get('total_score',0):<6.1f} {p.get('ml_score',0):<8.2f} {p.get('grade',''):<4}")

        # Feature importance
        print(f"\n特征重要性:")
        for feat, imp in model_info["importance"].items():
            bar = '█' * int(imp / 5)
            print(f"  {feat}: {bar} {imp}%")

    elif args.compare:
        # ── Collect + train + compare ──
        samples = collect_training_data(args.days, args.top_n)
        model_info = train_model(samples)
        compare_linear_vs_ml(samples, model_info)

        # Save
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        save_info = {k: v for k, v in model_info.items() if k != "model"}
        save_info["model"] = model_info["model"]
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(save_info, f)
        print(f"\n模型已保存: {MODEL_PATH}")

    else:
        # Default: train + save
        samples = collect_training_data(args.days, args.top_n)
        model_info = train_model(samples)
        compare_linear_vs_ml(samples, model_info)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        save_info = {k: v for k, v in model_info.items() if k != "model"}
        save_info["model"] = model_info["model"]
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(save_info, f)
        print(f"\n模型已保存: {MODEL_PATH}")
