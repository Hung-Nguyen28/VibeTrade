"""Test Gate P5 — Independent Verification Gate & Firewall (VibeTrade v1.1).

Validates:
1. DataAuditor: detects unconfirmed candles, lookahead timestamps, time gaps, crossed books.
2. StrategyReviewer: independently re-sums EvidenceItem contributions, verifies mathematical
   identities (S_raw = S_Bull - S_Bear, S_net = S_raw * M_regime), catches verdict tampering.
3. VerificationGate: consolidates 3-layer audit (Data, Strategy, Schema) and seals with SHA-256.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.vibetrade.data.okx_models import ClosedCandle, OrderBookLiquiditySnapshot
from src.vibetrade.research import (
    CrucibleEngine,
    EvidenceItem,
    FocusFeatureVector,
    MicrostructureLiquidityMetrics,
    ResearchReport,
    TrendMomentumMetrics,
    VolumeVolatilityMetrics,
)
from src.vibetrade.scanner.models import MarketRegimeSnapshot, make_signal_id
from src.vibetrade.verification import (
    DataAuditor,
    StrategyReviewer,
    VerificationGate,
)

NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
TF_15M = 15 * 60 * 1000


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def make_clean_candles(count: int = 30) -> list[ClosedCandle]:
    candles: list[ClosedCandle] = []
    start = NOW_MS - count * TF_15M
    for i in range(count):
        o_time = start + i * TF_15M
        c_time = o_time + TF_15M
        candles.append(
            ClosedCandle(
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_open_time=o_time,
                candle_close_time=c_time,
                open=Decimal("150.00"),
                high=Decimal("152.00"),
                low=Decimal("149.00"),
                close=Decimal("151.00"),
                vol_base=Decimal("1000.00"),
                vol_quote=Decimal("151000.00"),
                confirm=True,
            )
        )
    return candles


def make_clean_orderbook() -> OrderBookLiquiditySnapshot:
    return OrderBookLiquiditySnapshot(
        inst_id="SOL-USDT",
        ts_utc_ms=NOW_MS,
        best_bid=Decimal("150.00"),
        best_ask=Decimal("150.10"),
        mid_price=Decimal("150.05"),
        spread_bps=Decimal("6.66"),
        depth_levels=20,
        bid_depth_usdt=Decimal("50000.00"),
        ask_depth_usdt=Decimal("50000.00"),
        imbalance_ratio=Decimal("0.20"),
        probe_notional_usdt=Decimal("10.00"),
        est_buy_slippage_bps=Decimal("3.0"),
        est_sell_slippage_bps=Decimal("3.0"),
        buy_fully_filled=True,
        sell_fully_filled=True,
    )


def make_clean_report() -> ResearchReport:
    sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
    ev_bull = EvidenceItem(
        rule_id="BULL_RVOL_SURGE_01",
        persona="bull_researcher",
        metric="rvol_20",
        value="2.50x",
        threshold=">= 2.00x",
        weight=Decimal("25.00"),
        score_contribution=Decimal("20.00"),
        candle_close_time=NOW_MS,
        template_summary="Volume surge confirmed.",
    )
    ev_bear = EvidenceItem(
        rule_id="BEAR_RESISTANCE_NEAR_05",
        persona="bear_researcher",
        metric="distance_to_high_20_pct",
        value="0.40%",
        threshold="<= 0.50%",
        weight=Decimal("15.00"),
        score_contribution=Decimal("10.00"),
        candle_close_time=NOW_MS,
        template_summary="Resistance nearby.",
    )

    s_bull = Decimal("20.00")
    s_bear = Decimal("10.00")
    s_raw = Decimal("10.00")
    regime_mult = Decimal("1.10")
    s_net = (s_raw * regime_mult).quantize(Decimal("0.01"))  # 11.00

    return ResearchReport(
        report_id=f"rep:{sig_id}",
        signal_id=sig_id,
        inst_id="SOL-USDT",
        timeframe="15m",
        candle_close_time=NOW_MS,
        verdict="WATCHLIST_NEUTRAL",
        score_bull=s_bull,
        score_bear=s_bear,
        score_raw=s_raw,
        score_net=s_net,
        regime="BULL_TREND",
        regime_multiplier=regime_mult,
        evidence=(ev_bull, ev_bear),
        template_summary="Verdict WATCHLIST_NEUTRAL",
        evaluated_at_utc_ms=NOW_MS,
        missing_inputs=(),
    )


# ---------------------------------------------------------------------------
# 1. DataAuditor Tests
# ---------------------------------------------------------------------------


class TestDataAuditor:
    """Verifies that DataAuditor catches corrupt or lookahead market data."""

    def test_clean_market_data_passes(self) -> None:
        auditor = DataAuditor()
        candles = make_clean_candles(30)
        book = make_clean_orderbook()
        report = auditor.audit_focus_inputs(candles, book, audit_utc_ms=NOW_MS)
        assert report.passed is True
        assert len(report.violations) == 0

    def test_future_candle_is_caught(self) -> None:
        auditor = DataAuditor()
        candles = make_clean_candles(30)
        # Set audit time to BEFORE the last candle close (lookahead)
        report = auditor.audit_focus_inputs(candles, make_clean_orderbook(), audit_utc_ms=NOW_MS - 1000)
        assert report.passed is False
        assert any("FUTURE_CANDLE_CLOSE" in v for v in report.violations)

    def test_time_discontinuity_is_caught(self) -> None:
        auditor = DataAuditor()
        candles = make_clean_candles(30)
        # Introduce a gap between bar 10 and 11
        bar_11 = candles[11]
        candles[11] = ClosedCandle(
            inst_id=bar_11.inst_id,
            timeframe=bar_11.timeframe,
            candle_open_time=bar_11.candle_open_time + 60_000,  # 1 minute gap!
            candle_close_time=bar_11.candle_close_time + 60_000,
            open=bar_11.open,
            high=bar_11.high,
            low=bar_11.low,
            close=bar_11.close,
            vol_base=bar_11.vol_base,
            vol_quote=bar_11.vol_quote,
            confirm=True,
        )
        report = auditor.audit_focus_inputs(candles, make_clean_orderbook(), audit_utc_ms=NOW_MS + 60_000)
        assert report.passed is False
        assert any("TIME_DISCONTINUITY" in v for v in report.violations)

    def test_future_orderbook_timestamp_is_caught(self) -> None:
        auditor = DataAuditor()
        candles = make_clean_candles(30)
        book = make_clean_orderbook()
        # Set audit time to BEFORE orderbook timestamp
        report = auditor.audit_focus_inputs(candles, book, audit_utc_ms=NOW_MS - 5000)
        assert report.passed is False
        assert any("FUTURE_ORDERBOOK_TIMESTAMP" in v for v in report.violations)


# ---------------------------------------------------------------------------
# 2. StrategyReviewer Tests
# ---------------------------------------------------------------------------


class TestStrategyReviewer:
    """Verifies that StrategyReviewer catches calculation discrepancies and tampering."""

    def test_clean_strategy_report_passes(self) -> None:
        reviewer = StrategyReviewer()
        report = make_clean_report()
        res = reviewer.review_report(report)
        assert res.passed is True
        assert len(res.violations) == 0

    def test_tampered_bull_score_is_caught(self) -> None:
        reviewer = StrategyReviewer()
        clean = make_clean_report()
        # Tamper: inflate score_bull without changing evidence
        tampered = ResearchReport(
            report_id=clean.report_id,
            signal_id=clean.signal_id,
            inst_id=clean.inst_id,
            timeframe=clean.timeframe,
            candle_close_time=clean.candle_close_time,
            verdict=clean.verdict,
            score_bull=clean.score_bull + Decimal("30.00"),  # Tampered!
            score_bear=clean.score_bear,
            score_raw=clean.score_raw,
            score_net=clean.score_net,
            regime=clean.regime,
            regime_multiplier=clean.regime_multiplier,
            evidence=clean.evidence,
            template_summary=clean.template_summary,
            evaluated_at_utc_ms=clean.evaluated_at_utc_ms,
            missing_inputs=clean.missing_inputs,
        )
        res = reviewer.review_report(tampered)
        assert res.passed is False
        assert any("SCORE_BULL_MISMATCH" in v for v in res.violations)

    def test_tampered_verdict_threshold_is_caught(self) -> None:
        reviewer = StrategyReviewer()
        clean = make_clean_report()
        # Tamper: Declare ACTIONABLE_LONG when S_net is only 11.00 (< threshold 30.00)
        tampered = ResearchReport(
            report_id=clean.report_id,
            signal_id=clean.signal_id,
            inst_id=clean.inst_id,
            timeframe=clean.timeframe,
            candle_close_time=clean.candle_close_time,
            verdict="ACTIONABLE_LONG",  # Tampered verdict!
            score_bull=clean.score_bull,
            score_bear=clean.score_bear,
            score_raw=clean.score_raw,
            score_net=clean.score_net,
            regime=clean.regime,
            regime_multiplier=clean.regime_multiplier,
            evidence=clean.evidence,
            template_summary=clean.template_summary,
            evaluated_at_utc_ms=clean.evaluated_at_utc_ms,
            missing_inputs=clean.missing_inputs,
        )
        res = reviewer.review_report(tampered)
        assert res.passed is False
        assert any("VERDICT_THRESHOLD_BREACH" in v for v in res.violations)


# ---------------------------------------------------------------------------
# 3. VerificationGate Tests
# ---------------------------------------------------------------------------


class TestVerificationGate:
    """Verifies that VerificationGate issues signed receipts and halts tampered reports."""

    def test_clean_report_passes_and_receives_receipt(self) -> None:
        gate = VerificationGate()
        report = make_clean_report()
        candles = make_clean_candles(30)
        book = make_clean_orderbook()

        receipt = gate.verify_report(report, candles, book, audit_utc_ms=NOW_MS)
        assert receipt.status == "VERIFIED_PASS"
        assert receipt.auditor_passed is True
        assert receipt.reviewer_passed is True
        assert receipt.schema_passed is True
        assert receipt.can_proceed_to_risk is True
        assert len(receipt.report_sha256) == 64

    def test_tampered_report_fails_gate(self) -> None:
        gate = VerificationGate()
        clean = make_clean_report()
        # Tamper net score
        tampered = ResearchReport(
            report_id=clean.report_id,
            signal_id=clean.signal_id,
            inst_id=clean.inst_id,
            timeframe=clean.timeframe,
            candle_close_time=clean.candle_close_time,
            verdict=clean.verdict,
            score_bull=clean.score_bull,
            score_bear=clean.score_bear,
            score_raw=clean.score_raw,
            score_net=Decimal("99.99"),  # Tampered!
            regime=clean.regime,
            regime_multiplier=clean.regime_multiplier,
            evidence=clean.evidence,
            template_summary=clean.template_summary,
            evaluated_at_utc_ms=clean.evaluated_at_utc_ms,
            missing_inputs=clean.missing_inputs,
        )
        candles = make_clean_candles(30)
        book = make_clean_orderbook()

        receipt = gate.verify_report(tampered, candles, book, audit_utc_ms=NOW_MS)
        assert receipt.status == "VERIFIED_FAIL"
        assert receipt.can_proceed_to_risk is False
        assert any("SCORE_NET_MISMATCH" in v for v in receipt.violations)
