"""Bar-Close Confirmation gate (quant-data-guard §2).

A candle may feed an indicator or signal only when BOTH hold:

1. OKX flags it closed (``confirm == "1"``), and
2. ``candle_close_time = candle_open_time + bar_duration_ms <= current_utc_ms``.

There is deliberately no "keep unconfirmed rows when nothing else came back"
escape hatch: an empty result is reported as empty, never repainted with a
running candle.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Sequence

#: OKX ``bar`` token -> fixed bar duration in milliseconds. ``1D`` opens at
#: 16:00 UTC (00:00 UTC+8) but still lasts exactly 24h.
BAR_DURATION_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1H": 60 * 60_000,
    "2H": 2 * 60 * 60_000,
    "4H": 4 * 60 * 60_000,
    "6H": 6 * 60 * 60_000,
    "12H": 12 * 60 * 60_000,
    "1D": 24 * 60 * 60_000,
}

_CONFIRM_IDX = 8
_TS_IDX = 0


def bar_duration_ms(bar: str) -> int:
    """Return the duration of an OKX ``bar`` token in ms (``KeyError`` is wrapped)."""
    try:
        return BAR_DURATION_MS[bar]
    except KeyError as exc:
        raise ValueError(f"unsupported OKX bar {bar!r}; supported: {sorted(BAR_DURATION_MS)}") from exc


def utc_now_ms() -> int:
    """Current UTC wall clock in epoch milliseconds."""
    return int(time.time() * 1000)


def is_closed_row(row: Sequence[Any], bar: str, now_ms: int) -> bool:
    """True iff ``row`` passes the dual closed-bar test.

    Malformed rows (too short, non-integer timestamp) are treated as not closed.
    """
    if len(row) <= _CONFIRM_IDX:
        return False
    if str(row[_CONFIRM_IDX]) != "1":
        return False
    try:
        open_ms = int(str(row[_TS_IDX]))
    except (TypeError, ValueError):
        return False
    return open_ms + bar_duration_ms(bar) <= now_ms


def filter_closed_rows(rows: Iterable[Sequence[Any]], bar: str, now_ms: int) -> list[Sequence[Any]]:
    """Keep only rows that are confirmed AND whose close time is not in the future."""
    return [r for r in rows if is_closed_row(r, bar, now_ms)]
