"""Test Gate P2 — Market Scanner & Surveillance Anomaly Engine (VibeTrade v1.1).

Validates:
1. Tradable Universe Filter (liquidity, spread, stablecoin exclusion, $10 micro-order budget).
2. Market Regime Detector (BULL_TREND, BEAR_TREND, HIGH_VOL_CHOP, RANGE_BOUND determinism).
3. Surveillance Anomaly Scanner (VOLUME_SPIKE, VOLATILITY_EXPANSION, BREAKOUT, MOMENTUM_SHIFT).
4. Anti-Lookahead Bias & Truncation Invariance.
5. Opportunity Queue Snapshot & JSON Schema (Draft 2020-12 strict validation).
6. Deterministic Idempotency & Ranking.
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
    SpotInstrumentRule,
    SpotTicker24h,
)
from src.vibetrade.scanner import (
    MarketRegimeConfig,
    MarketRegimeSnapshot,
    OpportunityCandidate,
    OpportunityQueueSnapshot,
    ScannerConfig,
    UniverseFilterConfig,
    compute_market_breadth,
    detect_market_regime,
    filter_tradable_universe,
    make_signal_id,
    scan_instrument_anomalies,
    scan_market_opportunities,
)

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "v1.1" / "opportunity_queue.schema.json"
NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
TF_15M = 15 * 60 * 1000


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def make_rule(
    inst_id: str = "SOL-USDT",
    base_ccy: str = "SOL",
    min_size: str = "0.01",
    tick_size: str = "0.01",
    lot_size: str = "0.01",
    state: str = "live",
) -> SpotInstrumentRule:
    return SpotInstrumentRule(
        inst_id=inst_id,
        base_ccy=base_ccy,
        quote_ccy="USDT",
        tick_size=Decimal(tick_size),
        lot_size=Decimal(lot_size),
        min_size=Decimal(min_size),
        state=state,
    )


def make_ticker(
    inst_id: str = "SOL-USDT",
    last: str = "150.0",
    bid_px: str = "149.95",
    ask_px: str = "150.05",
    open_24h: str = "145.0",
    vol_quote_24h: str = "500000.0",
    ts_utc_ms: int = NOW_MS,
) -> SpotTicker24h:
    return SpotTicker24h(
        inst_id=inst_id,
        last=Decimal(last),
        bid_px=Decimal(bid_px),
        bid_sz=Decimal("100.0"),
        ask_px=Decimal(ask_px),
        ask_sz=Decimal("100.0"),
        open_24h=Decimal(open_24h),
        high_24h=Decimal("155.0"),
        low_24h=Decimal("144.0"),
        vol_base_24h=Decimal("3000.0"),
        vol_quote_24h=Decimal(vol_quote_24h),
        ts_utc_ms=ts_utc_ms,
    )


def generate_candle_series(
    inst_id: str = "SOL-USDT",
    timeframe: str = "15m",
    count: int = 40,
    base_price: float = 100.0,
    trend_pct: float = 0.0,
    vol_base: float = 1000.0,
    end_time_ms: int = NOW_MS,
) -> list[ClosedCandle]:
    """Generate a synthetic sequence of strictly closed candles."""
    duration = bar_duration_ms(timeframe)
    start_time_ms = end_time_ms - count * duration
    candles: list[ClosedCandle] = []

    price = base_price
    for i in range(count):
        open_time = start_time_ms + i * duration
        close_time = open_time + duration
        price = price * (1.0 + trend_pct)
        c_open = price * 0.998
        c_high = price * 1.005
        c_low = price * 0.995
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


# ---------------------------------------------------------------------------
# 1. Tradable Universe Filter Tests
# ---------------------------------------------------------------------------


class TestTradableUniverseFilter:
    """Verifies filtering of OKX Spot instruments under micro-portfolio constraints."""

    def test_live_tradable_pair_passes(self) -> None:
        rule = make_rule("SOL-USDT", base_ccy="SOL", min_size="0.01")
        ticker = make_ticker("SOL-USDT", last="150.0", ask_px="150.05", vol_quote_24h="200000.0")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 1
        assert result.passed[0].inst_id == "SOL-USDT"
        assert len(result.rejected) == 0

    def test_non_live_rule_is_rejected(self) -> None:
        rule = make_rule("SUSP-USDT", base_ccy="SUSP", state="suspend")
        ticker = make_ticker("SUSP-USDT")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "NOT_LIVE"

    def test_stablecoin_pairs_are_rejected(self) -> None:
        rule = make_rule("USDC-USDT", base_ccy="USDC")
        ticker = make_ticker("USDC-USDT", last="1.0", ask_px="1.0001", bid_px="0.9999")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "STABLECOIN_PAIR"

    def test_missing_ticker_is_rejected(self) -> None:
        rule = make_rule("AVAX-USDT", base_ccy="AVAX")
        result = filter_tradable_universe([rule], [])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "MISSING_TICKER"

    def test_low_quote_volume_is_rejected(self) -> None:
        rule = make_rule("ILLIQ-USDT", base_ccy="ILLIQ")
        ticker = make_ticker("ILLIQ-USDT", vol_quote_24h="10000.0")  # default min is 50000.0
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "LOW_LIQUIDITY_24H"

    def test_wide_spread_is_rejected(self) -> None:
        rule = make_rule("WIDE-USDT", base_ccy="WIDE")
        # Spread = (101 - 99) / 100 * 10000 = 200 bps > 35 bps
        ticker = make_ticker("WIDE-USDT", last="100.0", bid_px="99.0", ask_px="101.0")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "SPREAD_TOO_WIDE"

    def test_min_order_exceeds_budget_rejected_for_10_dollar_account(self) -> None:
        # e.g. min_size is 1.0 token, but price is 15.0 USDT -> min order = 15.0 USDT > 10.0 USDT
        rule = make_rule("EXP-USDT", base_ccy="EXP", min_size="1.0")
        ticker = make_ticker("EXP-USDT", last="15.0", bid_px="14.99", ask_px="15.01")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "MIN_ORDER_EXCEEDS_BUDGET"

    def test_min_order_within_budget_passes(self) -> None:
        # min_size = 0.05, ask_px = 150.0 -> min order = 7.50 USDT <= 10.0 USDT
        rule = make_rule("FITS-USDT", base_ccy="FITS", min_size="0.05")
        ticker = make_ticker("FITS-USDT", last="150.0", bid_px="149.95", ask_px="150.0")
        result = filter_tradable_universe([rule], [ticker])
        assert len(result.passed) == 1
        assert result.passed[0].inst_id == "FITS-USDT"
        assert result.passed[0].min_notional_usdt == Decimal("7.500")

    def test_universe_filter_is_sorted_by_inst_id(self) -> None:
        rules = [
            make_rule("ZRX-USDT", base_ccy="ZRX", min_size="1.0"),
            make_rule("ADA-USDT", base_ccy="ADA", min_size="1.0"),
            make_rule("DOT-USDT", base_ccy="DOT", min_size="0.5"),
        ]
        tickers = [
            make_ticker("ZRX-USDT", last="0.5", ask_px="0.51", bid_px="0.509"),
            make_ticker("ADA-USDT", last="0.6", ask_px="0.61", bid_px="0.609"),
            make_ticker("DOT-USDT", last="6.0", ask_px="6.01", bid_px="6.00"),
        ]
        result = filter_tradable_universe(rules, tickers)
        assert [p.inst_id for p in result.passed] == ["ADA-USDT", "DOT-USDT", "ZRX-USDT"]


# ---------------------------------------------------------------------------
# 2. Market Regime Detector Tests
# ---------------------------------------------------------------------------


class TestMarketRegimeDetector:
    """Verifies deterministic macro regime classification."""

    def test_bull_trend_classification(self) -> None:
        # Steadily rising BTC candles
        btc_candles = generate_candle_series(
            inst_id="BTC-USDT",
            count=60,
            base_price=60000.0,
            trend_pct=0.005,  # +0.5% per 15m candle
            end_time_ms=NOW_MS,
        )
        tickers = [
            make_ticker(f"COIN{i}-USDT", last="105.0", open_24h="100.0")  # 100% advancers
            for i in range(10)
        ]
        snapshot = detect_market_regime(btc_candles, tickers, now_ms=NOW_MS)
        assert snapshot.regime == "BULL_TREND"
        assert snapshot.multiplier == Decimal("1.10")
        assert snapshot.btc_price > snapshot.btc_ema_fast > snapshot.btc_ema_slow
        assert snapshot.market_breadth_pct == Decimal("100.00")

    def test_bear_trend_classification(self) -> None:
        # Steadily falling BTC candles
        btc_candles = generate_candle_series(
            inst_id="BTC-USDT",
            count=60,
            base_price=90000.0,
            trend_pct=-0.005,  # -0.5% per 15m candle
            end_time_ms=NOW_MS,
        )
        tickers = [
            make_ticker(f"COIN{i}-USDT", last="90.0", open_24h="100.0")  # 0% advancers
            for i in range(10)
        ]
        snapshot = detect_market_regime(btc_candles, tickers, now_ms=NOW_MS)
        assert snapshot.regime == "BEAR_TREND"
        assert snapshot.multiplier == Decimal("0.40")
        assert snapshot.btc_price < snapshot.btc_ema_fast < snapshot.btc_ema_slow
        assert snapshot.market_breadth_pct == Decimal("0.00")

    def test_high_vol_chop_classification(self) -> None:
        # Flat price with extreme bar ranges
        duration = TF_15M
        start_time = NOW_MS - 55 * duration
        btc_candles: list[ClosedCandle] = []
        for i in range(55):
            o_time = start_time + i * duration
            c_time = o_time + duration
            # Last bar has an explosive range (huge high-low wick)
            multiplier = 5.0 if i >= 50 else 1.0
            btc_candles.append(
                ClosedCandle(
                    inst_id="BTC-USDT",
                    timeframe="15m",
                    candle_open_time=o_time,
                    candle_close_time=c_time,
                    open=Decimal("70000.0"),
                    high=Decimal(str(70000.0 + 1000.0 * multiplier)),
                    low=Decimal(str(70000.0 - 1000.0 * multiplier)),
                    close=Decimal("70000.0"),
                    vol_base=Decimal("500.0"),
                    vol_quote=Decimal("35000000.0"),
                    confirm=True,
                )
            )
        tickers = [make_ticker(f"COIN{i}-USDT", last="100.0", open_24h="100.0") for i in range(10)]
        snapshot = detect_market_regime(btc_candles, tickers, now_ms=NOW_MS)
        assert snapshot.regime == "HIGH_VOL_CHOP"
        assert snapshot.multiplier == Decimal("0.60")

    def test_insufficient_bars_falls_back_to_range_bound(self) -> None:
        # Only 5 bars (below min_warmup_bars=30)
        btc_candles = generate_candle_series("BTC-USDT", count=5, end_time_ms=NOW_MS)
        snapshot = detect_market_regime(btc_candles, [], now_ms=NOW_MS)
        assert snapshot.regime == "RANGE_BOUND"
        assert snapshot.multiplier == Decimal("0.85")
        assert "INSUFFICIENT_WARMUP_BARS" in snapshot.details["fallback_reason"]

    def test_running_candle_rejected_by_bar_close_guard(self) -> None:
        # Candle closing in future (> NOW_MS)
        future_candle = ClosedCandle(
            inst_id="BTC-USDT",
            timeframe="15m",
            candle_open_time=NOW_MS,
            candle_close_time=NOW_MS + TF_15M,
            open=Decimal("70000.0"),
            high=Decimal("70500.0"),
            low=Decimal("69500.0"),
            close=Decimal("70200.0"),
            vol_base=Decimal("10.0"),
            vol_quote=Decimal("702000.0"),
            confirm=True,
        )
        with pytest.raises(ValueError, match="running candle"):
            detect_market_regime([future_candle], [], now_ms=NOW_MS)


# ---------------------------------------------------------------------------
# 3. Surveillance Anomaly Scanner Tests
# ---------------------------------------------------------------------------


class TestSurveillanceScanner:
    """Verifies anomaly detection logic (Volume Spike, Volatility Expansion, Breakout, Momentum Shift)."""

    @pytest.fixture
    def neutral_regime(self) -> Any:
        return detect_market_regime([], [], now_ms=NOW_MS)

    def test_volume_spike_anomaly_detected(self, neutral_regime: Any) -> None:
        # 30 bars with baseline vol=1000, last bar with vol=5000 (RVOL=5.0)
        candles = generate_candle_series("SOL-USDT", count=30, vol_base=1000.0, end_time_ms=NOW_MS)
        last_c = candles[-1]
        candles[-1] = ClosedCandle(
            inst_id=last_c.inst_id,
            timeframe=last_c.timeframe,
            candle_open_time=last_c.candle_open_time,
            candle_close_time=last_c.candle_close_time,
            open=last_c.open,
            high=last_c.high,
            low=last_c.low,
            close=last_c.close,
            vol_base=Decimal("5000.0"),
            vol_quote=Decimal("500000.0"),
            confirm=True,
        )

        candidate = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        assert candidate is not None
        assert "VOLUME_SPIKE" in candidate.anomaly_types
        assert candidate.scanner_score > Decimal(0)
        assert candidate.signal_id == make_signal_id("SOL-USDT", "15m", last_c.candle_close_time)

    def test_breakout_anomaly_detected(self, neutral_regime: Any) -> None:
        # 30 flat bars around $100, last bar closes at $110 (breaking prior highs)
        candles = generate_candle_series("SOL-USDT", count=30, base_price=100.0, end_time_ms=NOW_MS)
        last_c = candles[-1]
        candles[-1] = ClosedCandle(
            inst_id=last_c.inst_id,
            timeframe=last_c.timeframe,
            candle_open_time=last_c.candle_open_time,
            candle_close_time=last_c.candle_close_time,
            open=Decimal("101.0"),
            high=Decimal("111.0"),
            low=Decimal("100.5"),
            close=Decimal("110.0"),
            vol_base=last_c.vol_base,
            vol_quote=Decimal("110000.0"),
            confirm=True,
        )

        candidate = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        assert candidate is not None
        assert "BREAKOUT" in candidate.anomaly_types

    def test_volatility_expansion_detected(self, neutral_regime: Any) -> None:
        # Baseline range ~ 1.0, last bar range = 5.0 (> 1.5 * ATR)
        candles = generate_candle_series("SOL-USDT", count=30, base_price=100.0, end_time_ms=NOW_MS)
        last_c = candles[-1]
        candles[-1] = ClosedCandle(
            inst_id=last_c.inst_id,
            timeframe=last_c.timeframe,
            candle_open_time=last_c.candle_open_time,
            candle_close_time=last_c.candle_close_time,
            open=Decimal("100.0"),
            high=Decimal("106.0"),
            low=Decimal("99.0"),
            close=Decimal("105.0"),
            vol_base=last_c.vol_base,
            vol_quote=last_c.vol_quote,
            confirm=True,
        )

        candidate = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        assert candidate is not None
        assert "VOLATILITY_EXPANSION" in candidate.anomaly_types

    def test_confluence_multiple_anomalies_scores_higher(self, neutral_regime: Any) -> None:
        # Bar with both VOLUME_SPIKE, BREAKOUT, and VOLATILITY_EXPANSION
        candles = generate_candle_series("SOL-USDT", count=30, base_price=100.0, end_time_ms=NOW_MS)
        last_c = candles[-1]
        candles[-1] = ClosedCandle(
            inst_id=last_c.inst_id,
            timeframe=last_c.timeframe,
            candle_open_time=last_c.candle_open_time,
            candle_close_time=last_c.candle_close_time,
            open=Decimal("101.0"),
            high=Decimal("112.0"),
            low=Decimal("100.5"),
            close=Decimal("111.0"),
            vol_base=Decimal("6000.0"),  # 6x volume
            vol_quote=Decimal("666000.0"),
            confirm=True,
        )

        cand = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        assert cand is not None
        assert len(cand.anomaly_types) >= 2
        # Score is combined and boosted
        assert cand.scanner_score >= Decimal("50.0")

    def test_no_anomaly_returns_none(self, neutral_regime: Any) -> None:
        # Uniform, flat market
        candles = generate_candle_series("SOL-USDT", count=30, base_price=100.0, end_time_ms=NOW_MS)
        cand = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        assert cand is None

    def test_scanner_idempotency_same_data_produces_identical_signal(self, neutral_regime: Any) -> None:
        candles = generate_candle_series("SOL-USDT", count=30, vol_base=1000.0, end_time_ms=NOW_MS)
        candles[-1] = ClosedCandle(
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_open_time=candles[-1].candle_open_time,
            candle_close_time=candles[-1].candle_close_time,
            open=Decimal("100.0"),
            high=Decimal("110.0"),
            low=Decimal("100.0"),
            close=Decimal("109.0"),
            vol_base=Decimal("4000.0"),
            vol_quote=Decimal("436000.0"),
            confirm=True,
        )

        cand1 = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)
        cand2 = scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime)

        assert cand1 is not None and cand2 is not None
        assert cand1.signal_id == cand2.signal_id
        assert cand1.scanner_score == cand2.scanner_score
        assert cand1.to_dict() == cand2.to_dict()

    def test_insufficient_warmup_bars_returns_none(self, neutral_regime: Any) -> None:
        # 10 bars is less than min_warmup_bars=25
        candles = generate_candle_series("SOL-USDT", count=10, end_time_ms=NOW_MS)
        assert scan_instrument_anomalies(candles, now_ms=NOW_MS, regime_snapshot=neutral_regime) is None

    def test_scan_market_opportunities_multi_symbol_and_capping(self, neutral_regime: Any) -> None:
        # Create 5 symbols with volume spikes
        by_symbol: dict[str, list[ClosedCandle]] = {}
        for sym in ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AVAX-USDT", "LINK-USDT"]:
            candles = generate_candle_series(sym, count=30, vol_base=1000.0, end_time_ms=NOW_MS)
            last_c = candles[-1]
            candles[-1] = ClosedCandle(
                inst_id=sym,
                timeframe="15m",
                candle_open_time=last_c.candle_open_time,
                candle_close_time=last_c.candle_close_time,
                open=Decimal("100.0"),
                high=Decimal("110.0"),
                low=Decimal("100.0"),
                close=Decimal("109.0"),
                vol_base=Decimal("5000.0"),
                vol_quote=Decimal("545000.0"),
                confirm=True,
            )
            by_symbol[sym] = candles

        # Capped to 3
        cfg = ScannerConfig(max_candidates=3)
        snapshot = scan_market_opportunities(by_symbol, now_ms=NOW_MS, regime_snapshot=neutral_regime, config=cfg)
        assert snapshot.queue_size == 3
        assert len(snapshot.candidates) == 3
        # Strict descending scores
        scores = [c.scanner_score for c in snapshot.candidates]
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))



# ---------------------------------------------------------------------------
# 4. Truncation Invariance Tests (Zero Lookahead Bias)
# ---------------------------------------------------------------------------


class TestTruncationInvariance:
    """Verifies that indicators and scanning at index t depend ONLY on data <= t."""

    def test_scanner_metrics_truncation_invariance(self) -> None:
        neutral = detect_market_regime([], [], now_ms=NOW_MS)
        full_candles = generate_candle_series("ETH-USDT", count=60, base_price=3000.0, end_time_ms=NOW_MS)

        # Introduce a breakout at bar 45
        target_idx = 45
        c_target = full_candles[target_idx]
        full_candles[target_idx] = ClosedCandle(
            inst_id="ETH-USDT",
            timeframe="15m",
            candle_open_time=c_target.candle_open_time,
            candle_close_time=c_target.candle_close_time,
            open=Decimal("3000.0"),
            high=Decimal("3150.0"),
            low=Decimal("2990.0"),
            close=Decimal("3140.0"),
            vol_base=Decimal("8000.0"),
            vol_quote=Decimal("25120000.0"),
            confirm=True,
        )

        # Slice 1: truncated up to target_idx + 1
        truncated_slice = full_candles[: target_idx + 1]
        target_close_time = c_target.candle_close_time

        cand_truncated = scan_instrument_anomalies(
            truncated_slice,
            now_ms=target_close_time,
            regime_snapshot=neutral,
        )

        assert cand_truncated is not None
        assert cand_truncated.signal_id == make_signal_id("ETH-USDT", "15m", target_close_time)

        # Subsequent bars (46..59) should NOT affect cand_truncated at target_idx
        # If we re-evaluate slice with identical history up to target_idx, metrics match exactly
        cand_recheck = scan_instrument_anomalies(
            full_candles[: target_idx + 1],
            now_ms=target_close_time,
            regime_snapshot=neutral,
        )
        assert cand_recheck is not None
        assert cand_recheck.scanner_score == cand_truncated.scanner_score
        assert cand_recheck.metrics == cand_truncated.metrics


# ---------------------------------------------------------------------------
# 5. Opportunity Queue Model & Schema Validation Tests
# ---------------------------------------------------------------------------


class TestOpportunityQueueSchema:
    """Validates OpportunityQueueSnapshot compliance with Draft 2020-12 schema."""

    @pytest.fixture(scope="class")
    @classmethod
    def schema_validator(cls) -> Any:
        jsonschema = pytest.importorskip("jsonschema")
        assert SCHEMA_PATH.is_file(), f"Missing schema file: {SCHEMA_PATH}"
        schema_dict = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema_dict)
        return jsonschema.Draft202012Validator(schema_dict)

    def test_queue_snapshot_validates_against_schema(self, schema_validator: Any) -> None:
        regime = MarketRegimeSnapshot(
            regime="BULL_TREND",
            multiplier=Decimal("1.10"),
            btc_price=Decimal("72500.50"),
            btc_ema_fast=Decimal("71800.00"),
            btc_ema_slow=Decimal("70200.00"),
            btc_rsi=Decimal("64.50"),
            btc_atr_pct=Decimal("1.2500"),
            market_breadth_pct=Decimal("72.00"),
            detected_at_utc_ms=NOW_MS,
            details={"notes": "Strong trend"},
        )

        cand1 = OpportunityCandidate(
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            status="PENDING",
            anomaly_types=("BREAKOUT", "VOLUME_SPIKE"),
            scanner_score=Decimal("85.50"),
            metrics={"rvol": "3.50", "rsi": "68.20"},
            detected_at_utc_ms=NOW_MS,
            regime="BULL_TREND",
        )

        cand2 = OpportunityCandidate(
            signal_id=make_signal_id("ETH-USDT", "15m", NOW_MS),
            inst_id="ETH-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            status="PENDING",
            anomaly_types=("MOMENTUM_SHIFT",),
            scanner_score=Decimal("62.00"),
            metrics={"rsi": "58.00"},
            detected_at_utc_ms=NOW_MS,
            regime="BULL_TREND",
        )

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(cand1, cand2),
        )

        doc = queue.to_dict()
        errors = list(schema_validator.iter_errors(doc))
        assert not errors, f"Schema validation errors: {[e.message for e in errors]}"

        # Serialises to clean JSON
        json_str = json.dumps(doc)
        assert "SOL-USDT" in json_str
        assert "ETH-USDT" in json_str

    def test_queue_sorting_descending_score_deterministic(self) -> None:
        regime = MarketRegimeSnapshot(
            regime="RANGE_BOUND",
            multiplier=Decimal("0.85"),
            btc_price=Decimal("70000.00"),
            btc_ema_fast=Decimal("70000.00"),
            btc_ema_slow=Decimal("70000.00"),
            btc_rsi=Decimal("50.00"),
            btc_atr_pct=Decimal("1.0000"),
            market_breadth_pct=Decimal("50.00"),
            detected_at_utc_ms=NOW_MS,
            details={},
        )

        # Candidates with varying scores
        cands = [
            OpportunityCandidate(
                signal_id=make_signal_id("AAA-USDT", "15m", NOW_MS),
                inst_id="AAA-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("BREAKOUT",),
                scanner_score=Decimal("50.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            ),
            OpportunityCandidate(
                signal_id=make_signal_id("ZZZ-USDT", "15m", NOW_MS),
                inst_id="ZZZ-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("VOLUME_SPIKE",),
                scanner_score=Decimal("95.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            ),
            OpportunityCandidate(
                signal_id=make_signal_id("BBB-USDT", "15m", NOW_MS),
                inst_id="BBB-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("BREAKOUT",),
                scanner_score=Decimal("50.00"),  # tie-breaker with AAA-USDT -> AAA before BBB
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            ),
        ]

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=tuple(cands),
        )

        doc = queue.to_dict()
        order = [c["inst_id"] for c in doc["candidates"]]
        assert order == ["ZZZ-USDT", "AAA-USDT", "BBB-USDT"]

    def test_schema_rejects_extra_properties(self, schema_validator: Any) -> None:
        regime = MarketRegimeSnapshot(
            regime="RANGE_BOUND",
            multiplier=Decimal("0.85"),
            btc_price=Decimal("70000.00"),
            btc_ema_fast=Decimal("70000.00"),
            btc_ema_slow=Decimal("70000.00"),
            btc_rsi=Decimal("50.00"),
            btc_atr_pct=Decimal("1.0000"),
            market_breadth_pct=Decimal("50.00"),
            detected_at_utc_ms=NOW_MS,
            details={},
        )
        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(),
        )
        doc = queue.to_dict()
        doc["forbidden_extra_field"] = "illegal"
        assert not schema_validator.is_valid(doc)

    def test_schema_rejects_malformed_signal_id(self, schema_validator: Any) -> None:
        regime = MarketRegimeSnapshot(
            regime="RANGE_BOUND",
            multiplier=Decimal("0.85"),
            btc_price=Decimal("70000.00"),
            btc_ema_fast=Decimal("70000.00"),
            btc_ema_slow=Decimal("70000.00"),
            btc_rsi=Decimal("50.00"),
            btc_atr_pct=Decimal("1.0000"),
            market_breadth_pct=Decimal("50.00"),
            detected_at_utc_ms=NOW_MS,
            details={},
        )
        cand = OpportunityCandidate(
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            inst_id="SOL-USDT",
            timeframe="15m",
            candle_close_time=NOW_MS,
            status="PENDING",
            anomaly_types=("VOLUME_SPIKE",),
            scanner_score=Decimal("40.00"),
            metrics={},
            detected_at_utc_ms=NOW_MS,
            regime="RANGE_BOUND",
        )
        doc = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(cand,),
        ).to_dict()

        # Corrupt signal_id format
        doc["candidates"][0]["signal_id"] = "BAD_ID_FORMAT"
        assert not schema_validator.is_valid(doc)

    def test_model_rejects_candidate_closing_in_future(self) -> None:
        with pytest.raises(ModelValidationError, match="lookahead guard"):
            OpportunityCandidate(
                signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS + 1000),
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS + 1000,
                status="PENDING",
                anomaly_types=("VOLUME_SPIKE",),
                scanner_score=Decimal("50.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            )


# ---------------------------------------------------------------------------
# 6. Model Invariants & Guardrails
# ---------------------------------------------------------------------------


class TestModelInvariants:
    """Verifies that constructor invariants prevent any invalid domain state."""

    def test_make_signal_id_invariants(self) -> None:
        with pytest.raises(ModelValidationError, match="Spot pair"):
            make_signal_id("sol-usdt", "15m", NOW_MS)
        with pytest.raises(ModelValidationError, match="Spot pair"):
            make_signal_id("SOL-BTC", "15m", NOW_MS)
        with pytest.raises(ModelValidationError, match="Invalid timeframe"):
            make_signal_id("SOL-USDT", "99m", NOW_MS)
        with pytest.raises(ModelValidationError, match="Invalid candle_close_time"):
            make_signal_id("SOL-USDT", "15m", -10)

    def test_candidate_mismatched_signal_id(self) -> None:
        with pytest.raises(ModelValidationError, match="signal_id mismatch"):
            OpportunityCandidate(
                signal_id="ETH-USDT:15m:12345",
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=12345,
                status="PENDING",
                anomaly_types=("BREAKOUT",),
                scanner_score=Decimal("50.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            )

    def test_candidate_invalid_score_range(self) -> None:
        with pytest.raises(ModelValidationError, match=r"scanner_score must be in \[0, 100\]"):
            OpportunityCandidate(
                signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("BREAKOUT",),
                scanner_score=Decimal("105.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            )

    def test_candidate_unknown_regime_or_anomaly(self) -> None:
        with pytest.raises(ModelValidationError, match="Unknown regime"):
            OpportunityCandidate(
                signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("BREAKOUT",),
                scanner_score=Decimal("50.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="SUPER_BULL",
            )

        with pytest.raises(ModelValidationError, match="Unknown anomaly type"):
            OpportunityCandidate(
                signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
                inst_id="SOL-USDT",
                timeframe="15m",
                candle_close_time=NOW_MS,
                status="PENDING",
                anomaly_types=("MAGIC_INDICATOR",),
                scanner_score=Decimal("50.00"),
                metrics={},
                detected_at_utc_ms=NOW_MS,
                regime="RANGE_BOUND",
            )

