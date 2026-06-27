"""Read-only platform contracts for broker account visibility."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


BrokerAdapter = Literal["paper", "xtquant_qmt", "broker_rest"]
TradeMode = Literal["paper", "live"]
Visibility = Literal["private", "tenant_shared", "public"]
DataScope = Literal["public", "tenant", "user", "account"]


class BrokerAdapterCapability(BaseModel):
    """Display and permission capability for a broker adapter."""

    adapter: BrokerAdapter
    display_name: str
    supports_paper_trading: bool
    supports_live_trading: bool
    supports_sync: bool = True
    supports_cancel: bool = True
    requires_local_gateway: bool = False
    order_types: list[str] = Field(default_factory=lambda: ["LIMIT"])
    asset_classes: list[str] = Field(default_factory=lambda: ["cn_stock"])

    @classmethod
    def for_adapter(cls, adapter: BrokerAdapter) -> "BrokerAdapterCapability":
        if adapter == "paper":
            return cls(
                adapter="paper",
                display_name="Paper Trading",
                supports_paper_trading=True,
                supports_live_trading=False,
                requires_local_gateway=False,
                order_types=["LIMIT", "MARKET"],
            )
        if adapter == "xtquant_qmt":
            return cls(
                adapter="xtquant_qmt",
                display_name="XtQuant QMT",
                supports_paper_trading=True,
                supports_live_trading=True,
                requires_local_gateway=True,
                order_types=["LIMIT", "MARKET"],
            )
        return cls(
            adapter="broker_rest",
            display_name="Broker REST",
            supports_paper_trading=True,
            supports_live_trading=True,
            requires_local_gateway=False,
            order_types=["LIMIT"],
        )


class BrokerAccountView(BaseModel):
    """Read-only account view safe for platform UI and authorization checks."""

    tenant_id: str
    owner_user_id: str
    account_id: str
    account_name: str
    adapter: BrokerAdapter
    trade_mode: TradeMode
    visibility: Visibility = "private"
    data_scope: DataScope = "account"
    is_default: bool = False
    can_trade: bool = False
    can_sync_positions: bool = True
    capability: BrokerAdapterCapability
    total_assets: float | None = Field(default=None, ge=0)
    available: float | None = Field(default=None, ge=0)
    market_value: float | None = Field(default=None, ge=0)
    last_synced_at: datetime | None = None

    @model_validator(mode="after")
    def validate_adapter_contract(self) -> "BrokerAccountView":
        if self.capability.adapter != self.adapter:
            raise ValueError("capability adapter must match account adapter")
        if self.trade_mode == "paper" and not self.capability.supports_paper_trading:
            raise ValueError("adapter does not support paper trading")
        if self.trade_mode == "live" and not self.capability.supports_live_trading:
            raise ValueError("adapter does not support live trading")
        return self
