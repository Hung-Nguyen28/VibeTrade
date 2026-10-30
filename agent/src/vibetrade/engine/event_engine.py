"""Hybrid Event Engine for Phase P3.

Coordinates surveillance cycles, enforces strict bar-close confirmation,
manages queue lifecycle transitions (PENDING -> IN_FOCUS -> EVALUATED / EXPIRED),
and gates candidate promotion into Focus Sessions based on scanner scores and L2 orderbook liquidity.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from src.vibetrade.data.okx_models import OrderBookLiquiditySnapshot
from src.vibetrade.engine.idempotency import SignalRegistry
from src.vibetrade.scanner.models import (
    OpportunityCandidate,
    OpportunityQueueSnapshot,
)

DEFAULT_SIGNAL_TTL_MS = 60 * 60 * 1000  # 1 hour
DEFAULT_MIN_FOCUS_SCORE = Decimal("50.0")
DEFAULT_MAX_FOCUS_PER_CYCLE = 3
DEFAULT_MAX_ORDERBOOK_SPREAD_BPS = Decimal("30.0")
DEFAULT_MAX_BUY_SLIPPAGE_BPS = Decimal("15.0")


@dataclass(frozen=True)
class EngineConfig:
    """Thresholds and caps for queue lifecycle and Focus Session triggering."""

    signal_ttl_ms: int = DEFAULT_SIGNAL_TTL_MS
    min_focus_score: Decimal = DEFAULT_MIN_FOCUS_SCORE
    max_focus_per_cycle: int = DEFAULT_MAX_FOCUS_PER_CYCLE
    max_orderbook_spread_bps: Decimal = DEFAULT_MAX_ORDERBOOK_SPREAD_BPS
    max_buy_slippage_bps: Decimal = DEFAULT_MAX_BUY_SLIPPAGE_BPS
    require_orderbook_fill: bool = True

    def __post_init__(self) -> None:
        if self.signal_ttl_ms <= 0:
            raise ValueError("signal_ttl_ms must be > 0")
        if self.min_focus_score < Decimal(0) or self.min_focus_score > Decimal(100):
            raise ValueError("min_focus_score must be in [0, 100]")
        if self.max_focus_per_cycle <= 0:
            raise ValueError("max_focus_per_cycle must be > 0")


@dataclass(frozen=True)
class EngineCycleResult:
    """Output of processing one surveillance cycle through the Event Engine."""

    promoted_candidates: tuple[OpportunityCandidate, ...]
    updated_queue: OpportunityQueueSnapshot
    expired_count: int
    skipped_duplicate_count: int
    stats: dict[str, Any]


def evaluate_orderbook_liquidity_gate(
    book: OrderBookLiquiditySnapshot | None,
    config: EngineConfig,
) -> tuple[bool, str]:
    """Check whether L2 depth can absorb a $10 micro-order within slippage and spread bounds."""
    if book is None:
        return False, "MISSING_ORDERBOOK"
    if config.require_orderbook_fill and not book.buy_fully_filled:
        return False, "BUY_NOT_FULLY_FILLED"
    if book.spread_bps > config.max_orderbook_spread_bps:
        return False, f"SPREAD_TOO_WIDE ({book.spread_bps:.2f} > {config.max_orderbook_spread_bps})"
    if book.est_buy_slippage_bps is None:
        return False, "UNKNOWN_SLIPPAGE"
    if book.est_buy_slippage_bps > config.max_buy_slippage_bps:
        return False, f"SLIPPAGE_TOO_HIGH ({book.est_buy_slippage_bps:.2f} > {config.max_buy_slippage_bps})"
    return True, "PASSED_LIQUIDITY_GATE"


def process_opportunity_cycle(
    current_queue: OpportunityQueueSnapshot,
    orderbooks_by_symbol: Mapping[str, OrderBookLiquiditySnapshot],
    registry: SignalRegistry,
    now_ms: int,
    config: EngineConfig | None = None,
) -> EngineCycleResult:
    """Run one event engine cycle.

    Enforces:
    1. Bar-Close confirmation: raises if any candle closes after now_ms.
    2. Deduplication & Idempotency: ignores already processed signals.
    3. Expiration: expires signals older than signal_ttl_ms.
    4. Focus Session Promotion: filters by min_focus_score + orderbook L2 liquidity,
       promoting at most max_focus_per_cycle candidates to IN_FOCUS.
    """
    cfg = config or EngineConfig()

    if current_queue.generated_at_utc_ms > now_ms:
        raise ValueError(
            f"queue generated at {current_queue.generated_at_utc_ms} > now {now_ms} (future queue)"
        )

    skipped_duplicates = 0
    expired_count = 0
    promoted_list: list[OpportunityCandidate] = []
    final_candidates: list[OpportunityCandidate] = []

    # Sort incoming candidates deterministically by (-scanner_score, inst_id)
    sorted_candidates = sorted(current_queue.candidates, key=lambda c: (-c.scanner_score, c.inst_id))

    for cand in sorted_candidates:
        # 1. Bar-Close confirmation
        if cand.candle_close_time > now_ms:
            raise ValueError(
                f"{cand.inst_id}: candle closes at {cand.candle_close_time} > now {now_ms} (running candle)"
            )

        signal_id = cand.signal_id

        # 2. Check if already processed (IN_FOCUS, EVALUATED, or EXPIRED)
        if registry.is_processed(signal_id):
            skipped_duplicates += 1
            # Retain existing candidate in queue if it was already marked
            existing_status = registry.get_status(signal_id) or cand.status
            final_candidates.append(
                OpportunityCandidate(
                    signal_id=cand.signal_id,
                    inst_id=cand.inst_id,
                    timeframe=cand.timeframe,
                    candle_close_time=cand.candle_close_time,
                    status=existing_status,
                    anomaly_types=cand.anomaly_types,
                    scanner_score=cand.scanner_score,
                    metrics=cand.metrics,
                    detected_at_utc_ms=cand.detected_at_utc_ms,
                    regime=cand.regime,
                )
            )
            continue

        # 3. Check for TTL expiration
        age_ms = now_ms - cand.candle_close_time
        if age_ms > cfg.signal_ttl_ms:
            expired_count += 1
            registry.register(cand, status="EXPIRED", now_ms=now_ms)
            registry.update_status(signal_id, "EXPIRED", now_ms)
            final_candidates.append(
                OpportunityCandidate(
                    signal_id=cand.signal_id,
                    inst_id=cand.inst_id,
                    timeframe=cand.timeframe,
                    candle_close_time=cand.candle_close_time,
                    status="EXPIRED",
                    anomaly_types=cand.anomaly_types,
                    scanner_score=cand.scanner_score,
                    metrics=cand.metrics,
                    detected_at_utc_ms=cand.detected_at_utc_ms,
                    regime=cand.regime,
                )
            )
            continue

        # 4. Candidate is active PENDING. Check Focus Session Gate
        can_promote = len(promoted_list) < cfg.max_focus_per_cycle
        has_min_score = cand.scanner_score >= cfg.min_focus_score
        book = orderbooks_by_symbol.get(cand.inst_id)
        liquidity_passed, reason = evaluate_orderbook_liquidity_gate(book, cfg)

        if can_promote and has_min_score and liquidity_passed:
            # Promote to IN_FOCUS
            promoted_candidate = OpportunityCandidate(
                signal_id=cand.signal_id,
                inst_id=cand.inst_id,
                timeframe=cand.timeframe,
                candle_close_time=cand.candle_close_time,
                status="IN_FOCUS",
                anomaly_types=cand.anomaly_types,
                scanner_score=cand.scanner_score,
                metrics=cand.metrics,
                detected_at_utc_ms=cand.detected_at_utc_ms,
                regime=cand.regime,
            )
            registry.register(cand, status="IN_FOCUS", now_ms=now_ms)
            registry.update_status(signal_id, "IN_FOCUS", now_ms)
            promoted_list.append(promoted_candidate)
            final_candidates.append(promoted_candidate)
        else:
            # Stays PENDING
            registry.register(cand, status="PENDING", now_ms=now_ms)
            final_candidates.append(cand)

    # Reconstruct updated OpportunityQueueSnapshot
    updated_queue = OpportunityQueueSnapshot(
        schema_version="1.1",
        generated_at_utc_ms=now_ms,
        market_regime=current_queue.market_regime,
        candidates=tuple(final_candidates),
    )

    stats = {
        "incoming_candidates": len(current_queue.candidates),
        "promoted_count": len(promoted_list),
        "expired_count": expired_count,
        "skipped_duplicate_count": skipped_duplicates,
        "pending_count": len([c for c in final_candidates if c.status == "PENDING"]),
    }

    return EngineCycleResult(
        promoted_candidates=tuple(promoted_list),
        updated_queue=updated_queue,
        expired_count=expired_count,
        skipped_duplicate_count=skipped_duplicates,
        stats=stats,
    )
