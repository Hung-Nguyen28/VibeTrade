"""Immutable domain models for Phase P4 — Deterministic Research Team & History.

Every numeric metric is serialized as a plain decimal string; every report is frozen,
and each evidence item is uniquely bound to a causal quantitative rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from src.vibetrade.data.okx_models import (
    ModelValidationError,
    _check_decimal_field,
    _check_usdt_inst_id,
    dec_str,
    parse_decimal,
    parse_epoch_ms,
)
from src.vibetrade.scanner.models import (
    VALID_REGIMES,
    VALID_TIMEFRAMES,
    make_signal_id,
)

SCHEMA_VERSION = "1.1"

VALID_VERDICTS: frozenset[str] = frozenset(
    {"ACTIONABLE_LONG", "WATCHLIST_NEUTRAL", "AVOID_BEARISH", "INCONCLUSIVE"}
)
VALID_PERSONAS: frozenset[str] = frozenset({"bull_researcher", "bear_researcher"})


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of quantitative evidence emitted by Bull or Bear researchers."""

    rule_id: str
    persona: str
    metric: str
    value: str
    threshold: str
    weight: Decimal
    score_contribution: Decimal
    candle_close_time: int
    template_summary: str

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ModelValidationError("rule_id cannot be empty")
        if self.persona not in VALID_PERSONAS:
            raise ModelValidationError(f"Invalid persona {self.persona!r}")
        if not self.metric or not self.value or not self.threshold or not self.template_summary:
            raise ModelValidationError("Evidence fields cannot be empty")
        _check_decimal_field(self, "weight", positive=False)
        _check_decimal_field(self, "score_contribution", positive=False)
        if self.candle_close_time <= 0:
            raise ModelValidationError("candle_close_time must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "persona": self.persona,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "weight": dec_str(self.weight.quantize(Decimal("0.01"))),
            "score_contribution": dec_str(self.score_contribution.quantize(Decimal("0.01"))),
            "candle_close_time": self.candle_close_time,
            "template_summary": self.template_summary,
        }


@dataclass(frozen=True)
class ResearchReport:
    """Deterministic explainable research verdict emitted by the Crucible."""

    report_id: str
    signal_id: str
    inst_id: str
    timeframe: str
    candle_close_time: int
    verdict: str
    score_bull: Decimal
    score_bear: Decimal
    score_raw: Decimal
    score_net: Decimal
    regime: str
    regime_multiplier: Decimal
    evidence: tuple[EvidenceItem, ...]
    template_summary: str
    evaluated_at_utc_ms: int
    missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_usdt_inst_id(self.inst_id)
        if self.timeframe not in VALID_TIMEFRAMES:
            raise ModelValidationError(f"Invalid timeframe {self.timeframe!r}")
        expected_signal_id = make_signal_id(self.inst_id, self.timeframe, self.candle_close_time)
        if self.signal_id != expected_signal_id:
            raise ModelValidationError(f"signal_id mismatch: {self.signal_id!r} != {expected_signal_id!r}")
        expected_report_id = f"rep:{self.signal_id}"
        if self.report_id != expected_report_id:
            raise ModelValidationError(f"report_id mismatch: {self.report_id!r} != {expected_report_id!r}")
        if self.verdict not in VALID_VERDICTS:
            raise ModelValidationError(f"Invalid verdict {self.verdict!r}")
        if self.regime not in VALID_REGIMES:
            raise ModelValidationError(f"Invalid regime {self.regime!r}")
        _check_decimal_field(self, "score_bull", positive=False)
        _check_decimal_field(self, "score_bear", positive=False)
        _check_decimal_field(self, "regime_multiplier", positive=True)
        if not isinstance(self.score_raw, Decimal) or not self.score_raw.is_finite():
            raise ModelValidationError("score_raw must be a finite Decimal")
        if not isinstance(self.score_net, Decimal) or not self.score_net.is_finite():
            raise ModelValidationError("score_net must be a finite Decimal")
        if self.candle_close_time > self.evaluated_at_utc_ms:
            raise ModelValidationError("candle_close_time cannot be in future of evaluated_at_utc_ms")
        if not self.template_summary:
            raise ModelValidationError("template_summary cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "signal_id": self.signal_id,
            "inst_id": self.inst_id,
            "timeframe": self.timeframe,
            "candle_close_time": self.candle_close_time,
            "verdict": self.verdict,
            "score_bull": dec_str(self.score_bull.quantize(Decimal("0.01"))),
            "score_bear": dec_str(self.score_bear.quantize(Decimal("0.01"))),
            "score_raw": dec_str(self.score_raw.quantize(Decimal("0.01"))),
            "score_net": dec_str(self.score_net.quantize(Decimal("0.01"))),
            "regime": self.regime,
            "regime_multiplier": dec_str(self.regime_multiplier.quantize(Decimal("0.01"))),
            "evidence": [e.to_dict() for e in self.evidence],
            "template_summary": self.template_summary,
            "evaluated_at_utc_ms": self.evaluated_at_utc_ms,
            "missing_inputs": list(self.missing_inputs),
        }


@dataclass(frozen=True)
class ResearchHistorySnapshot:
    """Canonical snapshot for research_history.json (schema v1.1)."""

    schema_version: str
    generated_at_utc_ms: int
    reports: tuple[ResearchReport, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
        if not isinstance(self.generated_at_utc_ms, int) or self.generated_at_utc_ms <= 0:
            raise ModelValidationError("generated_at_utc_ms must be positive")
        for r in self.reports:
            if not isinstance(r, ResearchReport):
                raise ModelValidationError("All reports must be ResearchReport instances")
            if r.evaluated_at_utc_ms > self.generated_at_utc_ms:
                raise ModelValidationError("Report evaluated after snapshot generation time")

    @property
    def total_reports(self) -> int:
        return len(self.reports)

    def to_dict(self) -> dict[str, Any]:
        # Deterministically sorted by evaluated_at_utc_ms descending, tie-breaking by report_id
        sorted_reports = sorted(self.reports, key=lambda r: (-r.evaluated_at_utc_ms, r.report_id))
        return {
            "schema_version": self.schema_version,
            "generated_at_utc_ms": self.generated_at_utc_ms,
            "total_reports": len(sorted_reports),
            "reports": [r.to_dict() for r in sorted_reports],
        }
