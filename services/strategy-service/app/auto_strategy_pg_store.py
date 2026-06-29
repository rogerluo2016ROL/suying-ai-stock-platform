"""PostgreSQL persistence for auto-trading strategy configs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auto_trading_engine import (
    BuyCondition,
    PositionRule,
    RiskRule,
    SellCondition,
    StrategyConfig,
)

TABLE_AUTO_STRATEGIES = "auto_trading_strategies"


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _condition_rows(conditions: list[BuyCondition] | list[SellCondition]) -> list[dict[str, Any]]:
    return [
        {
            "field": item.field,
            "operator": item.operator,
            "threshold": item.threshold,
            "description": item.description,
        }
        for item in conditions
    ]


async def record(db: AsyncSession, *, strategy: StrategyConfig) -> None:
    data = strategy.to_dict()
    await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_AUTO_STRATEGIES}
                (strategy_id, name, description, status, source_type, source_scheme_id,
                 buy_conditions, sell_conditions, position_rules, risk_rules,
                 trade_mode, check_interval_sec, capital, picks, created_at, updated_at)
            VALUES
                (:strategy_id, :name, :description, :status, :source_type, :source_scheme_id,
                 CAST(:buy_conditions AS jsonb), CAST(:sell_conditions AS jsonb),
                 CAST(:position_rules AS jsonb), CAST(:risk_rules AS jsonb),
                 :trade_mode, :check_interval_sec, :capital, CAST(:picks AS jsonb),
                 COALESCE(NULLIF(:created_at, '')::timestamptz, now()),
                 COALESCE(NULLIF(:updated_at, '')::timestamptz, now()))
            ON CONFLICT (strategy_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                source_type = EXCLUDED.source_type,
                source_scheme_id = EXCLUDED.source_scheme_id,
                buy_conditions = EXCLUDED.buy_conditions,
                sell_conditions = EXCLUDED.sell_conditions,
                position_rules = EXCLUDED.position_rules,
                risk_rules = EXCLUDED.risk_rules,
                trade_mode = EXCLUDED.trade_mode,
                check_interval_sec = EXCLUDED.check_interval_sec,
                capital = EXCLUDED.capital,
                picks = EXCLUDED.picks,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "strategy_id": strategy.id,
            "name": strategy.name,
            "description": strategy.description,
            "status": strategy.status,
            "source_type": strategy.source_type,
            "source_scheme_id": strategy.source_scheme_id,
            "buy_conditions": json.dumps(data["buy_conditions"], ensure_ascii=False),
            "sell_conditions": json.dumps(data["sell_conditions"], ensure_ascii=False),
            "position_rules": json.dumps(data["position_rules"], ensure_ascii=False),
            "risk_rules": json.dumps(data["risk_rules"], ensure_ascii=False),
            "trade_mode": strategy.trade_mode,
            "check_interval_sec": strategy.check_interval_sec,
            "capital": strategy.capital,
            "picks": json.dumps(strategy.picks, ensure_ascii=False),
            "created_at": strategy.created_at or "",
            "updated_at": strategy.updated_at or "",
        },
    )


async def list_all(db: AsyncSession) -> list[StrategyConfig]:
    result = await db.execute(
        text(
            f"""
            SELECT strategy_id, name, description, status, source_type, source_scheme_id,
                   buy_conditions, sell_conditions, position_rules, risk_rules,
                   trade_mode, check_interval_sec, capital, picks, created_at, updated_at
            FROM {TABLE_AUTO_STRATEGIES}
            ORDER BY updated_at DESC, id DESC
            """
        )
    )
    return [_row_to_strategy(_row_mapping(row)) for row in result.fetchall()]


async def get(db: AsyncSession, strategy_id: str) -> StrategyConfig | None:
    result = await db.execute(
        text(
            f"""
            SELECT strategy_id, name, description, status, source_type, source_scheme_id,
                   buy_conditions, sell_conditions, position_rules, risk_rules,
                   trade_mode, check_interval_sec, capital, picks, created_at, updated_at
            FROM {TABLE_AUTO_STRATEGIES}
            WHERE strategy_id = :strategy_id
            """
        ),
        {"strategy_id": strategy_id},
    )
    row = result.fetchone()
    return _row_to_strategy(_row_mapping(row)) if row else None


async def delete(db: AsyncSession, strategy_id: str) -> bool:
    result = await db.execute(
        text(
            f"""
            DELETE FROM {TABLE_AUTO_STRATEGIES}
            WHERE strategy_id = :strategy_id
            RETURNING strategy_id
            """
        ),
        {"strategy_id": strategy_id},
    )
    return result.fetchone() is not None


def _row_to_strategy(row: Any) -> StrategyConfig:
    position_rules = _json(row["position_rules"], {})
    risk_rules = _json(row["risk_rules"], {})
    buy_conditions = _json(row["buy_conditions"], [])
    sell_conditions = _json(row["sell_conditions"], [])
    return StrategyConfig(
        id=row["strategy_id"],
        name=row["name"],
        description=row["description"] or "",
        status=row["status"] or "draft",
        source_type=row["source_type"] or "custom",
        source_scheme_id=row["source_scheme_id"] or "",
        buy_conditions=[
            BuyCondition(
                field=item.get("field", ""),
                operator=item.get("operator", ">="),
                threshold=float(item.get("threshold", 0)),
                description=item.get("description", ""),
            )
            for item in buy_conditions
        ],
        sell_conditions=[
            SellCondition(
                field=item.get("field", ""),
                operator=item.get("operator", ">="),
                threshold=float(item.get("threshold", 0)),
                description=item.get("description", ""),
            )
            for item in sell_conditions
        ],
        position_rules=PositionRule(
            max_positions=int(position_rules.get("max_positions", 5)),
            single_max_pct=float(position_rules.get("single_max_pct", 0.20)),
            total_position_cap_pct=float(position_rules.get("total_position_cap_pct", 0.80)),
        ),
        risk_rules=RiskRule(
            daily_max_loss_pct=float(risk_rules.get("daily_max_loss_pct", 0.03)),
            stop_loss_pct=float(risk_rules.get("stop_loss_pct", 0.03)),
            take_profit_pct=float(risk_rules.get("take_profit_pct", 0.15)),
            trailing_stop_pct=float(risk_rules.get("trailing_stop_pct", 0.0)),
        ),
        trade_mode=row["trade_mode"] or "paper",
        check_interval_sec=int(row["check_interval_sec"] or 300),
        capital=float(row["capital"] or 1_000_000),
        picks=_json(row["picks"], []),
        created_at=_iso(row["created_at"]),
        updated_at=_iso(row["updated_at"]),
    )


def _row_mapping(row: Any) -> Any:
    return getattr(row, "_mapping", row)
