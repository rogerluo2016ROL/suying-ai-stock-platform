from dataclasses import dataclass
from typing import Any, Callable, Protocol

from kronos_factors.evaluation.factor_ic import evaluate_factor_rows


@dataclass(frozen=True)
class BacktestRequest:
    model_key: str
    forward_days: int = 5
    cost_bps: float = 14.0
    min_periods: int = 20
    min_per_day: int = 30
    min_observations: int = 500
    connection_factory: Callable[[], Any] | None = None


def compute_adjusted_return(entry_open, entry_adj, exit_close, exit_adj, cost_bps):
    entry = float(entry_open) * float(entry_adj or 1)
    exit_value = float(exit_close) * float(exit_adj or 1)
    if entry <= 0:
        raise ValueError("entry adjusted open must be positive")
    return exit_value / entry - 1 - float(cost_bps) / 10000.0


def load_stock_factor_rows(connection, request: BacktestRequest):
    """Load T+1-open to future-close adjusted returns for saved snapshots."""
    sql = """
      SELECT s.trade_date, s.factors, e.open, e.adj_factor, x.close, x.adj_factor
      FROM screening_snapshots s
      JOIN LATERAL (
        SELECT k.trade_date, k.open, a.adj_factor
        FROM daily_kline k LEFT JOIN adj_factor a ON a.code=k.code AND a.trade_date=k.trade_date
        WHERE k.code=s.stock_code AND k.trade_date>s.trade_date AND k.open>0
        ORDER BY k.trade_date LIMIT 1
      ) e ON TRUE
      JOIN LATERAL (
        SELECT k.close, a.adj_factor
        FROM daily_kline k LEFT JOIN adj_factor a ON a.code=k.code AND a.trade_date=k.trade_date
        WHERE k.code=s.stock_code AND k.trade_date>=e.trade_date AND k.close>0
        ORDER BY k.trade_date OFFSET %s LIMIT 1
      ) x ON TRUE
      WHERE s.model_key=%s AND s.factors IS NOT NULL
      ORDER BY s.trade_date, s.stock_code
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, (request.forward_days - 1, request.model_key))
        return [
            {"trade_date": row[0], "factors": row[1],
             "future_return": compute_adjusted_return(row[2], row[3], row[4], row[5], request.cost_bps)}
            for row in cursor.fetchall() if row[2] is not None and row[4] is not None
        ]


def load_cb_factor_rows(connection, request: BacktestRequest):
    """Load convertible-bond T+1-open returns (CB prices need no equity adj factor)."""
    sql = """
      SELECT s.trade_date, s.factors, e.open, x.close
      FROM screening_snapshots s
      JOIN LATERAL (
        SELECT k.trade_date, k.open FROM cb_daily k
        WHERE k.ts_code=s.stock_code AND k.trade_date>s.trade_date AND k.open>0
        ORDER BY k.trade_date LIMIT 1
      ) e ON TRUE
      JOIN LATERAL (
        SELECT k.close FROM cb_daily k
        WHERE k.ts_code=s.stock_code AND k.trade_date>=e.trade_date AND k.close>0
        ORDER BY k.trade_date OFFSET %s LIMIT 1
      ) x ON TRUE
      WHERE s.model_key=%s AND s.factors IS NOT NULL
      ORDER BY s.trade_date, s.stock_code
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, (request.forward_days - 1, request.model_key))
        return [
            {"trade_date": row[0], "factors": row[1],
             "future_return": compute_adjusted_return(row[2], 1, row[3], 1, request.cost_bps)}
            for row in cursor.fetchall() if row[2] is not None and row[3] is not None
        ]


def evaluate_request(rows, request: BacktestRequest):
    return evaluate_factor_rows(
        rows, min_periods=request.min_periods, min_per_day=request.min_per_day,
        min_observations=request.min_observations,
    )

class BacktestAdapter(Protocol):
    model_key: str
    def run(self, request: BacktestRequest, readiness): ...
