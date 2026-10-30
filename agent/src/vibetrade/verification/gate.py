"""Independent Verification Gate for Phase P5.

Acts as the final firewall before any candidate reaches the Risk Controller (P6).
Merges DataAuditor, StrategyReviewer, and runtime JSON Schema validation.
Emits an immutable VerificationReceipt sealed with a SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import jsonschema

from src.vibetrade.data.okx_models import ClosedCandle, OrderBookLiquiditySnapshot
from src.vibetrade.research.models import ResearchReport
from src.vibetrade.verification.data_auditor import DataAuditor
from src.vibetrade.verification.models import VerificationReceipt
from src.vibetrade.verification.strategy_reviewer import StrategyReviewer

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schema" / "v1.1" / "research_history.schema.json"


class VerificationGate:
    """Consolidated independent verification firewall for P5."""

    def __init__(
        self,
        data_auditor: DataAuditor | None = None,
        strategy_reviewer: StrategyReviewer | None = None,
        schema_path: Path | None = None,
    ) -> None:
        self.data_auditor = data_auditor or DataAuditor()
        self.strategy_reviewer = strategy_reviewer or StrategyReviewer()
        self.schema_path = schema_path or DEFAULT_SCHEMA_PATH
        self._schema_validator: jsonschema.Draft202012Validator | None = None

    def _get_validator(self) -> jsonschema.Draft202012Validator:
        if self._schema_validator is None:
            if not self.schema_path.is_file():
                raise FileNotFoundError(f"Schema file not found at {self.schema_path}")
            schema_data = json.loads(self.schema_path.read_text(encoding="utf-8"))
            # We want to validate an individual report object against #/$defs/report
            report_schema = {
                "$schema": schema_data["$schema"],
                "$defs": schema_data["$defs"],
                "$ref": "#/$defs/report",
            }
            jsonschema.Draft202012Validator.check_schema(report_schema)
            self._schema_validator = jsonschema.Draft202012Validator(report_schema)
        return self._schema_validator

    def verify_report(
        self,
        report: ResearchReport,
        candles: Sequence[ClosedCandle],
        orderbook: OrderBookLiquiditySnapshot | None,
        audit_utc_ms: int,
    ) -> VerificationReceipt:
        """Run full three-layer independent verification on a ResearchReport."""
        violations: list[str] = []

        # 1. Layer 1: Data Auditor
        data_audit = self.data_auditor.audit_focus_inputs(candles, orderbook, audit_utc_ms)
        if not data_audit.passed:
            violations.extend([f"DATA_AUDIT_{v}" for v in data_audit.violations])

        # 2. Layer 2: Strategy Reviewer
        strategy_review = self.strategy_reviewer.review_report(report)
        if not strategy_review.passed:
            violations.extend([f"STRATEGY_REVIEW_{v}" for v in strategy_review.violations])

        # 3. Layer 3: Runtime Schema Validation
        report_dict = report.to_dict()
        validator = self._get_validator()
        schema_errors = list(validator.iter_errors(report_dict))
        schema_passed = len(schema_errors) == 0
        if not schema_passed:
            violations.extend([f"SCHEMA_VIOLATION_{e.message}" for e in schema_errors])

        # 4. Canonical SHA-256 seal
        canonical_json = json.dumps(report_dict, sort_keys=True, allow_nan=False)
        report_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        overall_passed = data_audit.passed and strategy_review.passed and schema_passed
        status = "VERIFIED_PASS" if overall_passed else "VERIFIED_FAIL"
        receipt_id = f"ver:{report.signal_id}"

        return VerificationReceipt(
            receipt_id=receipt_id,
            signal_id=report.signal_id,
            report_id=report.report_id,
            report_sha256=report_hash,
            status=status,
            violations=tuple(violations),
            auditor_passed=data_audit.passed,
            reviewer_passed=strategy_review.passed,
            schema_passed=schema_passed,
            verified_at_utc_ms=audit_utc_ms,
        )
