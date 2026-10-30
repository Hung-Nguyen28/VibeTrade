"""Order-book liquidity metrics (P1) — Decimal port of ``_walk_book`` without ``ccxt``.

Inherits the semantics of ``agent/src/tools/orderbook_depth_tool.py``:

* rows with non-finite / non-positive price or size are dropped;
* either side empty -> error (never guess a mid price);
* crossed or locked book -> error;
* the probe order is sized once from the pre-trade mid (``qty = notional / mid``)
  and walks the ask ladder (buy) / bid ladder (sell);
* partial fills are reported (``*_fully_filled = False``), never disguised.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from src.vibetrade.data.okx_models import (
    ModelValidationError,
    OrderBookLiquiditySnapshot,
    parse_decimal,
    parse_epoch_ms,
)

_BPS = Decimal(10_000)
_ZERO = Decimal(0)
_BPS_QUANT = Decimal("0.0001")
_RATIO_QUANT = Decimal("0.00000001")

Level = tuple[Decimal, Decimal]


class OrderBookError(ValueError):
    """Raised for an unusable book (empty side, crossed/locked, malformed)."""


def clean_levels(raw: Any) -> list[Level]:
    """Normalise OKX ``[[px, sz, ...], ...]`` rows into ``(price, size)`` Decimals.

    Malformed / non-finite / non-positive rows are skipped.
    """
    out: list[Level] = []
    if not isinstance(raw, (list, tuple)):
        return out
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            price = parse_decimal(row[0], "price")
            size = parse_decimal(row[1], "size")
        except ModelValidationError:
            continue
        if price <= _ZERO or size <= _ZERO:
            continue
        out.append((price, size))
    return out


def walk_book(levels: Sequence[Level], base_qty_target: Decimal) -> dict[str, Any]:
    """Consume ``levels`` (best price first) until ``base_qty_target`` is filled."""
    remaining = base_qty_target
    base_filled = _ZERO
    quote_filled = _ZERO
    levels_used = 0
    for price, size in levels:
        if remaining <= _ZERO:
            break
        take = min(size, remaining)
        base_filled += take
        quote_filled += take * price
        remaining -= take
        levels_used += 1
    return {
        "filled_base_qty": base_filled,
        "filled_notional_quote": quote_filled,
        "avg_price": (quote_filled / base_filled) if base_filled > _ZERO else None,
        "levels_used": levels_used,
        "fully_filled": remaining <= _ZERO,
        "unfilled_base_qty": max(remaining, _ZERO),
    }


def build_orderbook_snapshot(
    inst_id: str,
    book: Mapping[str, Any],
    *,
    depth_levels: int = 20,
    probe_notional_usdt: Decimal = Decimal("10"),
) -> OrderBookLiquiditySnapshot:
    """Build an :class:`OrderBookLiquiditySnapshot` from one OKX ``/market/books`` entry."""
    if depth_levels <= 0:
        raise OrderBookError("depth_levels must be positive")
    if probe_notional_usdt <= _ZERO or not probe_notional_usdt.is_finite():
        raise OrderBookError("probe_notional_usdt must be a finite positive Decimal")

    bids = sorted(clean_levels(book.get("bids")), key=lambda lv: lv[0], reverse=True)
    asks = sorted(clean_levels(book.get("asks")), key=lambda lv: lv[0])
    if not bids or not asks:
        raise OrderBookError(f"{inst_id}: empty book side (bids={len(bids)}, asks={len(asks)})")

    best_bid, best_ask = bids[0][0], asks[0][0]
    if best_bid >= best_ask:
        raise OrderBookError(f"{inst_id}: crossed/locked book bid={best_bid} ask={best_ask}")

    try:
        ts_ms = parse_epoch_ms(book.get("ts"), "ts")
    except ModelValidationError as exc:
        raise OrderBookError(f"{inst_id}: book has no usable timestamp: {exc}") from exc

    mid = (best_bid + best_ask) / 2
    spread_bps = ((best_ask - best_bid) / mid * _BPS).quantize(_BPS_QUANT, rounding=ROUND_HALF_UP)

    top_bids, top_asks = bids[:depth_levels], asks[:depth_levels]
    bid_depth = sum((p * s for p, s in top_bids), _ZERO)
    ask_depth = sum((p * s for p, s in top_asks), _ZERO)
    total = bid_depth + ask_depth
    imbalance = ((bid_depth - ask_depth) / total).quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)

    target_qty = probe_notional_usdt / mid
    buy = walk_book(asks, target_qty)
    sell = walk_book(bids, target_qty)

    buy_slip = (
        ((buy["avg_price"] - mid) / mid * _BPS).quantize(_BPS_QUANT, rounding=ROUND_HALF_UP)
        if buy["avg_price"] is not None
        else None
    )
    sell_slip = (
        ((mid - sell["avg_price"]) / mid * _BPS).quantize(_BPS_QUANT, rounding=ROUND_HALF_UP)
        if sell["avg_price"] is not None
        else None
    )

    return OrderBookLiquiditySnapshot(
        inst_id=inst_id,
        ts_utc_ms=ts_ms,
        best_bid=best_bid,
        best_ask=best_ask,
        mid_price=mid,
        spread_bps=spread_bps,
        depth_levels=depth_levels,
        bid_depth_usdt=bid_depth,
        ask_depth_usdt=ask_depth,
        imbalance_ratio=imbalance,
        probe_notional_usdt=probe_notional_usdt,
        est_buy_slippage_bps=buy_slip,
        est_sell_slippage_bps=sell_slip,
        buy_fully_filled=buy["fully_filled"],
        sell_fully_filled=sell["fully_filled"],
    )
