"""Deterministic Bull & Bear Researchers for Phase P4.

Evaluates evidence-based quantitative rules with fixed weights totaling 100 points per side.
Every point contribution is strictly bound to an immutable EvidenceItem.
Zero LLM cost, zero fake roleplay, 100% deterministic arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from src.vibetrade.data.okx_models import dec_str
from src.vibetrade.research.analysts import FocusFeatureVector
from src.vibetrade.research.models import EvidenceItem


@dataclass(frozen=True)
class ResearcherScore:
    persona: str
    total_score: Decimal
    evidence: tuple[EvidenceItem, ...]


class BullResearcher:
    """Evaluates bullish evidence rules totaling 100 fixed weight points."""

    def evaluate(self, features: FocusFeatureVector) -> ResearcherScore:
        if not features.is_complete or features.trend is None or features.vol is None or features.liq is None:
            return ResearcherScore(persona="bull_researcher", total_score=Decimal("0.00"), evidence=())

        trend = features.trend
        vol = features.vol
        liq = features.liq
        c_time = features.candle_close_time
        evidence_list: list[EvidenceItem] = []
        total_pts = Decimal("0.00")

        # 1. RVOL Surge (Weight: 25.0)
        w1 = Decimal("25.00")
        if vol.rvol_20 >= 2.0 or vol.volume_zscore >= 2.0:
            scale = min(vol.rvol_20 / 4.0, 1.0)
            score1 = Decimal(str(round(float(w1) * scale, 2)))
            total_pts += score1
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_RVOL_SURGE_01",
                    persona="bull_researcher",
                    metric="rvol_20",
                    value=f"{vol.rvol_20:.2f}x",
                    threshold=">= 2.00x",
                    weight=w1,
                    score_contribution=score1,
                    candle_close_time=c_time,
                    template_summary=f"RVOL(20) at {vol.rvol_20:.2f}x (Z={vol.volume_zscore:.2f}) indicates strong volume participation (+{score1:.2f} pts).",
                )
            )

        # 2. EMA & RSI Momentum (Weight: 25.0)
        w2 = Decimal("25.00")
        if trend.ema_alignment == "BULLISH" and 52.0 <= trend.rsi_14 <= 75.0:
            score2 = w2
            total_pts += score2
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_EMA_MOMENTUM_02",
                    persona="bull_researcher",
                    metric="rsi_14",
                    value=f"{trend.rsi_14:.2f}",
                    threshold="52.00 <= RSI <= 75.00",
                    weight=w2,
                    score_contribution=score2,
                    candle_close_time=c_time,
                    template_summary=f"Bullish EMA alignment (EMA9 > EMA21) with healthy RSI at {trend.rsi_14:.2f} (+{score2:.2f} pts).",
                )
            )

        # 3. Higher Timeframe Alignment (Weight: 20.0)
        w3 = Decimal("20.00")
        if trend.htf_trend == "BULLISH":
            score3 = w3
            total_pts += score3
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_HTF_ALIGNMENT_03",
                    persona="bull_researcher",
                    metric="htf_trend",
                    value="BULLISH",
                    threshold="== BULLISH",
                    weight=w3,
                    score_contribution=score3,
                    candle_close_time=c_time,
                    template_summary=f"Higher timeframe (1H) trend confirms bullish market structure (+{score3:.2f} pts).",
                )
            )
        elif trend.htf_trend == "NEUTRAL":
            score3 = Decimal("10.00")
            total_pts += score3
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_HTF_ALIGNMENT_03",
                    persona="bull_researcher",
                    metric="htf_trend",
                    value="NEUTRAL",
                    threshold=">= NEUTRAL",
                    weight=w3,
                    score_contribution=score3,
                    candle_close_time=c_time,
                    template_summary=f"Higher timeframe trend is neutral, partial points awarded (+{score3:.2f} pts).",
                )
            )

        # 4. Orderbook Imbalance (Weight: 15.0)
        w4 = Decimal("15.00")
        if liq.imbalance_ratio >= 0.10:
            scale = min(liq.imbalance_ratio / 0.50, 1.0)
            score4 = Decimal(str(round(float(w4) * scale, 2)))
            total_pts += score4
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_OB_IMBALANCE_04",
                    persona="bull_researcher",
                    metric="imbalance_ratio",
                    value=f"{liq.imbalance_ratio:+.2f}",
                    threshold=">= +0.10",
                    weight=w4,
                    score_contribution=score4,
                    candle_close_time=c_time,
                    template_summary=f"L2 orderbook shows positive bid dominance with imbalance {liq.imbalance_ratio:+.2f} (+{score4:.2f} pts).",
                )
            )

        # 5. Low Slippage Execution (Weight: 15.0)
        w5 = Decimal("15.00")
        if liq.est_buy_slippage_bps <= 6.0 and liq.spread_bps <= 15.0 and liq.buy_fully_filled:
            score5 = w5
            total_pts += score5
            evidence_list.append(
                EvidenceItem(
                    rule_id="BULL_TIGHT_SLIPPAGE_05",
                    persona="bull_researcher",
                    metric="est_buy_slippage_bps",
                    value=f"{liq.est_buy_slippage_bps:.2f} bps",
                    threshold="<= 6.00 bps",
                    weight=w5,
                    score_contribution=score5,
                    candle_close_time=c_time,
                    template_summary=f"Micro-order ($10) fills with low slippage {liq.est_buy_slippage_bps:.2f} bps and tight spread {liq.spread_bps:.2f} bps (+{score5:.2f} pts).",
                )
            )

        clamped_score = min(max(total_pts, Decimal("0.00")), Decimal("100.00"))
        return ResearcherScore(
            persona="bull_researcher",
            total_score=clamped_score,
            evidence=tuple(evidence_list),
        )


class BearResearcher:
    """Evaluates bearish risk and headwind rules totaling 100 fixed weight points."""

    def evaluate(self, features: FocusFeatureVector) -> ResearcherScore:
        if not features.is_complete or features.trend is None or features.vol is None or features.liq is None:
            return ResearcherScore(persona="bear_researcher", total_score=Decimal("0.00"), evidence=())

        trend = features.trend
        vol = features.vol
        liq = features.liq
        c_time = features.candle_close_time
        evidence_list: list[EvidenceItem] = []
        total_pts = Decimal("0.00")

        # 1. Extreme Overbought RSI (Weight: 25.0)
        w1 = Decimal("25.00")
        if trend.rsi_14 >= 75.0:
            scale = min((trend.rsi_14 - 75.0) / 15.0, 1.0)
            score1 = max(Decimal(str(round(float(w1) * scale, 2))), Decimal("10.00"))
            total_pts += score1
            evidence_list.append(
                EvidenceItem(
                    rule_id="BEAR_EXTREME_OVERBOUGHT_01",
                    persona="bear_researcher",
                    metric="rsi_14",
                    value=f"{trend.rsi_14:.2f}",
                    threshold=">= 75.00",
                    weight=w1,
                    score_contribution=score1,
                    candle_close_time=c_time,
                    template_summary=f"Wilder RSI reached overextended level {trend.rsi_14:.2f}, indicating exhaustion risk (+{score1:.2f} risk pts).",
                )
            )

        # 2. HTF Trend Headwind or Bearish EMA (Weight: 25.0)
        w2 = Decimal("25.00")
        if trend.htf_trend == "BEARISH" or trend.ema_alignment == "BEARISH":
            score2 = w2
            total_pts += score2
            evidence_list.append(
                EvidenceItem(
                    rule_id="BEAR_HTF_HEADWIND_02",
                    persona="bear_researcher",
                    metric="ema_alignment",
                    value=f"{trend.ema_alignment} (HTF: {trend.htf_trend})",
                    threshold="== BEARISH",
                    weight=w2,
                    score_contribution=score2,
                    candle_close_time=c_time,
                    template_summary=f"Counter-trend posture: fast EMA below slow EMA or HTF trend is bearish (+{score2:.2f} risk pts).",
                )
            )

        # 3. Thin Liquidity / High Slippage (Weight: 20.0)
        w3 = Decimal("20.00")
        if liq.est_buy_slippage_bps >= 10.0 or liq.spread_bps >= 20.0 or not liq.buy_fully_filled:
            scale = min(liq.est_buy_slippage_bps / 20.0, 1.0)
            score3 = max(Decimal(str(round(float(w3) * scale, 2))), Decimal("8.00"))
            total_pts += score3
            evidence_list.append(
                EvidenceItem(
                    rule_id="BEAR_THIN_LIQUIDITY_03",
                    persona="bear_researcher",
                    metric="est_buy_slippage_bps",
                    value=f"{liq.est_buy_slippage_bps:.2f} bps",
                    threshold=">= 10.00 bps",
                    weight=w3,
                    score_contribution=score3,
                    candle_close_time=c_time,
                    template_summary=f"Execution friction: elevated buy slippage {liq.est_buy_slippage_bps:.2f} bps on $10 order (+{score3:.2f} risk pts).",
                )
            )

        # 4. Sell Wall / Negative Imbalance (Weight: 15.0)
        w4 = Decimal("15.00")
        if liq.imbalance_ratio <= -0.10:
            scale = min(abs(liq.imbalance_ratio) / 0.50, 1.0)
            score4 = Decimal(str(round(float(w4) * scale, 2)))
            total_pts += score4
            evidence_list.append(
                EvidenceItem(
                    rule_id="BEAR_OB_PRESSURE_04",
                    persona="bear_researcher",
                    metric="imbalance_ratio",
                    value=f"{liq.imbalance_ratio:+.2f}",
                    threshold="<= -0.10",
                    weight=w4,
                    score_contribution=score4,
                    candle_close_time=c_time,
                    template_summary=f"L2 orderbook sell-wall pressure detected with imbalance {liq.imbalance_ratio:+.2f} (+{score4:.2f} risk pts).",
                )
            )

        # 5. Nearby Resistance Rejection (Weight: 15.0)
        w5 = Decimal("15.00")
        if trend.distance_to_high_20_pct <= 0.50:
            score5 = w5
            total_pts += score5
            evidence_list.append(
                EvidenceItem(
                    rule_id="BEAR_RESISTANCE_NEAR_05",
                    persona="bear_researcher",
                    metric="distance_to_high_20_pct",
                    value=f"{trend.distance_to_high_20_pct:.2f}%",
                    threshold="<= 0.50%",
                    weight=w5,
                    score_contribution=score5,
                    candle_close_time=c_time,
                    template_summary=f"Price is within {trend.distance_to_high_20_pct:.2f}% of 20-bar resistance high, risking rejection (+{score5:.2f} risk pts).",
                )
            )

        clamped_score = min(max(total_pts, Decimal("0.00")), Decimal("100.00"))
        return ResearcherScore(
            persona="bear_researcher",
            total_score=clamped_score,
            evidence=tuple(evidence_list),
        )
