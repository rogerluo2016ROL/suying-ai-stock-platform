"""Settlement report store for strategy-service.

A plan is considered settled when a SettlementRecord exists for it (in
PostgreSQL or the in-memory fallback store), or its status is one of
SETTLED_STATUSES (settled/closed) — the latter path produces a deterministic
mock report so the preview page renders end-to-end until a real settlement
producer lands.

TODO(settlement-producer): add the `plan_settlements` migration under
services/sql/ and have the plan-settlement job write records via record();
the PG read path below already targets that table and fails safe to the
in-memory store when the table does not exist yet.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLE_PLAN_SETTLEMENTS = "plan_settlements"

# Plan statuses that count as "已结算" even when no SettlementRecord is found.
SETTLED_STATUSES = ("settled", "closed")


@dataclass
class SettlementRecord:
    plan_id: str
    settled_at: str                       # ISO date, e.g. "2026-06-25"
    period: dict                          # {"start_date","end_date","holding_days"}
    summary: dict                         # see build_settlement_report() for keys
    trades: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    stocks: list[dict] = field(default_factory=list)
    daily_returns: list[dict] = field(default_factory=list)


class SettlementStore:
    """In-memory fallback, mirroring PlanStore semantics."""

    def __init__(self):
        self._records: dict[str, SettlementRecord] = {}
        self._lock = threading.Lock()

    def record(self, record: SettlementRecord) -> SettlementRecord:
        with self._lock:
            self._records[record.plan_id] = record
            return record

    def get(self, plan_id: str) -> SettlementRecord | None:
        return self._records.get(plan_id)

    def delete(self, plan_id: str) -> bool:
        with self._lock:
            if plan_id in self._records:
                del self._records[plan_id]
                return True
            return False


_store = SettlementStore()


def get_settlement_store() -> SettlementStore:
    return _store


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value or json.dumps(default, ensure_ascii=False))


# 表是否缺失的进程级缓存（#5）：探测一次后短路，避免每次 pg_get 都触发
# UndefinedTable → 被路由 safe wrapper 捕获 → WARNING 日志噪声。迁移落地（services/sql/
# 建 plan_settlements）后进程重启即自动探测到存在、恢复 PG 读路径。
_table_missing_cached: bool | None = None


async def pg_get(db: AsyncSession, plan_id: str) -> SettlementRecord | None:
    """Read a settlement record from PostgreSQL.

    The `plan_settlements` table is not migrated yet (see module TODO); probe
    once and cache "missing" so repeated calls short-circuit to None instead of
    raising UndefinedTable + WARNING on every /settlement-report (review #5).
    """
    global _table_missing_cached
    if _table_missing_cached is None:
        try:
            present = (
                await db.execute(
                    text("SELECT to_regclass(:t) IS NOT NULL"),
                    {"t": TABLE_PLAN_SETTLEMENTS},
                )
            ).scalar()
            _table_missing_cached = not present
        except Exception:
            _table_missing_cached = False  # 探测失败不缓存，保留原 fail-safe 路径
    if _table_missing_cached:
        return None

    result = await db.execute(
        text(
            """
            SELECT plan_id, settled_at, period, summary, trades, positions,
                   stocks, daily_returns
            FROM plan_settlements
            WHERE plan_id = :plan_id
            """
        ),
        {"plan_id": plan_id},
    )
    row = result.fetchone()
    if not row:
        return None
    settled_at = row[1]
    return SettlementRecord(
        plan_id=row[0],
        settled_at=settled_at.isoformat() if hasattr(settled_at, "isoformat") else settled_at,
        period=_json(row[2], {}),
        summary=_json(row[3], {}),
        trades=_json(row[4], []),
        positions=_json(row[5], {}),
        stocks=_json(row[6], []),
        daily_returns=_json(row[7], []),
    )


# ── Report assembly ──────────────────────────────────────────────────────────


def build_settlement_report(
    *,
    plan_id: str,
    plan_name: str,
    capital: float,
    picks: list[dict],
    record: SettlementRecord | None,
    source: str,
) -> dict:
    """Assemble the settlement-report response body.

    When a real SettlementRecord exists its fields are used verbatim; summary
    keys the settlement producer has not filled yet fall back to deterministic
    mocks (see TODO markers). When no record exists at all the whole report is
    mocked from the plan picks.
    """
    if record is None:
        record = _mock_record(plan_id=plan_id, capital=capital, picks=picks)
        source = "mock"

    summary = dict(record.summary)
    # TODO(settlement-producer): annualized_return / profit_loss_ratio /
    # sharpe_ratio are mocked until the producer computes them from real
    # trade fills and daily equity.
    defaults = _mock_summary_defaults(plan_id=plan_id, period=record.period)
    for key, value in defaults.items():
        summary.setdefault(key, value)

    return {
        "plan_id": plan_id,
        "plan_name": plan_name,
        "settlement_date": record.settled_at,
        "period": {
            "start_date": record.period.get("start_date"),
            "end_date": record.period.get("end_date"),
            "holding_days": record.period.get("holding_days"),
        },
        "summary": summary,
        "trades": record.trades,
        "positions": record.positions,
        "stocks": record.stocks,
        "daily_returns": record.daily_returns,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": source,
    }


def _rng(plan_id: str) -> random.Random:
    seed = int(hashlib.md5(plan_id.encode("utf-8")).hexdigest()[:8], 16)
    return random.Random(seed)


def _mock_summary_defaults(*, plan_id: str, period: dict) -> dict:
    """TODO(settlement-producer): deterministic stand-ins for unfilled keys."""
    rng = _rng(plan_id)
    holding_days = period.get("holding_days") or 5
    total_pnl_pct = round(rng.uniform(-0.06, 0.12), 4)
    return {
        "total_pnl_pct": total_pnl_pct,
        "annualized_return": round(total_pnl_pct * 365 / holding_days, 4),
        "max_drawdown": round(-rng.uniform(0.01, 0.06), 4),
        "win_rate": round(rng.uniform(0.4, 0.9), 4),
        "profit_loss_ratio": round(rng.uniform(1.0, 2.5), 2),
        "sharpe_ratio": round(rng.uniform(0.5, 2.5), 2),
    }


def _mock_record(*, plan_id: str, capital: float, picks: list[dict]) -> SettlementRecord:
    """TODO(settlement-producer): mock settlement derived from plan picks.

    Deterministic per plan_id so repeated calls render the same report.
    """
    rng = _rng(plan_id)
    settled_at = datetime.now(timezone.utc).date().isoformat()
    holding_days = rng.randint(3, 15)
    start_date = (
        datetime.fromisoformat(settled_at) - timedelta(days=holding_days)
    ).date().isoformat()

    picks = picks or [{"code": "MOCK000", "name": "模拟标的", "price": 10.0}]
    trades: list[dict] = []
    stocks: list[dict] = []
    positions: list[dict] = []
    total_pnl = 0.0
    win_count = 0

    for idx, pick in enumerate(picks):
        price = float(pick.get("price") or 10.0)
        qty = max(int(capital * 0.2 / price / 100) * 100, 100)
        buy_price = round(price * 0.97, 2)
        sell_price = round(price * (1 + rng.uniform(-0.05, 0.12)), 2)
        pnl = round((sell_price - buy_price) * qty, 2)
        pnl_pct = round((sell_price - buy_price) / buy_price, 4)
        total_pnl += pnl
        if pnl > 0:
            win_count += 1
        code = pick.get("code", f"MOCK{idx:03d}")
        name = pick.get("name", "")
        trades.append({
            "time": f"{start_date}T09:35:00+00:00",
            "code": code, "name": name,
            "direction": "buy", "qty": qty, "price": buy_price, "pnl": 0.0,
        })
        trades.append({
            "time": f"{settled_at}T14:55:00+00:00",
            "code": code, "name": name,
            "direction": "sell", "qty": qty, "price": sell_price, "pnl": pnl,
        })
        stocks.append({
            "code": code, "name": name, "direction": "buy",
            "avg_buy_price": buy_price, "avg_sell_price": sell_price,
            "qty": qty, "pnl": pnl, "pnl_pct": pnl_pct,
        })

    # TODO(settlement-producer): mock a residual holding so the positions
    # section renders; real records come from the settlement-time snapshot.
    first = picks[0]
    hold_price = float(first.get("price") or 10.0)
    hold_qty = 100
    positions.append({
        "code": first.get("code", "MOCK000"), "name": first.get("name", ""),
        "qty": hold_qty, "avg_cost": round(hold_price * 0.99, 2),
        "close_price": hold_price,
        "market_value": round(hold_price * hold_qty, 2),
        "pnl": round(hold_price * 0.01 * hold_qty, 2),
        "pnl_pct": 0.0101,
    })

    stocks.sort(key=lambda s: s["pnl"], reverse=True)
    daily_returns = [
        {"date": (datetime.fromisoformat(start_date) + timedelta(days=i)).date().isoformat(),
         "cumulative_return": round((total_pnl / capital) * (i + 1) / (holding_days + 1), 4)}
        for i in range(holding_days + 1)
    ]

    return SettlementRecord(
        plan_id=plan_id,
        settled_at=settled_at,
        period={"start_date": start_date, "end_date": settled_at, "holding_days": holding_days},
        summary={
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / capital, 4),
            "win_rate": round(win_count / len(stocks), 4) if stocks else 0.0,
            "win_count": win_count,
            "total_stock_count": len(stocks),
            "trade_count": len(trades),
        },
        trades=trades,
        positions=positions,
        stocks=stocks,
        daily_returns=daily_returns,
    )
