"""Unit tests for M06 (audit-model-2026-06-22): training group split 无横截面泄露.

验证 training_engine._group_split_masks:
  1. train / val 无任何同日样本跨集 (横截面泄露断言)
  2. val 起点在 train 之后连续日期段 (时间顺序)
  3. horizon embargo gap 生效 (split 与 val 之间有 purge 区间)

位于 services/training-service/tests/, 由本目录 conftest.py 把 training-service
目录加入 sys.path, 直接 ``from app.training_engine import ...``. 不再用
sys.path.insert + sys.modules.pop("app") hack (W-1, ML-P0 review).

Run: cd services/training-service && pytest tests/test_group_split.py -v
"""
import numpy as np
import pandas as pd
import pytest

from app.training_engine import _group_split_masks


def _make_train_df(n_dates=60, n_stocks=10):
    """构造 n_dates 个日期 × n_stocks 只股票的训练样本 DataFrame."""
    rows = []
    for d in range(n_dates):
        date = f"2024-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}"
        for s in range(n_stocks):
            rows.append({
                "date": date,
                "code": f"00000{s}",
                "momentum": float(np.random.normal(5, 2)),
                "ret_5d": float(np.random.normal(0, 3)),
            })
    return pd.DataFrame(rows)


def test_group_split_no_same_date_across_sets():
    """M06 核心: train/val 不能有任何重叠日期 (横截面泄露断言)."""
    df = _make_train_df(n_dates=60, n_stocks=10)
    train_mask, val_mask = _group_split_masks(df, test_size=0.2, horizon=5)
    train_dates = set(df.loc[train_mask, "date"].unique())
    val_dates = set(df.loc[val_mask, "date"].unique())
    overlap = train_dates & val_dates
    assert overlap == set(), f"train/val 重叠日期: {sorted(overlap)[:5]}"


def test_group_split_val_after_train_chronologically():
    """M06: val 的所有日期都严格晚于 train 的所有日期."""
    df = _make_train_df(n_dates=60, n_stocks=5)
    train_mask, val_mask = _group_split_masks(df, test_size=0.2, horizon=5)
    train_max = df.loc[train_mask, "date"].max()
    val_min = df.loc[val_mask, "date"].min()
    assert val_min > train_max, f"val_min={val_min} 不晚于 train_max={train_max}"


def test_group_split_embargo_gap_present():
    """M06: split 与 val 之间有 embargo (purge) 区间被丢弃."""
    df = _make_train_df(n_dates=60, n_stocks=5)
    horizon = 10
    train_mask, val_mask = _group_split_masks(df, test_size=0.2, horizon=horizon)
    dates = sorted(df["date"].unique())
    split_idx = int(len(dates) * (1 - 0.2))
    split_date = dates[split_idx]
    train_max = df.loc[train_mask, "date"].max()
    val_min = df.loc[val_mask, "date"].min()
    assert train_max < split_date
    assert val_min >= split_date
    purged = [d for d in dates if train_max < d < val_min]
    assert len(purged) >= 1, f"embargo/purge 区间为空, train_max={train_max} val_min={val_min}"


def test_group_split_raises_on_too_few_dates():
    """M06: 日期太少时应抛 ValueError."""
    df = _make_train_df(n_dates=3, n_stocks=2)
    with pytest.raises(ValueError):
        _group_split_masks(df, test_size=0.2, horizon=5)
