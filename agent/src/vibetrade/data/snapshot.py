"""Assemble the canonical ``market_snapshot.json`` document (schema v1.1)."""

from __future__ import annotations

from typing import Any, Iterable

from src.vibetrade.data.okx_models import (
    ClosedCandle,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
    SpotTicker24h,
)

SCHEMA_VERSION = "1.1"
SOURCE = "okx_public_v5"


def build_market_snapshot(
    *,
    generated_at_utc_ms: int,
    inst_type: str | None = None,
    instruments: Iterable[SpotInstrumentRule] = (),
    tickers: Iterable[SpotTicker24h] = (),
    candles: Iterable[ClosedCandle] = (),
    orderbooks: Iterable[OrderBookLiquiditySnapshot] = (),
) -> dict[str, Any]:
    """Return a JSON-serialisable snapshot with a deterministic ordering."""
    if not isinstance(generated_at_utc_ms, int) or isinstance(generated_at_utc_ms, bool) or generated_at_utc_ms <= 0:
        raise ValueError("generated_at_utc_ms must be a positive int (UTC epoch ms)")
    inst_list = sorted(instruments, key=lambda r: r.inst_id)
    candle_list = sorted(candles, key=lambda c: (c.inst_id, c.timeframe, c.candle_open_time))
    late = [c for c in candle_list if c.candle_close_time > generated_at_utc_ms]
    if late:
        raise ValueError(
            f"{late[0].inst_id}@{late[0].candle_open_time}: candle closes after snapshot time (running candle)"
        )

    # Automatically deduce inst_type if not explicitly specified
    if inst_type is None:
        has_swap = any(r.inst_id.endswith("-SWAP") for r in inst_list) or any(c.inst_id.endswith("-SWAP") for c in candle_list)
        resolved_inst_type = "SWAP" if has_swap else "SPOT"
    else:
        resolved_inst_type = inst_type

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc_ms": generated_at_utc_ms,
        "source": SOURCE,
        "inst_type": resolved_inst_type,
        "quote_ccy": "USDT",
        "instruments": [r.to_dict() for r in inst_list],
        "tickers": [t.to_dict() for t in sorted(tickers, key=lambda t: t.inst_id)],
        "candles": [c.to_dict() for c in candle_list],
        "orderbooks": [o.to_dict() for o in sorted(orderbooks, key=lambda o: o.inst_id)],
    }
