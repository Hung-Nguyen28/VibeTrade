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

DEFAULT_FEE_RATE = Decimal("0.0005")  # 0.05% OKX Futures taker fee
DEFAULT_SPOT_FEE_RATE = Decimal("0.001")  # 0.10% OKX Spot taker fee
DEFAULT_INITIAL_BALANCE = Decimal("10.0")
DEFAULT_FUTURES_LEVERAGE = Decimal("3")
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
    default_leverage: Decimal = DEFAULT_FUTURES_LEVERAGE

    def __post_init__(self) -> None:
        if self.initial_balance <= Decimal(0):
            raise ValueError("initial_balance must be > 0")
        if self.fee_rate < Decimal(0):
            raise ValueError("fee_rate must be >= 0")
        if self.default_leverage <= Decimal(0):
            raise ValueError("default_leverage must be > 0")


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of attempting to execute an order."""

    success: bool
    position: OpenPosition | None
    rejected_record: RejectedOrderRecord | None
    cash_delta_usdt: Decimal  # negative for purchases/margin (margin + fee)


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
    side: str = "LONG",
    leverage: Decimal = DEFAULT_FUTURES_LEVERAGE,
) -> ExecutionResult:
    """Execute a proposed LONG or SHORT order with 3-timestamp tracking and OKX constraints."""
    cfg = config or PaperTradingConfig()
    order_id = f"ord:{signal_id}:{execution_timestamp}"
    norm_side = "SHORT" if side in {"SHORT", "SELL"} else "LONG"
    is_futures = inst_rule.inst_id.endswith("-SWAP") or getattr(inst_rule, "ct_val", Decimal("1")) != Decimal("1")

    # 1. Determine Base Reference Price & Execution Fill Price
    if mode == ExecutionMode.LIVE_PAPER:
        if norm_side == "SHORT":
            base_fill_px = orderbook.best_bid
            slippage_bps = (
                orderbook.est_sell_slippage_bps
                if orderbook.est_sell_slippage_bps is not None
                else cfg.default_latency_slippage_bps
            )
            # Sell fills lower on slippage
            fill_price = base_fill_px * (Decimal("1.0") - (slippage_bps / _BPS_DIVISOR))
            if price_at_candle_close > Decimal(0):
                schedule_drift_bps = (price_at_candle_close - fill_price) / price_at_candle_close * _BPS_DIVISOR
            else:
                schedule_drift_bps = Decimal("0.00")
            depth_filled = orderbook.sell_fully_filled
        else:
            base_fill_px = orderbook.best_ask
            slippage_bps = (
                orderbook.est_buy_slippage_bps
                if orderbook.est_buy_slippage_bps is not None
                else cfg.default_latency_slippage_bps
            )
            fill_price = base_fill_px * (Decimal("1.0") + (slippage_bps / _BPS_DIVISOR))
            if price_at_candle_close > Decimal(0):
                schedule_drift_bps = (fill_price - price_at_candle_close) / price_at_candle_close * _BPS_DIVISOR
            else:
                schedule_drift_bps = Decimal("0.00")
            depth_filled = orderbook.buy_fully_filled
        schedule_drift_ms = execution_timestamp - candle_close_time
    else:
        # Backtest mode
        if next_candle_open is None or next_candle_open <= Decimal(0):
            ref_px = price_at_candle_close
        else:
            ref_px = next_candle_open
        slippage_bps = cfg.default_latency_slippage_bps
        fill_price = (
            ref_px * (Decimal("1.0") - (slippage_bps / _BPS_DIVISOR))
            if norm_side == "SHORT"
            else ref_px * (Decimal("1.0") + (slippage_bps / _BPS_DIVISOR))
        )
        depth_filled = True
        schedule_drift_ms = 0
        schedule_drift_bps = Decimal("0.00")

    fill_price = round_tick(fill_price, inst_rule.tick_size)

    # 2. Check Orderbook Depth Absorption
    if not depth_filled:
        rej = RejectedOrderRecord(
            order_id=order_id,
            signal_id=signal_id,
            inst_id=inst_rule.inst_id,
            side=norm_side,
            proposed_notional_usdt=proposed_notional_usdt,
            constraint_code="ORDERBOOK_DEPTH_UNAVAILABLE",
            details=f"Orderbook could not fully fill probe notional for {norm_side}",
            timestamp_ms=execution_timestamp,
        )
        return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 3. Round Base Quantity / Contracts
    ct_val = getattr(inst_rule, "ct_val", Decimal("1"))
    ct_mult = getattr(inst_rule, "ct_mult", Decimal("1"))

    if is_futures:
        one_ct_notional = fill_price * ct_val * ct_mult
        raw_contracts = proposed_notional_usdt / one_ct_notional
        contracts = round_down_lot(raw_contracts, inst_rule.lot_size)
        qty_base = contracts * ct_val * ct_mult
        actual_notional = contracts * one_ct_notional
        effective_leverage = leverage if leverage > Decimal(0) else cfg.default_leverage
        required_margin = actual_notional / effective_leverage

        if cfg.minimum_order_check and contracts < inst_rule.min_size:
            min_notional_needed = inst_rule.min_size * one_ct_notional
            rej = RejectedOrderRecord(
                order_id=order_id,
                signal_id=signal_id,
                inst_id=inst_rule.inst_id,
                side=norm_side,
                proposed_notional_usdt=proposed_notional_usdt,
                constraint_code="BELOW_OKX_MIN_SIZE",
                details=(
                    f"Computed contracts {contracts} < OKX minSz {inst_rule.min_size} "
                    f"(requires at least {min_notional_needed:.4f} USDT at fill price {fill_price})"
                ),
                timestamp_ms=execution_timestamp,
            )
            return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))
    else:
        # Spot mode fallback
        raw_qty = proposed_notional_usdt / fill_price
        qty_base = round_down_lot(raw_qty, inst_rule.lot_size)
        contracts = qty_base
        actual_notional = qty_base * fill_price
        effective_leverage = Decimal("1")
        required_margin = actual_notional

        if cfg.minimum_order_check and qty_base < inst_rule.min_size:
            min_notional_needed = inst_rule.min_size * fill_price
            rej = RejectedOrderRecord(
                order_id=order_id,
                signal_id=signal_id,
                inst_id=inst_rule.inst_id,
                side=norm_side,
                proposed_notional_usdt=proposed_notional_usdt,
                constraint_code="BELOW_OKX_MIN_SIZE",
                details=(
                    f"Computed qty {qty_base} < OKX minSz {inst_rule.min_size} "
                    f"(requires at least {min_notional_needed:.4f} USDT at fill price {fill_price})"
                ),
                timestamp_ms=execution_timestamp,
            )
            return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 4. Fee & Financial Settlement Check
    # If caller used default fee rate on spot, preserve 0.1% for spot test backwards compatibility
    if not is_futures and cfg.fee_rate == DEFAULT_FEE_RATE:
        eff_fee_rate = DEFAULT_SPOT_FEE_RATE
    else:
        eff_fee_rate = cfg.fee_rate

    fee_usdt = actual_notional * eff_fee_rate
    total_cost = required_margin + fee_usdt

    if total_cost > available_cash_usdt:
        rej = RejectedOrderRecord(
            order_id=order_id,
            signal_id=signal_id,
            inst_id=inst_rule.inst_id,
            side=norm_side,
            proposed_notional_usdt=proposed_notional_usdt,
            constraint_code="INSUFFICIENT_CASH_AFTER_FEE",
            details=(
                f"Required total cash {total_cost:.6f} USDT (margin={required_margin:.6f} + fee={fee_usdt:.6f}) "
                f"> available cash {available_cash_usdt:.6f} USDT"
            ),
            timestamp_ms=execution_timestamp,
        )
        return ExecutionResult(success=False, position=None, rejected_record=rej, cash_delta_usdt=Decimal("0.00"))

    # 5. Schedule Drift Cost calculation
    if norm_side == "SHORT":
        schedule_drift_cost = (price_at_candle_close - fill_price) * qty_base
    else:
        schedule_drift_cost = (fill_price - price_at_candle_close) * qty_base

    # 6. Liquidation & SL/TP
    mmr = Decimal("0.01")
    if norm_side == "SHORT":
        liq_price = fill_price * (Decimal("1") + Decimal("1") / effective_leverage) / (Decimal("1") + mmr)
        sl_price = fill_price * Decimal("1.03")
        tp_price = fill_price * Decimal("0.95")
    else:
        liq_price = fill_price * (Decimal("1") - Decimal("1") / effective_leverage) / (Decimal("1") - mmr)
        sl_price = fill_price * Decimal("0.97")
        tp_price = fill_price * Decimal("1.05")

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
        side=norm_side,
        leverage=effective_leverage,
        isolated_margin_usdt=required_margin,
        contracts=contracts,
        ct_val=ct_val,
        liquidation_price=liq_price,
        stop_loss_price=sl_price,
        take_profit_price=tp_price,
        accumulated_funding_usdt=Decimal("0.00"),
    )

    return ExecutionResult(
        success=True,
        position=pos,
        rejected_record=None,
        cash_delta_usdt=-total_cost,
    )
