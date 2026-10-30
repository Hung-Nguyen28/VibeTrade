"""Immutable domain models for Phase P2 — Market Scanner and Opportunity Queue.

Every numeric field is represented by finite Decimal (or plain string in serialization),
all models are frozen dataclasses, and signal_id conforms strictly to:
    signal_id = f"{inst_id}:{timeframe}:{candle_close_time}"
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from src.vibetrade.data.bar_close import BAR_DURATION_MS
from src.vibetrade.data.okx_models import (
    ModelValidationError,
    _check_decimal_field,
    _check_usdt_inst_id,
    dec_str,
    parse_decimal,
    parse_epoch_ms,
)

SCHEMA_VERSION = "1.1"

VALID_REGIMES: frozenset[str] = frozenset(
    {"BULL_TREND", "BEAR_TREND", "HIGH_VOL_CHOP", "RANGE_BOUND"}
)
VALID_STATUSES: frozenset[str] = frozenset(
    {"PENDING", "IN_FOCUS", "EVALUATED", "EXPIRED"}
)
VALID_ANOMALIES: frozenset[str] = frozenset(
    {
        "VOLUME_SPIKE",
        "VOLATILITY_EXPANSION",
        "BREAKOUT",
        "MOMENTUM_SHIFT",
        "BULLISH_BREAKOUT",
        "BULLISH_MOMENTUM",
        "BEARISH_BREAKDOWN",
        "BEARISH_MOMENTUM",
    }
)
VALID_TIMEFRAMES: frozenset[str] = frozenset(BAR_DURATION_MS.keys())


def make_signal_id(inst_id: str, timeframe: str, candle_close_time: int) -> str:
    """Format canonical deterministic signal_id: ``<inst_id>:<timeframe>:<close_time>``."""
    _check_usdt_inst_id(inst_id)
    if timeframe not in VALID_TIMEFRAMES:
        raise ModelValidationError(f"Invalid timeframe {timeframe!r}")
    if not isinstance(candle_close_time, int) or candle_close_time <= 0:
        raise ModelValidationError(f"Invalid candle_close_time {candle_close_time!r}")
    return f"{inst_id}:{timeframe}:{candle_close_time}"


@dataclass(frozen=True)
class MarketRegimeSnapshot:
    """Market regime detection snapshot across BTC and whole USDT Spot market."""

    regime: str
    multiplier: Decimal
    btc_price: Decimal
    btc_ema_fast: Decimal
    btc_ema_slow: Decimal
    btc_rsi: Decimal
    btc_atr_pct: Decimal
    market_breadth_pct: Decimal
    detected_at_utc_ms: int
    details: dict[str, Any]

    def __post_init__(self) -> None:
        if self.regime not in VALID_REGIMES:
            raise ModelValidationError(f"Unknown regime {self.regime!r}")
        for name in (
            "multiplier",
            "btc_price",
            "btc_ema_fast",
            "btc_ema_slow",
            "btc_rsi",
            "btc_atr_pct",
            "market_breadth_pct",
        ):
            _check_decimal_field(self, name, positive=(name not in {"btc_rsi", "btc_atr_pct", "market_breadth_pct"}))
        if not isinstance(self.detected_at_utc_ms, int) or self.detected_at_utc_ms <= 0:
            raise ModelValidationError("detected_at_utc_ms must be a positive int")
        if not isinstance(self.details, dict):
            raise ModelValidationError("details must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "multiplier": dec_str(self.multiplier.quantize(Decimal("0.01"))),
            "btc_price": dec_str(self.btc_price.quantize(Decimal("0.01"))),
            "btc_ema_fast": dec_str(self.btc_ema_fast.quantize(Decimal("0.01"))),
            "btc_ema_slow": dec_str(self.btc_ema_slow.quantize(Decimal("0.01"))),
            "btc_rsi": dec_str(self.btc_rsi.quantize(Decimal("0.01"))),
            "btc_atr_pct": dec_str(self.btc_atr_pct.quantize(Decimal("0.0001"))),
            "market_breadth_pct": dec_str(self.market_breadth_pct.quantize(Decimal("0.01"))),
            "detected_at_utc_ms": self.detected_at_utc_ms,
            "details": self.details,
        }


@dataclass(frozen=True)
class OpportunityCandidate:
    """Single anomaly candidate emitted by the surveillance scanner."""

    signal_id: str
    inst_id: str
    timeframe: str
    candle_close_time: int
    status: str
    anomaly_types: tuple[str, ...]
    scanner_score: Decimal
    metrics: dict[str, str]
    detected_at_utc_ms: int
    regime: str

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.timeframe not in VALID_TIMEFRAMES:
            raise ModelValidationError(f"Invalid timeframe {self.timeframe!r}")
        expected_signal_id = make_signal_id(self.inst_id, self.timeframe, self.candle_close_time)
        if self.signal_id != expected_signal_id:
            raise ModelValidationError(f"signal_id mismatch: got {self.signal_id!r}, expected {expected_signal_id!r}")
        if self.status not in VALID_STATUSES:
            raise ModelValidationError(f"Invalid candidate status {self.status!r}")
        if not self.anomaly_types:
            raise ModelValidationError("anomaly_types cannot be empty")
        for atype in self.anomaly_types:
            if atype not in VALID_ANOMALIES:
                raise ModelValidationError(f"Unknown anomaly type {atype!r}")
        _check_decimal_field(self, "scanner_score", positive=False)
        if self.scanner_score < Decimal(0) or self.scanner_score > Decimal(100):
            raise ModelValidationError(f"scanner_score must be in [0, 100] (got {self.scanner_score})")
        if not isinstance(self.detected_at_utc_ms, int) or self.detected_at_utc_ms <= 0:
            raise ModelValidationError("detected_at_utc_ms must be positive int")
        if self.candle_close_time > self.detected_at_utc_ms:
            raise ModelValidationError("candle_close_time cannot be in future of detected_at_utc_ms (lookahead guard)")
        if self.regime not in VALID_REGIMES:
            raise ModelValidationError(f"Unknown regime {self.regime!r}")
        if not isinstance(self.metrics, dict):
            raise ModelValidationError("metrics must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "inst_id": self.inst_id,
            "timeframe": self.timeframe,
            "candle_close_time": self.candle_close_time,
            "status": self.status,
            "anomaly_types": list(self.anomaly_types),
            "scanner_score": dec_str(self.scanner_score.quantize(Decimal("0.01"))),
            "metrics": {k: str(v) for k, v in self.metrics.items()},
            "detected_at_utc_ms": self.detected_at_utc_ms,
            "regime": self.regime,
        }


@dataclass(frozen=True)
class OpportunityQueueSnapshot:
    """Canonical document for opportunity_queue.json."""

    schema_version: str
    generated_at_utc_ms: int
    market_regime: MarketRegimeSnapshot
    candidates: tuple[OpportunityCandidate, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
        if not isinstance(self.generated_at_utc_ms, int) or self.generated_at_utc_ms <= 0:
            raise ModelValidationError("generated_at_utc_ms must be a positive int")
        if not isinstance(self.market_regime, MarketRegimeSnapshot):
            raise ModelValidationError("market_regime must be a MarketRegimeSnapshot instance")
        for cand in self.candidates:
            if not isinstance(cand, OpportunityCandidate):
                raise ModelValidationError("all candidates must be OpportunityCandidate instances")
            if cand.candle_close_time > self.generated_at_utc_ms:
                raise ModelValidationError(f"{cand.inst_id}: candidate closes after snapshot generation time")

    @property
    def queue_size(self) -> int:
        return len(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        # Strictly sort candidates descending by scanner_score, tie-breaking by inst_id ascending
        sorted_candidates = sorted(self.candidates, key=lambda c: (-c.scanner_score, c.inst_id))
        return {
            "schema_version": self.schema_version,
            "generated_at_utc_ms": self.generated_at_utc_ms,
            "market_regime": self.market_regime.to_dict(),
            "queue_size": len(sorted_candidates),
            "candidates": [c.to_dict() for c in sorted_candidates],
        }
