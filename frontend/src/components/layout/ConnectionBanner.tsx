import { AlertTriangle, AlertCircle, RefreshCw } from "lucide-react";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUtcTime } from "@/lib/staticData";

export function ConnectionBanner() {
  const { heartbeat, isStale, error, refreshing, refresh, loadSnapshots } = useSnapshotStore();

  if (error) {
    return (
      <aside
        className="w-full flex items-center justify-between gap-3 border-b border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs text-rose-400"
        role="alert"
        aria-label="Snapshot Error"
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>Snapshot Load Error:</strong> {error}
          </span>
        </div>
        <button
          type="button"
          onClick={() => loadSnapshots(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-md border border-rose-500/40 bg-rose-500/20 px-2.5 py-1 text-xs font-medium text-rose-300 hover:bg-rose-500/30 transition-colors focus:outline-none focus:ring-1 focus:ring-rose-400"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
          Retry
        </button>
      </aside>
    );
  }

  if (isStale && heartbeat) {
    const finishTime = heartbeat.cycle_finished_at_utc_ms || heartbeat.cycle_started_at_utc_ms;
    return (
      <aside
        className="w-full flex items-center justify-between gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-400"
        role="status"
        aria-label="Pipeline Degraded or Stale"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>Pipeline Degraded / Stale:</strong> Last cycle completed at{" "}
            <span className="font-mono tabular-nums">{formatUtcTime(finishTime)}</span> (Status:{" "}
            <span className="font-mono">{heartbeat.status}</span>, Drift:{" "}
            <span className="font-mono">{heartbeat.schedule_drift_ms}ms</span>)
          </span>
        </div>
        <button
          type="button"
          onClick={() => refresh()}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/20 px-2.5 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/30 transition-colors focus:outline-none focus:ring-1 focus:ring-amber-400"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
          Refresh Snapshots
        </button>
      </aside>
    );
  }

  return null;
}
