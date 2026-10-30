"""Test Gate P3 — Hybrid Event Engine (VibeTrade v1.1).

Validates:
1. Idempotency & Signal Registry (preventing duplicate processing of signals).
2. FIFO / TTL pruning of registry.
3. Strict Bar-Close Confirmation gate in Event Engine.
4. Queue Lifecycle transitions: PENDING -> IN_FOCUS -> EVALUATED / EXPIRED.
5. Focus Session Gate (score threshold, L2 orderbook liquidity, max promotions per cycle).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.vibetrade.data.okx_models import OrderBookLiquiditySnapshot
from src.vibetrade.engine import (
    EngineConfig,
    EngineCycleResult,
    SignalRegistry,
    evaluate_orderbook_liquidity_gate,
    process_opportunity_cycle,
)
from src.vibetrade.scanner.models import (
    MarketRegimeSnapshot,
    OpportunityCandidate,
    OpportunityQueueSnapshot,
    make_signal_id,
)

NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
TF_15M = 15 * 60 * 1000
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "v1.1" / "opportunity_queue.schema.json"


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------


def make_test_regime() -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        regime="BULL_TREND",
        multiplier=Decimal("1.10"),
        btc_price=Decimal("70000.00"),
        btc_ema_fast=Decimal("69000.00"),
        btc_ema_slow=Decimal("68000.00"),
        btc_rsi=Decimal("60.00"),
        btc_atr_pct=Decimal("1.5000"),
        market_breadth_pct=Decimal("65.00"),
        detected_at_utc_ms=NOW_MS,
        details={},
    )


def make_test_candidate(
    inst_id: str = "SOL-USDT",
    timeframe: str = "15m",
    candle_close_time: int = NOW_MS,
    score: str = "75.00",
    status: str = "PENDING",
    detected_at_utc_ms: int | None = None,
) -> OpportunityCandidate:
    sig_id = make_signal_id(inst_id, timeframe, candle_close_time)
    det_ms = detected_at_utc_ms or max(candle_close_time, NOW_MS)
    return OpportunityCandidate(
        signal_id=sig_id,
        inst_id=inst_id,
        timeframe=timeframe,
        candle_close_time=candle_close_time,
        status=status,
        anomaly_types=("BREAKOUT", "VOLUME_SPIKE"),
        scanner_score=Decimal(score),
        metrics={"rvol": "2.5"},
        detected_at_utc_ms=det_ms,
        regime="BULL_TREND",
    )


def make_test_orderbook(
    inst_id: str = "SOL-USDT",
    spread_bps: str = "10.0",
    buy_slippage_bps: str = "5.0",
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
        imbalance_ratio=Decimal("0.20"),
        probe_notional_usdt=Decimal("10.00"),
        est_buy_slippage_bps=Decimal(buy_slippage_bps),
        est_sell_slippage_bps=Decimal("5.0"),
        buy_fully_filled=buy_fully_filled,
        sell_fully_filled=True,
    )


# ---------------------------------------------------------------------------
# 1. Idempotency Registry Tests
# ---------------------------------------------------------------------------


class TestSignalRegistry:
    """Verifies state tracking and pruning within SignalRegistry."""

    def test_registration_and_processed_check(self) -> None:
        registry = SignalRegistry()
        cand = make_test_candidate("SOL-USDT")

        # Initially unregistered
        assert not registry.has_signal(cand.signal_id)
        assert not registry.is_processed(cand.signal_id)

        # Register as PENDING
        entry = registry.register(cand, status="PENDING", now_ms=NOW_MS)
        assert registry.has_signal(cand.signal_id)
        assert registry.get_status(cand.signal_id) == "PENDING"
        # PENDING is not considered 'processed'
        assert not registry.is_processed(cand.signal_id)

        # Update to IN_FOCUS -> becomes processed
        registry.update_status(cand.signal_id, "IN_FOCUS", now_ms=NOW_MS)
        assert registry.is_processed(cand.signal_id)
        assert registry.get_status(cand.signal_id) == "IN_FOCUS"

    def test_ttl_and_fifo_pruning(self) -> None:
        registry = SignalRegistry()
        t0 = NOW_MS - 100_000
        # Register 5 signals at t0
        for i in range(5):
            c = make_test_candidate(f"COIN{i}-USDT", candle_close_time=t0)
            registry.register(c, status="EVALUATED", now_ms=t0)

        # Register 1 fresh signal at NOW_MS
        fresh = make_test_candidate("FRESH-USDT", candle_close_time=NOW_MS)
        registry.register(fresh, status="PENDING", now_ms=NOW_MS)

        # Prune with TTL=50_000 ms relative to NOW_MS
        pruned_count = registry.prune(now_ms=NOW_MS, max_entries=10, ttl_ms=50_000)
        assert pruned_count == 5
        assert len(registry) == 1
        assert registry.has_signal(fresh.signal_id)

    def test_capacity_fifo_pruning(self) -> None:
        registry = SignalRegistry()
        for i in range(10):
            c = make_test_candidate(f"COIN{i}-USDT", candle_close_time=NOW_MS)
            registry.register(c, status="PENDING", now_ms=NOW_MS + i * 1000)

        # Cap at 4 entries
        pruned = registry.prune(now_ms=NOW_MS + 20_000, max_entries=4, ttl_ms=10_000_000)
        assert pruned == 6
        assert len(registry) == 4


# ---------------------------------------------------------------------------
# 2. Event Engine Bar-Close Gate Tests
# ---------------------------------------------------------------------------


class TestEventEngineBarCloseGate:
    """Verifies that running or future-dated candles are strictly rejected."""

    def test_running_candle_rejected_by_engine(self) -> None:
        registry = SignalRegistry()
        regime = make_test_regime()
        future_close = NOW_MS + 10_000
        cand_future = make_test_candidate("BTC-USDT", candle_close_time=future_close)

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=future_close,
            market_regime=regime,
            candidates=(cand_future,),
        )

        with pytest.raises(ValueError, match="future queue"):
            process_opportunity_cycle(
                current_queue=queue,
                orderbooks_by_symbol={},
                registry=registry,
                now_ms=NOW_MS,
            )


# ---------------------------------------------------------------------------
# 3. Lifecycle Transitions & Focus Session Trigger Tests
# ---------------------------------------------------------------------------


class TestEventEnginePromotionAndLifecycle:
    """Verifies promotion logic, idempotency deduplication, and signal expiration."""

    def test_signal_ttl_expiration(self) -> None:
        registry = SignalRegistry()
        regime = make_test_regime()
        # Candidate closed 2 hours ago (> default TTL of 1 hour)
        old_time = NOW_MS - (2 * 60 * 60 * 1000)
        cand_old = make_test_candidate("SOL-USDT", candle_close_time=old_time)

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(cand_old,),
        )

        result = process_opportunity_cycle(
            current_queue=queue,
            orderbooks_by_symbol={},
            registry=registry,
            now_ms=NOW_MS,
        )

        assert result.expired_count == 1
        assert len(result.promoted_candidates) == 0
        assert result.updated_queue.candidates[0].status == "EXPIRED"
        assert registry.get_status(cand_old.signal_id) == "EXPIRED"

    def test_idempotency_prevents_duplicate_focus_session(self) -> None:
        registry = SignalRegistry()
        regime = make_test_regime()
        cand = make_test_candidate("SOL-USDT", score="80.00")
        book = make_test_orderbook("SOL-USDT")

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(cand,),
        )

        # Cycle 1: Candidate is promoted to IN_FOCUS
        res1 = process_opportunity_cycle(
            current_queue=queue,
            orderbooks_by_symbol={"SOL-USDT": book},
            registry=registry,
            now_ms=NOW_MS,
        )
        assert len(res1.promoted_candidates) == 1
        assert res1.promoted_candidates[0].status == "IN_FOCUS"
        assert res1.skipped_duplicate_count == 0

        # Cycle 2: Same candidate presented again in surveillance queue
        res2 = process_opportunity_cycle(
            current_queue=queue,
            orderbooks_by_symbol={"SOL-USDT": book},
            registry=registry,
            now_ms=NOW_MS,
        )
        # MUST be deduplicated! 0 new promotions
        assert len(res2.promoted_candidates) == 0
        assert res2.skipped_duplicate_count == 1

    def test_focus_session_gate_checks(self) -> None:
        registry = SignalRegistry()
        regime = make_test_regime()

        # Cand 1: Low score (40.0 < min_focus_score=50.0) -> Should NOT promote
        c_low = make_test_candidate("LOW-USDT", score="40.00")
        book_low = make_test_orderbook("LOW-USDT")

        # Cand 2: High score, but missing orderbook -> Should NOT promote
        c_nobook = make_test_candidate("NOBOOK-USDT", score="70.00")

        # Cand 3: High score, but wide spread (40 bps > max=30 bps) -> Should NOT promote
        c_widespread = make_test_candidate("WIDE-USDT", score="75.00")
        book_wide = make_test_orderbook("WIDE-USDT", spread_bps="40.0")

        # Cand 4: High score, good orderbook -> Should PROMOTE
        c_good = make_test_candidate("GOOD-USDT", score="85.00")
        book_good = make_test_orderbook("GOOD-USDT", spread_bps="10.0", buy_slippage_bps="4.0")

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=(c_low, c_nobook, c_widespread, c_good),
        )

        books = {
            "LOW-USDT": book_low,
            "WIDE-USDT": book_wide,
            "GOOD-USDT": book_good,
        }

        result = process_opportunity_cycle(
            current_queue=queue,
            orderbooks_by_symbol=books,
            registry=registry,
            now_ms=NOW_MS,
        )

        assert len(result.promoted_candidates) == 1
        assert result.promoted_candidates[0].inst_id == "GOOD-USDT"
        assert result.promoted_candidates[0].status == "IN_FOCUS"

    def test_max_focus_per_cycle_capping(self) -> None:
        registry = SignalRegistry()
        regime = make_test_regime()

        # 5 candidates with high scores
        cands = [
            make_test_candidate(f"COIN{i}-USDT", score=f"{80 + i}.00")
            for i in range(5)
        ]
        books = {f"COIN{i}-USDT": make_test_orderbook(f"COIN{i}-USDT") for i in range(5)}

        queue = OpportunityQueueSnapshot(
            schema_version="1.1",
            generated_at_utc_ms=NOW_MS,
            market_regime=regime,
            candidates=tuple(cands),
        )

        cfg = EngineConfig(max_focus_per_cycle=2)
        result = process_opportunity_cycle(
            current_queue=queue,
            orderbooks_by_symbol=books,
            registry=registry,
            now_ms=NOW_MS,
            config=cfg,
        )

        # Promoted top 2 only
        assert len(result.promoted_candidates) == 2
        promoted_ids = [c.inst_id for c in result.promoted_candidates]
        assert promoted_ids == ["COIN4-USDT", "COIN3-USDT"]  # highest scores 84, 83
