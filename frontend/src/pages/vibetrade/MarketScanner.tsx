import { useState, useMemo } from "react";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import { formatPct, safeNumber } from "@/lib/staticData";
import { Search, ArrowUpDown } from "lucide-react";
import type { OrderbookDepth, CandidateOpportunity } from "@/types/vibetrade";

export function MarketScanner() {
  const { marketSnapshot, opportunityQueue } = useSnapshotStore();
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState<"vol" | "spread" | "slippage" | "price">("vol");
  const [sortAsc, setSortAsc] = useState(false);

  const orderbookMap = useMemo(() => {
    const map = new Map<string, OrderbookDepth>();
    marketSnapshot?.orderbooks?.forEach((ob) => map.set(ob.inst_id, ob));
    return map;
  }, [marketSnapshot]);

  const queueMap = useMemo(() => {
    const map = new Map<string, CandidateOpportunity>();
    opportunityQueue?.candidates?.forEach((c) => map.set(c.inst_id, c));
    return map;
  }, [opportunityQueue]);

  const rows = useMemo(() => {
    if (!marketSnapshot?.tickers) return [];
    return marketSnapshot.tickers.map((ticker) => {
      const ob = orderbookMap.get(ticker.inst_id);
      const queueItem = queueMap.get(ticker.inst_id);

      const lastPx = safeNumber(ticker.last);
      const open24h = safeNumber(ticker.open_24h, lastPx);
      const changePct = open24h > 0 ? ((lastPx - open24h) / open24h) * 100 : 0;
      const volQuote = safeNumber(ticker.vol_quote_24h);
      const spreadBps = safeNumber(ob?.spread_bps || ticker.spread_bps);
      const buySlippage = safeNumber(ob?.est_buy_slippage_bps, 0);

      return {
        inst_id: ticker.inst_id,
        last: lastPx,
        changePct,
        high_24h: safeNumber(ticker.high_24h),
        low_24h: safeNumber(ticker.low_24h),
        vol_quote_24h: volQuote,
        spread_bps: spreadBps,
        est_buy_slippage_bps: buySlippage,
        imbalance_ratio: safeNumber(ob?.imbalance_ratio, 0),
        anomalies: queueItem?.anomaly_types || [],
        inQueue: !!queueItem,
      };
    });
  }, [marketSnapshot, orderbookMap, queueMap]);

  const filteredRows = useMemo(() => {
    const list = rows.filter((r) =>
      r.inst_id.toLowerCase().includes(searchTerm.trim().toLowerCase())
    );

    list.sort((a, b) => {
      let diff = 0;
      if (sortBy === "vol") diff = a.vol_quote_24h - b.vol_quote_24h;
      else if (sortBy === "spread") diff = a.spread_bps - b.spread_bps;
      else if (sortBy === "slippage") diff = a.est_buy_slippage_bps - b.est_buy_slippage_bps;
      else if (sortBy === "price") diff = a.last - b.last;
      return sortAsc ? diff : -diff;
    });

    return list;
  }, [rows, searchTerm, sortBy, sortAsc]);

  const toggleSort = (column: "vol" | "spread" | "slippage" | "price") => {
    if (sortBy === column) {
      setSortAsc(!sortAsc);
    } else {
      setSortBy(column);
      setSortAsc(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Market Scanner</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            OKX Public REST v5 · USDT Spot Pairs · Micro-liquidity & Surveillance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search symbol (e.g. BTC, SOL)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-56 sm:w-64 pl-9 pr-3 py-1.5 rounded-lg border border-border/80 bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 font-mono"
            />
          </div>
        </div>
      </div>

      {/* Summary KPI Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="rounded-lg border border-border/60 bg-card p-3 font-mono">
          <span className="text-muted-foreground text-[11px]">Total Monitored Pairs</span>
          <p className="text-lg font-bold text-foreground mt-1">{rows.length} USDT Spot</p>
        </div>
        <div className="rounded-lg border border-border/60 bg-card p-3 font-mono">
          <span className="text-muted-foreground text-[11px]">Average Spread</span>
          <p className="text-lg font-bold text-foreground mt-1">
            {rows.length > 0
              ? `${(
                  rows.reduce((sum, r) => sum + r.spread_bps, 0) / rows.length
                ).toFixed(2)} bps`
              : "0.00 bps"}
          </p>
        </div>
        <div className="rounded-lg border border-border/60 bg-card p-3 font-mono">
          <span className="text-muted-foreground text-[11px]">Active Queue Triggers</span>
          <p className="text-lg font-bold text-emerald-400 mt-1">
            {rows.filter((r) => r.inQueue).length} Pairs In Focus
          </p>
        </div>
        <div className="rounded-lg border border-border/60 bg-card p-3 font-mono">
          <span className="text-muted-foreground text-[11px]">Data Ingestion Mode</span>
          <p className="text-lg font-bold text-primary mt-1">Confirmed Bars Only</p>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border/60 bg-card overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-muted/40 border-b border-border/60 font-mono text-[11px] text-muted-foreground uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Instrument</th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort("price")}
                >
                  <div className="flex items-center gap-1">
                    <span>Price</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="px-4 py-3 font-medium">24h Change</th>
                <th className="px-4 py-3 font-medium">24h High / Low</th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort("vol")}
                >
                  <div className="flex items-center gap-1">
                    <span>24h Quote Vol</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort("spread")}
                >
                  <div className="flex items-center gap-1">
                    <span>Spread (bps)</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort("slippage")}
                >
                  <div className="flex items-center gap-1">
                    <span>$10 Est Slippage</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="px-4 py-3 font-medium">Imbalance</th>
                <th className="px-4 py-3 font-medium">Surveillance Flags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono text-xs tabular-nums">
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                    No matching instruments found.
                  </td>
                </tr>
              ) : (
                filteredRows.map((r) => (
                  <tr
                    key={r.inst_id}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-bold text-foreground">
                      <div className="flex items-center gap-2">
                        <span>{r.inst_id}</span>
                        {r.inQueue && (
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-foreground font-semibold">
                      ${r.last < 1 ? r.last.toFixed(6) : r.last.toFixed(2)}
                    </td>
                    <td
                      className={`px-4 py-3 font-semibold ${
                        r.changePct >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {formatPct(r.changePct, 2)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-[11px]">
                      ${r.high_24h.toFixed(2)} / ${r.low_24h.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      ${r.vol_quote_24h.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-1.5 py-0.5 rounded text-[11px] ${
                          r.spread_bps <= 15
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "bg-amber-500/10 text-amber-400"
                        }`}
                      >
                        {r.spread_bps.toFixed(2)} bps
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-foreground">
                        {r.est_buy_slippage_bps.toFixed(2)} bps
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          r.imbalance_ratio > 0
                            ? "text-emerald-400"
                            : r.imbalance_ratio < 0
                            ? "text-rose-400"
                            : "text-muted-foreground"
                        }
                      >
                        {r.imbalance_ratio > 0 ? "+" : ""}
                        {r.imbalance_ratio.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {r.anomalies.length > 0 ? (
                          r.anomalies.map((anom: string) => (
                            <span
                              key={anom}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-primary/15 text-primary border border-primary/30"
                            >
                              {anom}
                            </span>
                          ))
                        ) : (
                          <span className="text-muted-foreground text-[11px]">Nominal</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
