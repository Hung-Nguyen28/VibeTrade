"""Stateless Cycle Orchestrator for Phase P7-A (VibeTrade v1.1).

Runs an end-to-end 15-minute surveillance cycle in < 2 minutes:
1. Loads current state from state_dir (or initializes fresh $10.0 micro-portfolio).
2. P1: Ingests OKX market data (rules, tickers, closed candles, orderbooks) or mock provider.
3. P2: Tradable Universe Filter + Market Regime + Anomaly Scanner.
4. Portfolio: Updates mark-to-market and checks TP/SL/Exit rules for open positions.
5. P3: Hybrid Event Engine (Bar-Close Gate, deduplication, Focus Session promotion).
6. P4: Deterministic Research Team (Analysts, Bull, Bear, Crucible).
7. P5: Independent Verification Gate (DataAuditor, StrategyReviewer, signed receipt).
8. P6: Immutable Risk Controller + Paper Execution ($10 budget constraints, drift tracking).
9. P7: Atomically persists the 5 canonical JSON files via StateManager.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vibetrade.data.bar_close import bar_duration_ms
from src.vibetrade.data.okx_models import (
    ClosedCandle,
    OrderBookLiquiditySnapshot,
    SpotInstrumentRule,
    SpotTicker24h,
)
from src.vibetrade.data.snapshot import build_market_snapshot
from src.vibetrade.engine import (
    EngineConfig,
    SignalEntry,
    SignalRegistry,
    process_opportunity_cycle,
)
from src.vibetrade.paper import (
    ExecutionMode,
    OpenPosition,
    PaperPortfolio,
    PaperTradingConfig,
    RejectedOrderRecord,
    simulate_order_execution,
)
from src.vibetrade.research import (
    CrucibleEngine,
    extract_analysts_features,
)
from src.vibetrade.risk import (
    ImmutableRiskController,
    RiskConfig,
)
from src.vibetrade.scanner import (
    MarketRegimeConfig,
    OpportunityCandidate,
    OpportunityQueueSnapshot,
    ScannerConfig,
    UniverseFilterConfig,
    detect_market_regime,
    filter_tradable_universe,
    scan_market_opportunities,
)
from src.vibetrade.state import (
    HeartbeatSnapshot,
    StateManager,
)
from src.vibetrade.verification import VerificationGate

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "AVAX-USDT-SWAP",
)


@dataclass(frozen=True)
class CycleRunResult:
    """Execution summary of a single surveillance cycle run."""

    run_id: str
    status: str
    duration_ms: int
    scanned_symbols_count: int
    focus_sessions_count: int
    orders_executed_count: int
    orders_rejected_count: int
    state_changed: bool
    snapshot_hashes: dict[str, str]
    error_summary: str | None


def generate_mock_market_data(
    symbols: Sequence[str],
    now_ms: int,
    trigger_anomaly_on: str | None = "SOL-USDT",
) -> tuple[
    list[SpotInstrumentRule],
    list[SpotTicker24h],
    dict[str, list[ClosedCandle]],
    dict[str, OrderBookLiquiditySnapshot],
]:
    """Generate rich, valid mock market fixtures for dry runs and testing."""
    rules: list[SpotInstrumentRule] = []
    tickers: list[SpotTicker24h] = []
    candles_by_symbol: dict[str, list[ClosedCandle]] = {}
    orderbooks: dict[str, OrderBookLiquiditySnapshot] = {}

    tf_15m_ms = 15 * 60 * 1000

    base_prices = {
        "BTC-USDT-SWAP": 70000.0,
        "ETH-USDT-SWAP": 3000.0,
        "SOL-USDT-SWAP": 150.0,
        "DOGE-USDT-SWAP": 0.20,
        "AVAX-USDT-SWAP": 30.0,
        "BTC-USDT": 70000.0,
        "ETH-USDT": 3000.0,
        "SOL-USDT": 150.0,
        "DOGE-USDT": 0.20,
        "AVAX-USDT": 30.0,
    }

    ct_val_map = {
        "BTC": Decimal("0.01"),
        "ETH": Decimal("0.1"),
        "SOL": Decimal("1"),
        "DOGE": Decimal("100"),
        "AVAX": Decimal("1"),
    }

    for sym in symbols:
        base_ccy = sym.split("-")[0]
        base_px = base_prices.get(sym, 50.0)
        is_swap = sym.endswith("-SWAP")
        ct_val = ct_val_map.get(base_ccy, Decimal("1")) if is_swap else Decimal("1")

        # Rule
        rules.append(
            SpotInstrumentRule(
                inst_id=sym,
                base_ccy=base_ccy,
                quote_ccy="USDT",
                tick_size=Decimal("0.01"),
                lot_size=Decimal("1") if is_swap else Decimal("0.01"),
                min_size=Decimal("1") if is_swap else Decimal("0.01"),
                state="live",
                ct_val=ct_val,
                ct_mult=Decimal("1"),
                max_lever=Decimal("100"),
                ct_type="linear",
                settle_ccy="USDT",
            )
        )

        # Ticker
        ask_px = Decimal(str(round(base_px * 1.0005, 4)))
        bid_px = Decimal(str(round(base_px * 0.9995, 4)))
        tickers.append(
            SpotTicker24h(
                inst_id=sym,
                last=Decimal(str(round(base_px, 4))),
                bid_px=bid_px,
                bid_sz=Decimal("100.00"),
                ask_px=ask_px,
                ask_sz=Decimal("100.00"),
                open_24h=Decimal(str(round(base_px * 0.98, 4))),
                high_24h=Decimal(str(round(base_px * 1.02, 4))),
                low_24h=Decimal(str(round(base_px * 0.97, 4))),
                vol_base_24h=Decimal("10000.00"),
                vol_quote_24h=Decimal("5000000.00"),
                ts_utc_ms=now_ms,
            )
        )

        # Candles (60 closed bars with natural oscillation for healthy RSI and causal EMA)
        sym_candles: list[ClosedCandle] = []
        bar_count = 60
        # Align to latest closed 15m candle boundary (Anti-Lookahead & Bar-Close Confirmation)
        last_closed_c_time = (now_ms // tf_15m_ms) * tf_15m_ms
        start_time = last_closed_c_time - bar_count * tf_15m_ms
        for i in range(bar_count):
            o_time = start_time + i * tf_15m_ms
            c_time = o_time + tf_15m_ms
            drift = 0.0003 * i
            cycle = 0.006 * math.sin(i)
            p = base_px * (1.0 + drift + cycle)
            vol = 1000.0

            # If anomaly trigger is requested on the last bar
            if trigger_anomaly_on and (sym == trigger_anomaly_on or sym.startswith(trigger_anomaly_on.split("-")[0])) and i == bar_count - 1:
                p = base_px * (1.0 + drift) * 1.018  # Breakout jump
                vol = 6000.0  # Volume spike (RVOL=6.0)

            c_open = p * 0.998
            c_high = p * 1.005
            c_low = p * 0.995
            c_close = p

            sym_candles.append(
                ClosedCandle(
                    inst_id=sym,
                    timeframe="15m",
                    candle_open_time=o_time,
                    candle_close_time=c_time,
                    open=Decimal(str(round(c_open, 4))),
                    high=Decimal(str(round(c_high, 4))),
                    low=Decimal(str(round(c_low, 4))),
                    close=Decimal(str(round(c_close, 4))),
                    vol_base=Decimal(str(round(vol, 2))),
                    vol_quote=Decimal(str(round(vol * c_close, 2))),
                    confirm=True,
                )
            )
        candles_by_symbol[sym] = sym_candles

        # Orderbook
        orderbooks[sym] = OrderBookLiquiditySnapshot(
            inst_id=sym,
            ts_utc_ms=now_ms,
            best_bid=bid_px,
            best_ask=ask_px,
            mid_price=(bid_px + ask_px) / 2,
            spread_bps=Decimal("10.00"),
            depth_levels=20,
            bid_depth_usdt=Decimal("80000.00"),
            ask_depth_usdt=Decimal("80000.00"),
            imbalance_ratio=Decimal("0.25"),
            probe_notional_usdt=Decimal("10.00"),
            est_buy_slippage_bps=Decimal("3.5"),
            est_sell_slippage_bps=Decimal("3.5"),
            buy_fully_filled=True,
            sell_fully_filled=True,
        )

    return rules, tickers, candles_by_symbol, orderbooks


class StatelessCycleRunner:
    """One-shot orchestrator executing Phases P1 -> P6 and persisting P7 snapshots."""

    def __init__(
        self,
        state_dir: Path | str,
        symbols: Sequence[str] = DEFAULT_SYMBOLS,
        risk_config: RiskConfig | None = None,
        engine_config: EngineConfig | None = None,
        paper_config: PaperTradingConfig | None = None,
    ) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_mgr = StateManager(self.state_dir)
        self.symbols = tuple(symbols)
        self.risk_controller = ImmutableRiskController(risk_config)
        self.verification_gate = VerificationGate()
        self.crucible_engine = CrucibleEngine()
        self.engine_config = engine_config or EngineConfig()
        self.paper_config = paper_config or PaperTradingConfig()

    def run_cycle(
        self,
        now_ms: int | None = None,
        dry_run: bool = True,
        trigger_anomaly_on: str | None = "SOL-USDT",
    ) -> CycleRunResult:
        t0 = int(time.time() * 1000)
        current_time = now_ms if now_ms is not None else t0
        run_id = f"run:cycle:{current_time}"
        error_summary: str | None = None
        orders_executed = 0
        orders_rejected = 0
        focus_sessions_count = 0

        try:
            # 1. Load or Initialize PaperPortfolio
            portfolio = PaperPortfolio(initial_balance_usdt=self.paper_config.initial_balance)
            prior_portfolio_doc = self.state_mgr.load_doc("paper_portfolio")
            if prior_portfolio_doc:
                # Restore cash, realized pnl, fees
                portfolio.cash_balance_usdt = Decimal(str(prior_portfolio_doc.get("cash_balance_usdt", "10.00")))
                portfolio.cumulative_realized_pnl_usdt = Decimal(
                    str(prior_portfolio_doc.get("cumulative_realized_pnl_usdt", "0.00"))
                )
                portfolio.total_fees_paid_usdt = Decimal(str(prior_portfolio_doc.get("total_fees_paid_usdt", "0.00")))
                portfolio.total_schedule_drift_cost_usdt = Decimal(
                    str(prior_portfolio_doc.get("total_schedule_drift_cost_usdt", "0.00"))
                )
                portfolio.total_funding_fees_usdt = Decimal(
                    str(prior_portfolio_doc.get("total_funding_fees_usdt", "0.00"))
                )
                for pos_raw in prior_portfolio_doc.get("open_positions", []):
                    pos = OpenPosition(
                        position_id=str(pos_raw["position_id"]),
                        inst_id=str(pos_raw["inst_id"]),
                        entry_order_id=str(pos_raw["entry_order_id"]),
                        entry_price=Decimal(str(pos_raw["entry_price"])),
                        qty_base=Decimal(str(pos_raw["qty_base"])),
                        notional_entry_usdt=Decimal(str(pos_raw["notional_entry_usdt"])),
                        entry_fee_usdt=Decimal(str(pos_raw["entry_fee_usdt"])),
                        candle_close_time=int(pos_raw["candle_close_time"]),
                        signal_timestamp=int(pos_raw["signal_timestamp"]),
                        execution_timestamp=int(pos_raw["execution_timestamp"]),
                        schedule_drift_ms=int(pos_raw["schedule_drift_ms"]),
                        schedule_drift_bps=Decimal(str(pos_raw["schedule_drift_bps"])),
                        schedule_drift_cost_usdt=Decimal(str(pos_raw["schedule_drift_cost_usdt"])),
                        current_mark_price=Decimal(str(pos_raw["current_mark_price"])),
                        unrealized_pnl_usdt=Decimal(str(pos_raw["unrealized_pnl_usdt"])),
                        side=str(pos_raw.get("side", "LONG")),
                        leverage=Decimal(str(pos_raw.get("leverage", "3"))),
                        isolated_margin_usdt=Decimal(str(pos_raw.get("isolated_margin_usdt", "0"))),
                        contracts=Decimal(str(pos_raw.get("contracts", "0"))),
                        ct_val=Decimal(str(pos_raw.get("ct_val", "1"))),
                        liquidation_price=Decimal(str(pos_raw.get("liquidation_price", "0"))),
                        stop_loss_price=Decimal(str(pos_raw.get("stop_loss_price", "0"))),
                        take_profit_price=Decimal(str(pos_raw.get("take_profit_price", "0"))),
                        accumulated_funding_usdt=Decimal(str(pos_raw.get("accumulated_funding_usdt", "0"))),
                    )
                    portfolio._open_positions[pos.inst_id] = pos

            # 2. P1 — Data Layer Ingestion
            if dry_run:
                rules, tickers, candles_by_symbol, orderbooks = generate_mock_market_data(
                    self.symbols,
                    now_ms=current_time,
                    trigger_anomaly_on=trigger_anomaly_on,
                )
            else:
                # Real OKX public client execution (or fallback)
                from src.vibetrade.data.okx_public_client import OKXPublicClient

                client = OKXPublicClient()
                rules = list(client.get_instruments())
                tickers_res = client.get_tickers("SWAP")
                tickers = list(tickers_res.tickers)
                candles_by_symbol = {}
                orderbooks = {}
                for sym in self.symbols:
                    try:
                        c_list = client.get_closed_candles(sym, bar="15m", limit=35)
                        candles_by_symbol[sym] = list(c_list)
                        bk = client.get_orderbook_snapshot(sym, depth=20, probe_notional_usdt=Decimal("10.00"))
                        orderbooks[sym] = bk
                    except Exception:
                        pass

            # Build market_snapshot document
            all_candles = [c for c_list in candles_by_symbol.values() for c in c_list]
            market_snapshot_doc = build_market_snapshot(
                generated_at_utc_ms=current_time,
                instruments=rules,
                tickers=tickers,
                candles=all_candles,
                orderbooks=list(orderbooks.values()),
            )

            # 3. P2 — Market Scanner & Regime
            btc_candles = candles_by_symbol.get("BTC-USDT-SWAP", candles_by_symbol.get("BTC-USDT", []))
            regime_snapshot = detect_market_regime(
                btc_candles=btc_candles,
                tickers=tickers,
                now_ms=current_time,
                config=MarketRegimeConfig(),
            )

            scanner_queue_snapshot = scan_market_opportunities(
                candles_by_symbol=candles_by_symbol,
                now_ms=current_time,
                regime_snapshot=regime_snapshot,
                config=ScannerConfig(),
            )

            # 4. Portfolio Maintenance: Update mark prices, funding fee & check Wick Liquidation / SL / TP
            mark_prices = {t.inst_id: t.last for t in tickers}
            portfolio.update_mark_prices(mark_prices)

            # Funding fee accounting: 8-hour intervals (00:00, 08:00, 16:00 UTC)
            is_funding_window = (current_time % (8 * 3600 * 1000)) < (15 * 60 * 1000)
            if is_funding_window:
                for inst_id, pos in list(portfolio.open_positions.items()):
                    if pos.inst_id.endswith("-SWAP") or pos.contracts > 0:
                        portfolio.apply_funding_fee(inst_id, Decimal("0.0001"), current_time)

            # Check exits using latest closed candle High/Low
            for inst_id, pos in list(portfolio.open_positions.items()):
                sym_candles = candles_by_symbol.get(inst_id, [])
                latest_candle = sym_candles[-1] if sym_candles else None

                if latest_candle is not None:
                    c_high = latest_candle.high
                    c_low = latest_candle.low

                    if pos.side in {"SHORT", "SELL"}:
                        if c_high >= pos.liquidation_price:
                            portfolio.close_position(inst_id, pos.liquidation_price, current_time, "LIQUIDATED", self.paper_config.fee_rate)
                        elif c_high >= pos.stop_loss_price:
                            portfolio.close_position(inst_id, pos.stop_loss_price, current_time, "STOP_LOSS", self.paper_config.fee_rate)
                        elif c_low <= pos.take_profit_price:
                            portfolio.close_position(inst_id, pos.take_profit_price, current_time, "TAKE_PROFIT", self.paper_config.fee_rate)
                    else:
                        if c_low <= pos.liquidation_price:
                            portfolio.close_position(inst_id, pos.liquidation_price, current_time, "LIQUIDATED", self.paper_config.fee_rate)
                        elif c_low <= pos.stop_loss_price:
                            portfolio.close_position(inst_id, pos.stop_loss_price, current_time, "STOP_LOSS", self.paper_config.fee_rate)
                        elif c_high >= pos.take_profit_price:
                            portfolio.close_position(inst_id, pos.take_profit_price, current_time, "TAKE_PROFIT", self.paper_config.fee_rate)
                else:
                    mark_px = mark_prices.get(inst_id, pos.current_mark_price)
                    if pos.side in {"SHORT", "SELL"}:
                        pct_return = (pos.entry_price - mark_px) / pos.entry_price * Decimal("100.0")
                    else:
                        pct_return = (mark_px - pos.entry_price) / pos.entry_price * Decimal("100.0")
                    if pct_return >= Decimal("5.0"):
                        portfolio.close_position(inst_id, mark_px, current_time, "TAKE_PROFIT", self.paper_config.fee_rate)
                    elif pct_return <= Decimal("-3.0"):
                        portfolio.close_position(inst_id, mark_px, current_time, "STOP_LOSS", self.paper_config.fee_rate)

            # 5. P3 — Hybrid Event Engine & Idempotency Seeding
            prior_queue_doc = self.state_mgr.load_doc("opportunity_queue")
            history_doc = self.state_mgr.load_doc("research_history") or {
                "schema_version": "1.1",
                "generated_at_utc_ms": current_time,
                "total_reports": 0,
                "reports": [],
            }
            existing_reports: list[dict[str, Any]] = list(history_doc.get("reports", []))

            registry = SignalRegistry()
            if prior_queue_doc:
                for c_dict in prior_queue_doc.get("candidates", []):
                    sig_id = c_dict.get("signal_id")
                    if sig_id:
                        entry = SignalEntry(
                            signal_id=sig_id,
                            inst_id=c_dict["inst_id"],
                            timeframe=c_dict["timeframe"],
                            candle_close_time=int(c_dict["candle_close_time"]),
                            status=c_dict.get("status", "PENDING"),
                            registered_at_ms=int(c_dict.get("detected_at_utc_ms", current_time)),
                            last_updated_ms=current_time,
                        )
                        registry._entries[sig_id] = entry

            for rep in existing_reports:
                sig_id = rep.get("signal_id")
                if sig_id:
                    if registry.has_signal(sig_id):
                        registry.update_status(sig_id, "EVALUATED", now_ms=current_time)
                    else:
                        entry = SignalEntry(
                            signal_id=sig_id,
                            inst_id=rep["inst_id"],
                            timeframe=rep["timeframe"],
                            candle_close_time=int(rep["candle_close_time"]),
                            status="EVALUATED",
                            registered_at_ms=int(rep.get("evaluated_at_utc_ms", current_time)),
                            last_updated_ms=current_time,
                        )
                        registry._entries[sig_id] = entry

            engine_res = process_opportunity_cycle(
                current_queue=scanner_queue_snapshot,
                orderbooks_by_symbol=orderbooks,
                registry=registry,
                now_ms=current_time,
                config=self.engine_config,
            )

            focus_sessions_count = len(engine_res.promoted_candidates)

            # 6. P4 & P5 & P6 — For each IN_FOCUS candidate
            rules_by_sym = {r.inst_id: r for r in rules}

            for cand in engine_res.promoted_candidates:
                sym = cand.inst_id
                c_15m = candles_by_symbol.get(sym, [])
                book = orderbooks.get(sym)

                # P4: Analysts Features & Crucible
                features = extract_analysts_features(
                    candles_15m=c_15m,
                    now_ms=current_time,
                    orderbook=book,
                )
                report = self.crucible_engine.evaluate_candidate(
                    features=features,
                    regime_snapshot=regime_snapshot,
                    now_ms=current_time,
                )

                # P5: Verification Gate
                receipt = self.verification_gate.verify_report(
                    report=report,
                    candles=c_15m,
                    orderbook=book,
                    audit_utc_ms=current_time,
                )

                # Append to research history
                existing_reports.append(report.to_dict())

                # P6: Immutable Risk Controller & Execution
                if book is not None and sym in rules_by_sym:
                    rule = rules_by_sym[sym]
                    proposed_notional = Decimal("2.00")  # micro-order allocation ($2 on $10 portfolio)

                    risk_decision = self.risk_controller.evaluate_entry(
                        report=report,
                        receipt=receipt,
                        proposed_notional=proposed_notional,
                        current_open_positions_count=len(portfolio.open_positions),
                        current_drawdown_pct=portfolio.current_drawdown_pct,
                        orderbook=book,
                    )

                    order_side = "SHORT" if report.verdict == "ACTIONABLE_SHORT" else "LONG"

                    if risk_decision.approved:
                        exec_res = simulate_order_execution(
                            inst_rule=rule,
                            orderbook=book,
                            signal_id=cand.signal_id,
                            proposed_notional_usdt=proposed_notional,
                            candle_close_time=cand.candle_close_time,
                            signal_timestamp=cand.detected_at_utc_ms,
                            execution_timestamp=current_time,
                            available_cash_usdt=portfolio.cash_balance_usdt,
                            price_at_candle_close=Decimal(str(c_15m[-1].close if c_15m else book.mid_price)),
                            mode=ExecutionMode.LIVE_PAPER,
                            config=self.paper_config,
                            side=order_side,
                            leverage=self.risk_controller.config.max_leverage,
                        )
                        if exec_res.success and exec_res.position:
                            portfolio.open_position(exec_res)
                            orders_executed += 1
                        elif exec_res.rejected_record:
                            portfolio.record_rejected_order(exec_res.rejected_record)
                            orders_rejected += 1
                    else:
                        # Rejected by Risk Controller
                        rej = RejectedOrderRecord(
                            order_id=f"ord:{cand.signal_id}:{current_time}",
                            signal_id=cand.signal_id,
                            inst_id=sym,
                            side=order_side,
                            proposed_notional_usdt=proposed_notional,
                            constraint_code=risk_decision.constraint_code or "RISK_REJECTED",
                            details=risk_decision.details,
                            timestamp_ms=current_time,
                        )
                        portfolio.record_rejected_order(rej)
                        orders_rejected += 1

            # Mark promoted candidates as EVALUATED in registry & update opportunity queue doc
            promoted_ids = {c.signal_id for c in engine_res.promoted_candidates}
            for sid in promoted_ids:
                if registry.has_signal(sid):
                    registry.update_status(sid, "EVALUATED", now_ms=current_time)

            updated_candidates: list[OpportunityCandidate] = []
            for c in engine_res.updated_queue.candidates:
                if c.signal_id in promoted_ids:
                    updated_candidates.append(
                        OpportunityCandidate(
                            signal_id=c.signal_id,
                            inst_id=c.inst_id,
                            timeframe=c.timeframe,
                            candle_close_time=c.candle_close_time,
                            status="EVALUATED",
                            anomaly_types=c.anomaly_types,
                            scanner_score=c.scanner_score,
                            metrics=c.metrics,
                            detected_at_utc_ms=c.detected_at_utc_ms,
                            regime=c.regime,
                        )
                    )
                else:
                    updated_candidates.append(c)

            queue_snapshot = OpportunityQueueSnapshot(
                schema_version=engine_res.updated_queue.schema_version,
                generated_at_utc_ms=engine_res.updated_queue.generated_at_utc_ms,
                market_regime=engine_res.updated_queue.market_regime,
                candidates=tuple(updated_candidates),
            )
            queue_doc = queue_snapshot.to_dict()

            # Prepare final documents
            portfolio_doc = portfolio.snapshot(now_ms=current_time).to_dict()
            history_doc["generated_at_utc_ms"] = current_time
            history_doc["reports"] = existing_reports
            history_doc["total_reports"] = len(existing_reports)

            # Persist all 5 documents atomically via StateManager
            t_finish = int(time.time() * 1000)
            duration = max(0, t_finish - t0)

            def heartbeat_builder(state_changed: bool, hashes: dict[str, str]) -> dict[str, Any]:
                hb = HeartbeatSnapshot(
                    schema_version="1.1",
                    run_id=run_id,
                    cycle_started_at_utc_ms=current_time,
                    cycle_finished_at_utc_ms=t_finish,
                    duration_ms=duration,
                    schedule_drift_ms=0,
                    status="HEALTHY",
                    okx_api_status="MOCK" if dry_run else "OK",
                    scanned_symbols_count=len(self.symbols),
                    focus_sessions_triggered=focus_sessions_count,
                    orders_executed_count=orders_executed,
                    orders_rejected_count=orders_rejected,
                    state_changed=state_changed,
                    snapshot_hashes=hashes,
                    error_summary=None,
                )
                return hb.to_dict()

            state_changed, hashes = self.state_mgr.save_cycle_state(
                market_snapshot=market_snapshot_doc,
                opportunity_queue=queue_doc,
                paper_portfolio=portfolio_doc,
                research_history=history_doc,
                heartbeat_builder_fn=heartbeat_builder,
            )

            return CycleRunResult(
                run_id=run_id,
                status="HEALTHY",
                duration_ms=duration,
                scanned_symbols_count=len(self.symbols),
                focus_sessions_count=focus_sessions_count,
                orders_executed_count=orders_executed,
                orders_rejected_count=orders_rejected,
                state_changed=state_changed,
                snapshot_hashes=hashes,
                error_summary=None,
            )

        except Exception as exc:
            t_finish = int(time.time() * 1000)
            duration = max(0, t_finish - t0)
            err_msg = str(exc)
            return CycleRunResult(
                run_id=run_id,
                status="ERROR",
                duration_ms=duration,
                scanned_symbols_count=0,
                focus_sessions_count=0,
                orders_executed_count=0,
                orders_rejected_count=0,
                state_changed=False,
                snapshot_hashes={},
                error_summary=err_msg,
            )
