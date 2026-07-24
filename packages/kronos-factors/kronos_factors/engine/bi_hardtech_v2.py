from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class V2Config:
    gap_min_pct: float = -1.5
    gap_max_pct: float = 3.0
    max_daily_entries: int = 2
    bull_cap: float = 0.50
    neutral_cap: float = 0.30
    single_position_cap: float = 0.15


@dataclass(frozen=True)
class Confirmation:
    accepted: bool
    reason: str
    gap_pct: float | None


def market_allows_entry(regime: str) -> bool:
    return regime.strip().lower() in {"bull", "neutral"}


def confirm_t1_open(
    previous_close: float,
    open_price: float,
    sector_change: float | None,
    config: V2Config,
) -> Confirmation:
    if previous_close <= 0 or open_price <= 0:
        return Confirmation(False, "price_missing", None)

    gap_pct = round((open_price / previous_close - 1.0) * 100.0, 10)
    if gap_pct < config.gap_min_pct:
        return Confirmation(False, "gap_below_min", gap_pct)
    if gap_pct > config.gap_max_pct:
        return Confirmation(False, "gap_above_max", gap_pct)
    if sector_change is None:
        return Confirmation(False, "sector_missing", gap_pct)
    if sector_change < 0:
        return Confirmation(False, "sector_negative", gap_pct)
    return Confirmation(True, "accepted", gap_pct)


def select_daily_entries(
    candidates: list[dict],
    open_by_code: dict[str, float],
    close_by_code: dict[str, float],
    config: V2Config,
) -> tuple[list[dict], list[dict]]:
    selected: list[dict] = []
    rejected: list[dict] = []

    for candidate in candidates:
        code = candidate["code"]
        decision = confirm_t1_open(
            close_by_code.get(code, 0.0),
            open_by_code.get(code, 0.0),
            candidate.get("sector_change"),
            config,
        )
        enriched = {
            **candidate,
            "accepted": decision.accepted,
            "confirmation_reason": decision.reason,
            "gap_pct": decision.gap_pct,
        }

        if not decision.accepted:
            rejected.append(enriched)
            continue

        if len(selected) >= config.max_daily_entries:
            rejected.append(
                {
                    **enriched,
                    "accepted": False,
                    "confirmation_reason": "daily_limit",
                }
            )
            continue

        selected.append(enriched)

    return selected, rejected
