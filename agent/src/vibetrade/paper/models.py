"""Immutable domain models for Phase P6 — Paper Trading Micro-Portfolio ($10.0).

All currency quantities are Decimals with high precision (1e-8 for base crypto amounts,
plain decimal string serialization, zero binary float drift).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from src.vibetrade.data.okx_models import (
    ModelValidationError,
    _check_decimal_field,
    _check_usdt_inst_id,
    dec_str,
    parse_decimal,
)

SCHEMA_VERSION = "1.1"

VALID_EXIT_REASONS: frozenset[str] = frozenset(
    {"TAKE_PROFIT", "STOP_LOSS", "TIME_STOP", "SIGNAL_EXIT", "LIQUIDATED"}
)


@dataclass(frozen=True)
class RejectedOrderRecord:
    """An order rejected by OKX constraints, risk limits, or insufficient capital."""

    order_id: str
    signal_id: str
    inst_id: str
    side: str
    proposed_notional_usdt: Decimal
    constraint_code: str
    details: str
    timestamp_ms: int

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.side not in {"BUY", "SELL", "LONG", "SHORT"}:
            raise ModelValidationError(f"Invalid side {self.side!r}")
        _check_decimal_field(self, "proposed_notional_usdt")
        if not self.constraint_code or not self.order_id or not self.signal_id:
            raise ModelValidationError("Mandatory strings cannot be empty")
        if self.timestamp_ms <= 0:
            raise ModelValidationError("timestamp_ms must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "signal_id": self.signal_id,
            "inst_id": self.inst_id,
            "side": self.side,
            "proposed_notional_usdt": dec_str(self.proposed_notional_usdt.quantize(Decimal("0.0001"))),
            "constraint_code": self.constraint_code,
            "details": self.details,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class OpenPosition:
    """An active open position tracking 3 execution timestamps, schedule drift, and margin/liquidation."""

    position_id: str
    inst_id: str
    entry_order_id: str
    entry_price: Decimal
    qty_base: Decimal
    notional_entry_usdt: Decimal
    entry_fee_usdt: Decimal
    candle_close_time: int
    signal_timestamp: int
    execution_timestamp: int
    schedule_drift_ms: int
    schedule_drift_bps: Decimal
    schedule_drift_cost_usdt: Decimal
    current_mark_price: Decimal
    unrealized_pnl_usdt: Decimal
    side: str = "LONG"
    leverage: Decimal = Decimal("3")
    isolated_margin_usdt: Decimal = Decimal("0")
    contracts: Decimal = Decimal("0")
    ct_val: Decimal = Decimal("1")
    liquidation_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    take_profit_price: Decimal = Decimal("0")
    accumulated_funding_usdt: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.side not in {"LONG", "SHORT", "BUY", "SELL"}:
            raise ModelValidationError(f"Invalid side {self.side!r}")
        for name in ("entry_price", "qty_base", "notional_entry_usdt", "current_mark_price"):
            _check_decimal_field(self, name)
        _check_decimal_field(self, "entry_fee_usdt", positive=False)
        for name in ("candle_close_time", "signal_timestamp", "execution_timestamp"):
            if getattr(self, name) <= 0:
                raise ModelValidationError(f"{name} must be positive")

        # Compute defaults for futures fields if unset
        val_ct = self.ct_val if self.ct_val > Decimal(0) else Decimal("1")
        object.__setattr__(self, "ct_val", val_ct)

        if self.contracts <= Decimal(0):
            object.__setattr__(self, "contracts", self.qty_base / val_ct)

        lev = self.leverage if self.leverage > Decimal(0) else Decimal("3")
        object.__setattr__(self, "leverage", lev)

        if self.isolated_margin_usdt <= Decimal(0):
            object.__setattr__(self, "isolated_margin_usdt", self.notional_entry_usdt / lev)

        if self.liquidation_price <= Decimal(0):
            mmr = Decimal("0.01")
            if self.side in {"SHORT", "SELL"}:
                liq = self.entry_price * (Decimal("1") + Decimal("1") / lev) / (Decimal("1") + mmr)
            else:
                liq = self.entry_price * (Decimal("1") - Decimal("1") / lev) / (Decimal("1") - mmr)
            object.__setattr__(self, "liquidation_price", max(Decimal("0.00000001"), liq))

        if self.stop_loss_price <= Decimal(0):
            sl = self.entry_price * Decimal("1.03") if self.side in {"SHORT", "SELL"} else self.entry_price * Decimal("0.97")
            object.__setattr__(self, "stop_loss_price", sl)

        if self.take_profit_price <= Decimal(0):
            tp = self.entry_price * Decimal("0.95") if self.side in {"SHORT", "SELL"} else self.entry_price * Decimal("1.05")
            object.__setattr__(self, "take_profit_price", tp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "inst_id": self.inst_id,
            "entry_order_id": self.entry_order_id,
            "side": self.side,
            "entry_price": dec_str(self.entry_price.quantize(Decimal("0.00000001"))),
            "qty_base": dec_str(self.qty_base.quantize(Decimal("0.00000001"))),
            "contracts": dec_str(self.contracts.quantize(Decimal("0.00000001"))),
            "ct_val": dec_str(self.ct_val.quantize(Decimal("0.00000001"))),
            "leverage": dec_str(self.leverage.quantize(Decimal("0.01"))),
            "isolated_margin_usdt": dec_str(self.isolated_margin_usdt.quantize(Decimal("0.0001"))),
            "notional_entry_usdt": dec_str(self.notional_entry_usdt.quantize(Decimal("0.0001"))),
            "entry_fee_usdt": dec_str(self.entry_fee_usdt.quantize(Decimal("0.00000001"))),
            "candle_close_time": self.candle_close_time,
            "signal_timestamp": self.signal_timestamp,
            "execution_timestamp": self.execution_timestamp,
            "schedule_drift_ms": self.schedule_drift_ms,
            "schedule_drift_bps": dec_str(self.schedule_drift_bps.quantize(Decimal("0.01"))),
            "schedule_drift_cost_usdt": dec_str(self.schedule_drift_cost_usdt.quantize(Decimal("0.00000001"))),
            "current_mark_price": dec_str(self.current_mark_price.quantize(Decimal("0.00000001"))),
            "liquidation_price": dec_str(self.liquidation_price.quantize(Decimal("0.00000001"))),
            "stop_loss_price": dec_str(self.stop_loss_price.quantize(Decimal("0.00000001"))),
            "take_profit_price": dec_str(self.take_profit_price.quantize(Decimal("0.00000001"))),
            "accumulated_funding_usdt": dec_str(self.accumulated_funding_usdt.quantize(Decimal("0.00000001"))),
            "unrealized_pnl_usdt": dec_str(self.unrealized_pnl_usdt.quantize(Decimal("0.00000001"))),
        }


@dataclass(frozen=True)
class ClosedTradeRecord:
    """Historical completed trade record with exact fee deductions and realized PnL."""

    trade_id: str
    position_id: str
    inst_id: str
    entry_price: Decimal
    exit_price: Decimal
    qty_base: Decimal
    entry_fee_usdt: Decimal
    exit_fee_usdt: Decimal
    gross_pnl_usdt: Decimal
    net_realized_pnl_usdt: Decimal
    schedule_drift_cost_usdt: Decimal
    entry_timestamp: int
    exit_timestamp: int
    exit_reason: str
    side: str = "LONG"

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.side not in {"LONG", "SHORT", "BUY", "SELL"}:
            raise ModelValidationError(f"Invalid side {self.side!r}")
        for name in ("entry_price", "exit_price", "qty_base"):
            _check_decimal_field(self, name)
        for name in ("entry_fee_usdt", "exit_fee_usdt"):
            _check_decimal_field(self, name, positive=False)
        if self.exit_reason not in VALID_EXIT_REASONS:
            raise ModelValidationError(f"Invalid exit_reason {self.exit_reason!r}")
        if self.entry_timestamp <= 0 or self.exit_timestamp <= 0:
            raise ModelValidationError("Timestamps must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "position_id": self.position_id,
            "inst_id": self.inst_id,
            "side": self.side,
            "entry_price": dec_str(self.entry_price.quantize(Decimal("0.00000001"))),
            "exit_price": dec_str(self.exit_price.quantize(Decimal("0.00000001"))),
            "qty_base": dec_str(self.qty_base.quantize(Decimal("0.00000001"))),
            "entry_fee_usdt": dec_str(self.entry_fee_usdt.quantize(Decimal("0.00000001"))),
            "exit_fee_usdt": dec_str(self.exit_fee_usdt.quantize(Decimal("0.00000001"))),
            "gross_pnl_usdt": dec_str(self.gross_pnl_usdt.quantize(Decimal("0.00000001"))),
            "net_realized_pnl_usdt": dec_str(self.net_realized_pnl_usdt.quantize(Decimal("0.00000001"))),
            "schedule_drift_cost_usdt": dec_str(self.schedule_drift_cost_usdt.quantize(Decimal("0.00000001"))),
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "exit_reason": self.exit_reason,
        }


@dataclass(frozen=True)
class PaperPortfolioSnapshot:
    """Canonical document conforming to schema/v1.1/paper_portfolio.schema.json."""

    schema_version: str
    generated_at_utc_ms: int
    initial_balance_usdt: Decimal
    cash_balance_usdt: Decimal
    total_equity_usdt: Decimal
    cumulative_realized_pnl_usdt: Decimal
    total_unrealized_pnl_usdt: Decimal
    total_fees_paid_usdt: Decimal
    total_schedule_drift_cost_usdt: Decimal
    open_positions: tuple[OpenPosition, ...]
    closed_trades: tuple[ClosedTradeRecord, ...]
    rejected_orders: tuple[RejectedOrderRecord, ...]
    total_funding_fees_usdt: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
        if self.generated_at_utc_ms <= 0:
            raise ModelValidationError("generated_at_utc_ms must be positive")
        _check_decimal_field(self, "initial_balance_usdt")
        _check_decimal_field(self, "cash_balance_usdt", positive=False)
        _check_decimal_field(self, "total_equity_usdt", positive=False)
        _check_decimal_field(self, "total_fees_paid_usdt", positive=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at_utc_ms": self.generated_at_utc_ms,
            "initial_balance_usdt": dec_str(self.initial_balance_usdt.quantize(Decimal("0.0001"))),
            "cash_balance_usdt": dec_str(self.cash_balance_usdt.quantize(Decimal("0.00000001"))),
            "total_equity_usdt": dec_str(self.total_equity_usdt.quantize(Decimal("0.00000001"))),
            "cumulative_realized_pnl_usdt": dec_str(self.cumulative_realized_pnl_usdt.quantize(Decimal("0.00000001"))),
            "total_unrealized_pnl_usdt": dec_str(self.total_unrealized_pnl_usdt.quantize(Decimal("0.00000001"))),
            "total_fees_paid_usdt": dec_str(self.total_fees_paid_usdt.quantize(Decimal("0.00000001"))),
            "total_schedule_drift_cost_usdt": dec_str(self.total_schedule_drift_cost_usdt.quantize(Decimal("0.00000001"))),
            "total_funding_fees_usdt": dec_str(self.total_funding_fees_usdt.quantize(Decimal("0.00000001"))),
            "open_positions": [p.to_dict() for p in self.open_positions],
            "closed_trades": [t.to_dict() for t in self.closed_trades],
            "rejected_orders": [r.to_dict() for r in self.rejected_orders],
        }
