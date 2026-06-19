"""复权因子工具 — 对 daily_kline 做后复权修正.

后复权公式: adj_price = price × (latest_factor / on_date_factor)
确保历史价格与当前价格可比，消除除权除息导致的跳空。

Usage:
    from kronos_factors.scorer.adj_factor import get_adj_factor_map, apply_adj_to_kline
"""

import logging
import numpy as np

logger = logging.getLogger("kronos-factors.adj_factor")


def get_adj_factor_map(db) -> dict[str, float]:
    """获取每只股票的最新复权因子 (benchmark for 后复权).

    Returns: {code: latest_adj_factor}
    """
    try:
        rows = db.execute(
            "SELECT a.code, a.adj_factor FROM adj_factor a "
            "JOIN (SELECT code, MAX(trade_date) as max_date FROM adj_factor "
            "GROUP BY code) b ON a.code=b.code AND a.trade_date=b.max_date"
        ).fetchall()
        return {r["code"]: float(r["adj_factor"] or 1.0) for r in rows if r["adj_factor"]}
    except Exception as e:
        logger.debug("adj_factor lookup failed: %s", e)
        return {}


def apply_adj_to_kline(code: str, closes: np.ndarray, dates: list,
                       adj_map: dict[str, float], db=None) -> np.ndarray:
    """对收盘价序列做后复权修正.

    Args:
        code: 股票代码
        closes: 原始收盘价序列 (oldest first)
        dates: 对应日期序列 (YYYY-MM-DD 字符串)
        adj_map: {code: latest_factor} from get_adj_factor_map()
        db: optional DB connection for fallback factor lookup

    Returns: 复权后的收盘价 (same shape)
    """
    if code not in adj_map or len(closes) == 0:
        return closes

    latest_factor = adj_map[code]
    if latest_factor <= 0:
        return closes

    adj_closes = np.copy(closes).astype(np.float64)
    n = len(closes)

    # Try to get per-date adj factors for precise adjustment
    try:
        if db is not None and n > 0:
            date_list = "','".join(str(d) for d in dates[-n:])
            factors = db.execute(
                f"SELECT trade_date, adj_factor FROM adj_factor "
                f"WHERE code=? AND trade_date IN ('{date_list}')",
                (code,)
            ).fetchall()
            factor_dict = {str(r["trade_date"]): float(r["adj_factor"] or 1.0)
                          for r in factors if r["adj_factor"]}

            if factor_dict:
                for i in range(n):
                    d = str(dates[i])[:10]
                    date_factor = factor_dict.get(d, latest_factor)
                    if date_factor > 0:
                        adj_closes[i] = closes[i] * latest_factor / date_factor
                return adj_closes
    except Exception:
        pass

    # Fallback: use latest_factor as universal divisor (less precise)
    adj_closes = closes * latest_factor / latest_factor  # no-op without date-level data
    return closes  # return original if we can't get date-level factors


def apply_adj_to_df(df, code: str, adj_map: dict[str, float], db=None):
    """对 pandas DataFrame 的 OHLCV 做后复权 (in-place).

    DataFrame 需包含 columns: open, high, low, close 和 index (date).
    """
    if code not in adj_map or df is None or len(df) == 0:
        return df

    latest_factor = adj_map[code]
    if latest_factor <= 0:
        return df

    dates = df.index if hasattr(df, 'index') else df['trade_date']
    closes = df['close'].values
    n = len(closes)

    try:
        if db is not None:
            date_strs = [str(d)[:10] for d in dates]
            date_list = "','".join(date_strs)
            factors = db.execute(
                f"SELECT trade_date, adj_factor FROM adj_factor "
                f"WHERE code=? AND trade_date IN ('{date_list}')",
                (code,)
            ).fetchall()
            factor_dict = {str(r["trade_date"]): float(r["adj_factor"] or 1.0)
                          for r in factors if r["adj_factor"]}

            if factor_dict:
                ratios = np.ones(n, dtype=np.float64)
                for i in range(n):
                    d = date_strs[i]
                    df_val = factor_dict.get(d, latest_factor)
                    ratios[i] = latest_factor / df_val if df_val > 0 else 1.0

                for col in ['open', 'high', 'low', 'close']:
                    if col in df.columns:
                        df[col] = df[col].values * ratios
                return df
    except Exception as e:
        logger.debug("adj_factor apply_adj_to_df failed for %s: %s", code, e)

    return df
