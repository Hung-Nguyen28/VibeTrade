"""Immutable Risk Controller for Phase P6.

Inviolable risk gate protecting micro-portfolio ($10.0):
1. RiskConfig is frozen in memory, sealed with SHA-256 hash. Zero mutation methods.
2. AI / Research modules have read-only visibility, zero write access.
3. Strict checks on verification receipt, position concentration, total positions,
   drawdown circuit breaker, and liquidity limits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.vibetrade.data.okx_models import OrderBookLiquiditySnapshot, dec_str
from src.vibetrade.research.models import ResearchReport
from src.vibetrade.verification.models import VerificationReceipt

DEFAULT_MAX_POSITION_NOTIONAL = Decimal("3.00")  # $3.00 max on $10 portfolio
DEFAULT_MAX_OPEN_POSITIONS = 3
DEFAULT_MAX_PORTFOLIO_DRAWDOWN_PCT = Decimal("15.00")
DEFAULT_MAX_ALLOWED_SPREAD_BPS = Decimal("25.00")
DEFAULT_MAX_ALLOWED_SLIPPAGE_BPS = Decimal("12.00")


@dataclass(frozen=True)
class RiskConfig:
    """Immutable, frozen risk configuration."""

    max_position_notional_usdt: Decimal = DEFAULT_MAX_POSITION_NOTIONAL
    max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS
    max_portfolio_drawdown_pct: Decimal = DEFAULT_MAX_PORTFOLIO_DRAWDOWN_PCT
    max_allowed_spread_bps: Decimal = DEFAULT_MAX_ALLOWED_SPREAD_BPS
    max_allowed_slippage_bps: Decimal = DEFAULT_MAX_ALLOWED_SLIPPAGE_BPS
    require_verification_pass: bool = True

    def __post_init__(self) -> None:
        if self.max_position_notional_usdt <= Decimal(0):
            raise ValueError("max_position_notional_usdt must be > 0")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be > 0")
        if self.max_portfolio_drawdown_pct <= Decimal(0):
            raise ValueError("max_portfolio_drawdown_pct must be > 0")
        if self.max_allowed_spread_bps <= Decimal(0):
            raise ValueError("max_allowed_spread_bps must be > 0")
        if self.max_allowed_slippage_bps <= Decimal(0):
            raise ValueError("max_allowed_slippage_bps must be > 0")

    @property
    def config_sha256(self) -> str:
        payload = (
            f"{self.max_position_notional_usdt}:"
            f"{self.max_open_positions}:"
            f"{self.max_portfolio_drawdown_pct}:"
            f"{self.max_allowed_spread_bps}:"
            f"{self.max_allowed_slippage_bps}:"
            f"{self.require_verification_pass}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RiskDecision:
    """Decision emitted by the Risk Controller for an entry proposal."""

    approved: bool
    constraint_code: str | None
    details: str
    config_hash: str


class ImmutableRiskController:
    """Inviolable Risk Controller protecting $10 capital."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()

    @property
    def config(self) -> RiskConfig:
        return self._config

    def evaluate_entry(
        self,
        report: ResearchReport,
        receipt: VerificationReceipt,
        proposed_notional: Decimal,
        current_open_positions_count: int,
        current_drawdown_pct: Decimal,
        orderbook: OrderBookLiquiditySnapshot,
    ) -> RiskDecision:
        cfg = self._config
        cfg_hash = cfg.config_sha256

        # 1. Independent Verification Gate check
        if cfg.require_verification_pass:
            if not receipt.can_proceed_to_risk:
                return RiskDecision(
                    approved=False,
                    constraint_code="VERIFICATION_NOT_PASSED",
                    details=f"Receipt status is {receipt.status} with violations: {receipt.violations}",
                    config_hash=cfg_hash,
                )
            if report.verdict != "ACTIONABLE_LONG":
                return RiskDecision(
                    approved=False,
                    constraint_code="VERDICT_NOT_ACTIONABLE",
                    details=f"Report verdict is {report.verdict}, expected ACTIONABLE_LONG",
                    config_hash=cfg_hash,
                )

        # 2. Portfolio Drawdown Circuit Breaker
        if current_drawdown_pct >= cfg.max_portfolio_drawdown_pct:
            return RiskDecision(
                approved=False,
                constraint_code="PORTFOLIO_DRAWDOWN_CIRCUIT_BREAKER",
                details=f"Drawdown {current_drawdown_pct:.2f}% >= max {cfg.max_portfolio_drawdown_pct:.2f}%",
                config_hash=cfg_hash,
            )

        # 3. Maximum Open Positions Cap
        if current_open_positions_count >= cfg.max_open_positions:
            return RiskDecision(
                approved=False,
                constraint_code="MAX_OPEN_POSITIONS_REACHED",
                details=f"Open positions ({current_open_positions_count}) reached cap ({cfg.max_open_positions})",
                config_hash=cfg_hash,
            )

        # 4. Single Position Notional Cap
        if proposed_notional > cfg.max_position_notional_usdt:
            return RiskDecision(
                approved=False,
                constraint_code="POSITION_NOTIONAL_CAP_EXCEEDED",
                details=f"Proposed notional {proposed_notional:.2f} > max {cfg.max_position_notional_usdt:.2f}",
                config_hash=cfg_hash,
            )

        # 5. Spread Check
        if orderbook.spread_bps > cfg.max_allowed_spread_bps:
            return RiskDecision(
                approved=False,
                constraint_code="SPREAD_EXCEEDS_RISK_LIMIT",
                details=f"Spread {orderbook.spread_bps:.2f} bps > max {cfg.max_allowed_spread_bps:.2f} bps",
                config_hash=cfg_hash,
            )

        # 6. Slippage Check
        if orderbook.est_buy_slippage_bps is not None and orderbook.est_buy_slippage_bps > cfg.max_allowed_slippage_bps:
            return RiskDecision(
                approved=False,
                constraint_code="SLIPPAGE_EXCEEDS_RISK_LIMIT",
                details=f"Buy slippage {orderbook.est_buy_slippage_bps:.2f} bps > max {cfg.max_allowed_slippage_bps:.2f} bps",
                config_hash=cfg_hash,
            )

        return RiskDecision(
            approved=True,
            constraint_code=None,
            details="All risk gates passed successfully.",
            config_hash=cfg_hash,
        )
