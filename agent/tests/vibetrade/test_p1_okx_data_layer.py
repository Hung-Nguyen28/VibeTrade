"""Phase P1 test gate — OKX Data Layer (offline; no network).

Five groups, mirroring the P1 gate in ``P0_AUDIT_REPORT.md`` §4 / Step 5:

1. Bar-Close Gate
2. USDT Spot Universe & Precision
3. Orderbook Walk & Anomaly
4. HTTP Resilience & No-Fallback
5. Truncation Invariance (Anti-Lookahead)

plus snapshot-schema checks. Every test is hermetic: HTTP is a scripted fake
session, time is injected, and no loader outside OKX is ever resolvable.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
import requests

import backtest.loaders.okx as okx
from backtest.loaders import registry
from src.vibetrade.data import indicators as ind
from src.vibetrade.data.bar_close import (
    BAR_DURATION_MS,
    filter_closed_rows,
    is_closed_row,
)
from src.vibetrade.data.okx_models import (
    ClosedCandle,
    ModelValidationError,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
    SpotTicker24h,
)
from src.vibetrade.data.okx_public_client import (
    ALLOWED_PATHS,
    BASE_URL,
    OKXPublicClient,
    OKXPublicError,
    select_trading_universe,
)
from src.vibetrade.data.orderbook import OrderBookError, build_orderbook_snapshot, walk_book
from src.vibetrade.data.snapshot import build_market_snapshot

NOW = int(pd.Timestamp("2026-10-30T06:00:00Z").timestamp() * 1000)
M15 = BAR_DURATION_MS["15m"]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "v1.1" / "market_snapshot.schema.json"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def row(open_ms: int, confirm: str = "1", o="100", h="101", lo="99", c="100.5", vol="10", vq="1005") -> list[str]:
    """OKX candle row ``[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]``."""
    return [str(open_ms), o, h, lo, c, vol, vol, vq, confirm]


class FakeResponse:
    def __init__(self, payload: Any = None, status: int = 200, json_error: bool = False) -> None:
        self.status_code = status
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("not json")
        return self._payload


def ok(data: list[Any]) -> FakeResponse:
    return FakeResponse({"code": "0", "msg": "", "data": data})


class FakeSession:
    """Scripted ``requests.Session`` stand-in recording every call."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, params: dict[str, str] | None = None, timeout: Any = None, **kwargs: Any) -> Any:
        self.calls.append({"url": url, "params": params, "timeout": timeout, "kwargs": kwargs})
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


def make_client(script: list[Any], sleeps: list[float] | None = None, **kw: Any) -> tuple[OKXPublicClient, FakeSession]:
    session = FakeSession(script)
    sleeps = sleeps if sleeps is not None else []
    client = OKXPublicClient(session, sleep=sleeps.append, now_ms=lambda: NOW, **kw)  # type: ignore[arg-type]
    return client, session


INSTRUMENT_ROWS = [
    {"instId": "BTC-USDT", "baseCcy": "BTC", "quoteCcy": "USDT", "tickSz": "0.1", "lotSz": "0.00000001", "minSz": "0.00001", "state": "live"},
    {"instId": "ETH-USDT", "baseCcy": "ETH", "quoteCcy": "USDT", "tickSz": "0.01", "lotSz": "0.000001", "minSz": "0.0001", "state": "live"},
    {"instId": "USDC-USDT", "baseCcy": "USDC", "quoteCcy": "USDT", "tickSz": "0.0001", "lotSz": "0.000001", "minSz": "1", "state": "live"},
    {"instId": "OLD-USDT", "baseCcy": "OLD", "quoteCcy": "USDT", "tickSz": "0.01", "lotSz": "0.01", "minSz": "1", "state": "suspend"},
    {"instId": "BTC-USDC", "baseCcy": "BTC", "quoteCcy": "USDC", "tickSz": "0.1", "lotSz": "0.00000001", "minSz": "0.00001", "state": "live"},
    {"instId": "ETH-BTC", "baseCcy": "ETH", "quoteCcy": "BTC", "tickSz": "0.00001", "lotSz": "0.000001", "minSz": "0.0001", "state": "live"},
]


def ticker_row(inst: str = "BTC-USDT", bid="99.9", ask="100.1", **over: str) -> dict[str, str]:
    base = {
        "instId": inst, "last": "100", "bidPx": bid, "bidSz": "1", "askPx": ask, "askSz": "1",
        "open24h": "98", "high24h": "101", "low24h": "97", "vol24h": "1234.5", "volCcy24h": "123450", "ts": str(NOW),
    }
    base.update(over)
    return base


# =========================================================================== #
# 1. BAR-CLOSE GATE
# =========================================================================== #


