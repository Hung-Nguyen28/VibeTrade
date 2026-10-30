"""Order Execution & Constraint Simulator for Micro-Portfolio ($10.0).

Enforces:
1. Exact 3 UTC timestamps: candle_close_time, signal_timestamp, execution_timestamp.
2. LIVE_PAPER schedule drift cost tracking (comparing candle close price vs live fill price).
3. BACKTEST mode next-candle Open execution.
4. OKX Spot step size rounding (lot_size) and tick_size precision.
5. REJECTED_BY_CONSTRAINT transparent logging (never silently drop).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Mapping

from src.vibetrade.data.okx_models import (
    ClosedCandle,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
)
from src.vibetrade.paper.models import (
    OpenPosition,
    RejectedOrderRecord,
)

DEFAULT_FEE_RATE = Decimal("0.001")  # 0.10% each side
DEFAULT_INITIAL_BALANCE = Decimal("10.0")
_BPS_DIVISOR = Decimal("10000.0")


class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    LIVE_PAPER = "LIVE_PAPER"


@dataclass(frozen=True)
class PaperTradingConfig:
    initial_balance: Decimal = DEFAULT_INITIAL_BALANCE
    fee_rate: Decimal = DEFAULT_FEE_RATE
    slippage_model: str = "spread_plus_latency"
    minimum_order_check: bool = True
    default_latency_slippage_bps: Decimal = Decimal("2.0")

    def __post_init__(self) -> None:
        if self.initial_balance <= Decimal(0):
            raise ValueError("initial_balance must be > 0")
        if self.fee_rate < Decimal(0):
            raise ValueError("fee_rate must be >= 0")


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of attempting to execute an order."""

    success: bool
    position: OpenPosition | None
    rejected_record: RejectedOrderRecord | None
    cash_delta_usdt: Decimal  # negative for purchases (notional + fee)


def round_down_lot(qty: Decimal, lot_size: Decimal) -> Decimal:
    """Round quantity down to nearest lot_size multiple."""
    factor = (qty / lot_size).to_integral_value(rounding=ROUND_DOWN)
    return factor * lot_size


def round_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round price to nearest tick_size."""
    factor = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return factor * tick_size


def simulate_order_execution(
    inst_rule: SpotInstrumentRule,
    orderbook: OrderBookLiquiditySnapshot,
    signal_id: str,
    proposed_notional_usdt: Decimal,
    candle_close_time: int,
    signal_timestamp: int,
    execution_timestamp: int,
    available_cash_usdt: Decimal,
    price_at_candle_close: Decimal,
    mode: ExecutionMode = ExecutionMode.LIVE_PAPER,
    next_candle_open: Decimal | None = None,
    config: PaperTradingConfig | None = None,
) -> ExecutionResult:
    """Execute a proposed spot BUY order with 3-timestamp tracking and OKX constraints."""
    cfg = config or PaperTradingConfig()
    order_id = f"ord:{signal_id}:{execution_timestamp}"

    # 1. Determine Base Reference Price & Execution Fill Price
    if mode == ExecutionMode.LIVE_PAPER:
        # Live Paper mode: Must fill against orderbook at execution_timestamp
        base_fill_px = orderbook.best_ask
        slippage_bps = (
            orderbook.est_buy_slippage_bps
            if orderbook.est_buy_slippage_bps is not None
            else cfg.default_latency_slippage_bps
        )
        fill_price = base_fill_px * (Decimal("1.0") + (slippage_bps / _BPS_DIVISOR))
        schedule_drift_ms = execution_timestamp - candle_close_time
        if price_at_candle_close > Decimal(0):
            schedule_drift_bps = (fill_price - price_at_candle_close) / price_at_candle_close * _BPS_DIVISOR
        else:
            schedule_drift_bps = Decimal("0.00")
    else:
        # Backtest mode: Reference is next candle's open
        if next_candle_open is None or next_candle_open <= Decimal(0):
            ref_px = price_at_candle_close
        else:
            ref_px = next_candle_open
        slippage_bps = cfg.default_latency_slippage_bps
        fill_price = ref_px * (Decimal("1.0") + (slippage_bps / _BPS_DIVISOR))
        schedule_drift_ms = 0
        schedule_drift_bps = Decimal("0.00")

    fill_price = round_tick(fill_price, inst_rule.tick_size)

    # 2. Check Orderbook Depth Absorption
    if not orderbook.buy_fully_filled:
        rej = RejectedOrderRecord(
            order_id=order_id,
            signal_id=signal_id,
            inst_id=inst_rule.inst_id,
            side="BUY",
            proposed_notional_usdt=proposed_notional_usdt,
            constraint_code="ORDERBOOK_DEPTH_UNAVAILABLE",
            details="Orderbook could not fully fill probe notional",
            timestamp_ms=execution_timestamp,
        )
        return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 3. Round Base Quantity by lot_size
    raw_qty = proposed_notional_usdt / fill_price
    qty_base = round_down_lot(raw_qty, inst_rule.lot_size)

    # 4. OKX Min Size Constraint Check
    if cfg.minimum_order_check and qty_base < inst_rule.min_size:
        min_notional_needed = inst_rule.min_size * fill_price
        rej = RejectedOrderRecord(
            order_id=order_id,
            signal_id=signal_id,
            inst_id=inst_rule.inst_id,
            side="BUY",
            proposed_notional_usdt=proposed_notional_usdt,
            constraint_code="BELOW_OKX_MIN_SIZE",
            details=(
                f"Computed qty {qty_base} < OKX minSz {inst_rule.min_size} "
                f"(requires at least {min_notional_needed:.4f} USDT at fill price {fill_price})"
            ),
            timestamp_ms=execution_timestamp,
        )
        return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 5. Financial Settlement & Cash Availability Check
    actual_notional = qty_base * fill_price
    fee_usdt = actual_notional * cfg.fee_rate
    total_cost = actual_notional + fee_usdt

    if total_cost > available_cash_usdt:
        rej = RejectedOrderRecord(
            order_id=order_id,
            signal_id=signal_id,
            inst_id=inst_rule.inst_id,
            side="BUY",
            proposed_notional_usdt=proposed_notional_usdt,
            constraint_code="INSUFFICIENT_CASH_AFTER_FEE",
            details=(
                f"Required total cash {total_cost:.6f} USDT (notional={actual_notional:.6f} + fee={fee_usdt:.6f}) "
                f"> available cash {available_cash_usdt:.6f} USDT"
            ),
            timestamp_ms=execution_timestamp,
        )
        return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 6. Schedule Drift Cost calculation
    # schedule_drift_cost = (fill_price - price_at_candle_close) * qty_base
    schedule_drift_cost = (fill_price - price_at_candle_close) * qty_base

    # 7. Create OpenPosition
    position_id = f"pos:{inst_rule.inst_id}:{execution_timestamp}"
    pos = OpenPosition(
        position_id=position_id,
        inst_id=inst_rule.inst_id,
        entry_order_id=order_id,
        entry_price=fill_price,
        qty_base=qty_base,
        notional_entry_usdt=actual_notional,
        entry_fee_usdt=fee_usdt,
        candle_close_time=candle_close_time,
        signal_timestamp=signal_timestamp,
        execution_timestamp=execution_timestamp,
        schedule_drift_ms=schedule_drift_ms,
        schedule_drift_bps=schedule_drift_bps,
        schedule_drift_cost_usdt=schedule_drift_cost,
        current_mark_price=fill_price,
        unrealized_pnl_usdt=Decimal("0.00"),
    )

    return ExecutionResult(
        success=True,
        position=pos,
        rejected_record=None,
        cash_delta_usdt=-total_cost,
    )
