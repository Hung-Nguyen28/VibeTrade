"""State Manager & 5-File Atomic Persistence for Phase P7-A.

Coordinates read, write, validation, and FIFO rotation across the 5 canonical JSON snapshots:
1. market_snapshot.json
2. opportunity_queue.json
3. paper_portfolio.json
4. research_history.json
5. heartbeat.json

Enforces:
- 5-step atomic write protocol (.tmp -> schema validate -> fsync -> read-back -> os.replace).
- FIFO bounded history rotation for research_history.json (default 200 records).
- Smart Change Detection to notify CI when meaningful git commits are required.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "schema" / "v1.1"

FILENAMES = {
    "market_snapshot": "market_snapshot.json",
    "opportunity_queue": "opportunity_queue.json",
    "paper_portfolio": "paper_portfolio.json",
    "research_history": "research_history.json",
    "heartbeat": "heartbeat.json",
}

SCHEMA_FILES = {
    "market_snapshot": "market_snapshot.schema.json",
    "opportunity_queue": "opportunity_queue.schema.json",
    "paper_portfolio": "paper_portfolio.schema.json",
    "research_history": "research_history.schema.json",
    "heartbeat": "heartbeat.schema.json",
}

DEFAULT_MAX_HISTORY_RECORDS = 200


class StatePersistenceError(RuntimeError):
    """Raised when atomic write or validation fails."""


def compute_sha256(data: Mapping[str, Any]) -> str:
    """Canonical SHA-256 hash of a JSON-serializable dictionary."""
    canonical_bytes = json.dumps(data, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class StateManager:
    """Manages reading and atomic writing of the 5 canonical state files."""

    def __init__(
        self,
        state_dir: Path | str,
        schema_dir: Path | str = SCHEMA_DIR,
        max_history_records: int = DEFAULT_MAX_HISTORY_RECORDS,
    ) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.schema_dir = Path(schema_dir).resolve()
        self.max_history_records = max_history_records
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._validators: dict[str, jsonschema.Draft202012Validator] = {}

    def _get_validator(self, file_key: str) -> jsonschema.Draft202012Validator:
        if file_key not in self._validators:
            schema_file = self.schema_dir / SCHEMA_FILES[file_key]
            if not schema_file.is_file():
                raise FileNotFoundError(f"Schema file not found: {schema_file}")
            schema_dict = json.loads(schema_file.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema_dict)
            self._validators[file_key] = jsonschema.Draft202012Validator(schema_dict)
        return self._validators[file_key]

    def validate_doc(self, file_key: str, doc: Mapping[str, Any]) -> None:
        """Validate a document against its corresponding JSON schema."""
        validator = self._get_validator(file_key)
        errors = list(validator.iter_errors(doc))
        if errors:
            msgs = "; ".join(e.message for e in errors)
            raise StatePersistenceError(f"Validation failed for {file_key}: {msgs}")

    def atomic_write(self, file_key: str, doc: Mapping[str, Any]) -> None:
        """Atomically persist a document to its canonical file."""
        filename = FILENAMES[file_key]
        target_path = self.state_dir / filename
        tmp_path = self.state_dir / f"{filename}.tmp"

        # 1. In-memory validation
        self.validate_doc(file_key, doc)

        # 2. Serialize safely (allow_nan=False)
        try:
            payload = json.dumps(doc, indent=2, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise StatePersistenceError(f"Failed to serialize JSON for {file_key}: {exc}") from exc

        try:
            # 3. Write to temporary file with flush & fsync
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())

            # 4. Read back and parse to verify integrity
            with open(tmp_path, "r", encoding="utf-8") as f:
                readback = json.load(f)
            if not isinstance(readback, dict):
                raise StatePersistenceError(f"Read-back for {file_key} failed: not a dict")

            # 5. Atomic swap
            os.replace(tmp_path, target_path)
        except Exception as exc:
            if not isinstance(exc, StatePersistenceError):
                raise StatePersistenceError(f"Atomic write failed for {target_path}: {exc}") from exc
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def load_doc(self, file_key: str) -> dict[str, Any] | None:
        """Load and return an existing document if present, else None."""
        target_path = self.state_dir / FILENAMES[file_key]
        if not target_path.is_file():
            return None
        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def prune_research_history(self, history_doc: dict[str, Any]) -> dict[str, Any]:
        """Apply FIFO bounding to research_history.json reports."""
        reports = history_doc.get("reports", [])
        if len(reports) > self.max_history_records:
            # Sort newest first, then slice
            sorted_reports = sorted(reports, key=lambda r: (-r.get("evaluated_at_utc_ms", 0), r.get("report_id", "")))
            reports = sorted_reports[: self.max_history_records]
            history_doc["reports"] = reports
            history_doc["total_reports"] = len(reports)
        return history_doc

    def save_cycle_state(
        self,
        market_snapshot: Mapping[str, Any],
        opportunity_queue: Mapping[str, Any],
        paper_portfolio: Mapping[str, Any],
        research_history: Mapping[str, Any],
        heartbeat_builder_fn: Any,
    ) -> tuple[bool, dict[str, str]]:
        """Atomically persist all 5 files and determine if state changed meaningfully.

        Returns (state_changed, snapshot_hashes).
        """
        # 1. Prune history before hashing
        clean_history = self.prune_research_history(dict(research_history))

        # 2. Compute current hashes
        h_market = compute_sha256(market_snapshot)
        h_queue = compute_sha256(opportunity_queue)
        h_portfolio = compute_sha256(paper_portfolio)
        h_history = compute_sha256(clean_history)

        current_hashes = {
            "market_snapshot_sha256": h_market,
            "opportunity_queue_sha256": h_queue,
            "paper_portfolio_sha256": h_portfolio,
            "research_history_sha256": h_history,
        }

        # 3. Compare with prior heartbeat hashes for meaningful change detection
        prior_heartbeat = self.load_doc("heartbeat")
        prior_hashes = prior_heartbeat.get("snapshot_hashes", {}) if prior_heartbeat else {}
        state_changed = (
            prior_heartbeat is None
            or h_queue != prior_hashes.get("opportunity_queue_sha256")
            or h_portfolio != prior_hashes.get("paper_portfolio_sha256")
            or h_history != prior_hashes.get("research_history_sha256")
        )

        # 4. Build Heartbeat document
        heartbeat_doc = heartbeat_builder_fn(state_changed, current_hashes)

        # 5. Atomically persist all 5 files
        self.atomic_write("market_snapshot", market_snapshot)
        self.atomic_write("opportunity_queue", opportunity_queue)
        self.atomic_write("paper_portfolio", paper_portfolio)
        self.atomic_write("research_history", clean_history)
        self.atomic_write("heartbeat", heartbeat_doc)

        return state_changed, current_hashes
