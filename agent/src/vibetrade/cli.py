"""Command-line interface for VibeTrade v1.1.

Usage:
    python -m vibetrade.cli run-cycle --state-dir ./data-state
    python -m vibetrade.cli run-cycle --state-dir ./data-state --dry-run
    python -m vibetrade.cli seed-sample-state --state-dir ./frontend/public/data-state
    python -m vibetrade.cli init-experiment --state-dir ./data-state
    python -m vibetrade.cli evaluate-experiment --state-dir ./data-state --output P8_EXPERIMENT_REPORT.md
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Sequence

# Ensure agent and agent/src are in sys.path for direct invocations
_AGENT_DIR = Path(__file__).resolve().parents[2]
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from src.vibetrade.runner.cycle_runner import StatelessCycleRunner
from src.vibetrade.experiment.evaluator import ExperimentEvaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibetrade",
        description="VibeTrade v1.1 — Personal Autonomous Crypto Intelligence System ($0 Budget)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run-cycle
    cmd_run = subparsers.add_parser("run-cycle", help="Execute a single 15m surveillance & paper trading cycle")
    cmd_run.add_argument(
        "--state-dir",
        type=str,
        default="./data-state",
        help="Directory storing the 5 canonical JSON state files (default: ./data-state)",
    )
    cmd_run.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run using deterministic mock market fixtures without live network calls",
    )
    cmd_run.add_argument(
        "--seed-sample-state",
        action="store_true",
        default=False,
        help="Seed valid initial 5-file sample state before running cycle",
    )
    cmd_run.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Specific *-USDT pairs to scan",
    )

    # seed-sample-state
    cmd_seed = subparsers.add_parser("seed-sample-state", help="Generate valid 5-file sample state for frontend/testing")
    cmd_seed.add_argument(
        "--state-dir",
        type=str,
        required=True,
        help="Target directory where 5 JSON snapshots will be written",
    )

    # init-experiment (P8)
    cmd_init_exp = subparsers.add_parser(
        "init-experiment",
        help="Initialize clean 100% state for T0 ($10.00 cash, 0 positions) and register Baseline 2 BTC price",
    )
    cmd_init_exp.add_argument(
        "--state-dir",
        type=str,
        required=True,
        help="Directory where clean experiment state will be initialized",
    )
    cmd_init_exp.add_argument(
        "--btc-price",
        type=str,
        default=None,
        help="Explicit initial BTC-USDT price for Baseline 2 (default: fetched live from OKX or mock)",
    )
    cmd_init_exp.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in mock mode without live OKX API calls",
    )

    # evaluate-experiment (P8)
    cmd_eval_exp = subparsers.add_parser(
        "evaluate-experiment",
        help="Evaluate 7-day experiment performance after costs and generate P8_EXPERIMENT_REPORT.md",
    )
    cmd_eval_exp.add_argument(
        "--state-dir",
        type=str,
        required=True,
        help="Directory storing the 5 canonical JSON state files",
    )
    cmd_eval_exp.add_argument(
        "--output",
        type=str,
        default="P8_EXPERIMENT_REPORT.md",
        help="Output markdown file path (default: P8_EXPERIMENT_REPORT.md)",
    )
    cmd_eval_exp.add_argument(
        "--btc-price",
        type=str,
        default=None,
        help="Current BTC-USDT price (default: read from current state/market snapshot)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "seed-sample-state":
        target = Path(args.state_dir)
        runner = StatelessCycleRunner(state_dir=target)
        res = runner.run_cycle(dry_run=True, trigger_anomaly_on="SOL-USDT")
        if res.status == "HEALTHY":
            print(f"[vibetrade] Successfully seeded sample 5-file state at {target} (run_id={res.run_id})")
            return 0
        else:
            print(f"[vibetrade] Error seeding sample state: {res.error_summary}", file=sys.stderr)
            return 1

    if args.command == "init-experiment":
        target = Path(args.state_dir)
        btc_p0 = Decimal(args.btc_price) if args.btc_price else None
        evaluator = ExperimentEvaluator(state_dir=target)
        anchor = evaluator.init_experiment(btc_initial_price=btc_p0, dry_run=args.dry_run)
        print(f"[vibetrade] Successfully initialized Experiment {anchor['experiment_id']} at {target}")
        print(f"            Initial Capital: {anchor['initial_capital_usdt']} USDT")
        print(f"            Baseline 2 BTC T0 Price: ${anchor['btc_t0_price_usdt']}")
        return 0

    if args.command == "evaluate-experiment":
        target = Path(args.state_dir)
        btc_pt = Decimal(args.btc_price) if args.btc_price else None
        evaluator = ExperimentEvaluator(state_dir=target)
        metrics = evaluator.evaluate_experiment(btc_current_price=btc_pt)
        out_file = evaluator.write_report_file(args.output, metrics)
        print(f"[vibetrade] Experiment Evaluation Completed: {metrics.experiment_id}")
        print(f"            Duration: {metrics.duration_days:.1f} days")
        print(f"            VibeTrade Net Return: {metrics.post_cost_net_return_pct:+.2f}% (${metrics.current_equity_usdt:.4f})")
        print(f"            Baseline 1 (Cash): {metrics.baseline_cash.net_return_pct:+.2f}% (${metrics.baseline_cash.current_equity_usdt:.4f})")
        print(f"            Baseline 2 (BTC):  {metrics.baseline_btc.net_return_pct:+.2f}% (${metrics.baseline_btc.current_equity_usdt:.4f})")
        print(f"            Total Operational Friction: ${(metrics.total_fees_usdt + abs(metrics.total_schedule_drift_cost_usdt)):.4f} USDT")
        print(f"            Report written to: {out_file}")
        return 0

    if args.command == "run-cycle":
        target = Path(args.state_dir)
        symbols = args.symbols if args.symbols else None
        runner = StatelessCycleRunner(
            state_dir=target,
            symbols=symbols if symbols else ("BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "AVAX-USDT"),
        )
        res = runner.run_cycle(
            dry_run=args.dry_run or args.seed_sample_state,
            trigger_anomaly_on="SOL-USDT",
        )
        print(f"[vibetrade] Cycle run completed: status={res.status}, duration={res.duration_ms}ms, state_changed={res.state_changed}")
        print(f"            Scanned: {res.scanned_symbols_count}, Focus: {res.focus_sessions_count}, Executed: {res.orders_executed_count}, Rejected: {res.orders_rejected_count}")
        if res.status != "HEALTHY":
            print(f"[vibetrade] Error: {res.error_summary}", file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
