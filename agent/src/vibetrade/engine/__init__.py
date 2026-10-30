"""P3 — Hybrid Event Engine (Bar-Close Confirmation & Focus Session Trigger)."""

from src.vibetrade.engine.event_engine import (
    EngineConfig,
    EngineCycleResult,
    evaluate_orderbook_liquidity_gate,
    process_opportunity_cycle,
)
from src.vibetrade.engine.idempotency import (
    SignalEntry,
    SignalRegistry,
)

__all__ = [
    "EngineConfig",
    "EngineCycleResult",
    "SignalEntry",
    "SignalRegistry",
    "evaluate_orderbook_liquidity_gate",
    "process_opportunity_cycle",
]
