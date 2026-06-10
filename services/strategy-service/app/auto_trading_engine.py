"""Auto Trading Strategy Engine — generate StrategyConfig from plans or custom rules.

PRD AC-10.6~10.8: Strategy definition, scheme→strategy generation, custom strategies.
"""

import uuid
import threading
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("strategy-service.engine")


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BuyCondition:
    """A single buy-trigger condition."""
    field: str            # e.g. "signal_strength", "kronos_return", "factor_resonance"
    operator: str         # >=, <=, >, <, ==
    threshold: float
    description: str = ""


@dataclass
class SellCondition:
    """A single sell-trigger condition."""
    field: str
    operator: str
    threshold: float
    description: str = ""


@dataclass
class PositionRule:
    """Position management rules."""
    max_positions: int = 5
    single_max_pct: float = 0.20  # max allocation per stock
    total_position_cap_pct: float = 0.80  # max total position as % of capital


@dataclass
class RiskRule:
    """Risk management rules."""
    daily_max_loss_pct: float = 0.03    # pause trading if daily loss >= 3%
    stop_loss_pct: float = 0.03         # per-position stop-loss
    take_profit_pct: float = 0.15       # per-position take-profit
    trailing_stop_pct: float = 0.0      # 0 = disabled


@dataclass
class StrategyConfig:
    """Complete strategy configuration."""
    id: str
    name: str
    description: str = ""
    status: str = "draft"  # draft / active / paused / stopped / archived

    # Source
    source_type: str = "custom"  # "scheme" or "custom"
    source_scheme_id: str = ""   # plan ID if generated from scheme

    # Conditions
    buy_conditions: list[BuyCondition] = field(default_factory=list)
    sell_conditions: list[SellCondition] = field(default_factory=list)

    # Rules
    position_rules: PositionRule = field(default_factory=PositionRule)
    risk_rules: RiskRule = field(default_factory=RiskRule)

    # Runtime
    trade_mode: str = "paper"       # paper / live
    check_interval_sec: int = 300   # 5 minutes default
    capital: float = 1_000_000

    # Picks (from scheme)
    picks: list[dict] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "source_type": self.source_type,
            "source_scheme_id": self.source_scheme_id,
            "buy_conditions": [
                {"field": c.field, "operator": c.operator,
                 "threshold": c.threshold, "description": c.description}
                for c in self.buy_conditions
            ],
            "sell_conditions": [
                {"field": c.field, "operator": c.operator,
                 "threshold": c.threshold, "description": c.description}
                for c in self.sell_conditions
            ],
            "position_rules": {
                "max_positions": self.position_rules.max_positions,
                "single_max_pct": self.position_rules.single_max_pct,
                "total_position_cap_pct": self.position_rules.total_position_cap_pct,
            },
            "risk_rules": {
                "daily_max_loss_pct": self.risk_rules.daily_max_loss_pct,
                "stop_loss_pct": self.risk_rules.stop_loss_pct,
                "take_profit_pct": self.risk_rules.take_profit_pct,
                "trailing_stop_pct": self.risk_rules.trailing_stop_pct,
            },
            "trade_mode": self.trade_mode,
            "check_interval_sec": self.check_interval_sec,
            "capital": self.capital,
            "picks_count": len(self.picks),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Default condition sets
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_BUY_CONDITIONS = [
    BuyCondition(field="signal_strength", operator=">=", threshold=60,
                 description="信号强度 ≥ BUY (🟡 60分)"),
    BuyCondition(field="kronos_return", operator=">", threshold=8.0,
                 description="Kronos预测收益 > 8%"),
    BuyCondition(field="factor_resonance", operator=">=", threshold=2,
                 description="因子共振数 ≥ 2 (技术+资金+趋势中至少2个共振)"),
]

DEFAULT_SELL_CONDITIONS = [
    SellCondition(field="signal_strength", operator="<=", threshold=20,
                  description="信号强度 ≤ SELL (🔴 20分)"),
    SellCondition(field="kronos_trend", operator="==", threshold=1,
                  description="Kronos转为下跌趋势"),
    SellCondition(field="stop_loss", operator=">=", threshold=3.0,
                  description="止损: 浮亏 ≥ 3%"),
    SellCondition(field="take_profit", operator=">=", threshold=15.0,
                  description="止盈: 浮盈 ≥ 15%"),
]

DEFAULT_POSITION_RULES = PositionRule(
    max_positions=5,
    single_max_pct=0.20,
    total_position_cap_pct=0.80,
)

DEFAULT_RISK_RULES = RiskRule(
    daily_max_loss_pct=0.03,
    stop_loss_pct=0.03,
    take_profit_pct=0.15,
)


# ═══════════════════════════════════════════════════════════════════════════
# Strategy Store — in-memory, thread-safe
# ═══════════════════════════════════════════════════════════════════════════

class StrategyStore:
    """In-memory store for StrategyConfig objects."""

    def __init__(self):
        self._strategies: dict[str, StrategyConfig] = {}
        self._lock = threading.Lock()

    def create(self, strategy: StrategyConfig) -> StrategyConfig:
        with self._lock:
            now = datetime.now().isoformat()
            strategy.created_at = now
            strategy.updated_at = now
            self._strategies[strategy.id] = strategy
            return strategy

    def get(self, strategy_id: str) -> StrategyConfig | None:
        return self._strategies.get(strategy_id)

    def list_all(self) -> list[StrategyConfig]:
        with self._lock:
            return list(self._strategies.values())

    def update(self, strategy_id: str, **kwargs) -> StrategyConfig | None:
        with self._lock:
            s = self._strategies.get(strategy_id)
            if not s:
                return None
            for k, v in kwargs.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            s.updated_at = datetime.now().isoformat()
            return s

    def delete(self, strategy_id: str) -> bool:
        with self._lock:
            if strategy_id in self._strategies:
                del self._strategies[strategy_id]
                return True
            return False


