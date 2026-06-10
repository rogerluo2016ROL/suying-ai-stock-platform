"""Auto Trading Strategy Executor — async loop checking conditions and placing orders.

PRD AC-10.8 + AC-11.5~11.6:
  - Periodic condition evaluation loop
  - Calls trade-service for buy/sell orders
  - Calls signal-service for signal analysis
  - Configurable interval (default 5 min)
  - Supports start/pause/resume/stop lifecycle
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from dataclasses import dataclass, field

from app.auto_trading_engine import (
    StrategyConfig,
    BuyCondition,
    SellCondition,
    get_strategy_store,
)

logger = logging.getLogger("strategy-service.executor")

# ── Service URLs (configurable via env) ──────────────────────────────────
TRADE_SERVICE_URL = os.environ.get("TRADE_SERVICE_URL", "http://localhost:8006")
SIGNAL_SERVICE_URL = os.environ.get("SIGNAL_SERVICE_URL", "http://localhost:8004")


# ═══════════════════════════════════════════════════════════════════════════
# Execution log
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionLogEntry:
    timestamp: str
    level: str       # INFO / WARN / ERROR / BUY / SELL
    message: str
    details: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Executor state
# ═══════════════════════════════════════════════════════════════════════════

class ExecutorState:
    """Per-strategy executor state."""

    def __init__(self, strategy: StrategyConfig):
        self.strategy_id = strategy.id
        self.status: str = "idle"  # idle / running / paused / stopped
        self.started_at: str | None = None
        self.stopped_at: str | None = None
        self.last_check_at: str | None = None
        self.next_check_at: str | None = None
        self.checks_completed: int = 0
        self.orders_placed: int = 0
        self.errors: int = 0
        self.logs: list[ExecutionLogEntry] = []
        self._task: asyncio.Task | None = None
        self._pause_event: asyncio.Event | None = None
        self._stop_event: asyncio.Event | None = None

    def add_log(self, level: str, message: str, details: dict | None = None):
        entry = ExecutionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            message=message,
            details=details or {},
        )
        self.logs.append(entry)
        # Cap at 1000 entries
        if len(self.logs) > 1000:
            self.logs = self.logs[-500:]
        return entry

    def to_status_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_check_at": self.last_check_at,
            "next_check_at": self.next_check_at,
            "checks_completed": self.checks_completed,
            "orders_placed": self.orders_placed,
            "errors": self.errors,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Executor Manager — singleton managing all running executors
# ═══════════════════════════════════════════════════════════════════════════

class ExecutorManager:
    """Manages executor lifecycle for all strategies."""

    def __init__(self):
        self._executors: dict[str, ExecutorState] = {}
        self._lock = threading.Lock()

    def get(self, strategy_id: str) -> ExecutorState | None:
        return self._executors.get(strategy_id)

    def list_all(self) -> list[ExecutorState]:
        with self._lock:
            return list(self._executors.values())

    def start(self, strategy_id: str) -> ExecutorState:
        store = get_strategy_store()
        strategy = store.get(strategy_id)
        if strategy is None:
            raise ValueError(f"策略不存在: {strategy_id}")

        with self._lock:
            existing = self._executors.get(strategy_id)
            if existing and existing.status in ("running", "paused"):
                raise ValueError(f"策略已在执行中 (status={existing.status})，使用 resume 恢复或 stop 终止后重新 start")

            state = ExecutorState(strategy)
            state.status = "running"
            state.started_at = datetime.now(timezone.utc).isoformat()
            state._pause_event = asyncio.Event()
            state._pause_event.set()  # not paused initially
            state._stop_event = asyncio.Event()

            self._executors[strategy_id] = state

            # Update strategy status
            store.update(strategy_id, status="active")

            # Create and schedule the async task
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — schedule on a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            state._task = loop.create_task(_executor_loop(state, strategy))
            state.add_log("INFO", f"策略执行器已启动 (mode={strategy.trade_mode})")

        logger.info("Executor started for strategy %s", strategy_id)
        return state

    def pause(self, strategy_id: str) -> ExecutorState:
        state = self._executors.get(strategy_id)
        if state is None:
            raise ValueError(f"执行器未找到: {strategy_id}")
        if state.status != "running":
            raise ValueError(f"执行器状态为 {state.status}，无法暂停")
        state._pause_event.clear()
        state.status = "paused"
        state.add_log("INFO", "策略执行已暂停")
        get_strategy_store().update(strategy_id, status="paused")
        logger.info("Executor paused for strategy %s", strategy_id)
        return state

    def resume(self, strategy_id: str) -> ExecutorState:
        state = self._executors.get(strategy_id)
        if state is None:
            raise ValueError(f"执行器未找到: {strategy_id}")
        if state.status != "paused":
            raise ValueError(f"执行器状态为 {state.status}，无法恢复")
        state._pause_event.set()
        state.status = "running"
        state.add_log("INFO", "策略执行已恢复")
        get_strategy_store().update(strategy_id, status="active")
        logger.info("Executor resumed for strategy %s", strategy_id)
        return state

    def stop(self, strategy_id: str) -> ExecutorState:
        state = self._executors.get(strategy_id)
        if state is None:
            raise ValueError(f"执行器未找到: {strategy_id}")
        if state.status in ("stopped",):
            raise ValueError(f"执行器已停止")
        state._stop_event.set()
        state.status = "stopped"
        state.stopped_at = datetime.now(timezone.utc).isoformat()
        state.add_log("INFO", "策略执行已终止")
        get_strategy_store().update(strategy_id, status="stopped")
        logger.info("Executor stopped for strategy %s", strategy_id)
        return state


_executor_manager = ExecutorManager()


def get_executor_manager() -> ExecutorManager:
    return _executor_manager


# ═══════════════════════════════════════════════════════════════════════════
# Main execution loop
# ═══════════════════════════════════════════════════════════════════════════

async def _executor_loop(state: ExecutorState, strategy: StrategyConfig) -> None:
    """Main execution loop: check conditions → place orders → wait → repeat."""
    interval = strategy.check_interval_sec

    while not state._stop_event.is_set():
        # Check if paused
        await state._pause_event.wait()

        # Check stop again after potential pause
        if state._stop_event.is_set():
            break

        try:
            await _run_one_check(state, strategy)
        except asyncio.CancelledError:
            logger.info("Executor task cancelled for %s", strategy.id)
            break
        except Exception as e:
            state.errors += 1
            state.add_log("ERROR", f"执行异常: {str(e)}", {"error": str(e)})
            logger.exception("Executor error for strategy %s", strategy.id)

        # Wait for next check interval (check stop/pause every second)
        waited = 0
        while waited < interval:
            if state._stop_event.is_set():
                break
            await asyncio.sleep(1)
            waited += 1
            if state._pause_event.is_set():
                continue  # resume normal operation
            else:
                # Paused — just wait without counting toward interval
                await state._pause_event.wait()
                if state._stop_event.is_set():
                    break
                waited = 0  # reset interval after resume


async def _run_one_check(state: ExecutorState, strategy: StrategyConfig) -> None:
    """Execute one round of condition checking and order placement."""
    now = datetime.now(timezone.utc).isoformat()
    state.last_check_at = now
    state.next_check_at = datetime.fromtimestamp(
        time.time() + strategy.check_interval_sec, tz=timezone.utc
    ).isoformat()

    state.add_log("INFO", "开始执行检查", {"picks_count": len(strategy.picks)})

    # Get current positions from trade-service
    positions = await _fetch_positions(strategy.trade_mode)

    # Get account info for risk checks
    account = await _fetch_account(strategy.trade_mode)

    # Check daily loss limit first
    daily_pnl = account.get("daily_pnl", 0)
    daily_loss_pct = abs(daily_pnl) / strategy.capital if daily_pnl < 0 else 0
    if daily_loss_pct >= strategy.risk_rules.daily_max_loss_pct:
        state.add_log(
            "WARN",
            f"日亏损 {daily_loss_pct:.2%} 超过阈值 {strategy.risk_rules.daily_max_loss_pct:.2%}，跳过本次交易",
            {"daily_pnl": daily_pnl, "daily_loss_pct": round(daily_loss_pct, 4)},
        )
        state.checks_completed += 1
        # Auto-pause on daily loss threshold breach
        mgr = get_executor_manager()
        try:
            mgr.pause(strategy.id)
            state.add_log("WARN", "日亏损超限 — 自动暂停策略执行")
        except ValueError:
            pass
        return

    # Check total position cap
    total_market_value = sum(
        p.get("market_value", 0) for p in positions.get("positions", [])
    )
    total_position_pct = total_market_value / strategy.capital
    if total_position_pct >= strategy.position_rules.total_position_cap_pct:
        state.add_log(
            "INFO",
            f"总仓位 {total_position_pct:.1%} 已达上限 {strategy.position_rules.total_position_cap_pct:.1%}",
        )

    held_codes = {p.get("code", "") for p in positions.get("positions", []) if p.get("volume", 0) > 0}
    current_positions_count = len(held_codes)

    # ── Check SELL conditions for held positions ──
    for pos in positions.get("positions", []):
        code = pos.get("code", "")
        if not code:
            continue

        signal = await _fetch_signal(code)
        should_sell, sell_reason = _evaluate_sell_conditions(
            strategy.sell_conditions, signal, pos
        )

        if should_sell:
            state.add_log(
                "SELL",
                f"触发卖出条件: {code} — {sell_reason}",
                {"code": code, "reason": sell_reason, "pnl_pct": pos.get("pnl_pct", 0)},
            )
            result = await _place_order(
                symbol=code,
                direction="SELL",
                volume=pos.get("volume", 0),
                trade_mode=strategy.trade_mode,
            )
            state.orders_placed += 1
            state.add_log(
                "SELL",
                f"卖单已提交: {code} — order_id={result.get('order_id', '?')}",
                {"code": code, "order_id": result.get("order_id")},
            )

    # ── Check BUY conditions for picks not yet held ──
    if current_positions_count >= strategy.position_rules.max_positions:
        state.add_log(
            "INFO",
            f"持仓数 {current_positions_count} 已达上限 {strategy.position_rules.max_positions}",
        )

    for pick in strategy.picks:
        code = pick.get("code", "")
        if not code:
            continue

        # Skip already held
        if code in held_codes:
            continue

        # Skip if at max positions
        if current_positions_count >= strategy.position_rules.max_positions:
            break

        # Fetch signal for this pick
        signal = await _fetch_signal(code)
        should_buy, buy_reason = _evaluate_buy_conditions(
            strategy.buy_conditions, signal
        )

        if should_buy:
            # Calculate position size
            position_pct = strategy.position_rules.single_max_pct / strategy.position_rules.max_positions
            # Prefer pick's own entry price or signal price
            entry_price = float(pick.get("entry_price") or pick.get("price") or signal.get("price", 0))
            if entry_price <= 0:
                state.add_log("WARN", f"无法获取 {code} 价格，跳过买入", {"code": code})
                continue

            volume = int((strategy.capital * position_pct) / entry_price)
            volume = (volume // 100) * 100  # round to lot size
            if volume < 100:
                state.add_log("WARN", f"{code} 计算股数 {volume} < 100，跳过", {"code": code})
                continue

            state.add_log(
                "BUY",
                f"触发买入条件: {code} — {buy_reason}",
                {"code": code, "reason": buy_reason, "price": entry_price, "volume": volume},
            )

            result = await _place_order(
                symbol=code,
                direction="BUY",
                price=entry_price,
                volume=volume,
                trade_mode=strategy.trade_mode,
            )
            state.orders_placed += 1
            current_positions_count += 1
            held_codes.add(code)
            state.add_log(
                "BUY",
                f"买单已提交: {code} — order_id={result.get('order_id', '?')}",
                {"code": code, "order_id": result.get("order_id")},
            )

    state.checks_completed += 1
    state.add_log("INFO", f"检查完成 (第 {state.checks_completed} 轮)")


# ═══════════════════════════════════════════════════════════════════════════
# Condition evaluation
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_buy_conditions(
    conditions: list[BuyCondition],
    signal: dict,
) -> tuple[bool, str]:
    """Evaluate buy conditions against signal data.

    Returns:
        (should_buy, reason_string)
    """
    if not conditions:
        return True, "无条件买入"

    results = []
    for cond in conditions:
        passed, detail = _check_condition(cond.field, cond.operator, cond.threshold, signal)
        results.append((passed, cond.description, detail))

    all_passed = all(r[0] for r in results)
    if all_passed:
        reasons = ", ".join(r[1] for r in results)
        return True, f"全部条件满足: {reasons}"
    else:
        failed = [r[1] for r in results if not r[0]]
        return False, f"条件不满足: {'; '.join(failed)}"


def _evaluate_sell_conditions(
    conditions: list[SellCondition],
    signal: dict,
    position: dict,
) -> tuple[bool, str]:
    """Evaluate sell conditions against signal + position data.

    Returns:
        (should_sell, reason_string)
    """
    if not conditions:
        return False, ""

    # Merge position data into evaluation context
    context = {**signal}
    context["pnl_pct"] = position.get("pnl_pct", 0)
    context["stop_loss"] = abs(position.get("pnl_pct", 0)) if position.get("pnl_pct", 0) < 0 else 0
    context["take_profit"] = position.get("pnl_pct", 0) if position.get("pnl_pct", 0) > 0 else 0

    for cond in conditions:
        field_value = context.get(cond.field, 0)
        # Normalize kronos_trend: 1 = bearish/downtrend
        if cond.field == "kronos_trend":
            # Check if signal has kronos_trend field
            field_value = signal.get("kronos_trend", signal.get("components", {}).get("kronos_confidence", {}).get("score", 50))
            # Lower than 50 = bearish
            field_value = 1 if field_value < 50 else 0

        passed = _eval_op(field_value, cond.operator, cond.threshold)
        if passed:
            return True, cond.description

    return False, "未触发卖出条件"


def _check_condition(
    field: str, operator: str, threshold: float, context: dict
) -> tuple[bool, str]:
    """Check a single condition against the evaluation context."""
    # Map field names to context paths
    field_map = {
        "signal_strength": "signal.score",
        "kronos_return": "components.kronos_confidence.score",
        "factor_resonance": "components.factor_resonance.score",
    }

    # Resolve value from nested dict
    path = field_map.get(field, field)
    parts = path.split(".")
    value = context
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part, 0)
        else:
            value = 0
            break

    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0

    passed = _eval_op(value, operator, threshold)
    detail = f"{field}={value:.1f} {operator} {threshold}"
    return passed, detail


def _eval_op(value: float, operator: str, threshold: float) -> bool:
    """Evaluate a comparison operator."""
    if operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == "==":
        return value == threshold
    elif operator == "!=":
        return value != threshold
    return False


# ═══════════════════════════════════════════════════════════════════════════
# HTTP clients (async wrappers over urllib)
# ═══════════════════════════════════════════════════════════════════════════

async def _http_get(url: str, timeout: int = 10) -> dict:
    """Async HTTP GET returning parsed JSON."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_get, url, timeout)
    except Exception as e:
        logger.warning("HTTP GET %s failed: %s", url, e)
        return {"error": str(e)}


