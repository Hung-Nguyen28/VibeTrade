"""Immutable, finite-only domain models for the OKX Public Spot data layer (P1).

Every numeric field is a :class:`decimal.Decimal` (exchange precision is never
routed through binary floats) and every model is ``frozen=True``. ``NaN`` /
``Infinity`` / empty strings are rejected at construction so a bad exchange
payload can never reach an indicator, a scorer or a persisted snapshot.

Serialisation (``to_dict``) emits Decimals as plain-notation strings and
timestamps as integer UTC epoch milliseconds, matching
``schema/v1.1/market_snapshot.schema.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from src.vibetrade.data.bar_close import BAR_DURATION_MS, bar_duration_ms

QUOTE_CCY = "USDT"
_BPS = Decimal(10_000)
_ZERO = Decimal(0)


class ModelValidationError(ValueError):
    """Raised when an exchange payload violates a model invariant."""


def parse_decimal(value: Any, field: str) -> Decimal:
    """Parse ``value`` into a finite Decimal or raise :class:`ModelValidationError`."""
    if isinstance(value, bool) or value is None:
        raise ModelValidationError(f"{field}: not a number ({value!r})")
    if isinstance(value, Decimal):
        number = value
    else:
        text = str(value).strip()
        if not text:
            raise ModelValidationError(f"{field}: empty value")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ModelValidationError(f"{field}: not a number ({value!r})") from exc
    if not number.is_finite():
        raise ModelValidationError(f"{field}: non-finite value ({value!r})")
    return number


def _positive(value: Any, field: str) -> Decimal:
    number = parse_decimal(value, field)
    if number <= _ZERO:
        raise ModelValidationError(f"{field}: must be > 0 (got {number})")
    return number


def _non_negative(value: Any, field: str) -> Decimal:
    number = parse_decimal(value, field)
    if number < _ZERO:
        raise ModelValidationError(f"{field}: must be >= 0 (got {number})")
    return number


def parse_epoch_ms(value: Any, field: str) -> int:
    """Parse a positive integer epoch-millisecond timestamp."""
    if isinstance(value, bool):
        raise ModelValidationError(f"{field}: not an integer timestamp ({value!r})")
    try:
        ms = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ModelValidationError(f"{field}: not an integer timestamp ({value!r})") from exc
    if ms <= 0:
        raise ModelValidationError(f"{field}: must be > 0 (got {ms})")
    return ms


def dec_str(value: Decimal) -> str:
    """Plain-notation string (never exponent form) for JSON output."""
    return format(value, "f")


def _check_decimal_field(obj: Any, name: str, *, positive: bool = True) -> None:
    value = getattr(obj, name)
    if not isinstance(value, Decimal):
        raise ModelValidationError(f"{name}: must be Decimal (got {type(value).__name__})")
    if not value.is_finite():
        raise ModelValidationError(f"{name}: non-finite value")
    if positive and value <= _ZERO:
        raise ModelValidationError(f"{name}: must be > 0")
    if not positive and value < _ZERO:
        raise ModelValidationError(f"{name}: must be >= 0")


def _check_usdt_inst_id(inst_id: str) -> None:
    if not isinstance(inst_id, str) or not inst_id.endswith(f"-{QUOTE_CCY}") or inst_id.count("-") != 1:
        raise ModelValidationError(f"inst_id must be a '<BASE>-{QUOTE_CCY}' Spot pair (got {inst_id!r})")
    if inst_id != inst_id.upper():
        raise ModelValidationError(f"inst_id must be upper-case (got {inst_id!r})")


# ---------------------------------------------------------------------------
# SpotInstrumentRule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpotInstrumentRule:
    """Trading rules of one OKX Spot pair (``/public/instruments?instType=SPOT``)."""

    inst_id: str
    base_ccy: str
    quote_ccy: str
    tick_size: Decimal
    lot_size: Decimal
    min_size: Decimal
    state: str

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.quote_ccy != QUOTE_CCY:
            raise ModelValidationError(f"quote_ccy must be {QUOTE_CCY} (got {self.quote_ccy!r})")
        if self.inst_id != f"{self.base_ccy}-{self.quote_ccy}":
            raise ModelValidationError("inst_id does not match base_ccy/quote_ccy")
        for name in ("tick_size", "lot_size", "min_size"):
            _check_decimal_field(self, name)
        if not self.state:
            raise ModelValidationError("state: empty")

    @classmethod
    def from_okx(cls, row: Mapping[str, Any]) -> "SpotInstrumentRule":
        return cls(
            inst_id=str(row.get("instId", "")),
            base_ccy=str(row.get("baseCcy", "")),
            quote_ccy=str(row.get("quoteCcy", "")),
            tick_size=_positive(row.get("tickSz"), "tickSz"),
            lot_size=_positive(row.get("lotSz"), "lotSz"),
            min_size=_positive(row.get("minSz"), "minSz"),
            state=str(row.get("state", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inst_id": self.inst_id,
            "base_ccy": self.base_ccy,
            "quote_ccy": self.quote_ccy,
            "tick_size": dec_str(self.tick_size),
            "lot_size": dec_str(self.lot_size),
            "min_size": dec_str(self.min_size),
            "state": self.state,
        }


# ---------------------------------------------------------------------------
# SpotTicker24h
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpotTicker24h:
    """Top-of-book + 24h statistics of one Spot pair (``/market/tickers``)."""

    inst_id: str
    last: Decimal
    bid_px: Decimal
    bid_sz: Decimal
    ask_px: Decimal
    ask_sz: Decimal
    open_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal
    vol_base_24h: Decimal
    vol_quote_24h: Decimal
    ts_utc_ms: int

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        for name in ("last", "bid_px", "bid_sz", "ask_px", "ask_sz", "open_24h", "high_24h", "low_24h"):
            _check_decimal_field(self, name)
        for name in ("vol_base_24h", "vol_quote_24h"):
            _check_decimal_field(self, name, positive=False)
        if self.bid_px >= self.ask_px:
            raise ModelValidationError(f"{self.inst_id}: crossed/locked quote bid={self.bid_px} ask={self.ask_px}")
        if self.high_24h < self.low_24h:
            raise ModelValidationError(f"{self.inst_id}: high_24h < low_24h")
        if not isinstance(self.ts_utc_ms, int) or isinstance(self.ts_utc_ms, bool) or self.ts_utc_ms <= 0:
            raise ModelValidationError("ts_utc_ms must be a positive int")

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_px + self.ask_px) / 2

    @property
    def spread_bps(self) -> Decimal:
        return (self.ask_px - self.bid_px) / self.mid_price * _BPS

    @classmethod
    def from_okx(cls, row: Mapping[str, Any]) -> "SpotTicker24h":
        return cls(
            inst_id=str(row.get("instId", "")),
            last=_positive(row.get("last"), "last"),
            bid_px=_positive(row.get("bidPx"), "bidPx"),
            bid_sz=_positive(row.get("bidSz"), "bidSz"),
            ask_px=_positive(row.get("askPx"), "askPx"),
            ask_sz=_positive(row.get("askSz"), "askSz"),
            open_24h=_positive(row.get("open24h"), "open24h"),
            high_24h=_positive(row.get("high24h"), "high24h"),
            low_24h=_positive(row.get("low24h"), "low24h"),
            vol_base_24h=_non_negative(row.get("vol24h"), "vol24h"),
            vol_quote_24h=_non_negative(row.get("volCcy24h"), "volCcy24h"),
            ts_utc_ms=parse_epoch_ms(row.get("ts"), "ts"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inst_id": self.inst_id,
            "last": dec_str(self.last),
            "bid_px": dec_str(self.bid_px),
            "bid_sz": dec_str(self.bid_sz),
            "ask_px": dec_str(self.ask_px),
            "ask_sz": dec_str(self.ask_sz),
            "open_24h": dec_str(self.open_24h),
            "high_24h": dec_str(self.high_24h),
            "low_24h": dec_str(self.low_24h),
            "vol_base_24h": dec_str(self.vol_base_24h),
            "vol_quote_24h": dec_str(self.vol_quote_24h),
            "spread_bps": dec_str(self.spread_bps.quantize(Decimal("0.0001"))),
            "ts_utc_ms": self.ts_utc_ms,
        }


# ---------------------------------------------------------------------------
# ClosedCandle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosedCandle:
    """One fully closed OHLCV bar. An unclosed bar cannot be constructed."""

    inst_id: str
    timeframe: str
    candle_open_time: int
    candle_close_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    vol_base: Decimal
    vol_quote: Decimal
    confirm: bool = True

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.timeframe not in BAR_DURATION_MS:
            raise ModelValidationError(f"unsupported timeframe {self.timeframe!r}")
        if self.confirm is not True:
            raise ModelValidationError("ClosedCandle.confirm must be True (running candles are forbidden)")
        for name in ("candle_open_time", "candle_close_time"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ModelValidationError(f"{name} must be a positive int")
        if self.candle_close_time != self.candle_open_time + bar_duration_ms(self.timeframe):
            raise ModelValidationError("candle_close_time != candle_open_time + bar duration")
        for name in ("open", "high", "low", "close"):
            _check_decimal_field(self, name)
        for name in ("vol_base", "vol_quote"):
            _check_decimal_field(self, name, positive=False)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.high < self.low:
            raise ModelValidationError(f"{self.inst_id}@{self.candle_open_time}: OHLC invariant violated")

    @classmethod
    def from_okx_row(cls, inst_id: str, timeframe: str, row: Sequence[Any]) -> "ClosedCandle":
        """Build from an OKX candle row ``[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]``."""
        if len(row) < 9:
            raise ModelValidationError(f"candle row too short ({len(row)} < 9 columns)")
        if str(row[8]) != "1":
            raise ModelValidationError("candle is not confirmed (confirm != '1')")
        open_ms = parse_epoch_ms(row[0], "ts")
        return cls(
            inst_id=inst_id,
            timeframe=timeframe,
            candle_open_time=open_ms,
            candle_close_time=open_ms + bar_duration_ms(timeframe),
            open=_positive(row[1], "open"),
            high=_positive(row[2], "high"),
            low=_positive(row[3], "low"),
            close=_positive(row[4], "close"),
            vol_base=_non_negative(row[5], "vol"),
            vol_quote=_non_negative(row[7], "volCcyQuote"),
            confirm=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inst_id": self.inst_id,
            "timeframe": self.timeframe,
            "candle_open_time": self.candle_open_time,
            "candle_close_time": self.candle_close_time,
            "open": dec_str(self.open),
            "high": dec_str(self.high),
            "low": dec_str(self.low),
            "close": dec_str(self.close),
            "vol_base": dec_str(self.vol_base),
            "vol_quote": dec_str(self.vol_quote),
            "confirm": True,
        }


# ---------------------------------------------------------------------------
# OrderBookLiquiditySnapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderBookLiquiditySnapshot:
    """Top-N liquidity metrics and ``probe_notional_usdt`` impact cost of one book."""

    inst_id: str
    ts_utc_ms: int
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal
    spread_bps: Decimal
    depth_levels: int
    bid_depth_usdt: Decimal
    ask_depth_usdt: Decimal
    imbalance_ratio: Decimal
    probe_notional_usdt: Decimal
    est_buy_slippage_bps: Decimal | None
    est_sell_slippage_bps: Decimal | None
    buy_fully_filled: bool
    sell_fully_filled: bool

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if not isinstance(self.ts_utc_ms, int) or isinstance(self.ts_utc_ms, bool) or self.ts_utc_ms <= 0:
            raise ModelValidationError("ts_utc_ms must be a positive int")
        for name in ("best_bid", "best_ask", "mid_price", "probe_notional_usdt"):
            _check_decimal_field(self, name)
        for name in ("spread_bps", "bid_depth_usdt", "ask_depth_usdt"):
            _check_decimal_field(self, name, positive=False)
        if self.best_bid >= self.best_ask:
            raise ModelValidationError(f"{self.inst_id}: crossed/locked book")
        if not isinstance(self.imbalance_ratio, Decimal) or not (Decimal(-1) <= self.imbalance_ratio <= Decimal(1)):
            raise ModelValidationError("imbalance_ratio must be a Decimal in [-1, 1]")
        if not isinstance(self.depth_levels, int) or self.depth_levels <= 0:
            raise ModelValidationError("depth_levels must be a positive int")
        for name in ("est_buy_slippage_bps", "est_sell_slippage_bps"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise ModelValidationError(f"{name}: must be a finite Decimal or None")

    def to_dict(self) -> dict[str, Any]:
        def opt(v: Decimal | None) -> str | None:
            return None if v is None else dec_str(v)

        return {
            "inst_id": self.inst_id,
            "ts_utc_ms": self.ts_utc_ms,
            "best_bid": dec_str(self.best_bid),
            "best_ask": dec_str(self.best_ask),
            "mid_price": dec_str(self.mid_price),
            "spread_bps": dec_str(self.spread_bps),
            "depth_levels": self.depth_levels,
            "bid_depth_usdt": dec_str(self.bid_depth_usdt),
            "ask_depth_usdt": dec_str(self.ask_depth_usdt),
            "imbalance_ratio": dec_str(self.imbalance_ratio),
            "probe_notional_usdt": dec_str(self.probe_notional_usdt),
            "est_buy_slippage_bps": opt(self.est_buy_slippage_bps),
            "est_sell_slippage_bps": opt(self.est_sell_slippage_bps),
            "buy_fully_filled": self.buy_fully_filled,
            "sell_fully_filled": self.sell_fully_filled,
        }
