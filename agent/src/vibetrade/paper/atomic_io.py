"""Atomic State Persistence Protocol for Phase P6 (Paper Portfolio).

Follows the strict 5-step write protocol from skill atomic-state-persistence:
1. In-memory validation against JSON Schema (allow_nan=False).
2. Write to adjacent .tmp file in the same directory.
3. f.flush() + os.fsync(f.fileno()).
4. Read-back verification to guarantee non-truncation.
5. os.replace() atomic rename.
Rollback/cleanup of .tmp on failure guaranteed via try/finally.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from src.vibetrade.paper.models import PaperPortfolioSnapshot

DEFAULT_PORTFOLIO_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schema" / "v1.1" / "paper_portfolio.schema.json"


class AtomicStatePersistenceError(RuntimeError):
    """Raised when an atomic write fails or violates schema validation."""


def validate_portfolio_dict(data: Mapping[str, Any], schema_path: Path | None = None) -> None:
    """Validate data against paper_portfolio.schema.json."""
    path = schema_path or DEFAULT_PORTFOLIO_SCHEMA_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Schema file not found at {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    if errors:
        msg = "; ".join(e.message for e in errors)
        raise AtomicStatePersistenceError(f"Schema validation failed: {msg}")


def atomic_write_json(
    target_path: Path | str,
    data: Mapping[str, Any],
    schema_path: Path | None = None,
) -> None:
    """Execute the 5-step atomic persistence protocol."""
    target = Path(target_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.parent / f"{target.name}.tmp"

    # Step 1: In-memory schema validation & serialization
    validate_portfolio_dict(data, schema_path)
    try:
        payload_str = json.dumps(data, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AtomicStatePersistenceError(f"Failed to serialize JSON safely: {exc}") from exc

    try:
        # Step 2 & 3: Write to .tmp with flush and fsync
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload_str)
            f.flush()
            os.fsync(f.fileno())

        # Step 4: Read-back verification
        with open(tmp_path, "r", encoding="utf-8") as f:
            readback = json.load(f)
        if not isinstance(readback, dict):
            raise AtomicStatePersistenceError("Read-back verification did not yield a dictionary")

        # Step 5: Atomic replace
        os.replace(tmp_path, target)
    except Exception as exc:
        if not isinstance(exc, AtomicStatePersistenceError):
            raise AtomicStatePersistenceError(f"Atomic write failed for {target}: {exc}") from exc
        raise
    finally:
        # Cleanup temporary file if it still exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def save_portfolio_snapshot(
    target_path: Path | str,
    snapshot: PaperPortfolioSnapshot,
    schema_path: Path | None = None,
) -> None:
    """Serialize and atomically persist a PaperPortfolioSnapshot."""
    doc = snapshot.to_dict()
    atomic_write_json(target_path, doc, schema_path)
