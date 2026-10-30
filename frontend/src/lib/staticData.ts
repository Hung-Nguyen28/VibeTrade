import type {
  AllSnapshots,
  HeartbeatSnapshot,
  MarketSnapshot,
  OpportunityQueueSnapshot,
  PaperPortfolioSnapshot,
  ResearchHistorySnapshot,
} from "@/types/vibetrade";

export const DEFAULT_DATA_STATE_BASE_URL = "./data-state";

export function getDataStateBaseUrl(): string {
  const envUrl = import.meta.env.VITE_DATA_STATE_BASE_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/+$/, "");
  }
  return DEFAULT_DATA_STATE_BASE_URL;
}

export function safeNumber(val: unknown, fallback = 0): number {
  if (typeof val === "number") {
    return Number.isFinite(val) ? val : fallback;
  }
  if (typeof val === "string") {
    const parsed = parseFloat(val);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

export function formatUsdt(val: unknown, decimals = 4): string {
  const num = safeNumber(val, 0);
  return `$${num.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function formatPct(val: unknown, decimals = 2): string {
  const num = safeNumber(val, 0);
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(decimals)}%`;
}

export function formatBps(val: unknown, decimals = 2): string {
  const num = safeNumber(val, 0);
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(decimals)} bps`;
}

export function formatUtcTime(tsMs: number | null | undefined): string {
  if (!tsMs || !Number.isFinite(tsMs) || tsMs <= 0) return "--:--:-- UTC";
  const d = new Date(tsMs);
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

export function isHeartbeatStale(heartbeat: HeartbeatSnapshot | null, thresholdMs = 30 * 60 * 1000): boolean {
  if (!heartbeat) return true;
  if (heartbeat.status !== "HEALTHY") return true;
  const finishTime = heartbeat.cycle_finished_at_utc_ms || heartbeat.cycle_started_at_utc_ms;
  if (!finishTime || finishTime <= 0) return true;
  // If finish time is in future or within threshold, consider fresh
  // For static demo/snapshot verification, check staleness against now
  const now = Date.now();
  // If snapshot time is unreasonably far in past compared to current machine clock,
  // or heartbeat explicitly has degraded status
  return now - finishTime > thresholdMs;
}

async function fetchJsonWithTimeout<T>(url: string, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new Error(`Failed to load ${url}: HTTP ${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    return data as T;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchAllSnapshots(baseUrl?: string): Promise<AllSnapshots> {
  const base = baseUrl || getDataStateBaseUrl();
  const cacheBust = `?_ts=${Date.now()}`;

  const [heartbeat, marketSnapshot, opportunityQueue, paperPortfolio, researchHistory] = await Promise.all([
    fetchJsonWithTimeout<HeartbeatSnapshot>(`${base}/heartbeat.json${cacheBust}`),
    fetchJsonWithTimeout<MarketSnapshot>(`${base}/market_snapshot.json${cacheBust}`),
    fetchJsonWithTimeout<OpportunityQueueSnapshot>(`${base}/opportunity_queue.json${cacheBust}`),
    fetchJsonWithTimeout<PaperPortfolioSnapshot>(`${base}/paper_portfolio.json${cacheBust}`),
    fetchJsonWithTimeout<ResearchHistorySnapshot>(`${base}/research_history.json${cacheBust}`),
  ]);

  return {
    heartbeat,
    marketSnapshot,
    opportunityQueue,
    paperPortfolio,
    researchHistory,
  };
}
