"""Idempotency & Signal Registry for Phase P3 (Hybrid Event Engine).

Ensures that no candle signal is processed more than once across surveillance cycles.
Tracks signal lifecycle: PENDING -> IN_FOCUS -> EVALUATED / EXPIRED.
Includes deterministic FIFO/TTL pruning to keep memory and state footprint bounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.vibetrade.scanner.models import (
    VALID_STATUSES,
    OpportunityCandidate,
    make_signal_id,
)

PROCESSED_STATUSES: frozenset[str] = frozenset({"IN_FOCUS", "EVALUATED", "EXPIRED"})
DEFAULT_REGISTRY_CAPACITY = 2000
DEFAULT_REGISTRY_TTL_MS = 7 * 24 * 60 * 60 * 1000  # 7 days


@dataclass(frozen=True)
class SignalEntry:
    """An entry in the idempotency registry."""

    signal_id: str
    inst_id: str
    timeframe: str
    candle_close_time: int
    status: str
    registered_at_ms: int
    last_updated_ms: int

    def __post_init__(self) -> None:
        expected = make_signal_id(self.inst_id, self.timeframe, self.candle_close_time)
        if self.signal_id != expected:
            raise ValueError(f"signal_id mismatch: {self.signal_id!r} != {expected!r}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {self.status!r}")
        if self.registered_at_ms <= 0 or self.last_updated_ms <= 0:
            raise ValueError("Timestamps must be positive ints")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "inst_id": self.inst_id,
            "timeframe": self.timeframe,
            "candle_close_time": self.candle_close_time,
            "status": self.status,
            "registered_at_ms": self.registered_at_ms,
            "last_updated_ms": self.last_updated_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignalEntry:
        return cls(
            signal_id=str(data["signal_id"]),
            inst_id=str(data["inst_id"]),
            timeframe=str(data["timeframe"]),
            candle_close_time=int(data["candle_close_time"]),
            status=str(data["status"]),
            registered_at_ms=int(data["registered_at_ms"]),
            last_updated_ms=int(data["last_updated_ms"]),
        )


class SignalRegistry:
    """In-memory idempotency registry with serialization and bounded pruning."""

    def __init__(self, entries: Mapping[str, SignalEntry] | None = None) -> None:
        self._entries: dict[str, SignalEntry] = dict(entries or {})

    def __len__(self) -> int:
        return len(self._entries)

    def has_signal(self, signal_id: str) -> bool:
        return signal_id in self._entries

    def is_processed(self, signal_id: str) -> bool:
        """Return True if signal has already been promoted to IN_FOCUS, EVALUATED, or EXPIRED."""
        entry = self._entries.get(signal_id)
        if entry is None:
            return False
        return entry.status in PROCESSED_STATUSES

    def get_status(self, signal_id: str) -> str | None:
        entry = self._entries.get(signal_id)
        return None if entry is None else entry.status

    def register(
        self,
        candidate: OpportunityCandidate,
        status: str = "PENDING",
        now_ms: int = 0,
    ) -> SignalEntry:
        """Register a new candidate in the registry.

        If already present, does not overwrite unless updating.
        """
        signal_id = candidate.signal_id
        if signal_id in self._entries:
            return self._entries[signal_id]

        ts = now_ms if now_ms > 0 else candidate.detected_at_utc_ms
        entry = SignalEntry(
            signal_id=signal_id,
            inst_id=candidate.inst_id,
            timeframe=candidate.timeframe,
            candle_close_time=candidate.candle_close_time,
            status=status,
            registered_at_ms=ts,
            last_updated_ms=ts,
        )
        self._entries[signal_id] = entry
        return entry

    def update_status(self, signal_id: str, new_status: str, now_ms: int) -> SignalEntry:
        """Update an existing signal entry's status."""
        if signal_id not in self._entries:
            raise KeyError(f"Signal {signal_id!r} not found in registry")
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {new_status!r}")

        old = self._entries[signal_id]
        updated = SignalEntry(
            signal_id=old.signal_id,
            inst_id=old.inst_id,
            timeframe=old.timeframe,
            candle_close_time=old.candle_close_time,
            status=new_status,
            registered_at_ms=old.registered_at_ms,
            last_updated_ms=now_ms,
        )
        self._entries[signal_id] = updated
        return updated

    def prune(
        self,
        now_ms: int,
        max_entries: int = DEFAULT_REGISTRY_CAPACITY,
        ttl_ms: int = DEFAULT_REGISTRY_TTL_MS,
    ) -> int:
        """Prune signals exceeding TTL or maximum capacity (FIFO). Returns number of pruned entries."""
        initial_count = len(self._entries)
        if initial_count == 0:
            return 0

        # 1. Prune expired by TTL
        retained = {
            sid: entry
            for sid, entry in self._entries.items()
            if (now_ms - entry.last_updated_ms) <= ttl_ms
        }

        # 2. If still exceeding max_entries, keep newest by registered_at_ms
        if len(retained) > max_entries:
            sorted_items = sorted(
                retained.items(),
                key=lambda kv: (kv[1].registered_at_ms, kv[0]),
                reverse=True,
            )
            retained = dict(sorted_items[:max_entries])

        self._entries = retained
        return initial_count - len(self._entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in sorted(self._entries.values(), key=lambda e: e.signal_id)]
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignalRegistry:
        entries = {}
        for row in data.get("entries", []):
            entry = SignalEntry.from_dict(row)
            entries[entry.signal_id] = entry
        return cls(entries)
