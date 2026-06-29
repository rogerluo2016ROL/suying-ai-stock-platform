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

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auto_trading_engine import (
    StrategyConfig,
    BuyCondition,
    SellCondition,
    get_strategy_store,
)

logger = logging.getLogger("strategy-service.executor")


# ═══════════════════════════════════════════════════════════════════════════
# Risk-check DB engine (shared, process-level singleton) + fail-safe signal
# ═══════════════════════════════════════════════════════════════════════════
# AC-10: the 3 risk-check functions share a single async engine (built at
# module import = process startup, not per loop iteration). pool_timeout
# bounds how long a risk check can block the trading loop. On DB failure
# the functions raise RiskCheckUnavailable so the caller pauses the whole
# loop (systemic risk) instead of returning a neutral default that would
# let trading continue without stop-loss / risk gating.

def _resolve_risk_db_url() -> str:
    """Resolve an asyncpg-compatible Postgres URL (mirrors trade-service database.py).

    DATABASE_URL (asyncpg scheme) takes precedence; otherwise derive from
    KRONOS_PG_URL (psycopg2 scheme) by swapping the driver.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = os.environ.get(
            "KRONOS_PG_URL",
            "postgresql://kronos:kronos@localhost:6432/kronos",
        )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_risk_engine_init_error: Exception | None = None
try:
    _risk_engine = create_async_engine(
        _resolve_risk_db_url(),
        echo=False,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_timeout=5,
    )
except ModuleNotFoundError as e:
    _risk_engine = None
    _risk_engine_init_error = e


class RiskCheckUnavailable(RuntimeError):
    """DB unreachable during a risk check → fail-safe: caller pauses the loop.

    Raised instead of returning a neutral default (which would let trading
    continue without stop-loss / risk gating — a capital risk). Per AC-10 /
    ADR-007: connection failure is treated as a systemic risk, not a
    per-stock verdict.
    """


def _require_risk_engine():
    if _risk_engine is None:
        raise RiskCheckUnavailable(f"risk DB driver unavailable: {_risk_engine_init_error}")
    return _risk_engine

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
        self.status: str = "stopped"  # stopped / running / paused
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
            if existing:
                if existing.status == "running":
                    raise ValueError(f"策略已在执行中 (status=running)，请先 stop 再 start")
                if existing.status == "paused":
                    raise ValueError(f"策略已暂停 (status=paused)，请使用 resume 恢复，不要重复 start")
                if existing.status == "stopped":
                    # Allowed: stopped → start (clean restart)
                    pass

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
            # NOTE: start() must be called from within an async context (e.g. FastAPI route).
            # If no running loop exists, raise a clear error instead of silently failing.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                raise RuntimeError(
                    "ExecutorManager.start() must be called from within an async context. "
                    "Ensure the API route handler is async."
                )

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
    daily_loss_pct = abs(daily_pnl) / strategy.capital if daily_pnl < 0 and strategy.capital > 0 else 0
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

    # AC-10 fail-safe: the risk-check functions (announcement / ATR / forecast)
    # raise RiskCheckUnavailable when the risk DB is unreachable. Such a
    # connection failure is a systemic risk — we must NOT fall back to a
    # neutral default (which would let trading continue without stop-loss /
    # risk gating). Instead, pause the whole loop and bail out of this round.
    try:
        # ── Check SELL conditions for held positions ──
        for pos in positions.get("positions", []):
            code = pos.get("code", "")
            if not code:
                continue

            # P0: 公告事件风险检测 (优先于常规卖出条件)
            is_announcement_risk, announcement_reason = await _check_announcement_risk(code)
            if is_announcement_risk:
                state.add_log(
                    "SELL",
                    f"触发事件止损: {code} — {announcement_reason}",
                    {"code": code, "reason": announcement_reason, "source": "announcement_risk"},
                )
                lineage = _build_auto_order_lineage(strategy, code, "SELL")
                result = await _place_order(
                    symbol=code,
                    direction="SELL",
                    volume=pos.get("volume", 0),
                    trade_mode=strategy.trade_mode,
                    **lineage,
                )
                state.orders_placed += 1
                state.add_log(
                    "SELL",
                    f"事件止损卖单已提交: {code}",
                    {"code": code, "order_id": result.get("order_id"), **lineage},
                )
                continue  # 跳过常规卖出条件

            signal = await _fetch_signal(code)
            should_sell, sell_reason = await _evaluate_sell_conditions(
                strategy.sell_conditions, signal, pos
            )

            if should_sell:
                state.add_log(
                    "SELL",
                    f"触发卖出条件: {code} — {sell_reason}",
                    {"code": code, "reason": sell_reason, "pnl_pct": pos.get("pnl_pct", 0)},
                )
                lineage = _build_auto_order_lineage(strategy, code, "SELL")
                result = await _place_order(
                    symbol=code,
                    direction="SELL",
                    volume=pos.get("volume", 0),
                    trade_mode=strategy.trade_mode,
                    **lineage,
                )
                state.orders_placed += 1
                state.add_log(
                    "SELL",
                    f"卖单已提交: {code} — order_id={result.get('order_id', '?')}",
                    {"code": code, "order_id": result.get("order_id"), **lineage},
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

            # ── P3: 业绩预告负向过滤 ──
            forecast_warn = await _check_forecast_risk(code)
            if forecast_warn:
                state.add_log("WARN", f"跳过买入 {code}: 业绩预告风险 — {forecast_warn}", {"code": code})
                continue

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

                lineage = _build_auto_order_lineage(strategy, code, "BUY", pick)
                result = await _place_order(
                    symbol=code,
                    direction="BUY",
                    price=entry_price,
                    volume=volume,
                    trade_mode=strategy.trade_mode,
                    **lineage,
                )
                state.orders_placed += 1
                current_positions_count += 1
                held_codes.add(code)
                state.add_log(
                    "BUY",
                    f"买单已提交: {code} — order_id={result.get('order_id', '?')}",
                    {"code": code, "order_id": result.get("order_id"), **lineage},
                )
    except RiskCheckUnavailable as e:
        logger.error(
            "risk DB unreachable — pausing executor for manual intervention (strategy=%s): %s",
            strategy.id, e, exc_info=True,
        )
        state.add_log(
            "ERROR",
            f"风控检查 DB 不可达 — fail-safe 暂停整轮循环: {e}",
            {"error": str(e), "fail_safe": True},
        )
        mgr = get_executor_manager()
        try:
            mgr.pause(strategy.id)
            state.add_log(
                "ERROR",
                "DB 风控不可用 — 自动暂停策略执行（等待人工介入 / DB 恢复后 resume）",
            )
        except ValueError:
            # Already paused/stopped — nothing more to do.
            pass
        return  # 不下单：本轮中止

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


# ── P0: 公告事件风险检测 ──

_ANNOUNCEMENT_RISK_KEYWORDS = [
    "退市", "ST", "*ST", "暂停上市", "终止上市", "立案调查", "行政处罚",
    "业绩修正", "预亏", "预降", "亏损", "重大诉讼", "债务违约",
    "控股股东", "司法冻结", "轮候冻结", "破产", "重整",
    "无法表示意见", "否定意见", "保留意见", "关联方占用",
    "违规担保", "信息披露", "责令改正", "警示函", "监管函",
]


async def _check_announcement_risk(code: str) -> tuple[bool, str]:
    """Check if stock has recent risk-related announcements.

    Returns:
        (is_risky, reason_string)

    Raises:
        RiskCheckUnavailable: if the risk DB is unreachable (caller must pause
        the loop — never return a neutral default, per AC-10).
    """
    try:
        async with _require_risk_engine().connect() as conn:
            result = await conn.execute(
                sa_text(
                    "SELECT title, ann_date FROM announcements "
                    "WHERE code = :code AND ann_date >= CURRENT_DATE - INTERVAL '3 days' "
                    "ORDER BY ann_date DESC LIMIT 10"
                ),
                {"code": code},
            )
            rows = result.fetchall()

        for title, ann_date in rows:
            title_str = str(title or "")
            for kw in _ANNOUNCEMENT_RISK_KEYWORDS:
                if kw in title_str:
                    return True, f"风险公告[{ann_date}]: {title_str[:80]}"
        return False, ""
    except Exception as e:
        logger.warning("公告风险检查 DB 不可达 code=%s: %s", code, e)
        raise RiskCheckUnavailable(f"announcement_risk DB unreachable: {e}") from e


async def _get_atr_stop_loss(code: str) -> float:
    """P4: ATR-based dynamic stop loss (替代硬编码 3%).

    stop_loss_pct = 1.5 × ATR(14) / close × 100
    低位震荡股 ~2%, 高位活跃股 ~5-7%

    Returns: stop_loss percentage (e.g. 3.5 = 3.5%), or 0 if insufficient data.

    Raises:
        RiskCheckUnavailable: if the risk DB is unreachable (caller must pause
        the loop — never return 0 which would fall back to a weaker stop, per AC-10).
    """
    import numpy as np
    try:
        async with _require_risk_engine().connect() as conn:
            result = await conn.execute(
                sa_text(
                    "SELECT high, low, close FROM daily_kline WHERE code = :code "
                    "ORDER BY trade_date DESC LIMIT 15"
                ),
                {"code": code},
            )
            rows = result.fetchall()

        if len(rows) < 14:
            return 0.0

        closes = np.array([r[2] for r in rows], dtype=np.float64)
        highs = np.array([r[0] for r in rows], dtype=np.float64)
        lows = np.array([r[1] for r in rows], dtype=np.float64)

        # ATR(14) calculation
        tr = np.maximum(highs - lows,
                        np.abs(highs - np.roll(closes, 1)),
                        np.abs(lows - np.roll(closes, 1)))
        tr[0] = highs[0] - lows[0]
        atr = np.mean(tr[:14])

        current_close = closes[0]
        if current_close > 0 and atr > 0:
            stop_pct = round(1.5 * atr / current_close * 100, 1)
            return max(2.0, min(8.0, stop_pct))  # clamp 2%~8%
        return 0.0
    except RiskCheckUnavailable:
        raise
    except Exception as e:
        logger.warning("ATR 止损检查 DB 不可达 code=%s: %s", code, e)
        raise RiskCheckUnavailable(f"atr_stop_loss DB unreachable: {e}") from e


async def _check_forecast_risk(code: str) -> str:
    """P3: 检查业绩预告风险 — 预减/预亏/首亏则阻止买入.

    Returns: warning string if risky, empty string otherwise.

    Raises:
        RiskCheckUnavailable: if the risk DB is unreachable (caller must pause
        the loop — never return "" which would allow buying, per AC-10).
    """
    try:
        async with _require_risk_engine().connect() as conn:
            result = await conn.execute(
                sa_text(
                    # NOTE: forecast_data has no change_reason column (schema
                    # drift from the original psycopg2 code which silently
                    # swallowed the error). Use forecast_net_profit as the
                    # negative-profit signal instead.
                    "SELECT forecast_type, forecast_net_profit FROM forecast_data "
                    "WHERE code = :code ORDER BY end_date DESC LIMIT 1"
                ),
                {"code": code},
            )
            row = result.fetchone()
        if row:
            ftype = str(row[0] or "")
            net_profit = row[1]
            is_loss = net_profit is not None and float(net_profit) < 0
            if any(kw in ftype for kw in ["预减", "首亏", "续亏", "预亏"]) or is_loss:
                profit_hint = f"净利={net_profit}" if is_loss else ""
                return f"{ftype}({profit_hint})" if profit_hint else ftype
        return ""
    except Exception as e:
        logger.warning("业绩预告风险检查 DB 不可达 code=%s: %s", code, e)
        raise RiskCheckUnavailable(f"forecast_risk DB unreachable: {e}") from e


async def _evaluate_sell_conditions(
    conditions: list[SellCondition],
    signal: dict,
    position: dict,
) -> tuple[bool, str]:
    """Evaluate sell conditions against signal + position data.

    Returns:
        (should_sell, reason_string)

    Raises:
        RiskCheckUnavailable: propagated from ``_get_atr_stop_loss`` when the
        risk DB is unreachable (caller pauses the loop).
    """
    if not conditions:
        return False, ""

    # Merge position data into evaluation context
    context = {**signal}
    context["pnl_pct"] = position.get("pnl_pct", 0)
    context["take_profit"] = position.get("pnl_pct", 0) if position.get("pnl_pct", 0) > 0 else 0

    # ── P4: ATR 动态止损 (替代硬编码 3%) ──
    code = position.get("code", "")
    dynamic_stop = await _get_atr_stop_loss(code)
    if dynamic_stop > 0:
        context["stop_loss"] = dynamic_stop
    else:
        context["stop_loss"] = abs(position.get("pnl_pct", 0)) if position.get("pnl_pct", 0) < 0 else 0

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

def _build_auto_order_lineage(
    strategy: StrategyConfig,
    symbol: str,
    direction: str,
    pick: dict | None = None,
) -> dict:
    """Build lineage IDs for strategy-service submitted orders."""
    source_plan_id = (pick or {}).get("plan_id") or strategy.source_scheme_id or strategy.id
    candidate_id = (pick or {}).get("candidate_id") or (pick or {}).get("id")
    context_suffix = int(time.time())
    return {
        "decision_context_id": f"CTX-auto-{strategy.id}-{symbol}-{context_suffix}",
        "candidate_id": candidate_id,
        "plan_id": source_plan_id,
    }

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


async def _http_post_json(url: str, payload: dict, timeout: int = 10) -> dict:
    """Async HTTP POST with JSON body, returning parsed JSON."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_post_json, url, payload, timeout)
    except Exception as e:
        logger.warning("HTTP POST %s failed: %s", url, e)
        return {"error": str(e)}


def _sync_post_json(url: str, payload: dict, timeout: int) -> dict:
    """Synchronous urllib POST with JSON body."""
    body = json.dumps({k: v for k, v in payload.items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8") if e.fp else ""
        logger.warning("HTTP POST %s → %s: %s", url, e.code, body_text)
        return {"error": f"HTTP {e.code}", "detail": body_text}
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
    decision_context_id: str | None = None,
    candidate_id: str | None = None,
    plan_id: str | None = None,
) -> dict:
    """Place an order via trade-service."""
    params = {
        "code": symbol,
        "direction": direction,
        "price": price,
        "volume": volume,
        "trade_mode": trade_mode,
        "decision_context_id": decision_context_id,
        "candidate_id": candidate_id,
        "plan_id": plan_id,
    }
    url = f"{TRADE_SERVICE_URL}/api/v1/trade/order"
    return await _http_post_json(url, params)


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
