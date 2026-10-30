import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import {
  safeNumber,
  formatUsdt,
  formatPct,
  formatBps,
  formatUtcTime,
  isHeartbeatStale,
} from "@/lib/staticData";

import { Overview } from "@/pages/vibetrade/Overview";
import { MarketScanner } from "@/pages/vibetrade/MarketScanner";
import { OpportunityQueue } from "@/pages/vibetrade/OpportunityQueue";
import { AIResearchRoom } from "@/pages/vibetrade/AIResearchRoom";
import { PaperPortfolio } from "@/pages/vibetrade/PaperPortfolio";
import { Performance } from "@/pages/vibetrade/Performance";
import { SystemMonitor } from "@/pages/vibetrade/SystemMonitor";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";

import heartbeatFixture from "../../public/data-state/heartbeat.json";
import marketSnapshotFixture from "../../public/data-state/market_snapshot.json";
import opportunityQueueFixture from "../../public/data-state/opportunity_queue.json";
import paperPortfolioFixture from "../../public/data-state/paper_portfolio.json";
import researchHistoryFixture from "../../public/data-state/research_history.json";

describe("Phase P7-B: Static Data Layer & Utilities", () => {
  it("safeNumber parses numbers and strings safely and prevents NaN/Infinity", () => {
    expect(safeNumber(12.34)).toBe(12.34);
    expect(safeNumber("150.12")).toBe(150.12);
    expect(safeNumber("not-a-number", 10)).toBe(10);
    expect(safeNumber(Number.NaN, 5)).toBe(5);
    expect(safeNumber(Number.POSITIVE_INFINITY, 0)).toBe(0);
    expect(safeNumber(undefined, 42)).toBe(42);
  });

  it("formatters correctly format USDT, percentages, bps, and UTC timestamps", () => {
    expect(formatUsdt(10.5, 4)).toBe("$10.5000");
    expect(formatUsdt("9.99849", 2)).toBe("$10.00");
    expect(formatPct(5.25)).toBe("+5.25%");
    expect(formatPct(-2.5)).toBe("-2.50%");
    expect(formatBps(15.2)).toBe("+15.20 bps");
    expect(formatBps(-5)).toBe("-5.00 bps");

    const ts = 1793357771254;
    expect(formatUtcTime(ts)).toContain("UTC");
    expect(formatUtcTime(null)).toBe("--:--:-- UTC");
  });

  it("isHeartbeatStale detects fresh vs stale or degraded pipeline runs", () => {
    const fresh = {
      ...heartbeatFixture,
      cycle_finished_at_utc_ms: Date.now() - 5 * 60 * 1000, // 5 min ago
      status: "HEALTHY",
    };
    expect(isHeartbeatStale(fresh as any)).toBe(false);

    const stale = {
      ...heartbeatFixture,
      cycle_finished_at_utc_ms: Date.now() - 35 * 60 * 1000, // 35 min ago (>30m)
      status: "HEALTHY",
    };
    expect(isHeartbeatStale(stale as any)).toBe(true);

    const degraded = {
      ...heartbeatFixture,
      cycle_finished_at_utc_ms: Date.now() - 5 * 60 * 1000,
      status: "DEGRADED",
    };
    expect(isHeartbeatStale(degraded as any)).toBe(true);
    expect(isHeartbeatStale(null)).toBe(true);
  });
});