def _sync_get(url: str, timeout: int) -> dict:
    """Synchronous urllib GET."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        logger.warning("HTTP %s → %s", url, e.code)
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        logger.warning("HTTP request failed (%s): %s", url, e)
        return {"error": str(e)}


async def _http_post_query(url: str, params: dict, timeout: int = 10) -> dict:
    """Async HTTP POST with query parameters, returning parsed JSON."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_post_query, url, params, timeout)
    except Exception as e:
        logger.warning("HTTP POST %s failed: %s", url, e)
        return {"error": str(e)}


def _sync_post_query(url: str, params: dict, timeout: int) -> dict:
    """Synchronous urllib POST with query string."""
    from urllib.parse import urlencode

    query_string = urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query_string}"
    req = urllib.request.Request(full_url, method="POST", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        logger.warning("HTTP POST %s → %s: %s", url, e.code, body)
        return {"error": f"HTTP {e.code}", "detail": body}
    except Exception as e:
        logger.warning("HTTP POST failed (%s): %s", url, e)
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Service-specific fetch helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_signal(code: str) -> dict:
    """Fetch trading signal for a stock from signal-service."""
    url = f"{SIGNAL_SERVICE_URL}/api/v1/signal/analyze/{code}"
    return await _http_get(url)


async def _fetch_positions(trade_mode: str) -> dict:
    """Fetch current positions from trade-service."""
    url = f"{TRADE_SERVICE_URL}/api/v1/trade/positions?trade_mode={trade_mode}"
    return await _http_get(url)


async def _fetch_account(trade_mode: str) -> dict:
    """Fetch account info from trade-service."""
    url = f"{TRADE_SERVICE_URL}/api/v1/trade/account?trade_mode={trade_mode}"
    return await _http_get(url)


async def _place_order(
    symbol: str,
    direction: str,
    volume: int,
    trade_mode: str,
    price: float = 0,
) -> dict:
    """Place an order via trade-service."""
    params = {
        "code": symbol,
        "direction": direction,
        "price": price,
        "volume": volume,
        "trade_mode": trade_mode,
    }
    url = f"{TRADE_SERVICE_URL}/api/v1/trade/order"
    return await _http_post_query(url, params)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def run_strategy(strategy_id: str, mode: str = "paper") -> ExecutorState:
    """Start executing a strategy (convenience wrapper).

    Args:
        strategy_id: Strategy ID to execute.
        mode: 'paper' or 'live' — overrides the strategy's default trade_mode.

    Returns:
        ExecutorState for the running strategy.

    Raises:
        ValueError: If strategy not found or already running.
    """
    # Update trade_mode if specified
    store = get_strategy_store()
    strategy = store.get(strategy_id)
    if strategy is None:
        raise ValueError(f"策略不存在: {strategy_id}")
    if mode in ("paper", "live"):
        store.update(strategy_id, trade_mode=mode)

    mgr = get_executor_manager()
    return mgr.start(strategy_id)
