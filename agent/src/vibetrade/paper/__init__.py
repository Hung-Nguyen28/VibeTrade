"""P6 — Paper Trading Micro-Portfolio ($10.0) & Execution Engine (VibeTrade v1.1)."""

from src.vibetrade.paper.atomic_io import (
    AtomicStatePersistenceError,
    atomic_write_json,
    save_portfolio_snapshot,
    validate_portfolio_dict,
)
from src.vibetrade.paper.execution import (
    ExecutionMode,
    ExecutionResult,
    PaperTradingConfig,
    round_down_lot,
    round_tick,
    simulate_order_execution,
)
from src.vibetrade.paper.models import (
    ClosedTradeRecord,
    OpenPosition,
    PaperPortfolioSnapshot,
    RejectedOrderRecord,
)
from src.vibetrade.paper.portfolio import PaperPortfolio

__all__ = [
    "AtomicStatePersistenceError",
    "ClosedTradeRecord",
    "ExecutionMode",
    "ExecutionResult",
    "OpenPosition",
    "PaperPortfolio",
    "PaperPortfolioSnapshot",
    "PaperTradingConfig",
    "RejectedOrderRecord",
    "atomic_write_json",
    "round_down_lot",
    "round_tick",
    "save_portfolio_snapshot",
    "simulate_order_execution",
    "validate_portfolio_dict",
]