describe("Phase P7-B: 7-Screen Quant Dashboard UI Rendering", () => {
  beforeEach(() => {
    useSnapshotStore.getState().setSnapshotsDirectly({
      heartbeat: heartbeatFixture as any,
      marketSnapshot: marketSnapshotFixture as any,
      opportunityQueue: opportunityQueueFixture as any,
      paperPortfolio: paperPortfolioFixture as any,
      researchHistory: researchHistoryFixture as any,
    });
  });

  it("Screen 1 (Overview) renders total equity, separated PnL, regime and positions", () => {
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>
    );

    const expEquity = formatUsdt(safeNumber(paperPortfolioFixture.total_equity_usdt), 4);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Total Equity")).toBeInTheDocument();
    expect(screen.getByText(expEquity)).toBeInTheDocument();
    expect(screen.getByText("Realized PnL:")).toBeInTheDocument();
    expect(screen.getByText("Unrealized PnL:")).toBeInTheDocument();
    expect(screen.getByText(opportunityQueueFixture.market_regime.regime)).toBeInTheDocument();
    expect(screen.getAllByText(paperPortfolioFixture.open_positions[0].inst_id).length).toBeGreaterThan(0);
  });

  it("Screen 2 (Market Scanner) renders OKX Spot pairs, search filter, and spreads", () => {
    render(
      <MemoryRouter>
        <MarketScanner />
      </MemoryRouter>
    );

    expect(screen.getByText("Market Scanner")).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`${marketSnapshotFixture.tickers.length} USDT`, "i"))).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Search symbol/i)).toBeInTheDocument();
    const firstSym = marketSnapshotFixture.tickers[0].inst_id;
    const lastSym = marketSnapshotFixture.tickers[marketSnapshotFixture.tickers.length - 1].inst_id;
    expect(screen.getAllByText(firstSym).length).toBeGreaterThan(0);
    expect(screen.getAllByText(lastSym).length).toBeGreaterThan(0);

    // Search filter test
    const input = screen.getByPlaceholderText(/Search symbol/i);
    fireEvent.change(input, { target: { value: "SOL" } });
    expect(screen.getAllByText(/SOL-USDT(-SWAP)?/).length).toBeGreaterThan(0);
    expect(screen.queryByText("AVAX-USDT")).not.toBeInTheDocument();
  });

  it("Screen 3 (Opportunity Queue) renders idempotent signal_id, scanner score and metrics", () => {
    render(
      <MemoryRouter>
        <OpportunityQueue />
      </MemoryRouter>
    );

    expect(screen.getByText("Opportunity Queue")).toBeInTheDocument();
    expect(screen.getByText(`Queue Size: ${opportunityQueueFixture.candidates.length}`)).toBeInTheDocument();
    const cand = opportunityQueueFixture.candidates[0];
    expect(screen.getByText(cand.signal_id)).toBeInTheDocument();
    expect(screen.getByText(cand.scanner_score)).toBeInTheDocument();
    expect(screen.getByText(cand.anomaly_types[0])).toBeInTheDocument();
  });

  it("Screen 4 (AI Research Room) renders Bull/Bear weighted scores and Evidence Binding", () => {
    render(
      <MemoryRouter>
        <AIResearchRoom />
      </MemoryRouter>
    );

    expect(screen.getByText("AI Research Room")).toBeInTheDocument();
    expect(screen.getByText("+82.50 pts")).toBeInTheDocument();
    expect(screen.getAllByText("-15.00 pts").length).toBeGreaterThan(0);
    expect(screen.getByText("+74.25")).toBeInTheDocument();
    expect(screen.getByText("ACTIONABLE_LONG")).toBeInTheDocument();
    expect(screen.getByText("VERIFIED_PASS")).toBeInTheDocument();
    expect(screen.getByText("BULL_RVOL_SURGE_01")).toBeInTheDocument();
  });

  it("Screen 5 (Paper Portfolio) renders $10 account balances, 3 timestamps and drift cost", () => {
    render(
      <MemoryRouter>
        <PaperPortfolio />
      </MemoryRouter>
    );

    const expEquity = formatUsdt(safeNumber(paperPortfolioFixture.total_equity_usdt), 4);
    const expCash = formatUsdt(safeNumber(paperPortfolioFixture.cash_balance_usdt), 4);

    expect(screen.getByText(/Paper Portfolio/i)).toBeInTheDocument();
    expect(screen.getByText(expEquity)).toBeInTheDocument();
    expect(screen.getByText(expCash)).toBeInTheDocument();
    expect(screen.getByText("1. Candle Close:")).toBeInTheDocument();
    expect(screen.getByText("2. Signal Generated:")).toBeInTheDocument();
    expect(screen.getByText("3. Order Executed:")).toBeInTheDocument();
    expect(screen.getByText("Schedule Drift:")).toBeInTheDocument();
  });

  it("Screen 6 (Performance) renders net equity vs Baselines and friction decomposition", () => {
    render(
      <MemoryRouter>
        <Performance />
      </MemoryRouter>
    );

    expect(screen.getByText("Performance & Friction Analytics")).toBeInTheDocument();
    expect(screen.getByText("Baseline 1: $10.00 USDT Cash")).toBeInTheDocument();
    expect(screen.getByText("Baseline 2: BTC Buy & Hold ($10)")).toBeInTheDocument();
    expect(screen.getByText("Friction Cost Decomposition")).toBeInTheDocument();
    expect(screen.getByText("GitHub Actions Schedule Drift Cost")).toBeInTheDocument();
  });

  it("Screen 7 (System Monitor) renders telemetry, run_id, and SHA-256 hashes", () => {
    render(
      <MemoryRouter>
        <SystemMonitor />
      </MemoryRouter>
    );

    expect(screen.getByText("System Monitor & Telemetry")).toBeInTheDocument();
    expect(screen.getByText(heartbeatFixture.run_id)).toBeInTheDocument();
    expect(screen.getByText(`${heartbeatFixture.duration_ms} ms`)).toBeInTheDocument();
    expect(screen.getByText("SHA-256 Snapshot Verification Hashes")).toBeInTheDocument();
    expect(screen.getByText("market_snapshot.json")).toBeInTheDocument();
    expect(screen.getAllByText("VERIFIED_MATCH").length).toBe(4);
  });
});

