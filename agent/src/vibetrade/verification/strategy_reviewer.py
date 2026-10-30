"""Independent StrategyReviewer for Phase P5.

Independently recalculates Bull, Bear, S_raw, and S_net from raw EvidenceItems:
1. Re-sums evidence score contributions per persona.
2. Verifies exact formula identity: S_raw = S_Bull - S_Bear, S_net = S_raw * M_regime.
3. Checks rule_id validity, candle timestamp binding, and verdict threshold compliance.
"""

from __future__ import annotations

from decimal import Decimal

from src.vibetrade.research.models import EvidenceItem, ResearchReport
from src.vibetrade.verification.models import StrategyReviewReport

DEFAULT_ACTIONABLE_NET_THRESHOLD = Decimal("30.00")
DEFAULT_MAX_BEAR_RISK_THRESHOLD = Decimal("35.00")
DEFAULT_BEAR_VETO_THRESHOLD = Decimal("65.00")


class StrategyReviewer:
    """Independent auditor verifying mathematical logic and rule bindings of ResearchReports."""

    def __init__(
        self,
        actionable_net_threshold: Decimal = DEFAULT_ACTIONABLE_NET_THRESHOLD,
        max_bear_risk_threshold: Decimal = DEFAULT_MAX_BEAR_RISK_THRESHOLD,
        bear_veto_threshold: Decimal = DEFAULT_BEAR_VETO_THRESHOLD,
    ) -> None:
        self.actionable_net_threshold = actionable_net_threshold
        self.max_bear_risk_threshold = max_bear_risk_threshold
        self.bear_veto_threshold = bear_veto_threshold

    def review_report(self, report: ResearchReport) -> StrategyReviewReport:
        violations: list[str] = []
        details: dict[str, str] = {}

        if report.verdict == "INCONCLUSIVE":
            # For INCONCLUSIVE reports, verify scores are 0 and missing inputs are documented
            if report.score_bull != Decimal("0.00") or report.score_bear != Decimal("0.00") or report.score_net != Decimal("0.00"):
                violations.append("NON_ZERO_SCORES_IN_INCONCLUSIVE_REPORT")
            if not report.missing_inputs:
                violations.append("INCONCLUSIVE_REPORT_WITHOUT_MISSING_INPUTS")
            return StrategyReviewReport(
                passed=len(violations) == 0,
                violations=tuple(violations),
                recalculated_bull=Decimal("0.00"),
                recalculated_bear=Decimal("0.00"),
                recalculated_raw=Decimal("0.00"),
                recalculated_net=Decimal("0.00"),
                details=details,
            )

        # 1. Independent sum of EvidenceItem contributions
        sum_bull = Decimal("0.00")
        sum_bear = Decimal("0.00")

        for idx, ev in enumerate(report.evidence):
            # Check rule_id format
            if not ev.rule_id.startswith(("BULL_", "BEAR_")):
                violations.append(f"INVALID_RULE_ID_PREFIX_{ev.rule_id}_AT_INDEX_{idx}")
            # Check timestamp match
            if ev.candle_close_time != report.candle_close_time:
                violations.append(f"EVIDENCE_TIMESTAMP_MISMATCH_AT_INDEX_{idx}")

            if ev.persona == "bull_researcher":
                sum_bull += ev.score_contribution
            elif ev.persona == "bear_researcher":
                sum_bear += ev.score_contribution
            else:
                violations.append(f"UNKNOWN_EVIDENCE_PERSONA_{ev.persona}_AT_INDEX_{idx}")

        # Clamping checks (max 100.00)
        recalculated_bull = min(max(sum_bull, Decimal("0.00")), Decimal("100.00"))
        recalculated_bear = min(max(sum_bear, Decimal("0.00")), Decimal("100.00"))

        # Verify against report's score_bull & score_bear
        if abs(recalculated_bull - report.score_bull) > Decimal("0.01"):
            violations.append(f"SCORE_BULL_MISMATCH (calc={recalculated_bull} vs rep={report.score_bull})")
        if abs(recalculated_bear - report.score_bear) > Decimal("0.01"):
            violations.append(f"SCORE_BEAR_MISMATCH (calc={recalculated_bear} vs rep={report.score_bear})")

        # 2. Formula verification: S_raw = S_Bull - S_Bear, S_net = S_raw * M_regime
        recalculated_raw = recalculated_bull - recalculated_bear
        if abs(recalculated_raw - report.score_raw) > Decimal("0.01"):
            violations.append(f"SCORE_RAW_MISMATCH (calc={recalculated_raw} vs rep={report.score_raw})")

        recalculated_net = (recalculated_raw * report.regime_multiplier).quantize(Decimal("0.01"))
        if abs(recalculated_net - report.score_net) > Decimal("0.01"):
            violations.append(f"SCORE_NET_MISMATCH (calc={recalculated_net} vs rep={report.score_net})")

        # 3. Verdict threshold consistency
        expected_verdict: str
        if recalculated_net >= self.actionable_net_threshold and recalculated_bear <= self.max_bear_risk_threshold:
            expected_verdict = "ACTIONABLE_LONG"
        elif recalculated_raw <= -self.actionable_net_threshold and recalculated_bull <= self.max_bear_risk_threshold:
            expected_verdict = "ACTIONABLE_SHORT"
        elif recalculated_bear >= self.bear_veto_threshold:
            expected_verdict = "AVOID_BEARISH"
        elif recalculated_net > Decimal("0.00"):
            expected_verdict = "WATCHLIST_NEUTRAL"
        else:
            expected_verdict = "WATCHLIST_NEUTRAL"

        if report.verdict != expected_verdict:
            violations.append(f"VERDICT_THRESHOLD_BREACH (expected={expected_verdict} vs actual={report.verdict})")

        details["sum_bull"] = str(sum_bull)
        details["sum_bear"] = str(sum_bear)
        details["recalculated_net"] = str(recalculated_net)

        return StrategyReviewReport(
            passed=len(violations) == 0,
            violations=tuple(violations),
            recalculated_bull=recalculated_bull,
            recalculated_bear=recalculated_bear,
            recalculated_raw=recalculated_raw,
            recalculated_net=recalculated_net,
            details=details,
        )
