"""Causal primary indicators (P1): EMA, Wilder RSI, Wilder ATR, RVOL, Volume Z-Score.

Every function at row ``t`` reads rows ``<= t`` only (recursive ``ewm`` with
``adjust=False``; rolling windows over *prior* bars for volume baselines). No
negative shifts, no ``center=True``, no whole-series normalisation. This is
enforced by the Truncation Invariance test:
``F(df.iloc[:t]).iloc[-1] == F(df).iloc[t-1]``.

Warm-up rows are ``NaN`` — callers must treat ``NaN`` as "insufficient data"
(``INCONCLUSIVE``), never as ``0``.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from src.vibetrade.data.okx_models import ClosedCandle


def candles_to_frame(candles: Iterable[ClosedCandle]) -> pd.DataFrame:
    """Closed candles -> float DataFrame indexed by UTC ``candle_close_time``.

    Columns: ``open high low close volume vol_quote candle_open_time``.
    Input must be strictly ascending and single-symbol/single-timeframe.
    """
    rows = list(candles)
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vol_quote", "candle_open_time"])
    if len({(c.inst_id, c.timeframe) for c in rows}) != 1:
        raise ValueError("candles must share one inst_id and timeframe")
    opens = [c.candle_open_time for c in rows]
    if any(b <= a for a, b in zip(opens, opens[1:])):
        raise ValueError("candles must be strictly ascending by candle_open_time")
    frame = pd.DataFrame(
        {
            "open": [float(c.open) for c in rows],
            "high": [float(c.high) for c in rows],
            "low": [float(c.low) for c in rows],
            "close": [float(c.close) for c in rows],
            "volume": [float(c.vol_base) for c in rows],
            "vol_quote": [float(c.vol_quote) for c in rows],
            "candle_open_time": opens,
        },
        index=pd.to_datetime([c.candle_close_time for c in rows], unit="ms", utc=True),
    )
    frame.index.name = "candle_close_time"
    return frame


def assert_closed_frame(frame: pd.DataFrame, now_ms: int) -> None:
    """Raise if any bar closes after ``now_ms`` (Bar-Close Confirmation guard)."""
    if frame.empty:
        return
    last_close_ms = int(frame.index.max().value // 1_000_000)
    if last_close_ms > now_ms:
        raise ValueError(f"frame contains a bar closing at {last_close_ms} > now {now_ms} (running candle)")


def _finite_series(series: pd.Series, name: str) -> pd.Series:
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name}: contains NaN/Inf; clean the input before computing indicators")
    return series.astype(float)


def _check_window(window: int, minimum: int = 1) -> None:
    if not isinstance(window, int) or isinstance(window, bool) or window < minimum:
        raise ValueError(f"window must be an int >= {minimum} (got {window!r})")


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average, ``alpha = 2 / (span + 1)``; NaN until ``span`` bars exist."""
    _check_window(span)
    return _finite_series(close, "close").ewm(span=span, adjust=False, min_periods=span).mean()


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (``alpha = 1/period``); first value at index ``period``.

    ``avg_loss == 0``: RSI = 100 when ``avg_gain > 0`` else 50 (flat market).
    """
    _check_window(period)
    delta = _finite_series(close, "close").diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # first diff is NaN and is skipped by ewm; min_periods counts valid observations.
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.where(avg_loss != 0.0)
    out = 100.0 - 100.0 / (1.0 + rs)
    flat_up = (avg_loss == 0.0) & (avg_gain > 0.0)
    flat = (avg_loss == 0.0) & (avg_gain == 0.0)
    out = out.mask(flat_up, 100.0).mask(flat, 50.0)
    return out.where(avg_gain.notna() & avg_loss.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range using the *previous* close (row 0 falls back to ``high - low``)."""
    h = _finite_series(high, "high")
    lo = _finite_series(low, "low")
    c = _finite_series(close, "close")
    prev_close = c.shift(1)
    parts = pd.concat([h - lo, (h - prev_close).abs(), (lo - prev_close).abs()], axis=1)
    return parts.max(axis=1, skipna=True)


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder ATR; NaN until ``period`` bars exist."""
    _check_window(period)
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rvol(volume: pd.Series, window: int = 20) -> pd.Series:
    """Relative volume: ``volume[t] / mean(volume[t-window .. t-1])`` (prior bars only)."""
    _check_window(window)
    vol = _finite_series(volume, "volume")
    baseline = vol.shift(1).rolling(window=window, min_periods=window).mean()
    return vol / baseline.where(baseline > 0.0)


def volume_zscore(volume: pd.Series, window: int = 20) -> pd.Series:
    """``(volume[t] - mean_prior) / std_prior`` over the ``window`` prior bars (ddof=1)."""
    _check_window(window, minimum=2)
    vol = _finite_series(volume, "volume")
    prior = vol.shift(1).rolling(window=window, min_periods=window)
    std = prior.std(ddof=1)
    return (vol - prior.mean()) / std.where(std > 0.0)


# Backward/forward-compatible aliases
rvol_series = rvol
volume_zscore_series = volume_zscore
atr_series = atr_wilder
ema_series = ema
rsi_wilder_series = rsi_wilder

