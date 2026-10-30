import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUsdt, formatUtcTime, safeNumber } from "@/lib/staticData";
import {
  WalletCards,
  Coins,
  History,
  ShieldAlert,
} from "lucide-react";

export function PaperPortfolio() {
  const { paperPortfolio } = useSnapshotStore();

  const totalEquity = safeNumber(paperPortfolio?.total_equity_usdt, 10.0);
  const cashBalance = safeNumber(paperPortfolio?.cash_balance_usdt, 10.0);
  const realizedPnl = safeNumber(paperPortfolio?.cumulative_realized_pnl_usdt, 0.0);
  const unrealizedPnl = safeNumber(paperPortfolio?.total_unrealized_pnl_usdt, 0.0);
  const feesPaid = safeNumber(paperPortfolio?.total_fees_paid_usdt, 0.0);
  const fundingFees = safeNumber(paperPortfolio?.total_funding_fees_usdt, 0.0);
  const driftCost = safeNumber(paperPortfolio?.total_schedule_drift_cost_usdt, 0.0);

  const openPositions = paperPortfolio?.open_positions || [];
  const closedTrades = paperPortfolio?.closed_trades || [];
  const rejectedOrders = paperPortfolio?.rejected_orders || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Paper Portfolio — OKX Futures Edition ($10 Account)
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Isolated Margin · 3x Leverage · Liquidation Wick Gate · Funding Fee Accounting · 3 Timestamps Integrity
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <WalletCards className="h-3.5 w-3.5 text-primary" />
          <span>Capital: $10.00 USDT (Isolated 3x)</span>
        </div>
      </div>

      {/* Account Balances Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 font-mono text-xs">
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Total Equity</span>
          <p className="text-lg font-bold text-foreground mt-1 tabular-nums">
            {formatUsdt(totalEquity, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Cash Balance</span>
          <p className="text-lg font-bold text-foreground mt-1 tabular-nums">
            {formatUsdt(cashBalance, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Realized PnL</span>
          <p
            className={`text-lg font-bold mt-1 tabular-nums ${
              realizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {formatUsdt(realizedPnl, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Unrealized PnL</span>
          <p
            className={`text-lg font-bold mt-1 tabular-nums ${
              unrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {formatUsdt(unrealizedPnl, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Taker Fees (0.05%)</span>
          <p className="text-lg font-bold text-foreground mt-1 tabular-nums">
            {formatUsdt(feesPaid, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Funding Fees</span>
          <p
            className={`text-lg font-bold mt-1 tabular-nums ${
              fundingFees >= 0 ? "text-foreground" : "text-rose-400"
            }`}
          >
            {formatUsdt(fundingFees, 4)}
          </p>
        </div>
        <div className="p-3.5 rounded-xl border border-border/60 bg-card">
          <span className="text-[11px] text-muted-foreground">Drift Cost (GHA)</span>
          <p className="text-lg font-bold text-rose-400 mt-1 tabular-nums">
            {formatUsdt(driftCost, 4)}
          </p>
        </div>
      </div>

      {/* Open Positions Section */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Coins className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold tracking-tight">
              Open Positions ({openPositions.length})
            </h2>
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            Strict 3-Timestamp Execution Gate
          </span>
        </div>

        {openPositions.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground border border-dashed border-border/60 rounded-lg">
            No active positions open. Capital is 100% in USDT Cash.
          </div>
        ) : (
          <div className="space-y-4">
            {openPositions.map((pos) => {
              const uPnl = safeNumber(pos.unrealized_pnl_usdt);
              return (
                <div
                  key={pos.position_id}
                  className="rounded-lg border border-border/60 bg-background/50 p-4 space-y-3 font-mono text-xs"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/40 pb-2">
                    <div className="flex items-center gap-3">
                      <span className="text-base font-bold text-foreground">{pos.inst_id}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          (pos.side || "LONG") === "LONG"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                            : "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                        }`}
                      >
                        {pos.side || "LONG"} {pos.leverage || "3"}x
                      </span>
                      <span className="text-muted-foreground">Qty: {pos.qty_base}</span>
                      {pos.contracts && (
                        <span className="text-muted-foreground">
                          ({pos.contracts} cts)
                        </span>
                      )}
                      <span className="text-muted-foreground">
                        Notional: ${pos.notional_entry_usdt}
                      </span>
                      {pos.isolated_margin_usdt && (
                        <span className="text-primary/90 font-medium">
                          Margin: ${pos.isolated_margin_usdt}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 tabular-nums">
                      <span className="text-muted-foreground">Unrealized PnL:</span>
                      <span
                        className={`text-sm font-bold ${
                          uPnl >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {formatUsdt(uPnl, 4)}
                      </span>
                    </div>
                  </div>

                  {/* 3-Timestamp Visualizer */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 bg-muted/20 p-2.5 rounded border border-border/30 text-[11px] tabular-nums">
                    <div>
                      <span className="text-muted-foreground">1. Candle Close: </span>
                      <strong className="text-foreground">
                        {formatUtcTime(pos.candle_close_time)}
                      </strong>
                    </div>
                    <div>
                      <span className="text-muted-foreground">2. Signal Generated: </span>
                      <strong className="text-foreground">
                        {formatUtcTime(pos.signal_timestamp)}
                      </strong>
                    </div>
                    <div>
                      <span className="text-muted-foreground">3. Order Executed: </span>
                      <strong className="text-foreground">
                        {formatUtcTime(pos.execution_timestamp)}
                      </strong>
                    </div>
                  </div>

                  {/* Futures Pricing, Liquidation & Fee Decomposition */}
                  <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-muted-foreground text-[11px] tabular-nums pt-1">
                    <div>
                      Entry Price: <span className="text-foreground">${pos.entry_price}</span>
                    </div>
                    <div>
                      Mark Price:{" "}
                      <span className="text-foreground">${pos.current_mark_price}</span>
                    </div>
                    <div>
                      Liq Price:{" "}
                      <span className="text-amber-400 font-bold">
                        {pos.liquidation_price ? `$${pos.liquidation_price}` : "N/A"}
                      </span>
                    </div>
                    <div>
                      SL / TP:{" "}
                      <span className="text-foreground">
                        ${pos.stop_loss_price || "—"} / ${pos.take_profit_price || "—"}
                      </span>
                    </div>
                    <div>
                      Funding:{" "}
                      <span className="text-foreground">
                        ${pos.accumulated_funding_usdt || "0.0000"}
                      </span>
                    </div>
                    <div>
                      Schedule Drift:{" "}
                      <span className="text-rose-400">
                        {pos.schedule_drift_bps} bps (${pos.schedule_drift_cost_usdt})
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Closed Trades History */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold tracking-tight">
              Closed Trades History ({closedTrades.length})
            </h2>
          </div>
        </div>

        {closedTrades.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border/60 rounded-lg">
            No closed trades yet in current history.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/40 border-b border-border/60 font-mono text-[11px] text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-2.5">Trade ID</th>
                  <th className="px-4 py-2.5">Instrument</th>
                  <th className="px-4 py-2.5">Side</th>
                  <th className="px-4 py-2.5">Qty</th>
                  <th className="px-4 py-2.5">Entry Px</th>
                  <th className="px-4 py-2.5">Exit Px</th>
                  <th className="px-4 py-2.5">Realized PnL</th>
                  <th className="px-4 py-2.5">Fees</th>
                  <th className="px-4 py-2.5">Exit Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono text-xs tabular-nums">
                {closedTrades.map((tr) => (
                  <tr key={tr.trade_id} className="hover:bg-muted/30">
                    <td className="px-4 py-2.5 text-muted-foreground">{tr.trade_id}</td>
                    <td className="px-4 py-2.5 font-bold text-foreground">{tr.inst_id}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          (tr.side || "LONG") === "LONG"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-rose-500/20 text-rose-400"
                        }`}
                      >
                        {tr.side || "LONG"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">{tr.qty_base}</td>
                    <td className="px-4 py-2.5">${tr.entry_price}</td>
                    <td className="px-4 py-2.5">${tr.exit_price}</td>
                    <td
                      className={`px-4 py-2.5 font-bold ${
                        safeNumber(tr.realized_pnl_usdt) >= 0
                          ? "text-emerald-400"
                          : "text-rose-400"
                      }`}
                    >
                      {formatUsdt(tr.realized_pnl_usdt, 4)}
                    </td>
                    <td className="px-4 py-2.5">${tr.total_fees_usdt}</td>
                    <td className="px-4 py-2.5">
                      {tr.exit_reason === "LIQUIDATED" ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/30 text-rose-300 border border-rose-500">
                          LIQUIDATED
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{tr.exit_reason || "TAKE_PROFIT"}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Constraint Rejection Audit Log */}
      <div className="rounded-xl border border-amber-500/40 bg-card p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-amber-400" />
            <h2 className="text-sm font-semibold tracking-tight text-foreground">
              Constraint Rejection Log (REJECTED_BY_CONSTRAINT)
            </h2>
          </div>
          <span className="text-xs font-mono text-amber-400/90">
            Transparent Micro-Risk Enforcement
          </span>
        </div>

        {rejectedOrders.length === 0 ? (
          <div className="py-4 text-xs text-muted-foreground text-center">
            No rejected orders. All evaluated positions complied with $10 minSz and spread limits.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-amber-500/10 border-b border-amber-500/30 font-mono text-[11px] text-amber-300 uppercase">
                <tr>
                  <th className="px-4 py-2.5">Order ID</th>
                  <th className="px-4 py-2.5">Instrument</th>
                  <th className="px-4 py-2.5">Rejection Reason</th>
                  <th className="px-4 py-2.5">Timestamp (UTC)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono text-xs tabular-nums">
                {rejectedOrders.map((rej) => (
                  <tr key={rej.order_id} className="hover:bg-amber-500/5">
                    <td className="px-4 py-2.5 text-muted-foreground">{rej.order_id}</td>
                    <td className="px-4 py-2.5 font-bold text-foreground">{rej.inst_id}</td>
                    <td className="px-4 py-2.5 text-amber-400 font-semibold">{rej.reason}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {formatUtcTime(rej.rejected_at_utc_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
