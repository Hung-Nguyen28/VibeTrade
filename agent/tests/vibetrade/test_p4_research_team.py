"""Test Gate P4 — Deterministic Research Team & Explainable Personas (VibeTrade v1.1).

Validates:
1. Multi-dimensional Analysts feature extraction (Trend, Volume, Microstructure).
2. Missing Data Gate: strictly returns INCONCLUSIVE when inputs are incomplete/missing.
3. Bull & Bear Researcher scoring determinism and EvidenceItem binding.
4. Mathematical invariant: S_raw = S_Bull - S_Bear, S_net = S_raw * M_regime.
5. Schema compliance: research_history.json validates with Draft 2020-12 validator.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.vibetrade.data.bar_close import bar_duration_ms
from src.vibetrade.data.okx_models import (
    ClosedCandle,
    ModelValidationError,
    OrderBookLiquiditySnapshot,
)
from src.vibetrade.research import (
    BearResearcher,
    BullResearcher,
    CrucibleEngine,
    EvidenceItem,
    FocusFeatureVector,
    MicrostructureLiquidityMetrics,
    ResearchHistorySnapshot,
    ResearchReport,
    TrendMomentumMetrics,
    VolumeVolatilityMetrics,
    extract_analysts_features,
)
from src.vibetrade.scanner.models import (
    MarketRegimeSnapshot,
    make_signal_id,
)

NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
TF_15M = 15 * 60 * 1000
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "v1.1" / "research_history.schema.json"


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def generate_candles(
    inst_id: str = "SOL-USDT",
    timeframe: str = "15m",
    count: int = 35,
    base_price: float = 100.0,
    trend_pct: float = 0.002,
    vol_base: float = 1000.0,
    end_time_ms: int = NOW_MS,
) -> list[ClosedCandle]:
    duration = bar_duration_ms(timeframe)
    start_time_ms = end_time_ms - count * duration
    candles: list[ClosedCandle] = []

    price = base_price
    for i in range(count):
        open_time = start_time_ms + i * duration
        close_time = open_time + duration
        price = price * (1.0 + trend_pct)
        c_open = price * 0.998
        c_high = price * 1.004
        c_low = price * 0.996
        c_close = price

        candles.append(
            ClosedCandle(
                inst_id=inst_id,
                timeframe=timeframe,
                candle_open_time=open_time,
                candle_close_time=close_time,
                open=Decimal(str(round(c_open, 4))),
                high=Decimal(str(round(c_high, 4))),
                low=Decimal(str(round(c_low, 4))),
                close=Decimal(str(round(c_close, 4))),
                vol_base=Decimal(str(round(vol_base, 2))),
                vol_quote=Decimal(str(round(vol_base * price, 2))),
                confirm=True,
            )
        )
    return candles


def make_test_orderbook(
    inst_id: str = "SOL-USDT",
    spread_bps: str = "10.0",
    buy_slippage_bps: str = "4.0",
    imbalance_ratio: str = "0.25",
    buy_fully_filled: bool = True,
) -> OrderBookLiquiditySnapshot:
    return OrderBookLiquiditySnapshot(
        inst_id=inst_id,
        ts_utc_ms=NOW_MS,
        best_bid=Decimal("150.00"),
        best_ask=Decimal("150.15"),
        mid_price=Decimal("150.075"),
        spread_bps=Decimal(spread_bps),
        depth_levels=20,
        bid_depth_usdt=Decimal("50000.00"),
        ask_depth_usdt=Decimal("50000.00"),
        imbalance_ratio=Decimal(imbalance_ratio),
        probe_notional_usdt=Decimal("10.00"),
        est_buy_slippage_bps=Decimal(buy_slippage_bps),
        est_sell_slippage_bps=Decimal("4.0"),
        buy_fully_filled=buy_fully_filled,
        sell_fully_filled=True,
    )


def make_test_regime(regime: str = "BULL_TREND", multiplier: str = "1.10") -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        regime=regime,
        multiplier=Decimal(multiplier),
        btc_price=Decimal("70000.00"),
        btc_ema_fast=Decimal("69000.00"),
        btc_ema_slow=Decimal("68000.00"),
        btc_rsi=Decimal("60.00"),
        btc_atr_pct=Decimal("1.5000"),
        market_breadth_pct=Decimal("65.00"),
        detected_at_utc_ms=NOW_MS,
        details={},
    )


# ---------------------------------------------------------------------------
# 1. Multi-Dimensional Analysts Tests
# ---------------------------------------------------------------------------


class TestAnalystsFeatureExtraction:
    """Verifies feature extraction across trend, volume, and microstructure."""

    def test_complete_feature_extraction(self) -> None:
        candles_15m = generate_candles("SOL-USDT", count=30, end_time_ms=NOW_MS)
        candles_1h = generate_candles("SOL-USDT", timeframe="1H", count=25, end_time_ms=NOW_MS)
        book = make_test_orderbook("SOL-USDT")

        features = extract_analysts_features(
            candles_15m=candles_15m,
            now_ms=NOW_MS,
            orderbook=book,
            candles_1h=candles_1h,
        )

        assert features.is_complete
        assert len(features.missing_fields) == 0
        assert features.trend is not None
        assert features.trend.ema_alignment in {"BULLISH", "BEARISH"}
        assert features.vol is not None
        assert features.vol.rvol_20 > 0.0
        assert features.liq is not None
        assert features.liq.buy_fully_filled is True

    def test_missing_orderbook_flags_incomplete(self) -> None:
        candles_15m = generate_candles("SOL-USDT", count=30, end_time_ms=NOW_MS)
        features = extract_analysts_features(
            candles_15m=candles_15m,
            now_ms=NOW_MS,
            orderbook=None,  # Missing book!
        )
        assert not features.is_complete
        assert "orderbook_snapshot_missing" in features.missing_fields

    def test_insufficient_candles_flags_incomplete(self) -> None:
        candles_15m = generate_candles("SOL-USDT", count=10, end_time_ms=NOW_MS)  # Only 10 bars
        book = make_test_orderbook("SOL-USDT")
        features = extract_analysts_features(
            candles_15m=candles_15m,
            now_ms=NOW_MS,
            orderbook=book,
        )
        assert not features.is_complete
        assert any("insufficient_candles" in f for f in features.missing_fields)


# ---------------------------------------------------------------------------
# 2. Bull & Bear Researchers Tests
# ---------------------------------------------------------------------------


class TestBullAndBearResearchers:
    """Verifies deterministic rule evaluation and EvidenceItem binding."""

    def test_bull_researcher_scoring_and_evidence(self) -> None:
        # Construct features favorable to Bull
        features = FocusFeatureVector(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            trend=TrendMomentumMetrics(
                ema_fast=105.0,
                ema_slow=100.0,
                ema_alignment="BULLISH",
                rsi_14=62.0,  # healthy momentum
                macd_slope=1.5,
                distance_to_high_20_pct=5.0,
                htf_trend="BULLISH",
            ),
            vol=VolumeVolatilityMetrics(
                rvol_20=3.2,  # volume surge
                volume_zscore=2.8,
                atr_14=2.0,
                atr_pct=1.9,
                expansion_ratio=1.6,
            ),
            liq=MicrostructureLiquidityMetrics(
                spread_bps=8.0,
                est_buy_slippage_bps=3.5,  # tight slippage
                imbalance_ratio=0.35,  # positive bid dominance
                bid_depth_usdt=80000.0,
                buy_fully_filled=True,
            ),
            missing_fields=(),
        )

        researcher = BullResearcher()
        score = researcher.evaluate(features)

        assert score.persona == "bull_researcher"
        assert score.total_score >= Decimal("70.00")
        assert len(score.evidence) >= 4

        # Verify evidence properties
        for ev in score.evidence:
            assert ev.persona == "bull_researcher"
            assert ev.score_contribution > Decimal(0)
            assert ev.candle_close_time == NOW_MS
            assert ev.template_summary != ""

    def test_bear_researcher_scoring_and_evidence(self) -> None:
        # Construct features with heavy risk headwinds
        features = FocusFeatureVector(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            trend=TrendMomentumMetrics(
                ema_fast=95.0,
                ema_slow=100.0,
                ema_alignment="BEARISH",
                rsi_14=82.0,  # overbought!
                macd_slope=-1.0,
                distance_to_high_20_pct=0.20,  # right at resistance!
                htf_trend="BEARISH",
            ),
            vol=VolumeVolatilityMetrics(
                rvol_20=1.0,
                volume_zscore=0.0,
                atr_14=2.0,
                atr_pct=2.0,
                expansion_ratio=1.0,
            ),
            liq=MicrostructureLiquidityMetrics(
                spread_bps=28.0,  # wide spread
                est_buy_slippage_bps=16.0,  # high slippage
                imbalance_ratio=-0.30,  # sell wall pressure
                bid_depth_usdt=5000.0,
                buy_fully_filled=True,
            ),
            missing_fields=(),
        )

        researcher = BearResearcher()
        score = researcher.evaluate(features)

        assert score.persona == "bear_researcher"
        assert score.total_score >= Decimal("70.00")
        assert len(score.evidence) >= 4

    def test_researcher_absolute_determinism(self) -> None:
        candles_15m = generate_candles("ETH-USDT", count=30, end_time_ms=NOW_MS)
        book = make_test_orderbook("ETH-USDT")
        features = extract_analysts_features(candles_15m, now_ms=NOW_MS, orderbook=book)

        bull = BullResearcher()
        bear = BearResearcher()

        score_bull_1 = bull.evaluate(features)
        score_bull_2 = bull.evaluate(features)
        assert score_bull_1.total_score == score_bull_2.total_score
        assert [e.to_dict() for e in score_bull_1.evidence] == [e.to_dict() for e in score_bull_2.evidence]

        score_bear_1 = bear.evaluate(features)
        score_bear_2 = bear.evaluate(features)
        assert score_bear_1.total_score == score_bear_2.total_score
        assert [e.to_dict() for e in score_bear_1.evidence] == [e.to_dict() for e in score_bear_2.evidence]


# ---------------------------------------------------------------------------
# 3. Crucible & Explainable Decision Tests
# ---------------------------------------------------------------------------


class TestCrucibleEngine:
    """Verifies mathematical identity, Missing Data Gate, and verdict routing."""

    def test_missing_data_gate_returns_inconclusive(self) -> None:
        crucible = CrucibleEngine()
        regime = make_test_regime()
        incomplete_features = FocusFeatureVector(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            trend=None,
            vol=None,
            liq=None,
            missing_fields=("orderbook_snapshot_missing", "insufficient_candles"),
        )

        report = crucible.evaluate_candidate(incomplete_features, regime, now_ms=NOW_MS)
        assert report.verdict == "INCONCLUSIVE"
        assert report.score_bull == Decimal("0.00")
        assert report.score_bear == Decimal("0.00")
        assert report.score_net == Decimal("0.00")
        assert len(report.evidence) == 0
        assert "INCONCLUSIVE" in report.template_summary
        assert "orderbook_snapshot_missing" in report.missing_inputs

    def test_mathematical_identity_s_net_equals_s_raw_times_m_regime(self) -> None:
        crucible = CrucibleEngine()
        regime = make_test_regime("BULL_TREND", multiplier="1.10")

        features = FocusFeatureVector(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            trend=TrendMomentumMetrics(
                ema_fast=105.0,
                ema_slow=100.0,
                ema_alignment="BULLISH",
                rsi_14=60.0,
                macd_slope=1.0,
                distance_to_high_20_pct=4.0,
                htf_trend="BULLISH",
            ),
            vol=VolumeVolatilityMetrics(
                rvol_20=2.5,
                volume_zscore=2.0,
                atr_14=2.0,
                atr_pct=1.8,
                expansion_ratio=1.2,
            ),
            liq=MicrostructureLiquidityMetrics(
                spread_bps=8.0,
                est_buy_slippage_bps=3.0,
                imbalance_ratio=0.20,
                bid_depth_usdt=50000.0,
                buy_fully_filled=True,
            ),
            missing_fields=(),
        )

        report = crucible.evaluate_candidate(features, regime, now_ms=NOW_MS)

        # Invariant checks:
        assert report.score_raw == report.score_bull - report.score_bear
        expected_net = (report.score_raw * regime.multiplier).quantize(Decimal("0.01"))
        assert report.score_net == expected_net

    def test_bear_risk_veto(self) -> None:
        crucible = CrucibleEngine(bear_veto_threshold=Decimal("60.00"))
        regime = make_test_regime()

        # Features with extreme bear risk
        features = FocusFeatureVector(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            trend=TrendMomentumMetrics(
                ema_fast=90.0,
                ema_slow=100.0,
                ema_alignment="BEARISH",
                rsi_14=85.0,  # extreme overbought
                macd_slope=-2.0,
                distance_to_high_20_pct=0.10,
                htf_trend="BEARISH",
            ),
            vol=VolumeVolatilityMetrics(rvol_20=1.0, volume_zscore=0.0, atr_14=2.0, atr_pct=2.0, expansion_ratio=1.0),
            liq=MicrostructureLiquidityMetrics(
                spread_bps=25.0,
                est_buy_slippage_bps=18.0,
                imbalance_ratio=-0.35,
                bid_depth_usdt=5000.0,
                buy_fully_filled=True,
            ),
            missing_fields=(),
        )

        report = crucible.evaluate_candidate(features, regime, now_ms=NOW_MS)
        assert report.verdict == "AVOID_BEARISH"
        assert report.score_bear >= Decimal("60.00")


# ---------------------------------------------------------------------------
# 4. Research History Model & Schema Tests
# ---------------------------------------------------------------------------


class TestResearchHistorySchema:
    """Validates ResearchHistorySnapshot against JSON Schema Draft 2020-12."""

    @pytest.fixture(scope="class")
    @classmethod
    def schema_validator(cls) -> Any:
        jsonschema = pytest.importorskip("jsonschema")
        assert SCHEMA_PATH.is_file(), f"Missing schema file: {SCHEMA_PATH}"
        schema_dict = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema_dict)
        return jsonschema.Draft202012Validator(schema_dict)

    def test_research_history_validates_against_schema(self, schema_validator: Any) -> None:
        sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
        ev1 = EvidenceItem(
            rule_id="BULL_RVOL_SURGE_01",
            persona="bull_researcher",
            metric="rvol_20",
            value="2.80x",
            threshold=">= 2.00x",
            weight=Decimal("25.00"),
            score_contribution=Decimal("17.50"),
            candle_close_time=NOW_MS,
            template_summary="Volume surge confirmed.",
        )

        report = ResearchReport(
            report_id=f"rep:{sig_id}",
            signal_id=sig_id,
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            verdict="ACTIONABLE_LONG",
            score_bull=Decimal("65.00"),
            score_bear=Decimal("15.00"),
            score_raw=Decimal("50.00"),
            score_net=Decimal("55.00"),
            regime="BULL_TREND",
            regime_multiplier=Decimal("1.10"),
            evidence=(ev1,),
            template_summary="ACTIONABLE_LONG: Strong confluence.",
            evaluated_at_utc_ms=NOW_MS,
            missing_inputs=(),
        )

        snapshot = ResearchHistorySnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            reports=(report,),
        )

        doc = snapshot.to_dict()
        errors = list(schema_validator.iter_errors(doc))
        assert not errors, f"Schema validation errors: {[e.message for e in errors]}"

    def test_schema_rejects_extra_properties(self, schema_validator: Any) -> None:
        snapshot = ResearchHistorySnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            reports=(),
        )
        doc = snapshot.to_dict()
        doc["forbidden_extra"] = True
        assert not schema_validator.is_valid(doc)

    def test_schema_rejects_malformed_report_id(self, schema_validator: Any) -> None:
        sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
        report = ResearchReport(
            report_id=f"rep:{sig_id}",
            signal_id=sig_id,
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            verdict="ACTIONABLE_LONG",
            score_bull=Decimal("65.00"),
            score_bear=Decimal("15.00"),
            score_raw=Decimal("50.00"),
            score_net=Decimal("55.00"),
            regime="BULL_TREND",
            regime_multiplier=Decimal("1.10"),
            evidence=(),
            template_summary="Summary",
            evaluated_at_utc_ms=NOW_MS,
            missing_inputs=(),
        )
        doc = ResearchHistorySnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            reports=(report,),
        ).to_dict()

        doc["reports"][0]["report_id"] = "ILLEGAL_ID"
        assert not schema_validator.is_valid(doc)

    def test_inconclusive_report_validates_against_schema(self, schema_validator: Any) -> None:
        sig_id = make_signal_id("AVAX-USDT", "15m", NOW_MS)
        report = ResearchReport(
            report_id=f"rep:{sig_id}",
            signal_id=sig_id,
            inst_id="AVAX-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            verdict="INCONCLUSIVE",
            score_bull=Decimal("0.00"),
            score_bear=Decimal("0.00"),
            score_raw=Decimal("0.00"),
            score_net=Decimal("0.00"),
            regime="BULL_TREND",
            regime_multiplier=Decimal("1.10"),
            evidence=(),
            template_summary="Halted due to missing inputs",
            evaluated_at_utc_ms=NOW_MS,
            missing_inputs=("orderbook_snapshot_missing", "insufficient_candles"),
        )
        snapshot = ResearchHistorySnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            reports=(report,),
        )
        doc = snapshot.to_dict()
        assert schema_validator.is_valid(doc)


# ---------------------------------------------------------------------------
# 5. Model Invariants & Guardrails
# ---------------------------------------------------------------------------


class TestResearchModelInvariants:
    """Verifies domain constraints on EvidenceItem and ResearchReport."""

    def test_evidence_item_invariants(self) -> None:
        with pytest.raises(ModelValidationError, match="Invalid persona"):
            EvidenceItem(
                rule_id="RULE1",
                persona="illegal_persona",
                metric="rvol",
                value="2.0",
                threshold=">= 1.5",
                weight=Decimal("10.00"),
                score_contribution=Decimal("5.00"),
                candle_close_time=NOW_MS,
                template_summary="desc",
            )

        with pytest.raises(ModelValidationError, match="candle_close_time must be positive"):
            EvidenceItem(
                rule_id="RULE1",
                persona="bull_researcher",
                metric="rvol",
                value="2.0",
                threshold=">= 1.5",
                weight=Decimal("10.00"),
                score_contribution=Decimal("5.00"),
                candle_close_time=-1,
                template_summary="desc",
            )

    def test_research_report_invariants(self) -> None:
        sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
        # Mismatched report_id
        with pytest.raises(ModelValidationError, match="report_id mismatch"):
            ResearchReport(
                report_id="rep:DIFFERENT-ID:15m:123",
                signal_id=sig_id,
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                verdict="ACTIONABLE_LONG",
                score_bull=Decimal("50.00"),
                score_bear=Decimal("10.00"),
                score_raw=Decimal("40.00"),
                score_net=Decimal("44.00"),
                regime="BULL_TREND",
                regime_multiplier=Decimal("1.10"),
                evidence=(),
                template_summary="Summary",
                evaluated_at_utc_ms=NOW_MS,
                missing_inputs=(),
            )

        # Evaluated before candle close (lookahead violation)
        with pytest.raises(ModelValidationError, match="candle_close_time cannot be in future"):
            ResearchReport(
                report_id=f"rep:{sig_id}",
                signal_id=sig_id,
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                verdict="ACTIONABLE_LONG",
                score_bull=Decimal("50.00"),
                score_bear=Decimal("10.00"),
                score_raw=Decimal("40.00"),
                score_net=Decimal("44.00"),
                regime="BULL_TREND",
                regime_multiplier=Decimal("1.10"),
                evidence=(),
                template_summary="Summary",
                evaluated_at_utc_ms=NOW_MS - 1000,
                missing_inputs=(),
            )

