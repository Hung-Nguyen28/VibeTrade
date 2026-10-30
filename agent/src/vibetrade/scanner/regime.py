"""Market Regime Detector for VibeTrade v1.1.

Classifies market state into:
- BULL_TREND (multiplier 1.10)
- BEAR_TREND (multiplier 0.40)
- HIGH_VOL_CHOP (multiplier 0.60)
- RANGE_BOUND (multiplier 0.85)

Uses closed BTC-USDT bars and breadth across USDT Spot tickers.
Strictly causal: bar-close confirmed, zero lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from src.vibetrade.data.indicators import (
    assert_closed_frame,
    atr_wilder,
    candles_to_frame,
    ema,
    rsi_wilder,
)
from src.vibetrade.data.okx_models import (
    ClosedCandle,
    SpotTicker24h,
    parse_decimal,
)
from src.vibetrade.scanner.models import MarketRegimeSnapshot

REGIME_MULTIPLIERS: dict[str, Decimal] = {
    "BULL_TREND": Decimal("1.10"),
    "RANGE_BOUND": Decimal("0.85"),
    "HIGH_VOL_CHOP": Decimal("0.60"),
    "BEAR_TREND": Decimal("0.40"),
}


@dataclass(frozen=True)
class MarketRegimeConfig:
    """Configurable thresholds for market regime classification."""

    btc_inst_id: str = "BTC-USDT-SWAP"
    fast_ema_span: int = 20
    slow_ema_span: int = 50
    rsi_period: int = 14
    atr_period: int = 14
    atr_history_bars: int = 50
    high_vol_percentile: float = 80.0
    bull_rsi_threshold: float = 52.0
    bear_rsi_threshold: float = 48.0
    bull_breadth_threshold: float = 50.0
    bear_breadth_threshold: float = 45.0
    min_warmup_bars: int = 30


def compute_market_breadth(tickers: Sequence[SpotTicker24h]) -> Decimal:
    """Calculate percentage of USDT tickers with 24h gain (last >= open_24h)."""
    if not tickers:
        return Decimal("50.0")
    advancers = sum(1 for t in tickers if t.last >= t.open_24h)
    ratio = Decimal(advancers) / Decimal(len(tickers)) * Decimal(100)
    return ratio.quantize(Decimal("0.01"))


def detect_market_regime(
    btc_candles: Sequence[ClosedCandle],
    tickers: Sequence[SpotTicker24h],
    now_ms: int,
    config: MarketRegimeConfig | None = None,
) -> MarketRegimeSnapshot:
    """Detect current macro regime deterministically from closed BTC bars & tickers.

    Guarantees:
    - Never uses unconfirmed or future bars (assert_closed_frame).
    - Causal indicators (EMA, RSI, ATR).
    - Truncation invariant.
    """
    cfg = config or MarketRegimeConfig()
    breadth_pct = compute_market_breadth(tickers)

    if not btc_candles:
        # Graceful fallback when no BTC data is available
        return MarketRegimeSnapshot(
            regime="RANGE_BOUND",
            multiplier=REGIME_MULTIPLIERS["RANGE_BOUND"],
            btc_price=Decimal("100000.00"),
            btc_ema_fast=Decimal("100000.00"),
            btc_ema_slow=Decimal("100000.00"),
            btc_rsi=Decimal("50.00"),
            btc_atr_pct=Decimal("1.5000"),
            market_breadth_pct=breadth_pct,
            detected_at_utc_ms=now_ms,
            details={"fallback_reason": "NO_BTC_CANDLES"},
        )

    # Filter BTC candles and convert to causal DataFrame
    btc_list = [c for c in btc_candles if c.inst_id in {cfg.btc_inst_id, "BTC-USDT-SWAP", "BTC-USDT"}]
    if not btc_list:
        btc_list = list(btc_candles)  # caller may pass pre-filtered btc list

    frame = candles_to_frame(btc_list)
    assert_closed_frame(frame, now_ms)

    if len(frame) < cfg.min_warmup_bars:
        last_close = Decimal(str(frame["close"].iloc[-1]))
        return MarketRegimeSnapshot(
            regime="RANGE_BOUND",
            multiplier=REGIME_MULTIPLIERS["RANGE_BOUND"],
            btc_price=last_close,
            btc_ema_fast=last_close,
            btc_ema_slow=last_close,
            btc_rsi=Decimal("50.00"),
            btc_atr_pct=Decimal("1.5000"),
            market_breadth_pct=breadth_pct,
            detected_at_utc_ms=now_ms,
            details={"fallback_reason": f"INSUFFICIENT_WARMUP_BARS (have {len(frame)} < {cfg.min_warmup_bars})"},
        )

    # Compute causal indicators
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]

    ema_fast_s = ema(close, span=cfg.fast_ema_span)
    ema_slow_s = ema(close, span=cfg.slow_ema_span)
    rsi_s = rsi_wilder(close, period=cfg.rsi_period)
    atr_s = atr_wilder(high, low, close, period=cfg.atr_period)

    # Values at the last closed candle
    last_price = float(close.iloc[-1])
    fast_val = float(ema_fast_s.iloc[-1]) if pd.notna(ema_fast_s.iloc[-1]) else last_price
    slow_val = float(ema_slow_s.iloc[-1]) if pd.notna(ema_slow_s.iloc[-1]) else fast_val
    rsi_val = float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else 50.0
    atr_val = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else 0.0

    atr_pct_val = (atr_val / last_price * 100.0) if last_price > 0 else 0.0

    # ATR volatility percentile over lookback
    valid_atr = atr_s.dropna()
    lookback = min(len(valid_atr), cfg.atr_history_bars)
    if lookback > 1:
        hist_window = valid_atr.iloc[-lookback:]
        atr_rank = float((hist_window <= atr_val).mean() * 100.0)
    else:
        atr_rank = 50.0

    breadth_f = float(breadth_pct)

    # Decision Matrix
    # 1. High Volatility Chop: extreme ATR percentile without strong trend alignment,
    # or conflicting EMA alignment under elevated volatility.
    is_high_vol = atr_rank >= cfg.high_vol_percentile
    is_ema_bull = last_price > fast_val > slow_val
    is_ema_bear = last_price < fast_val < slow_val

    if is_high_vol and not (is_ema_bull and rsi_val >= cfg.bull_rsi_threshold and breadth_f >= cfg.bull_breadth_threshold):
        regime = "HIGH_VOL_CHOP"
    elif is_ema_bull and rsi_val >= cfg.bull_rsi_threshold and breadth_f >= cfg.bull_breadth_threshold:
        regime = "BULL_TREND"
    elif is_ema_bear and rsi_val <= cfg.bear_rsi_threshold and breadth_f <= cfg.bear_breadth_threshold:
        regime = "BEAR_TREND"
    elif is_high_vol:
        regime = "HIGH_VOL_CHOP"
    else:
        regime = "RANGE_BOUND"

    multiplier = REGIME_MULTIPLIERS[regime]

    return MarketRegimeSnapshot(
        regime=regime,
        multiplier=multiplier,
        btc_price=Decimal(str(round(last_price, 4))),
        btc_ema_fast=Decimal(str(round(fast_val, 4))),
        btc_ema_slow=Decimal(str(round(slow_val, 4))),
        btc_rsi=Decimal(str(round(rsi_val, 4))),
        btc_atr_pct=Decimal(str(round(atr_pct_val, 4))),
        market_breadth_pct=breadth_pct,
        detected_at_utc_ms=now_ms,
        details={
            "atr_rank_percentile": round(atr_rank, 2),
            "is_ema_bull": is_ema_bull,
            "is_ema_bear": is_ema_bear,
            "candles_analyzed": len(frame),
        },
    )