_strategy_store = StrategyStore()


def get_strategy_store() -> StrategyStore:
    return _strategy_store


# ═══════════════════════════════════════════════════════════════════════════
# Strategy generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_strategy_from_scheme(scheme_id: str) -> StrategyConfig:
    """Generate a StrategyConfig from an existing trading plan (scheme).

    PRD AC-10.6:
      - Reads plan from PlanStore
      - Maps picks to strategy targets
      - Sets default buy/sell/risk conditions
      - Returns StrategyConfig ready to execute

    Args:
        scheme_id: Plan ID from plan_store (e.g. "PLAN-A1B2C3D4")

    Returns:
        StrategyConfig with conditions and rules populated.

    Raises:
        ValueError: If the plan is not found or not in confirmed status.
    """
    from app.plan_store import get_store

    plan_store = get_store()
    plan = plan_store.get(scheme_id)

    if plan is None:
        raise ValueError(f"方案不存在: {scheme_id}")

    if plan.status not in ("confirmed", "active"):
        raise ValueError(
            f"方案状态必须为 confirmed 或 active，当前: {plan.status}。请先确认方案。"
        )

    # Build strategy from plan
    now = datetime.now().isoformat()
    strategy_id = f"STR-{uuid.uuid4().hex[:8].upper()}"

    strategy = StrategyConfig(
        id=strategy_id,
        name=f"自动策略-{plan.name}",
        description=f"由方案 {scheme_id} 自动生成。模型: {plan.model_name}",
        status="draft",
        source_type="scheme",
        source_scheme_id=scheme_id,

        # Default conditions per PRD AC-10.6
        buy_conditions=[BuyCondition(**{
            "field": c.field, "operator": c.operator,
            "threshold": c.threshold, "description": c.description,
        }) for c in DEFAULT_BUY_CONDITIONS],
        sell_conditions=[SellCondition(**{
            "field": c.field, "operator": c.operator,
            "threshold": c.threshold, "description": c.description,
        }) for c in DEFAULT_SELL_CONDITIONS],

        # Rules from plan + defaults
        position_rules=PositionRule(
            max_positions=getattr(plan, "max_positions", 5),
            single_max_pct=getattr(plan, "single_max_pct", 0.20),
            total_position_cap_pct=0.80,
        ),
        risk_rules=DEFAULT_RISK_RULES,

        # Plan data
        capital=plan.capital,
        picks=plan.picks.copy() if plan.picks else [],

        created_at=now,
        updated_at=now,
    )

    store = get_strategy_store()
    store.create(strategy)

    logger.info(
        "Strategy generated: %s from scheme %s (%d picks)",
        strategy_id, scheme_id, len(strategy.picks),
    )

    return strategy


def create_custom_strategy(
    name: str,
    description: str = "",
    buy_conditions: list[dict] | None = None,
    sell_conditions: list[dict] | None = None,
    position_rules: dict | None = None,
    risk_rules: dict | None = None,
    trade_mode: str = "paper",
    check_interval_sec: int = 300,
    capital: float = 1_000_000,
    picks: list[dict] | None = None,
) -> StrategyConfig:
    """Create a fully custom strategy from user-defined conditions.

    PRD AC-10.7: Custom strategy builder.
    """
    now = datetime.now().isoformat()
    strategy_id = f"STR-{uuid.uuid4().hex[:8].upper()}"

    # Parse buy conditions
    parsed_buy = []
    if buy_conditions:
        for c in buy_conditions:
            parsed_buy.append(BuyCondition(
                field=c.get("field", ""),
                operator=c.get("operator", ">="),
                threshold=float(c.get("threshold", 0)),
                description=c.get("description", ""),
            ))

    # Parse sell conditions
    parsed_sell = []
    if sell_conditions:
        for c in sell_conditions:
            parsed_sell.append(SellCondition(
                field=c.get("field", ""),
                operator=c.get("operator", ">="),
                threshold=float(c.get("threshold", 0)),
                description=c.get("description", ""),
            ))

    # Parse position rules
    pos_rules = DEFAULT_POSITION_RULES
    if position_rules:
        pos_rules = PositionRule(
            max_positions=int(position_rules.get("max_positions", 5)),
            single_max_pct=float(position_rules.get("single_max_pct", 0.20)),
            total_position_cap_pct=float(position_rules.get("total_position_cap_pct", 0.80)),
        )

    # Parse risk rules
    risk = DEFAULT_RISK_RULES
    if risk_rules:
        risk = RiskRule(
            daily_max_loss_pct=float(risk_rules.get("daily_max_loss_pct", 0.03)),
            stop_loss_pct=float(risk_rules.get("stop_loss_pct", 0.03)),
            take_profit_pct=float(risk_rules.get("take_profit_pct", 0.15)),
            trailing_stop_pct=float(risk_rules.get("trailing_stop_pct", 0.0)),
        )

    strategy = StrategyConfig(
        id=strategy_id,
        name=name,
        description=description,
        status="draft",
        source_type="custom",
        buy_conditions=parsed_buy or DEFAULT_BUY_CONDITIONS,
        sell_conditions=parsed_sell or DEFAULT_SELL_CONDITIONS,
        position_rules=pos_rules,
        risk_rules=risk,
        trade_mode=trade_mode,
        check_interval_sec=check_interval_sec,
        capital=capital,
        picks=picks or [],
        created_at=now,
        updated_at=now,
    )

    store = get_strategy_store()
    store.create(strategy)

    logger.info("Custom strategy created: %s", strategy_id)
    return strategy
