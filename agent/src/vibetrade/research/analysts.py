"""Multi-Dimensional Quantitative Analysts for Phase P4.

Extracts normalized feature vectors across 3 causal pillars:
1. Trend & Momentum (EMA alignment, Wilder RSI, momentum slope, higher TF confirmation).
2. Volume & Volatility (RVOL, Volume Z-Score, ATR%, bar expansion ratio).
3. Microstructure & Liquidity (L2 spread, orderbook depth, buy slippage for $10, book imbalance).

Strictly causal: bar-close confirmed, zero lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from src.vibetrade.data.indicators import (
    assert_closed_frame,
    atr_wilder,
    candles_to_frame,
    ema,
    rsi_wilder,
    rvol,
    volume_zscore,
)
from src.vibetrade.data.okx_models import ClosedCandle, OrderBookLiquiditySnapshot


@dataclass(frozen=True)
class TrendMomentumMetrics:
    ema_fast: float
    ema_slow: float
    ema_alignment: str  # "BULLISH" or "BEARISH"
    rsi_14: float
    macd_slope: float
    distance_to_high_20_pct: float
    htf_trend: str  # "BULLISH", "BEARISH", or "NEUTRAL"


@dataclass(frozen=True)
class VolumeVolatilityMetrics:
    rvol_20: float
    volume_zscore: float
    atr_14: float
    atr_pct: float
    expansion_ratio: float


@dataclass(frozen=True)
class MicrostructureLiquidityMetrics:
    spread_bps: float
    est_buy_slippage_bps: float
    imbalance_ratio: float
    bid_depth_usdt: float
    buy_fully_filled: bool


@dataclass(frozen=True)
class FocusFeatureVector:
    inst_id: str
    timeframe: str
    candle_close_time: int
    trend: TrendMomentumMetrics | None
    vol: VolumeVolatilityMetrics | None
    liq: MicrostructureLiquidityMetrics | None
    missing_fields: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0 and self.trend is not None and self.vol is not None and self.liq is not None


def extract_analysts_features(
    candles_15m: Sequence[ClosedCandle],
    now_ms: int,
    orderbook: OrderBookLiquiditySnapshot | None = None,
    candles_1h: Sequence[ClosedCandle] | None = None,
    min_warmup_bars: int = 25,
) -> FocusFeatureVector:
    """Extract causal multi-pillar feature vector for an in-focus candidate."""
    missing: list[str] = []

    if not candles_15m:
        return FocusFeatureVector(
            inst_id="UNKNOWN",
            timeframe="15m",
            candle_close_time=0,
            trend=None,
            vol=None,
            liq=None,
            missing_fields=("candles_15m_empty",),
        )

    inst_id = candles_15m[0].inst_id
    timeframe = candles_15m[0].timeframe

    frame = candles_to_frame(candles_15m)
    assert_closed_frame(frame, now_ms)

    if len(frame) < min_warmup_bars:
        missing.append(f"insufficient_candles_15m ({len(frame)} < {min_warmup_bars})")

    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    volume = frame["volume"]
    cur_close_time = int(frame.index[-1].value // 1_000_000)

    # 1. Trend & Momentum extraction
    trend_metrics: TrendMomentumMetrics | None = None
    if len(frame) >= min_warmup_bars:
        ema9 = ema(close, span=9)
        ema21 = ema(close, span=21)
        rsi14 = rsi_wilder(close, period=14)

        cur_close = float(close.iloc[-1])
        cur_ema9 = float(ema9.iloc[-1])
        cur_ema21 = float(ema21.iloc[-1])
        cur_rsi = float(rsi14.iloc[-1]) if pd.notna(rsi14.iloc[-1]) else 50.0

        alignment = "BULLISH" if cur_ema9 > cur_ema21 else "BEARISH"
        # Slope: difference between EMA spread over 3 bars
        spread_series = ema9 - ema21
        slope = float(spread_series.iloc[-1] - spread_series.iloc[-3]) if len(spread_series) >= 3 else 0.0

        lookback_20 = min(20, len(high) - 1)
        prior_max = float(high.iloc[-lookback_20 - 1 : -1].max()) if lookback_20 > 0 else cur_close
        dist_high = ((prior_max - cur_close) / prior_max * 100.0) if prior_max > 0 else 0.0

        # Higher timeframe (1H) trend
        htf_trend = "NEUTRAL"
        if candles_1h:
            frame_1h = candles_to_frame(candles_1h)
            assert_closed_frame(frame_1h, now_ms)
            if len(frame_1h) >= 20:
                ema20_1h = ema(frame_1h["close"], span=20)
                if float(frame_1h["close"].iloc[-1]) > float(ema20_1h.iloc[-1]):
                    htf_trend = "BULLISH"
                else:
                    htf_trend = "BEARISH"

        trend_metrics = TrendMomentumMetrics(
            ema_fast=cur_ema9,
            ema_slow=cur_ema21,
            ema_alignment=alignment,
            rsi_14=cur_rsi,
            macd_slope=slope,
            distance_to_high_20_pct=dist_high,
            htf_trend=htf_trend,
        )

    # 2. Volume & Volatility extraction
    vol_metrics: VolumeVolatilityMetrics | None = None
    if len(frame) >= min_warmup_bars:
        rvol_s = rvol(volume, window=20)
        zscore_s = volume_zscore(volume, window=20)
        atr_s = atr_wilder(high, low, close, period=14)

        cur_close = float(close.iloc[-1])
        cur_rvol = float(rvol_s.iloc[-1]) if pd.notna(rvol_s.iloc[-1]) else 1.0
        cur_zscore = float(zscore_s.iloc[-1]) if pd.notna(zscore_s.iloc[-1]) else 0.0
        cur_atr = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else 0.0
        cur_range = float(high.iloc[-1] - low.iloc[-1])
        expansion = (cur_range / cur_atr) if cur_atr > 0 else 1.0
        atr_pct = (cur_atr / cur_close * 100.0) if cur_close > 0 else 0.0

        vol_metrics = VolumeVolatilityMetrics(
            rvol_20=cur_rvol,
            volume_zscore=cur_zscore,
            atr_14=cur_atr,
            atr_pct=atr_pct,
            expansion_ratio=expansion,
        )

    # 3. Microstructure & Liquidity extraction
    liq_metrics: MicrostructureLiquidityMetrics | None = None
    if orderbook is None:
        missing.append("orderbook_snapshot_missing")
    else:
        slippage_val = float(orderbook.est_buy_slippage_bps) if orderbook.est_buy_slippage_bps is not None else 999.0
        liq_metrics = MicrostructureLiquidityMetrics(
            spread_bps=float(orderbook.spread_bps),
            est_buy_slippage_bps=slippage_val,
            imbalance_ratio=float(orderbook.imbalance_ratio),
            bid_depth_usdt=float(orderbook.bid_depth_usdt),
            buy_fully_filled=orderbook.buy_fully_filled,
        )

    return FocusFeatureVector(
        inst_id=inst_id,
        timeframe=timeframe,
        candle_close_time=cur_close_time,
        trend=trend_metrics,
        vol=vol_metrics,
        liq=liq_metrics,
        missing_fields=tuple(missing),
    )
