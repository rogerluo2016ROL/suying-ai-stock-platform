#!/usr/bin/env python3
"""拥挤度 (crowding) → 回撤预警 因子.

目的
----
度量单只个股当下的"交易拥挤程度", 在拥挤极端时预警潜在回撤风险.
与 bi_alpha_v15 的"低换手反转"互补 —— 这里关心"高换手/高估值/放量/急涨/
主力涌入"的极端, 即 cerebrum 记录的"极端值反转"风险 (机构活跃度 Top 组
年化 -52% 的同源教训: 极端拥挤 → 短期高点 → 回撤).

方向纪律: 拥挤度是"极端反转"型因子 —— 高拥挤 → 预期回撤 (回避/减仓方向),
**不是做多信号**. 回测判定必须看分组方向 (高拥挤组的未来回撤 vs 低拥挤组),
不能只看 IC (IC 有欺骗性, 见 cerebrum `backtest_institutional_activity` 教训).

设计
----
1. 单股取过去 ~250 交易日 6 成分: 自由流通换手率 / 成交额 / 量比 / PB /
   20日涨幅 / 主力净流入 (moneyflow.net_mf_amount).
2. 每成分算"当日值在自身历史的时序滚动分位" (0-1, 高=拥挤).
3. 等权合成 CI (有效成分等权, 缺失剔除, 至少 3 个有效).
4. CI → level: high(>0.90) / medium(>0.80) / low.

数据约定 (与 bi_alpha_v15 / leader 引擎一致)
----
- 走 kronos-factors DB adapter (PG-first, _get_db), 列名用 engine/SQLite 命名
  (code / trade_date / turnover_rate_f / volume_ratio / pb / amount / close /
   net_mf_amount), pg_adapter 透明转换 PG 列名 (pct_chg/change_pct 等).
- ⚠️ 换手率用 daily_basic.turnover_rate_f, **不用** daily_kline.turnover_rate
   (688 有 36% NULL).
- ⚠️ 涨幅用 close 自算, **不用** daily_kline.change_pct (688 仅 64% 有效).
- ⚠️ **不用** 北向个股 (hk_holdings) —— 2024-08 交易所停止披露 (见 cerebrum).
- moneyflow (主力资金) 同步到最新可用; 融资融券/股东户数滞后 ~3周, 暂不进主公式.

纪律
----
- 权重起步等权; 跑通后按 walk_forward 样本外 (IC + 分组方向) 校准, 对齐
  bi_alpha_v15 ICIR 纪律. 任何"有效"声明必须过 tools/walk_forward.py
  --strict-timeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────
# 参数 (起步值, 待 walk_forward 样本外校准)
# ─────────────────────────────────────────────────────────────────
LOOKBACK_DEFAULT = 250          # ~1 年交易日
HIGH_THRESHOLD = 0.90           # CI > 此值 → high
MEDIUM_THRESHOLD = 0.80         # CI > 此值 → medium
RET20_EXTREME_PCTL = 0.95       # 20日涨幅分位 > 此值 → 直接 high (对齐 screening_scorers 超买)
MIN_VALID_COMPONENTS = 3        # 至少 N 个有效成分才算 CI

COMPONENTS = ("turnover", "amount", "vol_ratio", "pb", "ret20", "main_flow")


# ─────────────────────────────────────────────────────────────────
# 纯逻辑 (便于单测, 无 DB 依赖)
# ─────────────────────────────────────────────────────────────────
def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return bool(np.isnan(v))
    except (TypeError, ValueError):
        return False


def rolling_pctile(history, current):
    """current 在 history (不含当日) + [current] 序列里的时序分位 (0-1).

    高 = 当日值相对自身历史更极端. 缺失或历史不足返回 None.
    """
    if _is_missing(current):
        return None
    arr = [v for v in history if not _is_missing(v)]
    arr.append(current)
    if len(arr) < 2:
        return None
    s = pd.Series(arr, dtype="float64")
    rank = s.rank().iloc[-1]  # average rank, 1..N
    # (rank-1)/(N-1): 对齐 bi_alpha_v15._pctile_ranks 口径, 最小=0 / 最大=1
    return float((rank - 1) / max(1, len(s) - 1))


def compute_ci(factor_pctls: dict) -> float | None:
    """等权合成 CI. factor_pctls: {component: pctl or None}.

    有效成分等权; 缺失剔除; 有效 < MIN_VALID_COMPONENTS 返回 None.
    """
    valid = [p for p in factor_pctls.values() if p is not None]
    if len(valid) < MIN_VALID_COMPONENTS:
        return None
    return float(np.mean(valid))


def ci_to_level(ci, ret20_pct=None) -> str:
    """CI → high/medium/low. ret20 分位极端 (>0.95) 直接升 high."""
    if ci is None:
        return "low"
    if ret20_pct is not None and ret20_pct > RET20_EXTREME_PCTL:
        return "high"
    if ci > HIGH_THRESHOLD:
        return "high"
    if ci > MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────
# DB 访问
# ─────────────────────────────────────────────────────────────────
def _load_history(db, code, trade_date, lookback):
    """取该股 daily_basic + daily_kline + moneyflow 历史.

    返回 {component: (history_list, current_value)}, 各序列按 trade_date DESC
    (index 0 = 当日 trade_date).
    """
    db_rows = db.execute(
        "SELECT trade_date, turnover_rate_f, volume_ratio, pb FROM daily_basic "
        "WHERE code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT ?",
        (code, trade_date, lookback + 5),
    ).fetchall()
    kl_rows = db.execute(
        "SELECT trade_date, amount, close FROM daily_kline "
        "WHERE code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT ?",
        (code, trade_date, lookback + 25),
    ).fetchall()
    mf_rows = db.execute(
        "SELECT trade_date, net_mf_amount FROM moneyflow "
        "WHERE code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT ?",
        (code, trade_date, lookback + 5),
    ).fetchall()

    def split(rows, key):
        if not rows:
            return [], None
        return [r[key] for r in rows[1:]], rows[0][key]

    t_hist, t_cur = split(db_rows, "turnover_rate_f")
    v_hist, v_cur = split(db_rows, "volume_ratio")
    pb_hist, pb_cur = split(db_rows, "pb")
    amt_hist, amt_cur = split(kl_rows, "amount")
    mf_hist, mf_cur = split(mf_rows, "net_mf_amount")

    # ret20: 按 trade_date DESC, closes[0]=当日; 当日 ret20 = closes[0]/closes[20]-1
    closes = [r["close"] for r in kl_rows if not _is_missing(r["close"])]
    ret20_cur = None
    ret20_hist = []
    if len(closes) >= 21:
        ret20_cur = closes[0] / closes[20] - 1
        ret20_hist = [closes[i] / closes[i + 20] - 1 for i in range(1, len(closes) - 20)]

    return {
        "turnover": (t_hist, t_cur),
        "amount": (amt_hist, amt_cur),
        "vol_ratio": (v_hist, v_cur),
        "pb": (pb_hist, pb_cur),
        "ret20": (ret20_hist, ret20_cur),
        "main_flow": (mf_hist, mf_cur),
    }


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────
def compute_crowding_risk(db, code, trade_date, lookback=LOOKBACK_DEFAULT) -> dict:
    """计算单股拥挤度风险.

    Returns:
        {
          "level": "high"|"medium"|"low",
          "ci_score": float | None,            # 0-1, 越高越拥挤
          "factor_pctl": {component: float},   # 各成分时序分位
          "flags": [str],                       # 极端成分标签, 如 "turnover_extreme"
          "rationale": str,
        }
    """
    hist = _load_history(db, code, trade_date, lookback)
    pctls = {comp: rolling_pctile(hist[comp][0], hist[comp][1]) for comp in COMPONENTS}

    ci = compute_ci(pctls)
    ret20_p = pctls.get("ret20")
    level = ci_to_level(ci, ret20_pct=ret20_p)

    flags = [f"{comp}_extreme" for comp, p in pctls.items()
             if p is not None and p > HIGH_THRESHOLD]

    return {
        "level": level,
        "ci_score": round(ci, 4) if ci is not None else None,
        "factor_pctl": {k: round(v, 3) for k, v in pctls.items() if v is not None},
        "flags": flags,
        "rationale": _build_rationale(level, ci, pctls),
    }


def _build_rationale(level, ci, pctls) -> str:
    if ci is None:
        return "数据不足, 无法计算拥挤度"
    extreme = [k for k, p in pctls.items() if p is not None and p > HIGH_THRESHOLD]
    head = f"拥挤度{level.upper()}(CI={ci:.2f})"
    return head + (f": {'/'.join(extreme)} 处于历史极端" if extreme else "")


# ─────────────────────────────────────────────────────────────────
# 批量扫描 (全市场/板块, 盘后预警用)
# ─────────────────────────────────────────────────────────────────
def scan_crowding(db, trade_date, board="688", lookback=LOOKBACK_DEFAULT, min_level="medium"):
    """扫描指定板块当日拥挤度, 返回达 min_level 及以上的票 (按 ci_score 降序).

    批量向量化 (pandas groupby + rolling.rank), 一次算全市场, 适合盘后扫描.
    与 compute_crowding_risk (单股) 口径一致 (同成分/阈值), 区别只在批量.

    Args:
        db: kronos DB adapter.
        trade_date: 'YYYY-MM-DD'.
        board: '688' 科创板 | 'all' 全市场.
        min_level: 'high' 只返 high; 'medium' 返 medium+high.

    Returns:
        [{code, level, ci_score, is_kechuang, factor_pctl}, ...] 按 ci_score 降序.
    """
    import datetime as _dt
    if board == "688":
        rows = db.execute("SELECT code FROM stocks WHERE board='科创板' AND is_st=0").fetchall()
    else:
        rows = db.execute("SELECT code FROM stocks WHERE is_st=0").fetchall()
    codes = [r["code"] for r in rows]
    if not codes:
        return []

    td = _dt.datetime.strptime(trade_date[:10], "%Y-%m-%d")
    start = (td - _dt.timedelta(days=int(lookback * 1.6))).strftime("%Y-%m-%d")
    basic = db.execute(
        "SELECT code, trade_date, turnover_rate_f, volume_ratio, pb FROM daily_basic "
        "WHERE trade_date BETWEEN ? AND ?", (start, trade_date)).fetchall()
    kline = db.execute(
        "SELECT code, trade_date, amount, close FROM daily_kline "
        "WHERE trade_date BETWEEN ? AND ?", (start, trade_date)).fetchall()
    mf = db.execute(
        "SELECT code, trade_date, net_mf_amount FROM moneyflow "
        "WHERE trade_date BETWEEN ? AND ?", (start, trade_date)).fetchall()
    bdf, kdf, mdf = pd.DataFrame(basic), pd.DataFrame(kline), pd.DataFrame(mf)
    if bdf.empty and kdf.empty:
        return []
    for d in (bdf, kdf, mdf):
        if not d.empty:
            d["trade_date"] = pd.to_datetime(d["trade_date"])
    panel = (bdf.merge(kdf, on=["code", "trade_date"], how="outer")
                .merge(mdf, on=["code", "trade_date"], how="outer"))
    panel = panel[panel["code"].isin(codes)].sort_values(["code", "trade_date"])

    g = panel.groupby("code", group_keys=False)

    def _rp(s):
        return s.rolling(lookback, min_periods=max(20, lookback // 2)).rank(pct=True)

    panel["turnover_pct"] = g["turnover_rate_f"].transform(_rp)
    panel["amount_pct"] = g["amount"].transform(_rp)
    panel["vol_ratio_pct"] = g["volume_ratio"].transform(_rp)
    panel["pb_pct"] = g["pb"].transform(_rp)
    panel["main_flow_pct"] = g["net_mf_amount"].transform(_rp)
    panel["ret20"] = g["close"].transform(lambda s: s.pct_change(20))
    panel["ret20_pct"] = g["ret20"].transform(_rp)
    cols = ["turnover_pct", "amount_pct", "vol_ratio_pct", "pb_pct", "ret20_pct", "main_flow_pct"]
    panel["ci_score"] = panel[cols].mean(axis=1, skipna=True)
    valid_cnt = panel[cols].notna().sum(axis=1)
    panel.loc[valid_cnt < MIN_VALID_COMPONENTS, "ci_score"] = float("nan")
    panel["level"] = "low"
    panel.loc[panel["ci_score"] > MEDIUM_THRESHOLD, "level"] = "medium"
    panel.loc[panel["ci_score"] > HIGH_THRESHOLD, "level"] = "high"
    panel.loc[panel["ret20_pct"] > RET20_EXTREME_PCTL, "level"] = "high"
    panel.loc[panel["ci_score"].isna(), "level"] = "low"

    day = pd.Timestamp(trade_date[:10])
    day_panel = panel[panel["trade_date"] == day]
    sel_levels = ["high"] if min_level == "high" else ["high", "medium"]
    sel = day_panel[day_panel["level"].isin(sel_levels)].sort_values("ci_score", ascending=False)

    out = []
    for _, r in sel.iterrows():
        out.append({
            "code": r["code"],
            "level": r["level"],
            "ci_score": round(float(r["ci_score"]), 4) if pd.notna(r["ci_score"]) else None,
            "is_kechuang": str(r["code"]).startswith("688"),
            "factor_pctl": {c: round(float(r[c]), 3) for c in cols if pd.notna(r[c])},
        })
    return out
