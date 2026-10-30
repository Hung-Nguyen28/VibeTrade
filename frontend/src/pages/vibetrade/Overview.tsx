import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUsdt, formatPct, formatUtcTime, safeNumber } from "@/lib/staticData";
import {
  Wallet,
  Coins,
  TrendingUp,
  ShieldCheck,
  Compass,
  Zap,
  Activity,
  ArrowUpRight,
} from "lucide-react";
import { Link } from "react-router";

export function Overview() {
  const { paperPortfolio, opportunityQueue, heartbeat, researchHistory } =
    useSnapshotStore();

  const totalEquity = safeNumber(paperPortfolio?.total_equity_usdt, 10.0);
  const cashBalance = safeNumber(paperPortfolio?.cash_balance_usdt, 10.0);
  const realizedPnl = safeNumber(paperPortfolio?.cumulative_realized_pnl_usdt, 0.0);
  const unrealizedPnl = safeNumber(paperPortfolio?.total_unrealized_pnl_usdt, 0.0);
  const totalReturnPct = ((totalEquity - 10.0) / 10.0) * 100;

  const regime = opportunityQueue?.market_regime;
  const candidates = opportunityQueue?.candidates || [];
  const openPositions = paperPortfolio?.open_positions || [];
  const latestReport = researchHistory?.reports?.[0];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Title & Quick Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Overview</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Personal Autonomous Crypto Intelligence System · $10 Micro Portfolio
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <Activity className="h-3.5 w-3.5 text-primary" />
          <span>Last Cycle: {formatUtcTime(heartbeat?.cycle_finished_at_utc_ms)}</span>
        </div>
      </div>

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Equity */}
        <div className="rounded-xl border border-border/60 bg-card p-4 shadow-sm hover:border-border transition-colors">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Total Equity</span>
            <Wallet className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono tracking-tight tabular-nums">
              {formatUsdt(totalEquity, 4)}
            </span>
            <span
              className={`text-xs font-mono font-medium ${
                totalReturnPct >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {formatPct(totalReturnPct, 2)}
            </span>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground flex items-center justify-between border-t border-border/40 pt-2 font-mono tabular-nums">
            <span>Initial: $10.0000</span>
            <span>Cash: {formatUsdt(cashBalance, 2)}</span>
          </div>
        </div>

        {/* Card 2: PnL Breakdown */}
        <div className="rounded-xl border border-border/60 bg-card p-4 shadow-sm hover:border-border transition-colors">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>PnL Breakdown (Separated)</span>
            <Coins className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Realized PnL:</span>
              <span
                className={`font-mono font-semibold tabular-nums ${
                  realizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {formatUsdt(realizedPnl, 4)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Unrealized PnL:</span>
              <span
                className={`font-mono font-semibold tabular-nums ${
                  unrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {formatUsdt(unrealizedPnl, 4)}
              </span>
            </div>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground flex items-center justify-between border-t border-border/40 pt-2 font-mono tabular-nums">
            <span>Fees Paid: {formatUsdt(paperPortfolio?.total_fees_paid_usdt, 4)}</span>
          </div>
        </div>

        {/* Card 3: Market Regime */}
        <div className="rounded-xl border border-border/60 bg-card p-4 shadow-sm hover:border-border transition-colors">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Market Regime</span>
            <Compass className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold bg-sky-500/15 text-sky-400 border border-sky-500/30 font-mono">
              {regime?.regime || "UNKNOWN"}
            </span>
            <span className="text-xs font-mono text-muted-foreground">
              M={regime?.multiplier || "1.00"}x
            </span>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground flex items-center justify-between border-t border-border/40 pt-2 font-mono tabular-nums">
            <span>BTC: ${safeNumber(regime?.btc_price).toLocaleString()}</span>
            <span>Breadth: {regime?.market_breadth_pct || "0.00"}%</span>
          </div>
        </div>

        {/* Card 4: System Heartbeat */}
        <div className="rounded-xl border border-border/60 bg-card p-4 shadow-sm hover:border-border transition-colors">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>System Health</span>
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-lg font-bold font-mono text-emerald-400">
              {heartbeat?.status || "HEALTHY"}
            </span>
            <span className="text-xs text-muted-foreground font-mono">
              ({heartbeat?.okx_api_status || "OKX PUBLIC"})
            </span>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground flex items-center justify-between border-t border-border/40 pt-2 font-mono tabular-nums">
            <span>Duration: {heartbeat?.duration_ms ?? 0}ms</span>
            <span>Drift: {heartbeat?.schedule_drift_ms ?? 0}ms</span>
          </div>
        </div>
      </div>

      {/* Main Overview Grid: Open Positions & Top Opportunities */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Open Positions Card */}
        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-amber-400" />
              <h2 className="text-sm font-semibold tracking-tight">Active Micro Positions</h2>
            </div>
            <Link
              to="/portfolio"
              className="text-xs text-primary hover:underline flex items-center gap-0.5"
            >
              View Full Portfolio <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          {openPositions.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground border border-dashed border-border/60 rounded-lg">
              No active positions in the $10 paper account.
            </div>
          ) : (
            <div className="space-y-3">
              {openPositions.map((pos) => {
                const uPnl = safeNumber(pos.unrealized_pnl_usdt);
                return (
                  <div
                    key={pos.position_id}
                    className="p-3.5 rounded-lg border border-border/50 bg-background/50 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-sm text-foreground">{pos.inst_id}</span>
                      <span
                        className={`font-semibold tabular-nums ${
                          uPnl >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {formatUsdt(uPnl, 4)} ({pos.unrealized_pnl_usdt} USDT)
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-muted-foreground font-mono tabular-nums text-[11px]">
                      <div>
                        Qty: <span className="text-foreground">{pos.qty_base}</span>
                      </div>
                      <div>
                        Entry: <span className="text-foreground">${pos.entry_price}</span>
                      </div>
                      <div>
                        Mark: <span className="text-foreground">${pos.current_mark_price}</span>
                      </div>
                      <div>
                        Notional: <span className="text-foreground">${pos.notional_entry_usdt}</span>
                      </div>
                      <div>
                        Fee: <span className="text-foreground">${pos.entry_fee_usdt}</span>
                      </div>
                      <div>
                        Drift Cost:{" "}
                        <span className="text-rose-400">{pos.schedule_drift_cost_usdt}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Top Candidate Opportunities */}
        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-400" />
              <h2 className="text-sm font-semibold tracking-tight">Active Opportunities</h2>
            </div>
            <Link
              to="/queue"
              className="text-xs text-primary hover:underline flex items-center gap-0.5"
            >
              View Queue <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          {candidates.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground border border-dashed border-border/60 rounded-lg">
              Queue is currently empty. Waiting for next 15-minute scanner cycle.
            </div>
          ) : (
            <div className="space-y-3">
              {candidates.map((c) => (
                <div
                  key={c.signal_id}
                  className="p-3.5 rounded-lg border border-border/50 bg-background/50 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between font-mono">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-foreground">{c.inst_id}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                        {c.timeframe}
                      </span>
                    </div>
                    <span className="font-semibold text-emerald-400 tabular-nums">
                      Score: {c.scanner_score}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {c.anomaly_types.map((anom) => (
                      <span
                        key={anom}
                        className="px-2 py-0.5 rounded text-[10px] font-mono bg-primary/10 text-primary border border-primary/20"
                      >
                        {anom}
                      </span>
                    ))}
                    <span className="ms-auto text-[10px] font-mono text-muted-foreground">
                      Status: <strong className="text-foreground">{c.status}</strong>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Latest Research Verdict Card */}
      {latestReport && (
        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-tight">
              Latest AI Research Verdict ({latestReport.inst_id} - {latestReport.timeframe})
            </h2>
            <Link
              to="/research"
              className="text-xs text-primary hover:underline flex items-center gap-0.5"
            >
              View Research Room <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="p-3.5 rounded-lg border border-border/50 bg-background/50 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span
                className={`px-2.5 py-1 rounded-md text-xs font-mono font-bold ${
                  latestReport.verdict === "ACTIONABLE_LONG"
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-slate-500/20 text-slate-400 border border-slate-500/30"
                }`}
              >
                {latestReport.verdict}
              </span>
              <div className="flex items-center gap-3 font-mono text-xs tabular-nums">
                <span>
                  Bull: <strong className="text-emerald-400">{latestReport.score_bull}</strong>
                </span>
                <span>
                  Bear: <strong className="text-rose-400">{latestReport.score_bear}</strong>
                </span>
                <span>
                  Net S_net: <strong className="text-primary">{latestReport.score_net}</strong>
                </span>
              </div>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed">
              {latestReport.template_summary}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