describe("Phase P7-B: Edge Cases & Stale / Error States", () => {
  it("renders INCONCLUSIVE and missing inputs banner in AIResearchRoom", () => {
    const reportWithMissing = {
      ...researchHistoryFixture.reports[0],
      verdict: "INCONCLUSIVE",
      missing_inputs: ["orderbook_depth_l2", "btc_regime_volatility"],
    };

    useSnapshotStore.getState().setSnapshotsDirectly({
      researchHistory: {
        schema_version: "1.1",
        generated_at_utc_ms: 1793357771254,
        total_reports: 1,
        reports: [reportWithMissing as any],
      },
    });

    render(
      <MemoryRouter>
        <AIResearchRoom />
      </MemoryRouter>
    );

    expect(screen.getByText("INCONCLUSIVE Fallback Triggered:")).toBeInTheDocument();
    expect(
      screen.getByText(/orderbook_depth_l2, btc_regime_volatility/)
    ).toBeInTheDocument();
  });

  it("renders REJECTED_BY_CONSTRAINT orders in PaperPortfolio", () => {
    useSnapshotStore.getState().setSnapshotsDirectly({
      paperPortfolio: {
        ...paperPortfolioFixture,
        rejected_orders: [
          {
            order_id: "ord:rej:123",
            inst_id: "ETH-USDT",
            reason: "REJECTED_BY_CONSTRAINT: Order notional $1.20 below minSz 0.01 ETH ($26.50)",
            rejected_at_utc_ms: 1793357771254,
          },
        ],
      } as any,
    });

    render(
      <MemoryRouter>
        <PaperPortfolio />
      </MemoryRouter>
    );

    expect(screen.getByText(/Order notional \$1.20 below minSz/)).toBeInTheDocument();
  });

  it("ConnectionBanner renders alert when error occurs", () => {
    useSnapshotStore.setState({ error: "Failed to fetch snapshots: Network error" });

    render(<ConnectionBanner />);

    expect(screen.getByText(/Snapshot Load Error:/)).toBeInTheDocument();
    expect(screen.getByText(/Failed to fetch snapshots/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });

  it("ConnectionBanner renders warning when heartbeat is stale", () => {
    useSnapshotStore.setState({
      error: null,
      isStale: true,
      heartbeat: {
        ...heartbeatFixture,
        cycle_finished_at_utc_ms: 1700000000000,
        status: "HEALTHY",
      } as any,
    });

    render(<ConnectionBanner />);

    expect(screen.getByText(/Pipeline Degraded \/ Stale:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Refresh Snapshots/i })).toBeInTheDocument();
  });

  it("handles empty initial bootstrap portfolio gracefully", () => {
    useSnapshotStore.getState().setSnapshotsDirectly({
      paperPortfolio: {
        schema_version: "1.1",
        generated_at_utc_ms: 1793357771254,
        initial_balance_usdt: "10.0000",
        cash_balance_usdt: "10.0000",
        total_equity_usdt: "10.0000",
        cumulative_realized_pnl_usdt: "0.0000",
        total_unrealized_pnl_usdt: "0.0000",
        total_fees_paid_usdt: "0.0000",
        total_schedule_drift_cost_usdt: "0.0000",
        open_positions: [],
        closed_trades: [],
        rejected_orders: [],
      },
    });

    render(
      <MemoryRouter>
        <PaperPortfolio />
      </MemoryRouter>
    );

    expect(screen.getByText(/No active positions open\. Capital is 100% in USDT Cash\./i)).toBeInTheDocument();
    expect(screen.getByText(/No closed trades yet in current history\./i)).toBeInTheDocument();
  });
});