class TestBarCloseGate:
    def test_confirm_zero_is_dropped(self) -> None:
        assert not is_closed_row(row(NOW - 2 * M15, confirm="0"), "15m", NOW)

    def test_confirm_one_but_close_in_future_is_dropped(self) -> None:
        # Anomalous exchange flag: confirm=1 yet the bar has not finished.
        assert not is_closed_row(row(NOW - 5 * 60_000, confirm="1"), "15m", NOW)

    def test_bar_closing_exactly_now_is_closed(self) -> None:
        assert is_closed_row(row(NOW - M15), "15m", NOW)

    def test_one_ms_before_close_is_not_closed(self) -> None:
        assert not is_closed_row(row(NOW - M15 + 1), "15m", NOW)

    @pytest.mark.parametrize("bad", [[], ["1"] * 8, ["abc", "1", "1", "1", "1", "1", "1", "1", "1"]])
    def test_malformed_rows_are_not_closed(self, bad: list[str]) -> None:
        assert not is_closed_row(bad, "15m", NOW)

    def test_mixed_page_keeps_only_closed_rows(self) -> None:
        rows = [row(NOW, "0"), row(NOW - 5 * 60_000, "1"), row(NOW - M15, "1"), row(NOW - 2 * M15, "1")]
        kept = filter_closed_rows(rows, "15m", NOW)
        assert [int(r[0]) for r in kept] == [NOW - M15, NOW - 2 * M15]

    def test_closed_candle_model_refuses_running_candle(self) -> None:
        with pytest.raises(ModelValidationError):
            ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW, "0"))
        with pytest.raises(ModelValidationError):
            ClosedCandle(
                "BTC-USDT", "15m", NOW, NOW + M15, Decimal(1), Decimal(1), Decimal(1), Decimal(1),
                Decimal(0), Decimal(0), confirm=False,
            )

    def test_client_page_with_only_unconfirmed_bar_yields_empty_not_repaint(self) -> None:
        client, _ = make_client([ok([row(NOW, "0")])])
        assert client.get_closed_candles("BTC-USDT", "15m") == ()

    def test_client_keeps_vol_quote_and_close_time_sorted_ascending(self) -> None:
        client, session = make_client([ok([row(NOW, "0"), row(NOW - M15, vq="2500.5"), row(NOW - 2 * M15)])])
        candles = client.get_closed_candles("BTC-USDT", "15m")
        assert [c.candle_open_time for c in candles] == [NOW - 2 * M15, NOW - M15]
        assert candles[-1].candle_close_time == NOW
        assert candles[-1].vol_quote == Decimal("2500.5")
        assert candles[-1].confirm is True
        assert session.calls[0]["url"] == f"{BASE_URL}/market/candles"

    def test_history_endpoint_and_limit_caps(self) -> None:
        client, session = make_client([ok([row(NOW - M15)])])
        client.get_closed_candles("BTC-USDT", "15m", history=True, limit=100, after_ms=NOW)
        assert session.calls[0]["url"].endswith("/market/history-candles")
        assert session.calls[0]["params"]["after"] == str(NOW)
        with pytest.raises(ValueError):
            client.get_closed_candles("BTC-USDT", "15m", history=True, limit=101)
        with pytest.raises(ValueError):
            client.get_closed_candles("BTC-USDT", "7m")

    # --- the surgical fix in agent/backtest/loaders/okx.py ------------------

    @staticmethod
    def _paginate(rows: list[list[str]], monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame | None:
        monkeypatch.setattr(okx, "utc_now_ms", lambda: NOW)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"code": "0", "data": rows}
        session = MagicMock()
        session.get.return_value = resp
        return okx.DataLoader()._paginate(
            session, okx.CANDLES_PATH, "BTC-USDT", NOW - 6 * M15, NOW + 4 * M15, "15m", 1
        )

    def test_loader_page_with_only_unconfirmed_bar_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression for the removed ``rows = confirmed if confirmed else list(raw_rows)``."""
        assert self._paginate([row(NOW, "0")], monkeypatch) is None

    def test_loader_drops_running_and_future_close_bars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        df = self._paginate(
            [row(NOW, "0"), row(NOW - 5 * 60_000, "1"), row(NOW - M15), row(NOW - 2 * M15)], monkeypatch
        )
        assert df is not None
        assert list(df["candle_close_time"]) == [NOW - M15, NOW]
        assert (df["candle_close_time"] <= NOW).all()

    def test_loader_preserves_vol_quote_and_close_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        df = self._paginate([row(NOW - M15, vq="777.25", vol="3")], monkeypatch)
        assert df is not None
        assert {"open", "high", "low", "close", "volume", "vol_quote", "candle_close_time"} <= set(df.columns)
        assert float(df["vol_quote"].iloc[0]) == 777.25
        assert float(df["volume"].iloc[0]) == 3.0
        assert str(df["candle_close_time"].dtype) == "int64"
        from tests.loader_contract import assert_loader_contract

        assert_loader_contract(df, context="okx p1")

    def test_loader_source_has_no_unconfirmed_fallback(self) -> None:
        source = Path(okx.__file__).read_text(encoding="utf-8")
        assert "else list(raw_rows)" not in source
        assert "filter_closed_rows" in source

    def test_assert_closed_frame_rejects_running_candle(self) -> None:
        good = ind.candles_to_frame([ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - M15))])
        ind.assert_closed_frame(good, NOW)
        with pytest.raises(ValueError):
            ind.assert_closed_frame(good, NOW - 1)


# =========================================================================== #
# 2. USDT SPOT UNIVERSE & PRECISION
# =========================================================================== #


class TestUsdtSpotUniverse:
    def test_instruments_filtered_to_live_usdt_spot_without_stablecoins(self) -> None:
        client, session = make_client([ok(INSTRUMENT_ROWS)])
        rules = client.get_spot_instruments()
        assert [r.inst_id for r in rules] == ["BTC-USDT", "ETH-USDT"]
        assert session.calls[0]["params"] == {"instType": "SPOT"}
        assert session.calls[0]["url"] == f"{BASE_URL}/public/instruments"

    def test_stablecoin_pairs_can_be_requested_explicitly(self) -> None:
        client, _ = make_client([ok(INSTRUMENT_ROWS)])
        ids = [r.inst_id for r in client.get_spot_instruments(exclude_stablecoin_pairs=False)]
        assert ids == ["BTC-USDT", "ETH-USDT", "USDC-USDT"]

    def test_live_only_false_includes_suspended(self) -> None:
        client, _ = make_client([ok(INSTRUMENT_ROWS)])
        ids = [r.inst_id for r in client.get_spot_instruments(live_only=False)]
        assert "OLD-USDT" in ids and all(i.endswith("-USDT") for i in ids)

    def test_precision_is_exact_decimal(self) -> None:
        rule = SpotInstrumentRule.from_okx(INSTRUMENT_ROWS[0])
        assert rule.tick_size == Decimal("0.1")
        assert rule.lot_size == Decimal("1E-8")
        assert rule.min_size == Decimal("0.00001")
        assert all(isinstance(v, Decimal) for v in (rule.tick_size, rule.lot_size, rule.min_size))
        # A float would not round-trip 0.00001 * 3 exactly; Decimal does.
        assert rule.min_size * 3 == Decimal("0.00003")

    @pytest.mark.parametrize(
        "patch",
        [
            {"tickSz": "NaN"}, {"lotSz": "Infinity"}, {"minSz": "-1"}, {"minSz": "0"}, {"tickSz": ""},
            {"lotSz": "abc"}, {"quoteCcy": "USDC"}, {"instId": "BTC-USDC"}, {"instId": "btc-usdt"},
        ],
    )
    def test_invalid_rule_payloads_are_rejected(self, patch: dict[str, str]) -> None:
        with pytest.raises((ModelValidationError, ValueError)):
            SpotInstrumentRule.from_okx({**INSTRUMENT_ROWS[0], **patch})

    def test_models_are_frozen(self) -> None:
        rule = SpotInstrumentRule.from_okx(INSTRUMENT_ROWS[0])
        with pytest.raises(Exception):
            rule.tick_size = Decimal(1)  # type: ignore[misc]

    def test_select_trading_universe_is_sorted_and_deterministic(self) -> None:
        rules = [SpotInstrumentRule.from_okx(r) for r in INSTRUMENT_ROWS if r["quoteCcy"] == "USDT"]
        ids = [r.inst_id for r in select_trading_universe(list(reversed(rules)))]
        assert ids == sorted(ids) == ["BTC-USDT", "ETH-USDT"]

    def test_tickers_one_request_skip_unquotable_and_non_usdt(self) -> None:
        rows = [
            ticker_row("ETH-USDT", "10", "10.01"),
            ticker_row("BTC-USDT"),
            ticker_row("DEAD-USDT", bid="", ask=""),
            ticker_row("CROSS-USDT", bid="5", ask="4"),
            ticker_row("ETH-BTC"),
        ]
        client, session = make_client([ok(rows)])
        result = client.get_spot_tickers()
        assert [t.inst_id for t in result.tickers] == ["BTC-USDT", "ETH-USDT"]
        assert result.skipped == 2
        assert len(session.calls) == 1
        assert session.calls[0]["params"] == {"instType": "SPOT"}

    def test_ticker_spread_bps_and_quote_volume(self) -> None:
        t = SpotTicker24h.from_okx(ticker_row())
        assert t.spread_bps == Decimal("20")  # (100.1-99.9)/100*1e4
        assert t.vol_quote_24h == Decimal("123450") and t.vol_base_24h == Decimal("1234.5")

    @pytest.mark.parametrize("patch", [{"last": "NaN"}, {"askPx": "0"}, {"high24h": "90", "low24h": "97"}, {"ts": "x"}])
    def test_invalid_ticker_payloads_rejected(self, patch: dict[str, str]) -> None:
        with pytest.raises(ModelValidationError):
            SpotTicker24h.from_okx(ticker_row(**patch))

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", ""])
    def test_candle_rows_with_non_finite_values_rejected(self, bad: str) -> None:
        with pytest.raises(ModelValidationError):
            ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - M15, c=bad))

    def test_candle_ohlc_invariant_enforced(self) -> None:
        with pytest.raises(ModelValidationError):
            ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - M15, h="99", lo="99", c="100.5"))


# =========================================================================== #
# 3. ORDERBOOK WALK & ANOMALY
# =========================================================================== #


def book(asks: list[list[str]], bids: list[list[str]], ts: str | None = str(NOW)) -> dict[str, Any]:
    out: dict[str, Any] = {"asks": asks, "bids": bids}
    if ts is not None:
        out["ts"] = ts
    return out


BOOK_OK = book(
    asks=[["100.2", "1", "0", "1"], ["100.1", "0.05", "0", "1"]],  # deliberately unsorted
    bids=[["99.8", "2", "0", "1"], ["99.9", "1", "0", "1"]],
)


class TestOrderbookWalk:
    def test_walk_book_full_and_partial(self) -> None:
        levels = [(Decimal("100.1"), Decimal("0.05")), (Decimal("100.2"), Decimal("1"))]
        full = walk_book(levels, Decimal("0.1"))
        assert full["fully_filled"] and full["levels_used"] == 2
        assert full["filled_notional_quote"] == Decimal("10.015")
        assert full["avg_price"] == Decimal("100.15")
        partial = walk_book(levels, Decimal("10"))
        assert not partial["fully_filled"]
        assert partial["filled_base_qty"] == Decimal("1.05")
        assert partial["unfilled_base_qty"] == Decimal("8.95")
        empty = walk_book([], Decimal("1"))
        assert empty["avg_price"] is None and not empty["fully_filled"]

    def test_snapshot_metrics_hand_computed_for_10_usdt_probe(self) -> None:
        snap = build_orderbook_snapshot("BTC-USDT", BOOK_OK, probe_notional_usdt=Decimal("10"))
        assert snap.best_bid == Decimal("99.9") and snap.best_ask == Decimal("100.1")
        assert snap.mid_price == Decimal("100")
        assert snap.spread_bps == Decimal("20.0000")
        assert snap.est_buy_slippage_bps == Decimal("15.0000")   # avg 100.15 vs mid 100
        assert snap.est_sell_slippage_bps == Decimal("10.0000")  # avg 99.9 vs mid 100
        assert snap.buy_fully_filled and snap.sell_fully_filled
        assert snap.bid_depth_usdt == Decimal("99.9") + Decimal("199.6")
        assert snap.ask_depth_usdt == Decimal("5.005") + Decimal("100.2")
        expected_imb = (Decimal("299.5") - Decimal("105.205")) / (Decimal("299.5") + Decimal("105.205"))
        assert abs(snap.imbalance_ratio - expected_imb) < Decimal("1E-7")
        assert snap.ts_utc_ms == NOW

    def test_partial_fill_is_reported_not_disguised(self) -> None:
        snap = build_orderbook_snapshot("BTC-USDT", BOOK_OK, probe_notional_usdt=Decimal("100000"))
        assert snap.buy_fully_filled is False and snap.sell_fully_filled is False
        assert snap.est_buy_slippage_bps is not None  # computed on what *was* filled

    def test_empty_side_rejected(self) -> None:
        with pytest.raises(OrderBookError):
            build_orderbook_snapshot("BTC-USDT", book(asks=[], bids=[["99.9", "1"]]))
        with pytest.raises(OrderBookError):
            build_orderbook_snapshot("BTC-USDT", book(asks=[["100", "1"]], bids=[]))

    @pytest.mark.parametrize("bid,ask", [("100.1", "100.1"), ("101", "100")])
    def test_crossed_or_locked_book_rejected(self, bid: str, ask: str) -> None:
        with pytest.raises(OrderBookError):
            build_orderbook_snapshot("BTC-USDT", book(asks=[[ask, "1"]], bids=[[bid, "1"]]))

    def test_invalid_levels_are_dropped_not_propagated(self) -> None:
        dirty = book(
            asks=[["NaN", "1"], ["0", "1"], ["100.1", "-5"], ["Infinity", "1"], ["x"], ["100.1", "0.05"], ["100.2", "1"]],
            bids=[["99.9", "1"], ["-1", "1"], ["99.8", "2"]],
        )
        snap = build_orderbook_snapshot("BTC-USDT", dirty)
        assert snap.best_ask == Decimal("100.1")
        assert snap.est_buy_slippage_bps == Decimal("15.0000")

    def test_missing_timestamp_rejected(self) -> None:
        with pytest.raises(OrderBookError):
            build_orderbook_snapshot("BTC-USDT", book(BOOK_OK["asks"], BOOK_OK["bids"], ts=None))

    def test_one_sided_no_fill_gives_none_slippage_model_is_valid(self) -> None:
        snap = OrderBookLiquiditySnapshot(
            "BTC-USDT", NOW, Decimal("99"), Decimal("101"), Decimal("100"), Decimal("200"), 1,
            Decimal(1), Decimal(1), Decimal(0), Decimal(10), None, None, False, False,
        )
        assert snap.to_dict()["est_buy_slippage_bps"] is None

    def test_client_books_endpoint(self) -> None:
        client, session = make_client([ok([BOOK_OK])])
        snap = client.get_orderbook_snapshot("BTC-USDT", depth=50)
        assert session.calls[0]["url"] == f"{BASE_URL}/market/books"
        assert session.calls[0]["params"] == {"instId": "BTC-USDT", "sz": "50"}
        assert snap.mid_price == Decimal("100")
        with pytest.raises(ValueError):
            client.get_orderbook_snapshot("BTC-USDT", depth=0)

    def test_client_books_empty_response(self) -> None:
        client, _ = make_client([ok([])])
        with pytest.raises(OKXPublicError):
            client.get_orderbook_snapshot("BTC-USDT")

    def test_snapshot_model_rejects_crossed_book_even_if_built_by_hand(self) -> None:
        with pytest.raises(ModelValidationError):
            OrderBookLiquiditySnapshot(
                "BTC-USDT", NOW, Decimal("101"), Decimal("100"), Decimal("100"), Decimal(0), 1,
                Decimal(1), Decimal(1), Decimal(0), Decimal(10), None, None, False, False,
            )


# =========================================================================== #
# 4. HTTP RESILIENCE & NO-FALLBACK
# =========================================================================== #


class TestHttpResilienceNoFallback:
    def test_429_then_502_then_success_uses_exponential_backoff(self) -> None:
        sleeps: list[float] = []
        client, session = make_client(
            [FakeResponse(status=429), FakeResponse(status=502), ok([row(NOW - M15)])], sleeps
        )
        candles = client.get_closed_candles("BTC-USDT", "15m")
        assert len(candles) == 1
        assert len(session.calls) == 3
        assert sleeps == [0.5, 1.0]

    def test_connection_error_and_timeout_are_retried(self) -> None:
        sleeps: list[float] = []
        client, session = make_client(
            [requests.ConnectionError("blip"), requests.Timeout("slow"), ok([row(NOW - M15)])], sleeps
        )
        assert len(client.get_closed_candles("BTC-USDT", "15m")) == 1
        assert len(session.calls) == 3

    def test_non_json_body_is_retried(self) -> None:
        client, session = make_client([FakeResponse(json_error=True), ok([row(NOW - M15)])])
        assert len(client.get_closed_candles("BTC-USDT", "15m")) == 1
        assert len(session.calls) == 2

    def test_okx_rate_limit_code_is_retried(self) -> None:
        busy = FakeResponse({"code": "50011", "msg": "Too Many Requests", "data": []})
        client, session = make_client([busy, ok([row(NOW - M15)])])
        assert len(client.get_closed_candles("BTC-USDT", "15m")) == 1
        assert len(session.calls) == 2

    def test_persistent_failure_is_bounded_and_raises(self) -> None:
        sleeps: list[float] = []
        client, session = make_client([FakeResponse(status=503)], sleeps, max_retries=3)
        with pytest.raises(OKXPublicError, match="after 4 attempts"):
            client.get_closed_candles("BTC-USDT", "15m")
        assert len(session.calls) == 4
        assert sleeps == [0.5, 1.0, 2.0]

    def test_backoff_is_capped(self) -> None:
        sleeps: list[float] = []
        client, _ = make_client([FakeResponse(status=500)], sleeps, max_retries=6, backoff_max_s=4.0)
        with pytest.raises(OKXPublicError):
            client.get_spot_tickers()
        assert max(sleeps) == 4.0

    def test_business_error_not_retried(self) -> None:
        bad = FakeResponse({"code": "51001", "msg": "Instrument ID does not exist", "data": []})
        client, session = make_client([bad])
        with pytest.raises(OKXPublicError, match="51001"):
            client.get_closed_candles("NOPE-USDT", "15m")
        assert len(session.calls) == 1

    def test_non_200_non_transient_status_not_retried(self) -> None:
        client, session = make_client([FakeResponse(status=403)])
        with pytest.raises(OKXPublicError, match="403"):
            client.get_spot_tickers()
        assert len(session.calls) == 1

    def test_failure_never_touches_another_venue(self) -> None:
        client, session = make_client([FakeResponse(status=503)], max_retries=2)
        with pytest.raises(OKXPublicError):
            client.get_spot_tickers()
        assert {c["url"] for c in session.calls} == {f"{BASE_URL}/market/tickers"}
        assert all(c["url"].startswith("https://www.okx.com/api/v5/") for c in session.calls)

    def test_explicit_timeouts_and_no_credentials(self) -> None:
        client, session = make_client([ok([])])
        client.get_spot_tickers()
        call = session.calls[0]
        assert call["timeout"] == (5.0, 10.0)
        assert "headers" not in call["kwargs"] and "auth" not in call["kwargs"]
        assert not any(k.upper().startswith("OK-ACCESS") for k in session.headers)

    def test_private_or_trade_paths_are_not_reachable(self) -> None:
        assert all(p.startswith(("/public/", "/market/")) for p in ALLOWED_PATHS)
        client, session = make_client([ok([])])
        for path in ("/trade/order", "/account/balance", "/market/../trade/order"):
            with pytest.raises(OKXPublicError, match="allow-listed"):
                client._get(path, {})
        assert session.calls == []

    def test_https_only_base_url(self) -> None:
        with pytest.raises(ValueError):
            OKXPublicClient(FakeSession([]), base_url="http://www.okx.com/api/v5")  # type: ignore[arg-type]

    def test_client_source_has_no_secret_surface(self) -> None:
        src = (Path(__file__).resolve().parents[2] / "src" / "vibetrade" / "data" / "okx_public_client.py").read_text(
            encoding="utf-8"
        )
        for needle in ("OK-ACCESS-KEY", "OK-ACCESS-SIGN", "passphrase", "/trade/", "ccxt", "binance", "yfinance"):
            assert needle.lower() not in src.lower().replace("never reach", ""), needle

    # --- No-Fallback ---------------------------------------------------------

    def test_crypto_fallback_chain_is_okx_only(self) -> None:
        assert registry.FALLBACK_CHAINS["crypto"] == ["okx"]
        assert registry._DEFAULT_CHAINS["crypto"] == ["okx"]
        assert registry.get_default_source_order("crypto") == ["okx"]

    def test_env_override_cannot_reintroduce_other_venues(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MARKET_DATA_ORDER_CRYPTO", "okx,binance,ccxt,yfinance")
        monkeypatch.setattr(registry, "_LAST_ORDER_ENV_SNAPSHOT", None)
        try:
            registry.refresh_source_order_overrides()
            assert registry.FALLBACK_CHAINS["crypto"] == ["okx"]
            assert registry.get_source_order_override("crypto") is None
        finally:
            monkeypatch.delenv("MARKET_DATA_ORDER_CRYPTO")
            registry._LAST_ORDER_ENV_SNAPSHOT = None
            registry.refresh_source_order_overrides()

    def test_market_data_fetch_does_not_walk_to_binance_ccxt_yahoo(self) -> None:
        from src import market_data

        tried: list[str] = []

        def resolver(source: str):
            tried.append(source)

            class Down:
                def fetch(self, *_a: Any, **_k: Any) -> dict:
                    raise RuntimeError(f"{source} unavailable")

            return Down

        result = market_data.fetch_market_data(
            codes=["BTC-USDT"], start_date="2026-10-01", end_date="2026-10-02", source="okx", loader_resolver=resolver
        )
        assert set(tried) == {"okx"}
        assert "BTC-USDT" not in result

    def test_resolve_loader_crypto_only_considers_okx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[str] = []

        class Unavailable:
            def __init__(self, name: str) -> None:
                self.name = name

            def is_available(self) -> bool:
                seen.append(self.name)
                return False

        registry._ensure_registered()
        monkeypatch.setattr(registry, "LOADER_REGISTRY", {n: (lambda n=n: Unavailable(n)) for n in registry.LOADER_REGISTRY})
        with pytest.raises(registry.NoAvailableSourceError):
            registry.resolve_loader("crypto")
        assert seen == ["okx"]


# =========================================================================== #
# 5. TRUNCATION INVARIANCE (ANTI-LOOKAHEAD) + indicator correctness
# =========================================================================== #


def make_frame(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    close = np.abs(close) + 5
    spread = rng.uniform(0.1, 1.5, n)
    high = close + spread
    low = np.maximum(close - spread, 0.01)
    volume = rng.uniform(50, 500, n)
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


INDICATORS: dict[str, Any] = {
    "ema_10": lambda d: ind.ema(d["close"], 10),
    "ema_50": lambda d: ind.ema(d["close"], 50),
    "rsi_14": lambda d: ind.rsi_wilder(d["close"], 14),
    "rsi_7": lambda d: ind.rsi_wilder(d["close"], 7),
    "atr_14": lambda d: ind.atr_wilder(d["high"], d["low"], d["close"], 14),
    "true_range": lambda d: ind.true_range(d["high"], d["low"], d["close"]),
    "rvol_20": lambda d: ind.rvol(d["volume"], 20),
    "vol_z_20": lambda d: ind.volume_zscore(d["volume"], 20),
}


def _same(a: float, b: float, tol: float = 1e-12) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= tol


class TestTruncationInvariance:
    @pytest.mark.parametrize("name", sorted(INDICATORS))
    def test_value_at_t_is_independent_of_the_future(self, name: str) -> None:
        """``F(df.iloc[:t]).iloc[-1] == F(df).iloc[t-1]`` for every t (tol 1e-12)."""
        fn, df = INDICATORS[name], make_frame()
        full = fn(df)
        for t in range(1, len(df) + 1):
            assert _same(float(fn(df.iloc[:t]).iloc[-1]), float(full.iloc[t - 1])), f"{name} lookahead at t={t}"

    @pytest.mark.parametrize("name", sorted(INDICATORS))
    def test_mutating_future_bars_never_changes_the_past(self, name: str) -> None:
        fn, df = INDICATORS[name], make_frame()
        k = 150
        base = fn(df)
        mutated = df.copy()
        mutated.iloc[k:, mutated.columns.get_indexer(["high", "close", "volume"])] *= 7.0
        mutated["low"] = np.minimum(mutated["low"], mutated[["open", "close"]].min(axis=1))
        after = fn(mutated)
        for i in range(k):
            assert _same(float(base.iloc[i]), float(after.iloc[i])), f"{name} row {i} changed by future edit"

    def test_warmup_rows_are_nan_not_zero(self) -> None:
        df = make_frame(60)
        assert ind.ema(df["close"], 10).iloc[:9].isna().all() and not np.isnan(ind.ema(df["close"], 10).iloc[9])
        rsi = ind.rsi_wilder(df["close"], 14)
        assert rsi.iloc[:14].isna().all() and not np.isnan(rsi.iloc[14])
        atr = ind.atr_wilder(df["high"], df["low"], df["close"], 14)
        assert atr.iloc[:13].isna().all() and not np.isnan(atr.iloc[13])
        assert ind.rvol(df["volume"], 20).iloc[:20].isna().all()
        assert ind.volume_zscore(df["volume"], 20).iloc[:20].isna().all()

    def test_non_finite_input_is_refused(self) -> None:
        df = make_frame(40)
        bad = df["close"].copy()
        bad.iloc[10] = np.nan
        for fn in (lambda s: ind.ema(s, 5), lambda s: ind.rsi_wilder(s, 5)):
            with pytest.raises(ValueError):
                fn(bad)
        bad.iloc[10] = np.inf
        with pytest.raises(ValueError):
            ind.ema(bad, 5)

    def test_invalid_windows_refused(self) -> None:
        s = make_frame(10)["close"]
        for w in (0, -1, 2.5, True):
            with pytest.raises(ValueError):
                ind.ema(s, w)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            ind.volume_zscore(s, 1)

    # --- known values ----------------------------------------------------

    def test_ema_known_values(self) -> None:
        s = pd.Series([1.0, 2.0, 3.0, 4.0])
        out = ind.ema(s, 3)  # alpha = 0.5, adjust=False
        assert out.iloc[:2].isna().all()
        assert out.iloc[2] == pytest.approx(0.5 * 3 + 0.5 * (0.5 * 2 + 0.5 * 1))
        assert out.iloc[3] == pytest.approx(0.5 * 4 + 0.5 * out.iloc[2])
        assert (ind.ema(pd.Series([5.0] * 20), 5).dropna() == 5.0).all()

    def test_rsi_extremes(self) -> None:
        assert ind.rsi_wilder(pd.Series(np.arange(1.0, 40.0)), 14).dropna().eq(100.0).all()
        assert ind.rsi_wilder(pd.Series(np.arange(40.0, 1.0, -1.0)), 14).dropna().eq(0.0).all()
        assert ind.rsi_wilder(pd.Series([10.0] * 40), 14).dropna().eq(50.0).all()

    def test_rsi_wilder_hand_computed(self) -> None:
        closes = pd.Series([10.0, 11.0, 10.5, 11.5, 11.0])
        out = ind.rsi_wilder(closes, 3)
        gains = [1.0, 0.0, 1.0, 0.0]
        losses = [0.0, 0.5, 0.0, 0.5]
        ag = al = None
        # Wilder via ewm(adjust=False): seed with first obs, alpha = 1/3
        ag, al = gains[0], losses[0]
        series = []
        for g, lo in zip(gains[1:], losses[1:]):
            ag = ag + (g - ag) / 3
            al = al + (lo - al) / 3
            series.append(100 - 100 / (1 + ag / al))
        assert out.iloc[3] == pytest.approx(series[1])
        assert out.iloc[4] == pytest.approx(series[2])
        assert out.iloc[:3].isna().all()

    def test_true_range_uses_previous_close(self) -> None:
        h = pd.Series([10.0, 12.0]); lo = pd.Series([9.0, 11.5]); c = pd.Series([9.5, 12.0])
        tr = ind.true_range(h, lo, c)
        assert tr.iloc[0] == pytest.approx(1.0)  # no previous close: high - low
        assert tr.iloc[1] == pytest.approx(max(0.5, abs(12 - 9.5), abs(11.5 - 9.5)))  # gap up counts

    def test_rvol_and_zscore_use_prior_bars_only(self) -> None:
        vol = pd.Series([10.0, 20.0, 30.0, 40.0, 100.0])
        r = ind.rvol(vol, 4)
        assert r.iloc[4] == pytest.approx(100.0 / np.mean([10, 20, 30, 40]))
        assert r.iloc[:4].isna().all()
        z = ind.volume_zscore(vol, 4)
        prior = np.array([10.0, 20.0, 30.0, 40.0])
        assert z.iloc[4] == pytest.approx((100.0 - prior.mean()) / prior.std(ddof=1))

    def test_zero_variance_or_zero_baseline_gives_nan_not_inf(self) -> None:
        flat = pd.Series([5.0] * 10)
        assert ind.volume_zscore(flat, 4).dropna().empty
        zero = pd.Series([0.0] * 10)
        assert ind.rvol(zero, 4).dropna().empty

    def test_candles_to_frame_closed_candles_roundtrip(self) -> None:
        candles = [ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - k * M15)) for k in (3, 2, 1)]
        frame = ind.candles_to_frame(candles)
        assert frame.index.tz is not None and frame.index.is_monotonic_increasing
        assert int(frame.index[-1].value // 1_000_000) == NOW
        ind.assert_closed_frame(frame, NOW)
        with pytest.raises(ValueError):
            ind.candles_to_frame(list(reversed(candles)))
        with pytest.raises(ValueError):
            ind.candles_to_frame([candles[0], ClosedCandle.from_okx_row("ETH-USDT", "15m", row(NOW - M15))])


# =========================================================================== #
# SNAPSHOT SCHEMA
# =========================================================================== #


class TestMarketSnapshotSchema:
    @staticmethod
    def _validator():
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return jsonschema.Draft202012Validator(schema)

    @staticmethod
    def _snapshot() -> dict[str, Any]:
        return build_market_snapshot(
            generated_at_utc_ms=NOW,
            instruments=[SpotInstrumentRule.from_okx(INSTRUMENT_ROWS[1]), SpotInstrumentRule.from_okx(INSTRUMENT_ROWS[0])],
            tickers=[SpotTicker24h.from_okx(ticker_row())],
            candles=[ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - M15, vq="1005.25"))],
            orderbooks=[build_orderbook_snapshot("BTC-USDT", BOOK_OK)],
        )

    def test_snapshot_validates_and_is_strict_json(self) -> None:
        snap = self._snapshot()
        self._validator().validate(snap)
        text = json.dumps(snap, allow_nan=False, sort_keys=True)  # no NaN/Infinity possible
        assert json.loads(text) == snap

    def test_snapshot_is_deterministic_and_sorted(self) -> None:
        a, b = self._snapshot(), self._snapshot()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        assert [i["inst_id"] for i in a["instruments"]] == ["BTC-USDT", "ETH-USDT"]

    def test_decimals_are_plain_strings_never_exponent(self) -> None:
        snap = self._snapshot()
        assert snap["instruments"][0]["lot_size"] == "0.00000001"
        for inst in snap["instruments"]:
            for field in ("tick_size", "lot_size", "min_size"):
                assert "e" not in str(inst[field]).lower()
        for t in snap["tickers"]:
            for field in ("last", "bid_px", "ask_px", "vol_base_24h", "vol_quote_24h"):
                assert "e" not in str(t[field]).lower()
        for c in snap["candles"]:
            for field in ("open", "high", "low", "close", "vol_base", "vol_quote"):
                assert "e" not in str(c[field]).lower()

    def test_schema_rejects_unconfirmed_candle_and_extras(self) -> None:
        v = self._validator()
        snap = self._snapshot()
        snap["candles"][0]["confirm"] = False
        assert not v.is_valid(snap)
        snap = self._snapshot()
        snap["candles"][0]["unexpected"] = 1
        assert not v.is_valid(snap)
        snap = self._snapshot()
        snap["tickers"][0]["last"] = "NaN"
        assert not v.is_valid(snap)
        snap = self._snapshot()
        snap["instruments"][0]["inst_id"] = "BTC-USDC"
        assert not v.is_valid(snap)
        snap = self._snapshot()
        snap["tickers"][0]["last"] = "0"
        assert not v.is_valid(snap)
        snap = self._snapshot()
        snap["source"] = "binance"
        assert not v.is_valid(snap)

    def test_builder_refuses_candle_closing_after_snapshot_time(self) -> None:
        late = ClosedCandle.from_okx_row("BTC-USDT", "15m", row(NOW - M15 + 60_000))
        with pytest.raises(ValueError, match="running candle"):
            build_market_snapshot(generated_at_utc_ms=NOW, candles=[late])
        with pytest.raises(ValueError):
            build_market_snapshot(generated_at_utc_ms=0)
