"""OKX Public REST v5 client — Zero-Secret, USDT Spot only (P1).

Design rules (``quant-data-guard`` + ``security``):

* **No credentials, ever.** No API-key header is built; only an allow-list of
  four public market-data paths can be requested, so a typo or a future edit
  cannot reach private or authenticated endpoints (fail-closed).
* **No cross-venue fallback.** A failed request raises :class:`OKXPublicError`
  after bounded retries; the caller decides (typically ``INCONCLUSIVE``).
* **Bar-close confirmation** is applied at the parser: only rows with
  ``confirm == "1"`` and ``candle_close_time <= now`` become
  :class:`~src.vibetrade.data.okx_models.ClosedCandle`.
* Explicit ``(connect, read)`` timeouts and bounded exponential backoff for
  HTTP 429/5xx, connection errors, non-JSON bodies and OKX rate-limit codes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping

import requests

from src.vibetrade.data.bar_close import BAR_DURATION_MS, filter_closed_rows, utc_now_ms
from src.vibetrade.data.okx_models import (
    QUOTE_CCY,
    ClosedCandle,
    ModelValidationError,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
    SpotTicker24h,
)
from src.vibetrade.data.orderbook import build_orderbook_snapshot

logger = logging.getLogger(__name__)

BASE_URL = "https://www.okx.com/api/v5"

#: The only endpoints this client can ever call (all public, unauthenticated).
ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        "/public/instruments",
        "/market/tickers",
        "/market/candles",
        "/market/history-candles",
        "/market/books",
    }
)

#: Base currencies that are themselves stable / fiat-pegged; ``<stable>-USDT``
#: pairs carry no directional signal and are excluded from the universe.
STABLECOIN_BASES: frozenset[str] = frozenset(
    {"USDC", "USDG", "FDUSD", "DAI", "TUSD", "USDP", "PYUSD", "USDD", "USDE", "EURT", "EURC", "USDT"}
)

_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})
_TRANSIENT_OKX_CODES = frozenset({"50001", "50011", "50013", "50026"})
_MAX_CANDLES_LIMIT = 300
_MAX_HISTORY_LIMIT = 100
_MAX_BOOK_DEPTH = 400


class OKXPublicError(RuntimeError):
    """The OKX public API could not provide a usable response (no fallback exists)."""


@dataclass(frozen=True)
class TickersResult:
    """Tickers that passed validation plus the number of rows skipped (e.g. no bid/ask)."""

    tickers: tuple[SpotTicker24h, ...]
    skipped: int


def is_stablecoin_pair(rule: SpotInstrumentRule) -> bool:
    return rule.base_ccy.upper() in STABLECOIN_BASES


def select_trading_universe(
    rules: list[SpotInstrumentRule] | tuple[SpotInstrumentRule, ...],
    *,
    exclude_stablecoin_pairs: bool = True,
) -> tuple[SpotInstrumentRule, ...]:
    """Live ``*-USDT`` Spot pairs, optionally without stablecoin bases, sorted by ``inst_id``."""
    chosen = [
        r
        for r in rules
        if r.state == "live" and r.quote_ccy == QUOTE_CCY and not (exclude_stablecoin_pairs and is_stablecoin_pair(r))
    ]
    return tuple(sorted(chosen, key=lambda r: r.inst_id))


class OKXPublicClient:
    """Minimal, deterministic OKX public market-data client."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        base_url: str = BASE_URL,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 10.0,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 8.0,
        sleep: Callable[[float], None] = time.sleep,
        now_ms: Callable[[], int] = utc_now_ms,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("OKXPublicClient requires an https:// base_url")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._session = session if session is not None else requests.Session()
        self._base_url = base_url.rstrip("/")
        self._timeout = (connect_timeout_s, read_timeout_s)
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep
        self._now_ms = now_ms

    # ------------------------------------------------------------------ core
    def _get(self, path: str, params: Mapping[str, str]) -> list[Any]:
        if path not in ALLOWED_PATHS:
            raise OKXPublicError(f"path {path!r} is not an allow-listed public market-data endpoint")
        url = f"{self._base_url}{path}"
        last_error: str = "no attempt made"
        for attempt in range(self._max_retries + 1):
            if attempt:
                delay = min(self._backoff_base_s * (2 ** (attempt - 1)), self._backoff_max_s)
                self._sleep(delay)
            try:
                resp = self._session.get(url, params=dict(params), timeout=self._timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = f"network error: {exc}"
                logger.warning("OKX %s attempt %d failed: %s", path, attempt + 1, last_error)
                continue
            if resp.status_code in _TRANSIENT_STATUS:
                last_error = f"HTTP {resp.status_code}"
                logger.warning("OKX %s attempt %d transient %s", path, attempt + 1, last_error)
                continue
            if resp.status_code != 200:
                raise OKXPublicError(f"OKX {path} HTTP {resp.status_code}")
            try:
                payload = resp.json()
            except ValueError:
                last_error = "non-JSON response body"
                continue
            if not isinstance(payload, dict):
                raise OKXPublicError(f"OKX {path}: unexpected payload type {type(payload).__name__}")
            code = str(payload.get("code", ""))
            if code in _TRANSIENT_OKX_CODES:
                last_error = f"OKX code={code} msg={payload.get('msg')}"
                continue
            if code != "0":
                raise OKXPublicError(f"OKX {path} code={code} msg={payload.get('msg')}")
            data = payload.get("data")
            if not isinstance(data, list):
                raise OKXPublicError(f"OKX {path}: 'data' is not a list")
            return data
        raise OKXPublicError(f"OKX {path} failed after {self._max_retries + 1} attempts: {last_error}")

    # ------------------------------------------------------------- endpoints
    def get_spot_instruments(
        self, *, live_only: bool = True, exclude_stablecoin_pairs: bool = True
    ) -> tuple[SpotInstrumentRule, ...]:
        """``GET /public/instruments?instType=SPOT`` -> live ``*-USDT`` rules."""
        rows = self._get("/public/instruments", {"instType": "SPOT"})
        rules: list[SpotInstrumentRule] = []
        for row in rows:
            if not isinstance(row, dict):
                raise OKXPublicError("instruments: row is not an object")
            if str(row.get("quoteCcy", "")) != QUOTE_CCY:
                continue  # non-USDT quote: out of universe, not an error
            if live_only and str(row.get("state", "")) != "live":
                continue
            rules.append(SpotInstrumentRule.from_okx(row))
        if live_only:
            return select_trading_universe(rules, exclude_stablecoin_pairs=exclude_stablecoin_pairs)
        kept = [r for r in rules if not (exclude_stablecoin_pairs and is_stablecoin_pair(r))]
        return tuple(sorted(kept, key=lambda r: r.inst_id))

    def get_spot_tickers(self) -> TickersResult:
        """``GET /market/tickers?instType=SPOT`` -> ``*-USDT`` tickers in ONE request."""
        rows = self._get("/market/tickers", {"instType": "SPOT"})
        tickers: list[SpotTicker24h] = []
        skipped = 0
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("instId", "")).endswith(f"-{QUOTE_CCY}"):
                continue
            try:
                tickers.append(SpotTicker24h.from_okx(row))
            except ModelValidationError as exc:
                skipped += 1
                logger.debug("ticker %s skipped: %s", row.get("instId"), exc)
        tickers.sort(key=lambda t: t.inst_id)
        return TickersResult(tickers=tuple(tickers), skipped=skipped)

    def get_closed_candles(
        self,
        inst_id: str,
        bar: str,
        *,
        limit: int = 100,
        after_ms: int | None = None,
        history: bool = False,
        now_ms: int | None = None,
    ) -> tuple[ClosedCandle, ...]:
        """``/market/candles`` (or ``/history-candles``) -> closed bars, ascending by time.

        ``after_ms`` requests records older than that open-time (OKX ``after``).
        Unconfirmed bars and bars whose close time is in the future are dropped.
        """
        if bar not in BAR_DURATION_MS:
            raise ValueError(f"unsupported bar {bar!r}")
        cap = _MAX_HISTORY_LIMIT if history else _MAX_CANDLES_LIMIT
        if not 1 <= limit <= cap:
            raise ValueError(f"limit must be in [1, {cap}]")
        params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
        if after_ms is not None:
            params["after"] = str(int(after_ms))
        path = "/market/history-candles" if history else "/market/candles"
        rows = self._get(path, params)
        current = self._now_ms() if now_ms is None else now_ms
        closed = filter_closed_rows(rows, bar, current)
        by_open: dict[int, ClosedCandle] = {}
        for row in closed:
            candle = ClosedCandle.from_okx_row(inst_id, bar, row)
            by_open[candle.candle_open_time] = candle
        return tuple(by_open[k] for k in sorted(by_open))

    def get_orderbook_snapshot(
        self,
        inst_id: str,
        *,
        depth: int = 50,
        probe_notional_usdt: Decimal = Decimal("10"),
    ) -> OrderBookLiquiditySnapshot:
        """``GET /market/books`` -> :class:`OrderBookLiquiditySnapshot`."""
        if not 1 <= depth <= _MAX_BOOK_DEPTH:
            raise ValueError(f"depth must be in [1, {_MAX_BOOK_DEPTH}]")
        rows = self._get("/market/books", {"instId": inst_id, "sz": str(depth)})
        if not rows or not isinstance(rows[0], dict):
            raise OKXPublicError(f"books {inst_id}: empty response")
        return build_orderbook_snapshot(
            inst_id,
            rows[0],
            depth_levels=min(depth, 20),
            probe_notional_usdt=probe_notional_usdt,
        )
