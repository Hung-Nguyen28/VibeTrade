"""Surveillance Anomaly Scanner for VibeTrade v1.1 (15m Surveillance Routine).

Scans closed OHLCV bars across tradable universe instruments for:
1. VOLUME_SPIKE: Relative Volume (RVOL) or Volume Z-Score surge.
2. VOLATILITY_EXPANSION: Bar range expands significantly above ATR14.
3. BREAKOUT: Local 20-bar resistance breakout on strong volume/close.
4. MOMENTUM_SHIFT: Short-term momentum shift (RSI slope + EMA alignment).

Computes a deterministic priority scanner_score in [0, 100] adjusted by Market Regime.
Anti-Lookahead Bias: strictly causal calculations, bar-close confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

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
from src.vibetrade.data.okx_models import ClosedCandle, dec_str
from src.vibetrade.scanner.models import (
    MarketRegimeSnapshot,
    OpportunityCandidate,
    OpportunityQueueSnapshot,
    make_signal_id,
)

DEFAULT_RVOL_THRESHOLD = 2.0
DEFAULT_ZSCORE_THRESHOLD = 2.5
DEFAULT_ATR_EXPANSION_MULT = 1.5
DEFAULT_BREAKOUT_LOOKBACK = 20
DEFAULT_RSI_MOMENTUM_THRESHOLD = 55.0
DEFAULT_MAX_CANDIDATES = 20
DEFAULT_MIN_WARMUP_BARS = 25


@dataclass(frozen=True)
class ScannerConfig:
    """Configurable thresholds for surveillance anomaly detection."""

    rvol_threshold: float = DEFAULT_RVOL_THRESHOLD
    volume_zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD
    atr_expansion_multiplier: float = DEFAULT_ATR_EXPANSION_MULT
    breakout_lookback: int = DEFAULT_BREAKOUT_LOOKBACK
    rsi_momentum_threshold: float = DEFAULT_RSI_MOMENTUM_THRESHOLD
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    min_warmup_bars: int = DEFAULT_MIN_WARMUP_BARS
    fast_ema_span: int = 9
    slow_ema_span: int = 21


def scan_instrument_anomalies(
    candles: Sequence[ClosedCandle],
    now_ms: int,
    regime_snapshot: MarketRegimeSnapshot,
    config: ScannerConfig | None = None,
) -> OpportunityCandidate | None:
    """Scan a single instrument's closed candles for quantitative anomalies.

    Returns an OpportunityCandidate if one or more anomalies are detected,
    otherwise None.
    """
    if not candles:
        return None

    cfg = config or ScannerConfig()
    inst_id = candles[0].inst_id
    timeframe = candles[0].timeframe

    frame = candles_to_frame(candles)
    assert_closed_frame(frame, now_ms)

    if len(frame) < cfg.min_warmup_bars:
        return None

    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    volume = frame["volume"]
    opens = frame["open"]

    # Compute causal indicators
    rvol_s = rvol(volume, window=20)
    zscore_s = volume_zscore(volume, window=20)
    atr_s = atr_wilder(high, low, close, period=14)
    ema_fast_s = ema(close, span=cfg.fast_ema_span)
    ema_slow_s = ema(close, span=cfg.slow_ema_span)
    rsi_s = rsi_wilder(close, period=14)

    # Current bar (t) values
    cur_close = float(close.iloc[-1])
    cur_open = float(opens.iloc[-1])
    cur_high = float(high.iloc[-1])
    cur_low = float(low.iloc[-1])
    cur_range = cur_high - cur_low
    cur_close_time = int(frame.index[-1].value // 1_000_000)

    cur_rvol = float(rvol_s.iloc[-1]) if pd.notna(rvol_s.iloc[-1]) else 1.0
    cur_zscore = float(zscore_s.iloc[-1]) if pd.notna(zscore_s.iloc[-1]) else 0.0
    cur_atr = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else cur_range
    cur_rsi = float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else 50.0
    prev_rsi = float(rsi_s.iloc[-2]) if len(rsi_s) >= 2 and pd.notna(rsi_s.iloc[-2]) else cur_rsi
    cur_ema_fast = float(ema_fast_s.iloc[-1]) if pd.notna(ema_fast_s.iloc[-1]) else cur_close
    cur_ema_slow = float(ema_slow_s.iloc[-1]) if pd.notna(ema_slow_s.iloc[-1]) else cur_close

    # Detection logic
    anomalies: list[str] = []
    volume_score = 0.0
    volatility_score = 0.0
    breakout_score = 0.0
    momentum_score = 0.0

    # 1. Volume Spike
    is_vol_spike = (cur_rvol >= cfg.rvol_threshold) or (cur_zscore >= cfg.volume_zscore_threshold)
    if is_vol_spike:
        anomalies.append("VOLUME_SPIKE")
        rvol_component = min(cur_rvol / 4.0, 1.0) * 20.0
        z_component = min(max(cur_zscore, 0.0) / 4.0, 1.0) * 15.0
        volume_score = rvol_component + z_component

    # 2. Volatility Expansion
    is_vol_exp = (cur_atr > 0.0) and (cur_range >= cfg.atr_expansion_multiplier * cur_atr)
    if is_vol_exp:
        anomalies.append("VOLATILITY_EXPANSION")
        volatility_score = min(cur_range / (2.0 * cur_atr), 1.0) * 25.0

    # 3. Breakout / Breakdown (Local 20-bar resistance breakout or support breakdown)
    lookback = min(cfg.breakout_lookback, len(frame) - 1)
    if lookback >= 5:
        prior_highs = high.iloc[-lookback - 1 : -1]
        prior_max_high = float(prior_highs.max())
        prior_lows = low.iloc[-lookback - 1 : -1]
        prior_min_low = float(prior_lows.min())

        if cur_close > prior_max_high and cur_close > cur_open:
            anomalies.extend(["BREAKOUT", "BULLISH_BREAKOUT"])
            breakout_score = 25.0
        elif cur_close < prior_min_low and cur_close < cur_open:
            anomalies.append("BEARISH_BREAKDOWN")
            breakout_score = 25.0

    # 4. Momentum Shift (Bullish or Bearish)
    is_bullish_momentum = (
        (cur_rsi >= cfg.rsi_momentum_threshold)
        and (cur_rsi > prev_rsi)
        and (cur_ema_fast > cur_ema_slow)
    )
    is_bearish_momentum = (
        (cur_rsi <= (100.0 - cfg.rsi_momentum_threshold))
        and (cur_rsi < prev_rsi)
        and (cur_ema_fast < cur_ema_slow)
    )
    if is_bullish_momentum:
        anomalies.extend(["MOMENTUM_SHIFT", "BULLISH_MOMENTUM"])
        momentum_score = 15.0
    elif is_bearish_momentum:
        anomalies.append("BEARISH_MOMENTUM")
        momentum_score = 15.0

    if not anomalies:
        return None

    # Calculate raw score (max 100.0)
    raw_score = min(volume_score + volatility_score + breakout_score + momentum_score, 100.0)
    # Apply regime multiplier
    regime_mult = float(regime_snapshot.multiplier)
    final_score = min(max(raw_score * regime_mult, 0.0), 100.0)

    signal_id = make_signal_id(inst_id, timeframe, cur_close_time)

    metrics = {
        "rvol": dec_str(Decimal(str(round(cur_rvol, 2)))),
        "volume_zscore": dec_str(Decimal(str(round(cur_zscore, 2)))),
        "atr": dec_str(Decimal(str(round(cur_atr, 4)))),
        "rsi": dec_str(Decimal(str(round(cur_rsi, 2)))),
        "price": dec_str(Decimal(str(round(cur_close, 4)))),
        "bar_range": dec_str(Decimal(str(round(cur_range, 4)))),
        "raw_score": dec_str(Decimal(str(round(raw_score, 2)))),
    }

    return OpportunityCandidate(
        signal_id=signal_id,
        inst_id=inst_id,
        timeframe=timeframe,
        candle_close_time=cur_close_time,
        status="PENDING",
        anomaly_types=tuple(sorted(anomalies)),
        scanner_score=Decimal(str(round(final_score, 2))),
        metrics=metrics,
        detected_at_utc_ms=now_ms,
        regime=regime_snapshot.regime,
    )


def scan_market_opportunities(
    candles_by_symbol: Mapping[str, Sequence[ClosedCandle]],
    now_ms: int,
    regime_snapshot: MarketRegimeSnapshot,
    config: ScannerConfig | None = None,
) -> OpportunityQueueSnapshot:
    """Scan all instruments and assemble a deterministic OpportunityQueueSnapshot."""
    cfg = config or ScannerConfig()
    candidates: list[OpportunityCandidate] = []

    # Sort symbols deterministically
    sorted_symbols = sorted(candles_by_symbol.keys())
    for symbol in sorted_symbols:
        symbol_candles = candles_by_symbol[symbol]
        cand = scan_instrument_anomalies(
            symbol_candles,
            now_ms=now_ms,
            regime_snapshot=regime_snapshot,
            config=cfg,
        )
        if cand is not None:
            candidates.append(cand)

    # Sort descending by scanner_score, tie-breaking by inst_id ascending
    sorted_candidates = sorted(candidates, key=lambda c: (-c.scanner_score, c.inst_id))
    # Cap to max_candidates
    capped_candidates = tuple(sorted_candidates[: cfg.max_candidates])

    return OpportunityQueueSnapshot(
        schema_version="1.1",
        generated_at_utc_ms=now_ms,
        market_regime=regime_snapshot,
        candidates=capped_candidates,
    )
