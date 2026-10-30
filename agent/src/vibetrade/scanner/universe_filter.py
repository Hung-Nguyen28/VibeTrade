"""Tradable Universe Filter for VibeTrade v1.1.

Filters live OKX *-USDT Spot instruments against micro-portfolio ($10.0) constraints:
1. Instruments must be live and quote currency must be USDT.
2. Stablecoin and pegged base currencies are excluded.
3. 24h quote volume must meet or exceed min_vol_quote_24h.
4. Bid-ask spread must not exceed max_spread_bps.
5. Minimum order notional (min_size * ask_px) must not exceed max_notional_per_trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from src.vibetrade.data.okx_models import (
    QUOTE_CCY,
    SpotInstrumentRule,
    SpotTicker24h,
    parse_decimal,
)
from src.vibetrade.data.okx_public_client import STABLECOIN_BASES, is_stablecoin_pair

DEFAULT_MIN_VOL_QUOTE_24H = Decimal("50000.0")
DEFAULT_MAX_SPREAD_BPS = Decimal("35.0")
DEFAULT_MAX_NOTIONAL_PER_TRADE = Decimal("10.0")


@dataclass(frozen=True)
class UniverseFilterConfig:
    """Configurable thresholds for tradable universe filtering."""

    min_vol_quote_24h: Decimal = DEFAULT_MIN_VOL_QUOTE_24H
    max_spread_bps: Decimal = DEFAULT_MAX_SPREAD_BPS
    max_notional_per_trade: Decimal = DEFAULT_MAX_NOTIONAL_PER_TRADE
    exclude_stablecoins: bool = True
    require_live: bool = True

    def __post_init__(self) -> None:
        if self.min_vol_quote_24h < Decimal(0):
            raise ValueError("min_vol_quote_24h must be >= 0")
        if self.max_spread_bps <= Decimal(0):
            raise ValueError("max_spread_bps must be > 0")
        if self.max_notional_per_trade <= Decimal(0):
            raise ValueError("max_notional_per_trade must be > 0")


@dataclass(frozen=True)
class TradableInstrument:
    """An instrument that has passed all liquidity and constraint checks."""

    inst_id: str
    rule: SpotInstrumentRule
    ticker: SpotTicker24h
    min_notional_usdt: Decimal
    spread_bps: Decimal
    vol_quote_24h: Decimal


@dataclass(frozen=True)
class RejectedInstrument:
    """Details of why an instrument was rejected by the universe filter."""

    inst_id: str
    reason: str
    details: str


@dataclass(frozen=True)
class UniverseFilterResult:
    """Full deterministic result of running the universe filter."""

    passed: tuple[TradableInstrument, ...]
    rejected: tuple[RejectedInstrument, ...]

    @property
    def passed_inst_ids(self) -> tuple[str, ...]:
        return tuple(inst.inst_id for inst in self.passed)

    @property
    def passed_rules(self) -> tuple[SpotInstrumentRule, ...]:
        return tuple(inst.rule for inst in self.passed)


def filter_tradable_universe(
    rules: Sequence[SpotInstrumentRule],
    tickers: Sequence[SpotTicker24h],
    config: UniverseFilterConfig | None = None,
) -> UniverseFilterResult:
    """Filter candidate Spot pairs deterministically against liquidity and $10 capital bounds.

    Returns a ``UniverseFilterResult`` containing sorted passed instruments and
    rejected instruments with full explanation.
    """
    cfg = config or UniverseFilterConfig()
    ticker_map: dict[str, SpotTicker24h] = {t.inst_id: t for t in tickers}

    passed: list[TradableInstrument] = []
    rejected: list[RejectedInstrument] = []

    # Sort rules deterministically by inst_id
    sorted_rules = sorted(rules, key=lambda r: r.inst_id)

    for rule in sorted_rules:
        inst_id = rule.inst_id

        # 1. State check
        if cfg.require_live and rule.state != "live":
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="NOT_LIVE",
                    details=f"State is {rule.state!r}, expected 'live'",
                )
            )
            continue

        # 2. Stablecoin check
        if cfg.exclude_stablecoins and is_stablecoin_pair(rule):
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="STABLECOIN_PAIR",
                    details=f"Base currency {rule.base_ccy} is a stablecoin/pegged asset",
                )
            )
            continue

        # 3. Ticker presence
        ticker = ticker_map.get(inst_id)
        if ticker is None:
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="MISSING_TICKER",
                    details="No 24h ticker data found for instrument",
                )
            )
            continue

        # 4. 24h quote volume liquidity
        if ticker.vol_quote_24h < cfg.min_vol_quote_24h:
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="LOW_LIQUIDITY_24H",
                    details=f"24h quote volume {ticker.vol_quote_24h} USDT < min {cfg.min_vol_quote_24h} USDT",
                )
            )
            continue

        # 5. Spread check
        if ticker.spread_bps > cfg.max_spread_bps:
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="SPREAD_TOO_WIDE",
                    details=f"Spread {ticker.spread_bps:.2f} bps > max {cfg.max_spread_bps} bps",
                )
            )
            continue

        # 6. Minimum order size vs micro-portfolio capital ($10)
        # Minimum notional required to place an order = min_size * ask_px
        min_notional = rule.min_size * ticker.ask_px
        if min_notional > cfg.max_notional_per_trade:
            rejected.append(
                RejectedInstrument(
                    inst_id=inst_id,
                    reason="MIN_ORDER_EXCEEDS_BUDGET",
                    details=(
                        f"Min order notional {min_notional:.4f} USDT (min_size={rule.min_size} * "
                        f"ask={ticker.ask_px}) exceeds max capital per trade {cfg.max_notional_per_trade} USDT"
                    ),
                )
            )
            continue

        # Passed all gates
        passed.append(
            TradableInstrument(
                inst_id=inst_id,
                rule=rule,
                ticker=ticker,
                min_notional_usdt=min_notional,
                spread_bps=ticker.spread_bps,
                vol_quote_24h=ticker.vol_quote_24h,
            )
        )

    return UniverseFilterResult(
        passed=tuple(sorted(passed, key=lambda p: p.inst_id)),
        rejected=tuple(sorted(rejected, key=lambda r: r.inst_id)),
    )
