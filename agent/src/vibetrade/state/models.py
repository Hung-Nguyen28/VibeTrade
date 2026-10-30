"""Domain models for Phase P7-A System State and Telemetry.

Models the 5th canonical document: heartbeat.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.vibetrade.data.okx_models import ModelValidationError

SCHEMA_VERSION = "1.1"

VALID_HEALTH_STATUSES: frozenset[str] = frozenset({"HEALTHY", "DEGRADED", "ERROR"})
VALID_OKX_STATUSES: frozenset[str] = frozenset({"OK", "DEGRADED", "UNREACHABLE", "MOCK"})


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """Operational telemetry and cryptographic heartbeat of one surveillance cycle."""

    schema_version: str
    run_id: str
    cycle_started_at_utc_ms: int
    cycle_finished_at_utc_ms: int
    duration_ms: int
    schedule_drift_ms: int
    status: str
    okx_api_status: str
    scanned_symbols_count: int
    focus_sessions_triggered: int
    orders_executed_count: int
    orders_rejected_count: int
    state_changed: bool
    snapshot_hashes: dict[str, str]
    error_summary: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
        if not self.run_id.startswith("run:"):
            raise ModelValidationError(f"run_id must start with 'run:' (got {self.run_id!r})")
        if self.status not in VALID_HEALTH_STATUSES:
            raise ModelValidationError(f"Invalid health status {self.status!r}")
        if self.okx_api_status not in VALID_OKX_STATUSES:
            raise ModelValidationError(f"Invalid okx_api_status {self.okx_api_status!r}")
        if self.cycle_started_at_utc_ms <= 0 or self.cycle_finished_at_utc_ms <= 0:
            raise ModelValidationError("Cycle timestamps must be positive")
        if self.duration_ms < 0:
            raise ModelValidationError("duration_ms must be >= 0")
        required_hashes = {
            "market_snapshot_sha256",
            "opportunity_queue_sha256",
            "paper_portfolio_sha256",
            "research_history_sha256",
        }
        if not required_hashes.issubset(self.snapshot_hashes.keys()):
            raise ModelValidationError(f"snapshot_hashes missing required keys: {required_hashes - set(self.snapshot_hashes.keys())}")
        for k in required_hashes:
            h = self.snapshot_hashes[k]
            if len(h) != 64:
                raise ModelValidationError(f"{k} must be 64-char hex string (got {h!r})")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "cycle_started_at_utc_ms": self.cycle_started_at_utc_ms,
            "cycle_finished_at_utc_ms": self.cycle_finished_at_utc_ms,
            "duration_ms": self.duration_ms,
            "schedule_drift_ms": self.schedule_drift_ms,
            "status": self.status,
            "okx_api_status": self.okx_api_status,
            "scanned_symbols_count": self.scanned_symbols_count,
            "focus_sessions_triggered": self.focus_sessions_triggered,
            "orders_executed_count": self.orders_executed_count,
            "orders_rejected_count": self.orders_rejected_count,
            "state_changed": self.state_changed,
            "snapshot_hashes": dict(self.snapshot_hashes),
            "error_summary": self.error_summary,
        }
