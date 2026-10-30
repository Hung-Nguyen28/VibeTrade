"""The Crucible & Explainable Decision Engine for Phase P4.

Aggregates independent Bull and Bear scores, enforces the Missing Data Gate,
applies the Market Regime Multiplier, and renders deterministic Evidence-based Templates.
Formula:
    S_raw = S_Bull - S_Bear
    S_net = S_raw * M_regime
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from src.vibetrade.data.okx_models import dec_str
from src.vibetrade.research.analysts import FocusFeatureVector
from src.vibetrade.research.models import EvidenceItem, ResearchReport
from src.vibetrade.research.researchers import BearResearcher, BullResearcher
from src.vibetrade.scanner.models import MarketRegimeSnapshot, make_signal_id


class CrucibleEngine:
    """Deterministic Crucible arbiter synthesizing Bull, Bear, and Market Regime."""

    def __init__(
        self,
        bull_researcher: BullResearcher | None = None,
        bear_researcher: BearResearcher | None = None,
        actionable_net_threshold: Decimal = Decimal("30.00"),
        max_bear_risk_threshold: Decimal = Decimal("35.00"),
        bear_veto_threshold: Decimal = Decimal("65.00"),
    ) -> None:
        self.bull_researcher = bull_researcher or BullResearcher()
        self.bear_researcher = bear_researcher or BearResearcher()
        self.actionable_net_threshold = actionable_net_threshold
        self.max_bear_risk_threshold = max_bear_risk_threshold
        self.bear_veto_threshold = bear_veto_threshold

    def evaluate_candidate(
        self,
        features: FocusFeatureVector,
        regime_snapshot: MarketRegimeSnapshot,
        now_ms: int,
    ) -> ResearchReport:
        """Synthesize multi-persona research into an explainable ResearchReport."""
        inst_id = features.inst_id
        timeframe = features.timeframe
        c_time = features.candle_close_time
        regime = regime_snapshot.regime
        regime_mult = regime_snapshot.multiplier

        # 1. Missing Data Gate: Halt immediately if any mandatory input is missing or NaN
        if not features.is_complete:
            missing = features.missing_fields or ("incomplete_feature_vector",)
            summary = (
                f"INCONCLUSIVE: Evaluation halted due to missing mandatory inputs: "
                f"[{', '.join(missing)}]. Zero guesswork applied."
            )
            # Ensure valid signal_id format even on early halt
            valid_time = c_time if c_time > 0 else now_ms
            signal_id = make_signal_id(inst_id, timeframe, valid_time)
            report_id = f"rep:{signal_id}"

            return ResearchReport(
                report_id=report_id,
                signal_id=signal_id,
                inst_id=inst_id,
                timeframe=timeframe,
                candle_close_time=valid_time,
                verdict="INCONCLUSIVE",
                score_bull=Decimal("0.00"),
                score_bear=Decimal("0.00"),
                score_raw=Decimal("0.00"),
                score_net=Decimal("0.00"),
                regime=regime,
                regime_multiplier=regime_mult,
                evidence=(),
                template_summary=summary,
                evaluated_at_utc_ms=now_ms,
                missing_inputs=tuple(missing),
            )

        # 2. Independent Bull & Bear evaluations
        bull_score = self.bull_researcher.evaluate(features)
        bear_score = self.bear_researcher.evaluate(features)

        s_bull = bull_score.total_score
        s_bear = bear_score.total_score
        s_raw = s_bull - s_bear
        s_net = (s_raw * regime_mult).quantize(Decimal("0.01"))

        all_evidence: list[EvidenceItem] = list(bull_score.evidence) + list(bear_score.evidence)

        # 3. Decision Matrix
        if s_bear >= self.bear_veto_threshold:
            verdict = "AVOID_BEARISH"
            reason = f"Bear risk score ({s_bear:.2f}) exceeded veto threshold ({self.bear_veto_threshold:.2f})"
        elif s_net >= self.actionable_net_threshold and s_bear <= self.max_bear_risk_threshold:
            verdict = "ACTIONABLE_LONG"
            reason = f"Net score {s_net:+.2f} >= {self.actionable_net_threshold} and bear risk {s_bear:.2f} <= {self.max_bear_risk_threshold}"
        elif s_net > Decimal("0.00"):
            verdict = "WATCHLIST_NEUTRAL"
            reason = f"Net score {s_net:+.2f} positive but below actionable threshold {self.actionable_net_threshold}"
        else:
            verdict = "AVOID_BEARISH"
            reason = f"Net score {s_net:+.2f} non-positive under regime {regime}"

        # 4. Evidence-based summary template
        summary = (
            f"Verdict {verdict} for {inst_id} ({timeframe}): "
            f"S_Bull={s_bull:.2f}, S_Bear={s_bear:.2f}, S_raw={s_raw:+.2f}, S_net={s_net:+.2f} "
            f"(Regime: {regime}, M={regime_mult:.2f}). Reason: {reason}. "
            f"Active Evidence: {len(bull_score.evidence)} bull factors, {len(bear_score.evidence)} bear risks."
        )

        signal_id = make_signal_id(inst_id, timeframe, c_time)
        report_id = f"rep:{signal_id}"

        return ResearchReport(
            report_id=report_id,
            signal_id=signal_id,
            inst_id=inst_id,
            timeframe=timeframe,
            candle_close_time=c_time,
            verdict=verdict,
            score_bull=s_bull,
            score_bear=s_bear,
            score_raw=s_raw,
            score_net=s_net,
            regime=regime,
            regime_multiplier=regime_mult,
            evidence=tuple(all_evidence),
            template_summary=summary,
            evaluated_at_utc_ms=now_ms,
            missing_inputs=(),
        )
