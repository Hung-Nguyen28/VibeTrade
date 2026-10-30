"""Domain models for Phase P5 — Independent Verification.

Verification acts as an independent firewall between Research (P4) and Risk/Execution (P6).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.vibetrade.data.okx_models import ModelValidationError, dec_str
from src.vibetrade.scanner.models import make_signal_id

VALID_VERIFICATION_STATUSES: frozenset[str] = frozenset({"VERIFIED_PASS", "VERIFIED_FAIL"})


@dataclass(frozen=True)
class DataAuditReport:
    """Findings of the independent DataAuditor."""

    passed: bool
    violations: tuple[str, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class StrategyReviewReport:
    """Findings of the independent StrategyReviewer."""

    passed: bool
    violations: tuple[str, ...]
    recalculated_bull: Decimal
    recalculated_bear: Decimal
    recalculated_raw: Decimal
    recalculated_net: Decimal
    details: dict[str, Any]


@dataclass(frozen=True)
class VerificationReceipt:
    """Canonical receipt certifying independent verification of a research report."""

    receipt_id: str
    signal_id: str
    report_id: str
    report_sha256: str
    status: str
    violations: tuple[str, ...]
    auditor_passed: bool
    reviewer_passed: bool
    schema_passed: bool
    verified_at_utc_ms: int

    def __post_init__(self) -> None:
        if not self.receipt_id.startswith("ver:"):
            raise ModelValidationError(f"receipt_id must start with 'ver:' (got {self.receipt_id!r})")
        if self.status not in VALID_VERIFICATION_STATUSES:
            raise ModelValidationError(f"Invalid verification status {self.status!r}")
        if not self.report_sha256 or len(self.report_sha256) != 64:
            raise ModelValidationError("report_sha256 must be a valid 64-char hex string")
        if self.verified_at_utc_ms <= 0:
            raise ModelValidationError("verified_at_utc_ms must be positive")

    @property
    def can_proceed_to_risk(self) -> bool:
        """Only VERIFIED_PASS signals may cross into the Risk Controller (P6)."""
        return self.status == "VERIFIED_PASS" and len(self.violations) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "signal_id": self.signal_id,
            "report_id": self.report_id,
            "report_sha256": self.report_sha256,
            "status": self.status,
            "violations": list(self.violations),
            "auditor_passed": self.auditor_passed,
            "reviewer_passed": self.reviewer_passed,
            "schema_passed": self.schema_passed,
            "verified_at_utc_ms": self.verified_at_utc_ms,
            "can_proceed_to_risk": self.can_proceed_to_risk,
        }
