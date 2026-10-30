import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router";
import {
  Sun,
  Moon,
  RefreshCw,
  ChevronsLeft,
  ChevronsRight,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";
import { safeGet, safeSet } from "@/lib/storage";
import { BrandMark } from "@/components/common/BrandMark";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";
import { SidebarNavigation } from "./SidebarNavigation";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatUtcTime } from "@/lib/staticData";

export function Layout() {
  const { dark, toggle } = useDarkMode();
  const [collapsed, setCollapsed] = useState(() => safeGet("qa-sidebar") === "collapsed");

  const {
    heartbeat,
    loading,
    refreshing,
    isStale,
    error,
    refresh,
    loadSnapshots,
  } = useSnapshotStore();

  useEffect(() => {
    loadSnapshots();
  }, [loadSnapshots]);

  useEffect(() => {
    safeSet("qa-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  const heartbeatStatus = error
    ? "ERROR"
    : isStale
    ? "STALE"
    : heartbeat?.status || "LOADING";

  const statusBg =
    heartbeatStatus === "HEALTHY"
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
      : heartbeatStatus === "STALE"
      ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
      : heartbeatStatus === "ERROR"
      ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
      : "bg-slate-500/10 text-slate-400 border-slate-500/30";

  const StatusIcon =
    heartbeatStatus === "HEALTHY"
      ? ShieldCheck
      : heartbeatStatus === "STALE"
      ? AlertTriangle
      : AlertCircle;

  return (
    <div className="flex h-screen bg-background text-foreground antialiased font-sans overflow-hidden">
      {/* Sidebar */}
      <aside
        aria-label="VibeTrade Sidebar"
        className={cn(
          "max-md:w-14 border-e border-border/60 bg-card flex flex-col shrink-0 transition-all duration-200 z-20",
          collapsed ? "w-14" : "w-64"
        )}
      >
        {/* Brand Header */}
        <div
          className={cn(
            "border-b border-border/60 flex items-center justify-between",
            collapsed ? "p-3 justify-center" : "px-4 py-3"
          )}
        >
          <Link
            to="/"
            aria-label="VibeTrade v1.1"
            className="flex items-center gap-2.5 overflow-hidden"
          >
            <BrandMark className="h-6 w-6 shrink-0 text-primary" />
            {!collapsed && (
              <div className="flex flex-col min-w-0">
                <span className="text-[14px] font-bold tracking-tight text-foreground truncate">
                  VibeTrade <span className="text-xs text-primary font-mono">v1.1</span>
                </span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-mono">
                  Autonomous Quant
                </span>
              </div>
            )}
          </Link>
          {!collapsed && (
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              aria-label="Collapse sidebar"
              className="hidden md:flex rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <ChevronsLeft className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Sidebar Navigation */}
        <SidebarNavigation collapsed={collapsed} />

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-border/60 flex flex-col gap-2">
          {collapsed ? (
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              aria-label="Expand sidebar"
              className="flex justify-center rounded p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <ChevronsRight className="h-4 w-4" />
            </button>
          ) : (
            <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
              <span className="font-mono text-[11px]">$0 Budget · OKX Spot</span>
              <a
                href="https://github.com/HKUDS/Vibe-Trading"
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 hover:text-foreground transition-colors"
              >
                Docs <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header Bar */}
        <header className="h-14 border-b border-border/60 bg-card/60 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            {/* Heartbeat Status Badge */}
            <div
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono border font-medium",
                statusBg
              )}
              title={
                heartbeat
                  ? `Run: ${heartbeat.run_id}\nFinished: ${formatUtcTime(
                      heartbeat.cycle_finished_at_utc_ms
                    )}\nDuration: ${heartbeat.duration_ms}ms\nDrift: ${
                      heartbeat.schedule_drift_ms
                    }ms`
                  : "No snapshot loaded"
              }
            >
              <StatusIcon className="h-3.5 w-3.5" />
              <span>{heartbeatStatus}</span>
              {heartbeat?.schedule_drift_ms !== undefined && (
                <span className="text-[10px] opacity-75 tabular-nums">
                  ({heartbeat.schedule_drift_ms}ms)
                </span>
              )}
            </div>

            {/* Cycle Finished Time */}
            {heartbeat?.cycle_finished_at_utc_ms && (
              <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground font-mono tabular-nums">
                <span className="text-muted-foreground/60">Cycle:</span>
                <span>{formatUtcTime(heartbeat.cycle_finished_at_utc_ms)}</span>
              </div>
            )}
          </div>

          {/* Right Header Actions */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => refresh()}
              disabled={loading || refreshing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
              title="Refresh static snapshots from data-state"
            >
              <RefreshCw
                className={cn("h-3.5 w-3.5", refreshing ? "animate-spin text-primary" : "")}
              />
              <span className="hidden sm:inline">
                {refreshing ? "Refreshing…" : "Refresh"}
              </span>
            </button>

            <button
              type="button"
              onClick={toggle}
              aria-label="Toggle dark mode"
              className="rounded-lg border border-border/80 bg-background p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>

        {/* Global Connection / Status Banner */}
        <ConnectionBanner />

        {/* Main View Area */}
        <main id="main" className="flex-1 overflow-y-auto p-4 md:p-6 bg-background">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
