"""Test Gate P6 — Immutable Risk Controller & Paper Trading $10 (VibeTrade v1.1).

Validates:
1. Immutability Gate: RiskConfig cannot be mutated at runtime (FrozenInstanceError).
2. Risk Controller Sovereignty: requires VERIFIED_PASS, enforces position concentration,
   max positions, drawdown circuit breaker, and spread/slippage limits.
3. Micro-Portfolio ($10.0) Precision & Costs: high-precision Decimal fee calculations
   (0.1% on $2.00 is exactly $0.00200000), strict realized vs unrealized PnL separation.
4. 3-Timestamp Execution & Schedule Drift Cost: LIVE_PAPER drift calculation and BACKTEST mode.
5. REJECTED_BY_CONSTRAINT transparent logging for below min_size and insufficient cash.
6. Atomic Write Protocol: 5-step write, schema validation, rollback on error, no orphan .tmp.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.vibetrade.data.okx_models import (
    ClosedCandle,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
)
from src.vibetrade.paper import (
    AtomicStatePersistenceError,
    ClosedTradeRecord,
    ExecutionMode,
    OpenPosition,
    PaperPortfolio,
    PaperPortfolioSnapshot,
    PaperTradingConfig,
    RejectedOrderRecord,
    atomic_write_json,
    round_down_lot,
    round_tick,
    save_portfolio_snapshot,
    simulate_order_execution,
)
from src.vibetrade.research import ResearchReport
from src.vibetrade.risk import (
    ImmutableRiskController,
    RiskConfig,
    RiskDecision,
)
from src.vibetrade.scanner.models import make_signal_id
from src.vibetrade.verification import VerificationReceipt

NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
TF_15M = 15 * 60 * 1000
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "v1.1" / "paper_portfolio.schema.json"


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def make_test_rule(
    inst_id: str = "SOL-USDT",
    min_size: str = "0.01",
    lot_size: str = "0.01",
    tick_size: str = "0.01",
) -> SpotInstrumentRule:
    return SpotInstrumentRule(
        inst_id=inst_id,
        base_ccy="SOL",
        quote_ccy="USDT",
        tick_size=Decimal(tick_size),
        lot_size=Decimal(lot_size),
        min_size=Decimal(min_size),
        state="live",
    )


def make_test_orderbook(
    inst_id: str = "SOL-USDT",
    best_ask: str = "150.00",
    spread_bps: str = "10.0",
    buy_slippage_bps: str = "3.0",
    buy_fully_filled: bool = True,
) -> OrderBookLiquiditySnapshot:
    ask = Decimal(best_ask)
    bid = ask - Decimal("0.10")
    return OrderBookLiquiditySnapshot(
        inst_id=inst_id,
        ts_utc_ms=NOW_MS,
        best_bid=bid,
        best_ask=ask,
        mid_price=(bid + ask) / 2,
        spread_bps=Decimal(spread_bps),
        depth_levels=20,
        bid_depth_usdt=Decimal("50000.00"),
        ask_depth_usdt=Decimal("50000.00"),
        imbalance_ratio=Decimal("0.20"),
        probe_notional_usdt=Decimal("10.00"),
        est_buy_slippage_bps=Decimal(buy_slippage_bps),
        est_sell_slippage_bps=Decimal("3.0"),
        buy_fully_filled=buy_fully_filled,
        sell_fully_filled=True,
    )


def make_test_receipt(status: str = "VERIFIED_PASS") -> VerificationReceipt:
    sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
    return VerificationReceipt(
        receipt_id=f"ver:{sig_id}",
        signal_id=sig_id,
        report_id=f"rep:{sig_id}",
        report_sha256="a" * 64,
        status=status,
        violations=() if status == "VERIFIED_PASS" else ("TEST_VIOLATION",),
        auditor_passed=(status == "VERIFIED_PASS"),
        reviewer_passed=(status == "VERIFIED_PASS"),
        schema_passed=(status == "VERIFIED_PASS"),
        verified_at_utc_ms=NOW_MS,
    )


def make_test_report(verdict: str = "ACTIONABLE_LONG") -> ResearchReport:
    sig_id = make_signal_id("SOL-USDT", "15m", NOW_MS)
    return ResearchReport(
        report_id=f"rep:{sig_id}",
        signal_id=sig_id,
        inst_id="SOL-USDT",
        timeframe="15m",
        candle_close_time=NOW_MS,
        verdict=verdict,
        score_bull=Decimal("60.00"),
        score_bear=Decimal("10.00"),
        score_raw=Decimal("50.00"),
        score_net=Decimal("55.00"),
        regime="BULL_TREND",
        regime_multiplier=Decimal("1.10"),
        evidence=(),
        template_summary="Actionable",
        evaluated_at_utc_ms=NOW_MS,
        missing_inputs=(),
    )


# ---------------------------------------------------------------------------
# 1. Immutability Gate & AST Verification Tests
# ---------------------------------------------------------------------------


class TestRiskImmutabilityGate:
    """Verifies that RiskConfig is physically immutable at runtime and unpolluted by AI."""

    def test_risk_config_is_frozen_in_memory(self) -> None:
        cfg = RiskConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.max_position_notional_usdt = Decimal("100.00")  # type: ignore[misc]

    def test_ast_research_does_not_mutate_risk_config(self) -> None:
        """Scan python files in src/vibetrade/research/ to ensure no risk config mutations."""
        research_dir = Path(__file__).resolve().parents[2] / "src" / "vibetrade" / "research"
        for py_file in research_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # Ensure no assignment to RiskConfig
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and "RiskConfig" in target.id:
                            pytest.fail(f"Illegal RiskConfig assignment in {py_file.name}:{node.lineno}")


# ---------------------------------------------------------------------------
# 2. Risk Controller Sovereignty Tests
# ---------------------------------------------------------------------------


class TestRiskControllerSovereignty:
    """Verifies that ImmutableRiskController enforces hard capital protection gates."""

    def test_approved_when_all_gates_pass(self) -> None:
        controller = ImmutableRiskController()
        report = make_test_report("ACTIONABLE_LONG")
        receipt = make_test_receipt("VERIFIED_PASS")
        book = make_test_orderbook("SOL-USDT")

        decision = controller.evaluate_entry(
            report=report,
            receipt=receipt,
            proposed_notional=Decimal("2.50"),  # <= max $3.00
            current_open_positions_count=1,      # < max 3
            current_drawdown_pct=Decimal("5.0"), # < max 15%
            orderbook=book,
        )
        assert decision.approved is True
        assert decision.constraint_code is None

    def test_rejected_when_verification_failed(self) -> None:
        controller = ImmutableRiskController()
        report = make_test_report("ACTIONABLE_LONG")
        receipt = make_test_receipt("VERIFIED_FAIL")
        book = make_test_orderbook("SOL-USDT")

        decision = controller.evaluate_entry(
            report=report,
            receipt=receipt,
            proposed_notional=Decimal("2.50"),
            current_open_positions_count=1,
            current_drawdown_pct=Decimal("0.0"),
            orderbook=book,
        )
        assert decision.approved is False
        assert decision.constraint_code == "VERIFICATION_NOT_PASSED"

    def test_rejected_when_drawdown_circuit_breaker_triggered(self) -> None:
        controller = ImmutableRiskController()
        report = make_test_report("ACTIONABLE_LONG")
        receipt = make_test_receipt("VERIFIED_PASS")
        book = make_test_orderbook("SOL-USDT")

        decision = controller.evaluate_entry(
            report=report,
            receipt=receipt,
            proposed_notional=Decimal("2.50"),
            current_open_positions_count=1,
            current_drawdown_pct=Decimal("16.50"),  # > max 15.00%
            orderbook=book,
        )
        assert decision.approved is False
        assert decision.constraint_code == "PORTFOLIO_DRAWDOWN_CIRCUIT_BREAKER"

    def test_rejected_when_notional_exceeds_cap(self) -> None:
        controller = ImmutableRiskController()
        report = make_test_report("ACTIONABLE_LONG")
        receipt = make_test_receipt("VERIFIED_PASS")
        book = make_test_orderbook("SOL-USDT")

        decision = controller.evaluate_entry(
            report=report,
            receipt=receipt,
            proposed_notional=Decimal("4.50"),  # > max $3.00
            current_open_positions_count=1,
            current_drawdown_pct=Decimal("0.0"),
            orderbook=book,
        )
        assert decision.approved is False
        assert decision.constraint_code == "POSITION_NOTIONAL_CAP_EXCEEDED"


# ---------------------------------------------------------------------------
# 3. Micro-Portfolio ($10.0) Precision & Costs Tests
# ---------------------------------------------------------------------------


class TestMicroPortfolioAccounting:
    """Verifies that high-precision crypto accounting never loses decimals or confuses realized/unrealized PnL."""

    def test_fee_precision_on_two_dollar_order(self) -> None:
        # $2.00 order with 0.1% fee rate = exactly $0.00200000
        rule = make_test_rule("SOL-USDT", min_size="0.01", lot_size="0.01")
        book = make_test_orderbook("SOL-USDT", best_ask="100.00", buy_slippage_bps="0.0")

        result = simulate_order_execution(
            inst_rule=rule,
            orderbook=book,
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            proposed_notional_usdt=Decimal("2.00"),
            candle_close_time=NOW_MS,
            signal_timestamp=NOW_MS,
            execution_timestamp=NOW_MS,
            available_cash_usdt=Decimal("10.00"),
            price_at_candle_close=Decimal("100.00"),
            config=PaperTradingConfig(fee_rate=Decimal("0.001")),
        )
        assert result.success is True
        assert result.position is not None
        # Notional is 0.02 * 100 = 2.00, fee is exactly 0.00200000
        assert result.position.entry_fee_usdt == Decimal("0.00200000")
        assert result.cash_delta_usdt == Decimal("-2.00200000")

    def test_portfolio_realized_and_unrealized_pnl_separation(self) -> None:
        portfolio = PaperPortfolio(initial_balance_usdt=Decimal("10.00"))
        rule = make_test_rule("SOL-USDT", min_size="0.01", lot_size="0.01")
        book = make_test_orderbook("SOL-USDT", best_ask="100.00", buy_slippage_bps="0.0")

        # Open $2.00 position
        exec_res = simulate_order_execution(
            inst_rule=rule,
            orderbook=book,
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            proposed_notional_usdt=Decimal("2.00"),
            candle_close_time=NOW_MS,
            signal_timestamp=NOW_MS,
            execution_timestamp=NOW_MS,
            available_cash_usdt=portfolio.cash_balance_usdt,
            price_at_candle_close=Decimal("100.00"),
        )
        portfolio.open_position(exec_res)

        # Mark-to-market up to $110.00 (+10%)
        portfolio.update_mark_prices({"SOL-USDT": Decimal("110.00")})
        # qty is 0.02, unrealized = (110 - 100) * 0.02 = +0.20
        assert portfolio.total_unrealized_pnl_usdt == Decimal("0.20000000")
        # Realized PnL remains exactly 0.00! Cash has not changed.
        assert portfolio.cumulative_realized_pnl_usdt == Decimal("0.00")
        assert portfolio.cash_balance_usdt == Decimal("7.99800000")
        # Total equity invariant: 7.998 + (0.02 * 110 = 2.20) = 10.198
        assert portfolio.total_equity_usdt == Decimal("10.19800000")

        # Close position at $110.00
        trade = portfolio.close_position(
            inst_id="SOL-USDT",
            exit_price=Decimal("110.00"),
            exit_timestamp=NOW_MS + 60_000,
            exit_reason="TAKE_PROFIT",
            fee_rate=Decimal("0.001"),
        )
        # Exit fee = 2.20 * 0.001 = 0.00220000
        # Net realized PnL = gross (0.20) - entry_fee (0.002) - exit_fee (0.0022) = 0.19580000
        assert trade.net_realized_pnl_usdt == Decimal("0.19580000")
        assert portfolio.cumulative_realized_pnl_usdt == Decimal("0.19580000")
        assert portfolio.total_unrealized_pnl_usdt == Decimal("0.00")
        # Cash balance is now 7.998 + (2.20 - 0.0022) = 10.19580000
        assert portfolio.cash_balance_usdt == Decimal("10.19580000")


# ---------------------------------------------------------------------------
# 4. 3-Timestamp Execution & Schedule Drift Cost Tests
# ---------------------------------------------------------------------------


class TestThreeTimestampAndDriftCost:
    """Verifies that LIVE_PAPER accurately records schedule drift and BACKTEST fills next Open."""

    def test_live_paper_drift_cost_calculated(self) -> None:
        rule = make_test_rule("SOL-USDT")
        # Price at candle close was 100.00, but execution occurred 5 minutes later at 102.00
        close_time = NOW_MS
        exec_time = NOW_MS + (5 * 60 * 1000)
        book_at_exec = make_test_orderbook("SOL-USDT", best_ask="102.00", buy_slippage_bps="0.0")

        result = simulate_order_execution(
            inst_rule=rule,
            orderbook=book_at_exec,
            signal_id=make_signal_id("SOL-USDT", "15m", close_time),
            proposed_notional_usdt=Decimal("2.04"),  # qty = 0.02
            candle_close_time=close_time,
            signal_timestamp=close_time + 1000,
            execution_timestamp=exec_time,
            available_cash_usdt=Decimal("10.00"),
            price_at_candle_close=Decimal("100.00"),
            mode=ExecutionMode.LIVE_PAPER,
        )

        assert result.success is True
        assert result.position is not None
        pos = result.position
        assert pos.candle_close_time == close_time
        assert pos.execution_timestamp == exec_time
        assert pos.schedule_drift_ms == 5 * 60 * 1000
        # Drift = (102 - 100) / 100 * 10000 = 200 bps
        assert pos.schedule_drift_bps == Decimal("200.00")
        # Drift cost = (102 - 100) * 0.02 = $0.04
        assert pos.schedule_drift_cost_usdt == Decimal("0.04000000")

    def test_backtest_fills_at_next_candle_open(self) -> None:
        rule = make_test_rule("SOL-USDT")
        book = make_test_orderbook("SOL-USDT", best_ask="100.00")

        result = simulate_order_execution(
            inst_rule=rule,
            orderbook=book,
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            proposed_notional_usdt=Decimal("2.00"),
            candle_close_time=NOW_MS,
            signal_timestamp=NOW_MS,
            execution_timestamp=NOW_MS,
            available_cash_usdt=Decimal("10.00"),
            price_at_candle_close=Decimal("100.00"),
            mode=ExecutionMode.BACKTEST,
            next_candle_open=Decimal("101.50"),
        )
        assert result.success is True
        assert result.position is not None
        # Base price filled is rounded around next_candle_open 101.50
        assert result.position.entry_price >= Decimal("101.50")
        assert result.position.schedule_drift_ms == 0


# ---------------------------------------------------------------------------
# 5. REJECTED_BY_CONSTRAINT Tests
# ---------------------------------------------------------------------------


class TestRejectedByConstraint:
    """Verifies that constraint violations are never dropped silently."""

    def test_below_min_size_rejection_logged(self) -> None:
        # Rule requires min_size 1.0 SOL, but $1.50 order at $150 only gets 0.01 SOL
        rule = make_test_rule("SOL-USDT", min_size="1.00", lot_size="0.01")
        book = make_test_orderbook("SOL-USDT", best_ask="150.00")

        result = simulate_order_execution(
            inst_rule=rule,
            orderbook=book,
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            proposed_notional_usdt=Decimal("1.50"),
            candle_close_time=NOW_MS,
            signal_timestamp=NOW_MS,
            execution_timestamp=NOW_MS,
            available_cash_usdt=Decimal("10.00"),
            price_at_candle_close=Decimal("150.00"),
        )
        assert result.success is False
        assert result.rejected_record is not None
        assert result.rejected_record.constraint_code == "BELOW_OKX_MIN_SIZE"

    def test_insufficient_cash_after_fee_rejection_logged(self) -> None:
        rule = make_test_rule("SOL-USDT", min_size="0.01")
        book = make_test_orderbook("SOL-USDT", best_ask="100.00")

        # Trying to place $5.00 order with only $3.00 available cash
        result = simulate_order_execution(
            inst_rule=rule,
            orderbook=book,
            signal_id=make_signal_id("SOL-USDT", "15m", NOW_MS),
            proposed_notional_usdt=Decimal("5.00"),
            candle_close_time=NOW_MS,
            signal_timestamp=NOW_MS,
            execution_timestamp=NOW_MS,
            available_cash_usdt=Decimal("3.00"),
            price_at_candle_close=Decimal("100.00"),
        )
        assert result.success is False
        assert result.rejected_record is not None
        assert result.rejected_record.constraint_code == "INSUFFICIENT_CASH_AFTER_FEE"


# ---------------------------------------------------------------------------
# 6. Atomic Persistence Protocol Tests
# ---------------------------------------------------------------------------


class TestAtomicStatePersistence:
    """Verifies atomic writes, schema validation, and rollback safety."""

    def test_atomic_write_preserves_old_file_on_schema_error(self, tmp_path: Path) -> None:
        target_file = tmp_path / "paper_portfolio.json"
        portfolio = PaperPortfolio(initial_balance_usdt=Decimal("10.00"))
        snapshot = portfolio.snapshot(now_ms=NOW_MS)

        # 1. Write initial valid snapshot
        save_portfolio_snapshot(target_file, snapshot)
        assert target_file.is_file()
        original_content = target_file.read_text(encoding="utf-8")

        # 2. Attempt atomic write with invalid data (violating schema: extra field & negative cash)
        invalid_doc = snapshot.to_dict()
        invalid_doc["forbidden_extra_field"] = "corrupt"
        invalid_doc["cash_balance_usdt"] = "-5.00"

        with pytest.raises(AtomicStatePersistenceError):
            atomic_write_json(target_file, invalid_doc)

        # 3. Verify original file is 100% untouched and no .tmp file exists
        assert target_file.read_text(encoding="utf-8") == original_content
        tmp_file = tmp_path / "paper_portfolio.json.tmp"
        assert not tmp_file.exists()
