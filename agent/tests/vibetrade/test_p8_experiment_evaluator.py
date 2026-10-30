"""Unit & Regression tests for Phase P8 — 7-Day Live Autonomous Experiment & Post-Cost Evaluator.

Covers:
1. init_experiment() creates clean $10.00 state with 0 positions and records Baseline 2 BTC anchor.
2. evaluate_experiment() accurately computes post-cost net return, win rate, profit factor, and max drawdown.
3. Mathematical precision for Baseline 1 ($10.00 USDT Cash) and Baseline 2 ($10.00 BTC Buy & Hold with 0.1% fees).
4. Friction decomposition (OKX 0.1% fees, schedule drift cost, slippage).
5. Edge cases: 0 closed trades (zero-division protection), REJECTED_BY_CONSTRAINT categorization, INCONCLUSIVE signals.
6. Markdown report generation matches institutional quant standard.
7. CLI commands: init-experiment & evaluate-experiment.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import pytest

from src.vibetrade.experiment.evaluator import (
    ExperimentEvaluator,
    ExperimentMetrics,
    FEE_RATE,
    ANCHOR_FILENAME,
)
from src.vibetrade.cli import main as cli_main


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    state_dir = tmp_path / "data-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_init_experiment_creates_clean_t0_state(temp_state_dir: Path) -> None:
    evaluator = ExperimentEvaluator(state_dir=temp_state_dir)
    anchor = evaluator.init_experiment(
        btc_initial_price=Decimal("70000.00"),
        dry_run=True,
        now_ms=1793300000000,
    )

    # 1. Check anchor file
    assert anchor["schema_version"] == "1.1"
    assert anchor["initial_capital_usdt"] == "10.00000000"
    assert anchor["btc_t0_price_usdt"] == "70000.00"
    assert (temp_state_dir / ANCHOR_FILENAME).is_file()

    # 2. Check paper_portfolio is clean $10.0 cash, 0 positions
    portfolio_file = temp_state_dir / "paper_portfolio.json"
    assert portfolio_file.is_file()
    port_data = json.loads(portfolio_file.read_text(encoding="utf-8"))
    assert port_data["cash_balance_usdt"] == "10.00000000"
    assert port_data["total_equity_usdt"] == "10.00000000"
    assert port_data["cumulative_realized_pnl_usdt"] == "0.00000000"
    assert len(port_data["open_positions"]) == 0
    assert len(port_data["closed_trades"]) == 0
    assert len(port_data["rejected_orders"]) == 0

    # 3. Check research_history is clean
    history_file = temp_state_dir / "research_history.json"
    assert history_file.is_file()
    hist_data = json.loads(history_file.read_text(encoding="utf-8"))
    assert hist_data["total_reports"] == 0
    assert len(hist_data["reports"]) == 0

    # 4. Check all 5 canonical files exist
    for f in ["market_snapshot.json", "opportunity_queue.json", "paper_portfolio.json", "research_history.json", "heartbeat.json"]:
        assert (temp_state_dir / f).is_file(), f"Missing canonical file: {f}"


def test_evaluate_experiment_nominal_scenario(temp_state_dir: Path) -> None:
    evaluator = ExperimentEvaluator(state_dir=temp_state_dir)
    evaluator.init_experiment(btc_initial_price=Decimal("70000.00"), dry_run=True, now_ms=1793300000000)

    # Populate a realistic 7-day post-cost scenario in paper_portfolio.json
    portfolio = {
        "schema_version": "1.1",
        "generated_at_utc_ms": 1793904800000,
        "initial_balance_usdt": "10.0000",
        "cash_balance_usdt": "8.85000000",
        "total_equity_usdt": "10.45000000",
        "cumulative_realized_pnl_usdt": "0.35000000",
        "total_unrealized_pnl_usdt": "0.10000000",
        "total_fees_paid_usdt": "0.01500000",
        "total_schedule_drift_cost_usdt": "-0.00250000",
        "open_positions": [
            {
                "position_id": "pos:SOL:1",
                "inst_id": "SOL-USDT",
                "entry_order_id": "ord:1",
                "entry_price": "150.00",
                "qty_base": "0.01000000",
                "notional_entry_usdt": "1.5000",
                "entry_fee_usdt": "0.0015",
                "candle_close_time": 1793900000000,
                "signal_timestamp": 1793900100000,
                "execution_timestamp": 1793900200000,
                "schedule_drift_ms": 200000,
                "schedule_drift_bps": "-15.00",
                "schedule_drift_cost_usdt": "-0.00225000",
                "current_mark_price": "160.00",
                "unrealized_pnl_usdt": "0.10000000",
            }
        ],
        "closed_trades": [
            {
                "trade_id": "tr:1",
                "position_id": "pos:1",
                "inst_id": "AVAX-USDT",
                "qty_base": "0.10000000",
                "entry_price": "30.00",
                "exit_price": "34.00",
                "entry_fee_usdt": "0.00300000",
                "exit_fee_usdt": "0.00340000",
                "gross_pnl_usdt": "0.40000000",
                "net_realized_pnl_usdt": "0.40000000",
                "schedule_drift_cost_usdt": "0.00000000",
                "entry_timestamp": 1793400000000,
                "exit_timestamp": 1793500000000,
                "exit_reason": "TAKE_PROFIT",
            },
            {
                "trade_id": "tr:2",
                "position_id": "pos:2",
                "inst_id": "ETH-USDT",
                "qty_base": "0.00100000",
                "entry_price": "2600.00",
                "exit_price": "2550.00",
                "entry_fee_usdt": "0.00260000",
                "exit_fee_usdt": "0.00250000",
                "gross_pnl_usdt": "-0.05000000",
                "net_realized_pnl_usdt": "-0.05000000",
                "schedule_drift_cost_usdt": "0.00000000",
                "entry_timestamp": 1793600000000,
                "exit_timestamp": 1793700000000,
                "exit_reason": "STOP_LOSS",
            },
        ],
        "rejected_orders": [
            {
                "order_id": "ord:rej:1",
                "signal_id": "sig:rej:1",
                "inst_id": "BTC-USDT",
                "side": "BUY",
                "proposed_notional_usdt": "1.0000",
                "constraint_code": "BELOW_OKX_MIN_SZ",
                "details": "Notional below minSz",
                "timestamp_ms": 1793500000000,
            },
            {
                "order_id": "ord:rej:2",
                "signal_id": "sig:rej:2",
                "inst_id": "DOGE-USDT",
                "side": "BUY",
                "proposed_notional_usdt": "1.5000",
                "constraint_code": "SPREAD_TOO_WIDE",
                "details": "Spread 45 bps > max 35 bps",
                "timestamp_ms": 1793600000000,
            },
        ],
    }
    evaluator.state_mgr.atomic_write("paper_portfolio", portfolio)

    # Populate research history with 1 inconclusive and 1 actionable
    history = {
        "schema_version": "1.1",
        "generated_at_utc_ms": 1793904800000,
        "total_reports": 2,
        "reports": [
            {
                "report_id": "rep:SOL-USDT:15m:1793900000000",
                "signal_id": "SOL-USDT:15m:1793900000000",
                "inst_id": "SOL-USDT",
                "timeframe": "15m",
                "candle_close_time": 1793900000000,
                "evaluated_at_utc_ms": 1793900100000,
                "verdict": "ACTIONABLE_LONG",
                "score_bull": "80.00",
                "score_bear": "15.00",
                "score_raw": "65.00",
                "regime": "BULL_TREND",
                "regime_multiplier": "1.10",
                "score_net": "71.50",
                "missing_inputs": [],
                "template_summary": "Actionable Long",
                "evidence": [],
            },
            {
                "report_id": "rep:ETH-USDT:15m:1793900000000",
                "signal_id": "ETH-USDT:15m:1793900000000",
                "inst_id": "ETH-USDT",
                "timeframe": "15m",
                "candle_close_time": 1793900000000,
                "evaluated_at_utc_ms": 1793900100000,
                "verdict": "INCONCLUSIVE",
                "score_bull": "0.00",
                "score_bear": "0.00",
                "score_raw": "0.00",
                "regime": "BULL_TREND",
                "regime_multiplier": "1.00",
                "score_net": "0.00",
                "missing_inputs": ["orderbook_depth_l2"],
                "template_summary": "Inconclusive due to missing inputs",
                "evidence": [],
            },
        ],
    }
    evaluator.state_mgr.atomic_write("research_history", history)

    # Evaluate at current BTC price = 73500.00 (5% gain from 70000)
    metrics = evaluator.evaluate_experiment(
        btc_current_price=Decimal("73500.00"),
        now_ms=1793904800000,
    )

    # 1. Portfolio Accounting
    assert metrics.current_equity_usdt == Decimal("10.45000000")
    assert metrics.post_cost_net_return_pct == Decimal("4.50")  # (10.45 - 10.0) / 10 * 100 = +4.50%
    assert metrics.total_closed_trades == 2
    assert metrics.winning_trades_count == 1
    assert metrics.losing_trades_count == 1
    assert metrics.win_rate_pct == Decimal("50.00")
    # Gross profit = 0.40, Gross loss = 0.05 -> Profit factor = 0.40 / 0.05 = 8.00
    assert metrics.profit_factor == Decimal("8.00")

    # 2. Friction
    assert metrics.total_fees_usdt == Decimal("0.01500000")
    assert metrics.total_schedule_drift_cost_usdt == Decimal("-0.00250000")
    assert metrics.inconclusive_count == 1
    assert metrics.actionable_count == 1
    assert metrics.rejected_by_constraint_count == 2
    assert "BELOW_OKX_MIN_SZ" in metrics.rejections_by_code
    assert "SPREAD_TOO_WIDE" in metrics.rejections_by_code

    # 3. Baseline 1 (Cash)
    assert metrics.baseline_cash.current_equity_usdt == Decimal("10.0000")
    assert metrics.baseline_cash.net_return_pct == Decimal("0.00")

    # 4. Baseline 2 (BTC Buy & Hold)
    # T0: $10.00 - 0.0100 fee = $9.9900 in BTC
    # Pt / P0 = 73500 / 70000 = 1.05
    # Gross = 9.9900 * 1.05 = 10.4895
    # Exit fee = 10.4895 * 0.001 = 0.0104895
    # Net BTC Equity = 10.4895 - 0.0104895 = 10.4790
    # Net BTC Return = (10.4790 - 10.0) / 10 * 100 = +4.79%
    assert metrics.baseline_btc.current_equity_usdt == Decimal("10.4790")
    assert metrics.baseline_btc.net_return_pct == Decimal("4.79")


def test_baseline_btc_drawdown_calculation(temp_state_dir: Path) -> None:
    evaluator = ExperimentEvaluator(state_dir=temp_state_dir)
    evaluator.init_experiment(btc_initial_price=Decimal("70000.00"), dry_run=True, now_ms=1793300000000)

    # When BTC drops from 70000 to 63000 (-10%)
    metrics = evaluator.evaluate_experiment(
        btc_current_price=Decimal("63000.00"),
        now_ms=1793904800000,
    )

    # Pt / P0 = 0.90
    # Gross = 9.9900 * 0.9 = 8.991
    # Exit fee = 8.991 * 0.001 = 0.008991
    # Net = 8.991 - 0.008991 = 8.9820
    # Return = -10.18%
    assert metrics.baseline_btc.current_equity_usdt == Decimal("8.9820")
    assert metrics.baseline_btc.net_return_pct == Decimal("-10.18")
    assert metrics.baseline_btc.max_drawdown_pct == Decimal("10.00")


def test_evaluate_experiment_empty_trades_division_safe(temp_state_dir: Path) -> None:
    evaluator = ExperimentEvaluator(state_dir=temp_state_dir)
    evaluator.init_experiment(btc_initial_price=Decimal("70000.00"), dry_run=True, now_ms=1793300000000)

    # 0 closed trades
    metrics = evaluator.evaluate_experiment(btc_current_price=Decimal("70000.00"))
    assert metrics.total_closed_trades == 0
    assert metrics.win_rate_pct == Decimal("0.00")
    assert metrics.profit_factor == Decimal("1.00")
    assert metrics.post_cost_net_return_pct == Decimal("0.00")


def test_generate_markdown_report_formatting(temp_state_dir: Path) -> None:
    evaluator = ExperimentEvaluator(state_dir=temp_state_dir)
    evaluator.init_experiment(btc_initial_price=Decimal("70000.00"), dry_run=True, now_ms=1793300000000)
    metrics = evaluator.evaluate_experiment(btc_current_price=Decimal("71000.00"))

    md = evaluator.generate_markdown_report(metrics)
    assert "# VibeTrade v1.1 — Phase P8 Post-Cost Evaluation Report" in md
    assert "Baseline 1 ($10.00 Cash)" in md
    assert "Baseline 2 (BTC Buy & Hold after fees)" in md
    assert "Institutional Friction & Operational Latency Decomposition" in md
    assert "Schedule Drift Cost (GHA Latency)" in md
    assert "Accounting Invariant Verified" in md

    # Write report file
    report_file = temp_state_dir / "P8_EXPERIMENT_REPORT.md"
    written_path = evaluator.write_report_file(report_file, metrics)
    assert written_path.is_file()
    assert written_path.read_text(encoding="utf-8") == md


def test_cli_init_and_evaluate_commands(temp_state_dir: Path) -> None:
    # 1. Run cli init-experiment
    rc_init = cli_main([
        "init-experiment",
        "--state-dir", str(temp_state_dir),
        "--btc-price", "70000.00",
        "--dry-run",
    ])
    assert rc_init == 0
    assert (temp_state_dir / ANCHOR_FILENAME).is_file()

    # 2. Run cli evaluate-experiment
    report_out = temp_state_dir / "CUSTOM_REPORT.md"
    rc_eval = cli_main([
        "evaluate-experiment",
        "--state-dir", str(temp_state_dir),
        "--btc-price", "72000.00",
        "--output", str(report_out),
    ])
    assert rc_eval == 0
    assert report_out.is_file()
    content = report_out.read_text(encoding="utf-8")
    assert "VibeTrade v1.1 — Phase P8 Post-Cost Evaluation Report" in content
