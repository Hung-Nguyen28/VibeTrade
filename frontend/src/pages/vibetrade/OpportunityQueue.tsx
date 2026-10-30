import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUtcTime, safeNumber } from "@/lib/staticData";
import { Layers, Sparkles, Compass, Clock } from "lucide-react";

export function OpportunityQueue() {
  const { opportunityQueue } = useSnapshotStore();

  const candidates = opportunityQueue?.candidates || [];
  const regime = opportunityQueue?.market_regime;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Opportunity Queue
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Idempotent Signals · Multi-factor Anomaly Triggers · Candidate Lifecycle
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5 text-primary" />
          <span>Queue Size: {candidates.length}</span>
        </div>
      </div>

      {/* Market Regime Context Banner */}
      {regime && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Compass className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-foreground font-mono">
                  Regime: {regime.regime}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-500/20 text-sky-300 font-semibold">
                  Multiplier: {regime.multiplier}x
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Market Breadth: {regime.market_breadth_pct}% · BTC Price: ${safeNumber(regime.btc_price).toLocaleString()} · BTC RSI(14): {regime.btc_rsi}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono tabular-nums text-muted-foreground">
            <div>
              BTC ATR%: <strong className="text-foreground">{regime.btc_atr_pct}%</strong>
            </div>
            <div>
              EMA Trend:{" "}
              <strong className={regime.details?.is_ema_bull ? "text-emerald-400" : "text-rose-400"}>
                {regime.details?.is_ema_bull ? "BULLISH" : "BEARISH"}
              </strong>
            </div>
          </div>
        </div>
      )}

      {/* Candidates List */}
      {candidates.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-card p-12 text-center text-xs text-muted-foreground space-y-2">
          <Layers className="h-8 w-8 mx-auto text-muted-foreground/40" />
          <p className="text-sm font-semibold text-foreground">No Candidates in Queue</p>
          <p>
            The scanner evaluates all USDT Spot pairs on every 15-minute candle close.
            When breakout or volume anomalies occur, signals are queued here idempotently.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {candidates.map((candidate) => {
            const statusColor =
              candidate.status === "EVALUATED"
                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                : candidate.status === "IN_FOCUS"
                ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                : candidate.status === "EXPIRED"
                ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                : "bg-slate-500/15 text-slate-400 border-slate-500/30";

            return (
              <div
                key={candidate.signal_id}
                className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm hover:border-border transition-colors"
              >
                {/* Top Row: Symbol, Status, Scanner Score */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-bold font-mono text-foreground">
                      {candidate.inst_id}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-mono bg-muted text-muted-foreground">
                      {candidate.timeframe}
                    </span>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold border ${statusColor}`}
                    >
                      {candidate.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono text-xs">
                    <span className="text-muted-foreground">Scanner Score:</span>
                    <span className="text-base font-bold text-emerald-400 tabular-nums">
                      {candidate.scanner_score}
                    </span>
                  </div>
                </div>

                {/* Idempotent signal_id & Timestamps */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono bg-background/60 p-3 rounded-lg border border-border/40">
                  <div className="truncate">
                    <span className="text-muted-foreground">signal_id: </span>
                    <span className="text-foreground font-semibold">{candidate.signal_id}</span>
                  </div>
                  <div className="flex items-center gap-4 text-muted-foreground">
                    <span>
                      Candle Close:{" "}
                      <strong className="text-foreground">
                        {formatUtcTime(candidate.candle_close_time)}
                      </strong>
                    </span>
                    <span>
                      Detected:{" "}
                      <strong className="text-foreground">
                        {formatUtcTime(candidate.detected_at_utc_ms)}
                      </strong>
                    </span>
                  </div>
                </div>

                {/* Anomaly Badges */}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground font-mono">
                    Triggered Anomalies:
                  </span>
                  {candidate.anomaly_types.map((anom) => (
                    <span
                      key={anom}
                      className="px-2 py-0.5 rounded text-xs font-mono bg-primary/15 text-primary border border-primary/30 flex items-center gap-1"
                    >
                      <Sparkles className="h-3 w-3" />
                      {anom}
                    </span>
                  ))}
                </div>

                {/* Quantitative Metric Breakdown Table */}
                <div className="border-t border-border/40 pt-3">
                  <div className="text-[11px] font-mono text-muted-foreground mb-2">
                    Observed Quantitative Indicators:
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 font-mono text-xs tabular-nums">
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">PRICE</div>
                      <div className="font-semibold text-foreground">
                        ${candidate.metrics?.price || "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">RVOL (20)</div>
                      <div className="font-semibold text-emerald-400">
                        {candidate.metrics?.rvol ? `${candidate.metrics.rvol}x` : "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">RSI (14)</div>
                      <div className="font-semibold text-foreground">
                        {candidate.metrics?.rsi || "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">ATR</div>
                      <div className="font-semibold text-foreground">
                        {candidate.metrics?.atr || "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">BAR RANGE</div>
                      <div className="font-semibold text-foreground">
                        {candidate.metrics?.bar_range || "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">VOL Z-SCORE</div>
                      <div className="font-semibold text-foreground">
                        {candidate.metrics?.volume_zscore || "N/A"}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/30 border border-border/30">
                      <div className="text-[10px] text-muted-foreground">RAW SCORE</div>
                      <div className="font-semibold text-primary">
                        {candidate.metrics?.raw_score || "N/A"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
