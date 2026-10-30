"""Independent DataAuditor for Phase P5.

Verifies input data integrity before research verdicts are trusted:
1. Every candle has confirm == True.
2. Every candle close time <= audit_utc_ms (zero running candles).
3. Monotonic, continuous time series with exact interval spacing (no missing/skipped bars).
4. Data freshness check (no excessive lag).
5. L2 orderbook sanity (bid < ask, no NaN/Inf, positive depths, non-future timestamp).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from src.vibetrade.data.bar_close import bar_duration_ms
from src.vibetrade.data.okx_models import ClosedCandle, OrderBookLiquiditySnapshot
from src.vibetrade.verification.models import DataAuditReport

DEFAULT_MAX_STALENESS_MS = 2 * 60 * 60 * 1000  # 2 hours


class DataAuditor:
    """Independent auditor validating market data inputs against lookahead, gaps, and corruptions."""

    def __init__(self, max_staleness_ms: int = DEFAULT_MAX_STALENESS_MS) -> None:
        self.max_staleness_ms = max_staleness_ms

    def audit_focus_inputs(
        self,
        candles: Sequence[ClosedCandle],
        orderbook: OrderBookLiquiditySnapshot | None,
        audit_utc_ms: int,
    ) -> DataAuditReport:
        violations: list[str] = []
        details: dict[str, str] = {}

        # 1. Candle Sequence Validation
        if not candles:
            violations.append("EMPTY_CANDLE_SEQUENCE")
        else:
            timeframe = candles[0].timeframe
            expected_interval = bar_duration_ms(timeframe)

            for idx, c in enumerate(candles):
                # (a) Confirmation check
                if not c.confirm:
                    violations.append(f"UNCONFIRMED_CANDLE_AT_INDEX_{idx}")
                # (b) Running candle / Lookahead check
                if c.candle_close_time > audit_utc_ms:
                    violations.append(f"FUTURE_CANDLE_CLOSE_AT_INDEX_{idx}")
                # (c) Finite numeric check
                for field in ("open", "high", "low", "close", "vol_base", "vol_quote"):
                    val = getattr(c, field)
                    if not isinstance(val, Decimal) or not val.is_finite():
                        violations.append(f"NON_FINITE_DECIMAL_{field.upper()}_AT_INDEX_{idx}")

            # Time continuity check
            for i in range(len(candles) - 1):
                prev_bar = candles[i]
                next_bar = candles[i + 1]
                expected_open = prev_bar.candle_open_time + expected_interval
                if next_bar.candle_open_time != expected_open:
                    violations.append(
                        f"TIME_DISCONTINUITY_BETWEEN_{prev_bar.candle_open_time}_AND_{next_bar.candle_open_time}"
                    )

            # Staleness check on last closed bar
            last_close = candles[-1].candle_close_time
            if (audit_utc_ms - last_close) > self.max_staleness_ms:
                violations.append("CANDLE_DATA_TOO_STALE")
                details["last_close_ms"] = str(last_close)
                details["audit_utc_ms"] = str(audit_utc_ms)

        # 2. OrderBook Validation
        if orderbook is None:
            violations.append("MISSING_ORDERBOOK")
        else:
            if orderbook.best_bid >= orderbook.best_ask:
                violations.append("CROSSED_ORDERBOOK")
            if orderbook.ts_utc_ms > audit_utc_ms:
                violations.append("FUTURE_ORDERBOOK_TIMESTAMP")
            if not orderbook.best_bid.is_finite() or not orderbook.best_ask.is_finite():
                violations.append("NON_FINITE_ORDERBOOK_PRICES")
            if orderbook.bid_depth_usdt < Decimal(0) or orderbook.ask_depth_usdt < Decimal(0):
                violations.append("NEGATIVE_ORDERBOOK_DEPTH")

        passed = len(violations) == 0
        return DataAuditReport(
            passed=passed,
            violations=tuple(violations),
            details=details,
        )
