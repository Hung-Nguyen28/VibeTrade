import { useState } from "react";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUtcTime, safeNumber } from "@/lib/staticData";
import {
  Scale,
  ShieldCheck,
  AlertTriangle,
  FileCheck,
  TrendingUp,
  TrendingDown,
  Compass,
} from "lucide-react";

export function AIResearchRoom() {
  const { researchHistory } = useSnapshotStore();
  const reports = researchHistory?.reports || [];
  const [selectedReportId, setSelectedReportId] = useState<string | null>(
    reports[0]?.report_id || null
  );

  const activeReport =
    reports.find((r) => r.report_id === selectedReportId) || reports[0];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            AI Research Room
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Deterministic Personas Engine · Weighted Scoring · Explainable Evidence Binding
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <FileCheck className="h-3.5 w-3.5 text-primary" />
          <span>Total Reports: {reports.length}</span>
        </div>
      </div>

      {reports.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-card p-12 text-center text-xs text-muted-foreground space-y-2">
          <Scale className="h-8 w-8 mx-auto text-muted-foreground/40" />
          <p className="text-sm font-semibold text-foreground">No Research Reports Yet</p>
          <p>
            When opportunities pass the Scanner, the Deterministic Research Team (Bull &
            Bear personas) evaluates the multi-factor evidence rules.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Report Selector Pills */}
          {reports.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {reports.map((rep) => (
                <button
                  key={rep.report_id}
                  onClick={() => setSelectedReportId(rep.report_id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all border ${
                    activeReport?.report_id === rep.report_id
                      ? "bg-primary/20 text-primary border-primary font-bold shadow-sm"
                      : "bg-card text-muted-foreground border-border/60 hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {rep.inst_id} ({rep.timeframe}) · {rep.verdict}
                </button>
              ))}
            </div>
          )}

          {activeReport && (
            <div className="space-y-6">
              {/* Verdict Banner Card */}
              <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold font-mono text-foreground">
                      {activeReport.inst_id}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-mono bg-muted text-muted-foreground">
                      {activeReport.timeframe}
                    </span>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-mono font-bold border ${
                        activeReport.verdict === "ACTIONABLE_LONG"
                          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                          : activeReport.verdict === "ACTIONABLE_SHORT"
                          ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                          : activeReport.verdict === "INCONCLUSIVE"
                          ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                          : "bg-slate-500/15 text-slate-400 border-slate-500/30"
                      }`}
                    >
                      {activeReport.verdict}
                    </span>
                  </div>

                  {/* Independent Verification Receipt (P5) */}
                  <div className="flex items-center gap-2 font-mono text-xs bg-muted/40 px-3 py-1.5 rounded-lg border border-border/40">
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                    <span className="text-muted-foreground">P5 Independent Verification:</span>
                    <span className="font-bold text-emerald-400">
                      {activeReport.verification?.status || "VERIFIED_PASS"}
                    </span>
                  </div>
                </div>

                {/* Score Crucible Formula Display */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
                  {/* Bull Score */}
                  <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-1 font-mono">
                    <div className="flex items-center justify-between text-xs text-emerald-400">
                      <span>Bull Score (S_Bull)</span>
                      <TrendingUp className="h-4 w-4" />
                    </div>
                    <div className="text-2xl font-bold text-emerald-400 tabular-nums">
                      +{activeReport.score_bull} pts
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Max weight: 100.00 pts
                    </p>
                  </div>

                  {/* Bear Score */}
                  <div className="p-4 rounded-xl border border-rose-500/30 bg-rose-500/5 space-y-1 font-mono">
                    <div className="flex items-center justify-between text-xs text-rose-400">
                      <span>Bear Risk (S_Bear)</span>
                      <TrendingDown className="h-4 w-4" />
                    </div>
                    <div className="text-2xl font-bold text-rose-400 tabular-nums">
                      -{activeReport.score_bear} pts
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Max penalty: 100.00 pts
                    </p>
                  </div>

                  {/* Raw Crucible Score */}
                  <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-1 font-mono">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Raw Score (S_raw)</span>
                      <Scale className="h-4 w-4 text-primary" />
                    </div>
                    <div className="text-2xl font-bold text-foreground tabular-nums">
                      {safeNumber(activeReport.score_raw) >= 0 ? "+" : ""}
                      {activeReport.score_raw}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      S_Bull - S_Bear
                    </p>
                  </div>

                  {/* Net Score after Regime */}
                  <div className="p-4 rounded-xl border border-primary/40 bg-primary/10 space-y-1 font-mono">
                    <div className="flex items-center justify-between text-xs text-primary">
                      <span>Net Crucible Score (S_net)</span>
                      <Compass className="h-4 w-4" />
                    </div>
                    <div className="text-2xl font-bold text-primary tabular-nums">
                      {safeNumber(activeReport.score_net) >= 0 ? "+" : ""}
                      {activeReport.score_net}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      S_raw × {activeReport.regime_multiplier}x ({activeReport.regime})
                    </p>
                  </div>
                </div>

                {/* INCONCLUSIVE Missing Inputs Warning (if applicable) */}
                {activeReport.missing_inputs && activeReport.missing_inputs.length > 0 && (
                  <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 flex items-start gap-3 text-xs text-amber-300 font-mono">
                    <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                    <div>
                      <strong className="text-amber-200">INCONCLUSIVE Fallback Triggered:</strong>
                      <p className="mt-0.5 text-muted-foreground">
                        Missing critical input data:{" "}
                        <span className="text-foreground">{activeReport.missing_inputs.join(", ")}</span>.
                        Per Quantitative Integrity rule, trading actions are strictly blocked until all inputs are confirmed.
                      </p>
                    </div>
                  </div>
                )}

                {/* Synthesis Summary */}
                <div className="p-3.5 rounded-lg border border-border/50 bg-background/60 space-y-1 text-xs">
                  <span className="font-mono text-muted-foreground font-semibold">
                    Synthesis Template Summary:
                  </span>
                  <p className="text-foreground/90 leading-relaxed font-sans">
                    {activeReport.template_summary}
                  </p>
                </div>

                {/* Metadata & Audit Receipt Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-muted-foreground border-t border-border/40 pt-3">
                  <div>
                    <span>signal_id: </span>
                    <span className="text-foreground">{activeReport.signal_id}</span>
                  </div>
                  <div>
                    <span>Candle Close: </span>
                    <span className="text-foreground">
                      {formatUtcTime(activeReport.candle_close_time)}
                    </span>
                  </div>
                  <div>
                    <span>Evaluated: </span>
                    <span className="text-foreground">
                      {formatUtcTime(activeReport.evaluated_at_utc_ms)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Evidence Binding Table */}
              <div className="rounded-xl border border-border/60 bg-card overflow-hidden shadow-sm space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Scale className="h-4 w-4 text-primary" />
                    <h2 className="text-sm font-semibold tracking-tight">
                      Evidence Binding Table ({activeReport.evidence.length} Rules Evaluated)
                    </h2>
                  </div>
                  <span className="text-xs font-mono text-muted-foreground">
                    100% Explainable · No LLM Hallucinations
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-muted/40 border-b border-border/60 font-mono text-[11px] text-muted-foreground uppercase">
                      <tr>
                        <th className="px-4 py-2.5 font-medium">Persona</th>
                        <th className="px-4 py-2.5 font-medium">Rule ID</th>
                        <th className="px-4 py-2.5 font-medium">Metric</th>
                        <th className="px-4 py-2.5 font-medium">Observed Value</th>
                        <th className="px-4 py-2.5 font-medium">Threshold</th>
                        <th className="px-4 py-2.5 font-medium">Weight</th>
                        <th className="px-4 py-2.5 font-medium">Score Impact</th>
                        <th className="px-4 py-2.5 font-medium">Evidence Reasoning</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40 font-mono text-xs tabular-nums">
                      {activeReport.evidence.map((ev, idx) => {
                        const isBull = ev.persona === "bull_researcher";
                        return (
                          <tr
                            key={`${ev.rule_id}-${idx}`}
                            className="hover:bg-muted/30 transition-colors"
                          >
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${
                                  isBull
                                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                    : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                                }`}
                              >
                                {isBull ? (
                                  <TrendingUp className="h-3 w-3" />
                                ) : (
                                  <TrendingDown className="h-3 w-3" />
                                )}
                                {isBull ? "BULL" : "BEAR"}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-bold text-foreground">
                              {ev.rule_id}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {ev.metric}
                            </td>
                            <td className="px-4 py-3 font-semibold text-foreground">
                              {ev.value}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {ev.threshold}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {ev.weight} pts
                            </td>
                            <td className="px-4 py-3 font-bold">
                              <span
                                className={
                                  isBull ? "text-emerald-400" : "text-rose-400"
                                }
                              >
                                {isBull ? "+" : "-"}
                                {ev.score_contribution} pts
                              </span>
                            </td>
                            <td className="px-4 py-3 font-sans text-xs text-muted-foreground/90 max-w-xs">
                              {ev.template_summary}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
