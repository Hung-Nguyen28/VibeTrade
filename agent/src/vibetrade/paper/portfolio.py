"""Paper Portfolio State Management for Micro-Portfolio ($10.0).

Strictly isolates:
1. realized_pnl_usdt (closed trades after both buy and sell fees).
2. unrealized_pnl_usdt (mark-to-market open position evaluation).
3. Total equity invariant: total_equity == cash + market_value_of_open_positions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

from src.vibetrade.paper.execution import ExecutionResult
from src.vibetrade.paper.models import (
    ClosedTradeRecord,
    OpenPosition,
    PaperPortfolioSnapshot,
    RejectedOrderRecord,
)

DEFAULT_PORTFOLIO_BALANCE = Decimal("10.0")


class PaperPortfolio:
    """Micro-portfolio holding cash, positions, trade logs, and fee accounting."""

    def __init__(
        self,
        initial_balance_usdt: Decimal = DEFAULT_PORTFOLIO_BALANCE,
        cash_balance_usdt: Decimal | None = None,
        open_positions: Mapping[str, OpenPosition] | None = None,
        closed_trades: Sequence[ClosedTradeRecord] | None = None,
        rejected_orders: Sequence[RejectedOrderRecord] | None = None,
        cumulative_realized_pnl_usdt: Decimal = Decimal("0.00"),
        total_fees_paid_usdt: Decimal = Decimal("0.00"),
        total_schedule_drift_cost_usdt: Decimal = Decimal("0.00"),
    ) -> None:
        self.initial_balance_usdt = initial_balance_usdt
        self.cash_balance_usdt = cash_balance_usdt if cash_balance_usdt is not None else initial_balance_usdt
        self._open_positions: dict[str, OpenPosition] = dict(open_positions or {})
        self._closed_trades: list[ClosedTradeRecord] = list(closed_trades or [])
        self._rejected_orders: list[RejectedOrderRecord] = list(rejected_orders or [])
        self.cumulative_realized_pnl_usdt = cumulative_realized_pnl_usdt
        self.total_fees_paid_usdt = total_fees_paid_usdt
        self.total_schedule_drift_cost_usdt = total_schedule_drift_cost_usdt
        self.peak_equity_usdt = max(self.initial_balance_usdt, self.total_equity_usdt)

    @property
    def open_positions(self) -> dict[str, OpenPosition]:
        return dict(self._open_positions)

    @property
    def closed_trades(self) -> list[ClosedTradeRecord]:
        return list(self._closed_trades)

    @property
    def rejected_orders(self) -> list[RejectedOrderRecord]:
        return list(self._rejected_orders)

    @property
    def total_unrealized_pnl_usdt(self) -> Decimal:
        return sum((p.unrealized_pnl_usdt for p in self._open_positions.values()), Decimal("0.00"))

    @property
    def total_market_value_usdt(self) -> Decimal:
        return sum((p.qty_base * p.current_mark_price for p in self._open_positions.values()), Decimal("0.00"))

    @property
    def total_equity_usdt(self) -> Decimal:
        return self.cash_balance_usdt + self.total_market_value_usdt

    @property
    def current_drawdown_pct(self) -> Decimal:
        cur_equity = self.total_equity_usdt
        if self.peak_equity_usdt <= Decimal(0):
            return Decimal("0.00")
        if cur_equity >= self.peak_equity_usdt:
            self.peak_equity_usdt = cur_equity
            return Decimal("0.00")
        dd = (self.peak_equity_usdt - cur_equity) / self.peak_equity_usdt * Decimal("100.00")
        return dd.quantize(Decimal("0.01"))

    def record_rejected_order(self, record: RejectedOrderRecord) -> None:
        self._rejected_orders.append(record)

    def open_position(self, result: ExecutionResult) -> None:
        """Apply a successful buy order execution to the portfolio."""
        if not result.success or result.position is None:
            raise ValueError("Cannot open position from unsuccessful ExecutionResult")
        pos = result.position
        if pos.inst_id in self._open_positions:
            raise KeyError(f"Position for {pos.inst_id} is already open")

        # Deduct cash (cash_delta_usdt is negative)
        self.cash_balance_usdt += result.cash_delta_usdt
        self.total_fees_paid_usdt += pos.entry_fee_usdt
        self.total_schedule_drift_cost_usdt += pos.schedule_drift_cost_usdt
        self._open_positions[pos.inst_id] = pos

        # Update peak equity
        if self.total_equity_usdt > self.peak_equity_usdt:
            self.peak_equity_usdt = self.total_equity_usdt

    def close_position(
        self,
        inst_id: str,
        exit_price: Decimal,
        exit_timestamp: int,
        exit_reason: str,
        fee_rate: Decimal = Decimal("0.001"),
    ) -> ClosedTradeRecord:
        """Close an existing spot position, realizing PnL and applying exit fee."""
        if inst_id not in self._open_positions:
            raise KeyError(f"No open position found for {inst_id}")

        pos = self._open_positions.pop(inst_id)
        exit_notional = pos.qty_base * exit_price
        exit_fee = exit_notional * fee_rate
        net_cash_returned = exit_notional - exit_fee

        self.cash_balance_usdt += net_cash_returned
        self.total_fees_paid_usdt += exit_fee

        gross_pnl = (exit_price - pos.entry_price) * pos.qty_base
        net_realized_pnl = gross_pnl - pos.entry_fee_usdt - exit_fee
        self.cumulative_realized_pnl_usdt += net_realized_pnl

        trade_id = f"trd:{inst_id}:{exit_timestamp}"
        record = ClosedTradeRecord(
            trade_id=trade_id,
            position_id=pos.position_id,
            inst_id=inst_id,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty_base=pos.qty_base,
            entry_fee_usdt=pos.entry_fee_usdt,
            exit_fee_usdt=exit_fee,
            gross_pnl_usdt=gross_pnl,
            net_realized_pnl_usdt=net_realized_pnl,
            schedule_drift_cost_usdt=pos.schedule_drift_cost_usdt,
            entry_timestamp=pos.execution_timestamp,
            exit_timestamp=exit_timestamp,
            exit_reason=exit_reason,
        )
        self._closed_trades.append(record)

        if self.total_equity_usdt > self.peak_equity_usdt:
            self.peak_equity_usdt = self.total_equity_usdt

        return record

    def update_mark_prices(self, mark_prices: Mapping[str, Decimal]) -> None:
        """Update mark-to-market prices for all open positions."""
        for inst_id, mark_px in mark_prices.items():
            if inst_id in self._open_positions:
                pos = self._open_positions[inst_id]
                unrealized = (mark_px - pos.entry_price) * pos.qty_base
                # Create updated open position
                self._open_positions[inst_id] = OpenPosition(
                    position_id=pos.position_id,
                    inst_id=pos.inst_id,
                    entry_order_id=pos.entry_order_id,
                    entry_price=pos.entry_price,
                    qty_base=pos.qty_base,
                    notional_entry_usdt=pos.notional_entry_usdt,
                    entry_fee_usdt=pos.entry_fee_usdt,
                    candle_close_time=pos.candle_close_time,
                    signal_timestamp=pos.signal_timestamp,
                    execution_timestamp=pos.execution_timestamp,
                    schedule_drift_ms=pos.schedule_drift_ms,
                    schedule_drift_bps=pos.schedule_drift_bps,
                    schedule_drift_cost_usdt=pos.schedule_drift_cost_usdt,
                    current_mark_price=mark_px,
                    unrealized_pnl_usdt=unrealized,
                )

        if self.total_equity_usdt > self.peak_equity_usdt:
            self.peak_equity_usdt = self.total_equity_usdt

    def snapshot(self, now_ms: int) -> PaperPortfolioSnapshot:
        """Generate canonical PaperPortfolioSnapshot."""
        return PaperPortfolioSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=now_ms,
            initial_balance_usdt=self.initial_balance_usdt,
            cash_balance_usdt=self.cash_balance_usdt,
            total_equity_usdt=self.total_equity_usdt,
            cumulative_realized_pnl_usdt=self.cumulative_realized_pnl_usdt,
            total_unrealized_pnl_usdt=self.total_unrealized_pnl_usdt,
            total_fees_paid_usdt=self.total_fees_paid_usdt,
            total_schedule_drift_cost_usdt=self.total_schedule_drift_cost_usdt,
            open_positions=tuple(sorted(self._open_positions.values(), key=lambda p: p.inst_id)),
            closed_trades=tuple(sorted(self._closed_trades, key=lambda t: (-t.exit_timestamp, t.trade_id))),
            rejected_orders=tuple(sorted(self._rejected_orders, key=lambda r: (-r.timestamp_ms, r.order_id))),
        )
