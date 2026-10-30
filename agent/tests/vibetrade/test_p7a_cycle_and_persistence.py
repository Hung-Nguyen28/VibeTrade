"""Test Gate P7-A — Stateless Cycle Orchestrator & 5-File Atomic State Persistence.

Validates:
1. heartbeat.schema.json (Draft 2020-12 strict validation & invariants).
2. StateManager: atomic writes (.tmp + fsync + os.replace), FIFO history rotation,
   smart change detection, rollback on error.
3. End-to-End StatelessCycleRunner:
   - Cycle 1: Ingest -> Scan -> Focus -> Research -> Verify -> Execute -> Persist 5 files.
   - Cycle 2: Same candles -> Idempotency prevents duplicate trades, updates mark-to-market.
4. CLI entrypoint execution and 5 seeded files validation.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import jsonschema

from src.vibetrade.cli import main as cli_main
from src.vibetrade.runner.cycle_runner import (
    CycleRunResult,
    StatelessCycleRunner,
    generate_mock_market_data,
)
from src.vibetrade.state import (
    FILENAMES,
    HeartbeatSnapshot,
    StateManager,
    StatePersistenceError,
)

NOW_MS = 1_730_269_200_000  # 2026-10-30 06:20:00 UTC
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema" / "v1.1"


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def make_clean_heartbeat_dict(state_changed: bool = True) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "run_id": f"run:test:{NOW_MS}",
        "cycle_started_at_utc_ms": NOW_MS,
        "cycle_finished_at_utc_ms": NOW_MS + 1500,
        "duration_ms": 1500,
        "schedule_drift_ms": 0,
        "status": "HEALTHY",
        "okx_api_status": "MOCK",
        "scanned_symbols_count": 5,
        "focus_sessions_triggered": 1,
        "orders_executed_count": 1,
        "orders_rejected_count": 0,
        "state_changed": state_changed,
        "snapshot_hashes": {
            "market_snapshot_sha256": "a" * 64,
            "opportunity_queue_sha256": "b" * 64,
            "paper_portfolio_sha256": "c" * 64,
            "research_history_sha256": "d" * 64,
        },
        "error_summary": None,
    }


# ---------------------------------------------------------------------------
# 1. Heartbeat Schema Tests
# ---------------------------------------------------------------------------


class TestHeartbeatSchema:
    """Verifies that heartbeat.schema.json strictly validates operational telemetry."""

    @pytest.fixture(scope="class")
    @classmethod
    def heartbeat_validator(cls) -> Any:
        schema_file = SCHEMA_DIR / "heartbeat.schema.json"
        assert schema_file.is_file(), f"Missing schema file {schema_file}"
        schema_dict = json.loads(schema_file.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema_dict)
        return jsonschema.Draft202012Validator(schema_dict)

    def test_valid_heartbeat_passes(self, heartbeat_validator: Any) -> None:
        doc = make_clean_heartbeat_dict()
        errors = list(heartbeat_validator.iter_errors(doc))
        assert not errors, f"Validation errors: {[e.message for e in errors]}"

    def test_schema_rejects_extra_properties(self, heartbeat_validator: Any) -> None:
        doc = make_clean_heartbeat_dict()
        doc["forbidden_extra"] = "illegal"
        assert not heartbeat_validator.is_valid(doc)

    def test_schema_rejects_invalid_hash_length(self, heartbeat_validator: Any) -> None:
        doc = make_clean_heartbeat_dict()
        doc["snapshot_hashes"]["market_snapshot_sha256"] = "tooshort"
        assert not heartbeat_validator.is_valid(doc)

    def test_schema_rejects_malformed_run_id(self, heartbeat_validator: Any) -> None:
        doc = make_clean_heartbeat_dict()
        doc["run_id"] = "bad_run_id_no_prefix"
        assert not heartbeat_validator.is_valid(doc)


# ---------------------------------------------------------------------------
# 2. StateManager & Atomic Persistence Tests
# ---------------------------------------------------------------------------


class TestStateManagerAtomicPersistence:
    """Verifies atomic write protocol, schema validation, rollback, and FIFO pruning."""

    def test_atomic_write_and_load_roundtrip(self, tmp_path: Path) -> None:
        mgr = StateManager(state_dir=tmp_path)
        doc = make_clean_heartbeat_dict()

        # Write heartbeat
        mgr.atomic_write("heartbeat", doc)
        loaded = mgr.load_doc("heartbeat")
        assert loaded is not None
        assert loaded["run_id"] == doc["run_id"]
        assert loaded["status"] == "HEALTHY"

    def test_atomic_write_rollback_on_schema_violation(self, tmp_path: Path) -> None:
        mgr = StateManager(state_dir=tmp_path)
        valid_doc = make_clean_heartbeat_dict()
        mgr.atomic_write("heartbeat", valid_doc)

        # Attempt to write invalid doc
        invalid_doc = dict(valid_doc)
        invalid_doc["status"] = "INVALID_STATUS_VALUE"

        with pytest.raises(StatePersistenceError):
            mgr.atomic_write("heartbeat", invalid_doc)

        # Original file is preserved
        loaded = mgr.load_doc("heartbeat")
        assert loaded is not None
        assert loaded["status"] == "HEALTHY"
        # No orphaned .tmp file
        assert not (tmp_path / "heartbeat.json.tmp").exists()

    def test_fifo_pruning_of_research_history(self, tmp_path: Path) -> None:
        mgr = StateManager(state_dir=tmp_path, max_history_records=5)
        # Create 12 dummy reports
        reports = [
            {
                "report_id": f"rep:COIN{i}-USDT:15m:{NOW_MS + i * 1000}",
                "evaluated_at_utc_ms": NOW_MS + i * 1000,
            }
            for i in range(12)
        ]
        history_doc = {
            "schema_version": "1.1",
            "generated_at_utc_ms": NOW_MS,
            "total_reports": 12,
            "reports": reports,
        }

        pruned = mgr.prune_research_history(history_doc)
        assert pruned["total_reports"] == 5
        assert len(pruned["reports"]) == 5
        # Kept the 5 newest (indices 11, 10, 9, 8, 7)
        newest_id = pruned["reports"][0]["report_id"]
        assert "COIN11" in newest_id


# ---------------------------------------------------------------------------
# 3. End-to-End StatelessCycleRunner Tests
# ---------------------------------------------------------------------------


class TestStatelessCycleRunnerEndToEnd:
    """Verifies full execution pipeline across two consecutive cycles."""

    def test_end_to_end_two_consecutive_cycles(self, tmp_path: Path) -> None:
        runner = StatelessCycleRunner(
            state_dir=tmp_path,
            symbols=["BTC-USDT", "ETH-USDT", "SOL-USDT"],
        )

        # CYCLE 1: Trigger anomaly on SOL-USDT -> should research, verify, execute trade
        res1 = runner.run_cycle(
            now_ms=NOW_MS,
            dry_run=True,
            trigger_anomaly_on="SOL-USDT",
        )
        assert res1.status == "HEALTHY"
        assert res1.scanned_symbols_count == 3
        assert res1.focus_sessions_count == 1
        assert res1.orders_executed_count == 1
        assert res1.state_changed is True

        # Verify all 5 files exist in state_dir and pass schema validation
        for file_key, filename in FILENAMES.items():
            f_path = tmp_path / filename
            assert f_path.is_file(), f"Missing state file: {filename}"
            doc = json.loads(f_path.read_text(encoding="utf-8"))
            runner.state_mgr.validate_doc(file_key, doc)

        # Inspect portfolio state after Cycle 1
        portfolio_doc = json.loads((tmp_path / "paper_portfolio.json").read_text(encoding="utf-8"))
        assert len(portfolio_doc["open_positions"]) == 1
        assert portfolio_doc["open_positions"][0]["inst_id"] == "SOL-USDT"
        assert Decimal(portfolio_doc["cash_balance_usdt"]) < Decimal("10.00")

        # CYCLE 2: Run cycle with SAME candle close timestamp (t2 = NOW_MS + 10s)
        # Idempotency registry must prevent duplicate execution!
        res2 = runner.run_cycle(
            now_ms=NOW_MS + 10_000,
            dry_run=True,
            trigger_anomaly_on="SOL-USDT",
        )
        assert res2.status == "HEALTHY"
        # Since SOL-USDT was already processed in Cycle 1, focus session promotion is 0
        assert res2.focus_sessions_count == 0
        assert res2.orders_executed_count == 0

        # Verify portfolio still has exactly 1 position (no duplicate order placed!)
        portfolio_doc_2 = json.loads((tmp_path / "paper_portfolio.json").read_text(encoding="utf-8"))
        assert len(portfolio_doc_2["open_positions"]) == 1


# ---------------------------------------------------------------------------
# 4. CLI Entrypoint Tests
# ---------------------------------------------------------------------------


class TestCLIEntrypoint:
    """Verifies that the CLI seed-sample-state and run-cycle subcommands work cleanly."""

    def test_cli_seed_sample_state(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "seeded_state"
        exit_code = cli_main(["seed-sample-state", "--state-dir", str(target_dir)])
        assert exit_code == 0
        for filename in FILENAMES.values():
            assert (target_dir / filename).is_file()

    def test_cli_run_cycle(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "cycle_state"
        exit_code = cli_main(["run-cycle", "--state-dir", str(target_dir), "--dry-run"])
        assert exit_code == 0
        heartbeat = json.loads((target_dir / "heartbeat.json").read_text(encoding="utf-8"))
        assert heartbeat["status"] == "HEALTHY"
