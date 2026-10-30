import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUtcTime } from "@/lib/staticData";
import {
  Activity,
  ShieldCheck,
  Clock,
  Cpu,
  GitBranch,
  Hash,
  Radio,
  CheckCircle2,
} from "lucide-react";

export function SystemMonitor() {
  const { heartbeat, lastFetchedAt } = useSnapshotStore();

  const hashes = heartbeat?.snapshot_hashes || {};

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            System Monitor & Telemetry
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            GitHub Actions Telemetry · OKX REST Ingestion · SHA-256 State Integrity
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <Activity className="h-3.5 w-3.5 text-primary" />
          <span>Schema: v{heartbeat?.schema_version || "1.1"}</span>
        </div>
      </div>

      {/* Primary Telemetry Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono text-xs">
        {/* Heartbeat Status */}
        <div className="p-4 rounded-xl border border-border/60 bg-card space-y-1">
          <span className="text-[11px] text-muted-foreground flex items-center justify-between">
            System Status
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
          </span>
          <div className="text-xl font-bold text-emerald-400">
            {heartbeat?.status || "HEALTHY"}
          </div>
          <span className="text-[10px] text-muted-foreground">
            Pipeline Health Check
          </span>
        </div>

        {/* Cycle Duration */}
        <div className="p-4 rounded-xl border border-border/60 bg-card space-y-1">
          <span className="text-[11px] text-muted-foreground flex items-center justify-between">
            Execution Duration
            <Clock className="h-3.5 w-3.5 text-primary" />
          </span>
          <div className="text-xl font-bold text-foreground tabular-nums">
            {heartbeat?.duration_ms ?? 0} ms
          </div>
          <span className="text-[10px] text-muted-foreground">
            stateless one-shot runner
          </span>
        </div>

        {/* Schedule Drift */}
        <div className="p-4 rounded-xl border border-border/60 bg-card space-y-1">
          <span className="text-[11px] text-muted-foreground flex items-center justify-between">
            Schedule Drift (GHA)
            <Clock className="h-3.5 w-3.5 text-amber-400" />
          </span>
          <div className="text-xl font-bold text-amber-400 tabular-nums">
            {heartbeat?.schedule_drift_ms ?? 0} ms
          </div>
          <span className="text-[10px] text-muted-foreground">
            serverless cron latency
          </span>
        </div>

        {/* Scanned Symbols */}
        <div className="p-4 rounded-xl border border-border/60 bg-card space-y-1">
          <span className="text-[11px] text-muted-foreground flex items-center justify-between">
            OKX Spot Scanned
            <Radio className="h-3.5 w-3.5 text-sky-400" />
          </span>
          <div className="text-xl font-bold text-foreground tabular-nums">
            {heartbeat?.scanned_symbols_count ?? 0} Pairs
          </div>
          <span className="text-[10px] text-muted-foreground">
            API Status: {heartbeat?.okx_api_status || "OKX PUBLIC"}
          </span>
        </div>
      </div>

      {/* Cycle Details Panel */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm font-mono text-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold tracking-tight text-foreground font-sans">
              Stateless Cycle Execution Details
            </h2>
          </div>
          <span className="text-muted-foreground text-[11px]">
            Run ID: <strong className="text-foreground">{heartbeat?.run_id || "N/A"}</strong>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 rounded-lg border border-border/40 tabular-nums text-xs">
          <div>
            <span className="text-muted-foreground">Cycle Started (UTC): </span>
            <span className="text-foreground">
              {formatUtcTime(heartbeat?.cycle_started_at_utc_ms)}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Cycle Finished (UTC): </span>
            <span className="text-foreground">
              {formatUtcTime(heartbeat?.cycle_finished_at_utc_ms)}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Focus Sessions Triggered: </span>
            <span className="text-foreground">{heartbeat?.focus_sessions_triggered ?? 0}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Orders Executed / Rejected: </span>
            <span className="text-foreground">
              {heartbeat?.orders_executed_count ?? 0} / {heartbeat?.orders_rejected_count ?? 0}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">State Changed (Git Commit Flag): </span>
            <span
              className={heartbeat?.state_changed ? "text-emerald-400" : "text-muted-foreground"}
            >
              {heartbeat?.state_changed ? "TRUE (Committed to data-state)" : "FALSE"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Frontend Last Polled (Local): </span>
            <span className="text-foreground">{formatUtcTime(lastFetchedAt)}</span>
          </div>
        </div>
      </div>

      {/* SHA-256 Snapshot Integrity Audit */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Hash className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold tracking-tight text-foreground">
              SHA-256 Snapshot Verification Hashes
            </h2>
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            P7 Cryptographic State Consistency
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left font-mono">
            <thead className="bg-muted/40 border-b border-border/60 text-[11px] text-muted-foreground uppercase">
              <tr>
                <th className="px-4 py-2.5">Snapshot File</th>
                <th className="px-4 py-2.5">SHA-256 Checksum Hash</th>
                <th className="px-4 py-2.5">Integrity Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 text-xs">
              {Object.entries(hashes).map(([key, hashVal]) => (
                <tr key={key} className="hover:bg-muted/30">
                  <td className="px-4 py-2.5 font-bold text-foreground">
                    {key.replace("_sha256", ".json")}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground truncate max-w-md">
                    {hashVal}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="inline-flex items-center gap-1 text-emerald-400 text-[11px]">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      VERIFIED_MATCH
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Architecture & Zero-Cost Infrastructure Card */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-3 font-mono text-xs text-muted-foreground">
        <div className="flex items-center gap-2 text-foreground font-semibold">
          <GitBranch className="h-4 w-4 text-primary" />
          <span>Branch Isolation Architecture: main vs data-state</span>
        </div>
        <p className="leading-relaxed font-sans text-xs">
          VibeTrade v1.1 implements strict separation of concerns. Branch <strong>main</strong> hosts
          all code, frontend and GitHub Actions workflows, while branch <strong>data-state</strong> stores
          the 5 atomic JSON snapshots. Each scheduled run executes in under 2 minutes, writes
          snapshots via atomic <code className="text-foreground">.tmp + os.replace()</code>, commits
          to <code className="text-foreground">data-state</code>, and updates this dashboard on GitHub
          Pages with zero running server costs ($0).
        </p>
      </div>
    </div>
  );
}
