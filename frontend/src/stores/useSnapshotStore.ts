import { create } from "zustand";
import type {
  AllSnapshots,
  HeartbeatSnapshot,
  MarketSnapshot,
  OpportunityQueueSnapshot,
  PaperPortfolioSnapshot,
  ResearchHistorySnapshot,
} from "@/types/vibetrade";
import { fetchAllSnapshots, isHeartbeatStale } from "@/lib/staticData";

export interface SnapshotState {
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastFetchedAt: number | null;

  heartbeat: HeartbeatSnapshot | null;
  marketSnapshot: MarketSnapshot | null;
  opportunityQueue: OpportunityQueueSnapshot | null;
  paperPortfolio: PaperPortfolioSnapshot | null;
  researchHistory: ResearchHistorySnapshot | null;

  isStale: boolean;

  loadSnapshots: (force?: boolean) => Promise<void>;
  refresh: () => Promise<void>;
  setSnapshotsDirectly: (snapshots: Partial<AllSnapshots>) => void;
}

export const useSnapshotStore = create<SnapshotState>((set, get) => ({
  loading: false,
  refreshing: false,
  error: null,
  lastFetchedAt: null,

  heartbeat: null,
  marketSnapshot: null,
  opportunityQueue: null,
  paperPortfolio: null,
  researchHistory: null,

  isStale: false,

  loadSnapshots: async (force = false) => {
    const state = get();
    if (state.loading && !force) return;
    if (state.lastFetchedAt && !force) return;

    set({ loading: true, error: null });
    try {
      const data = await fetchAllSnapshots();
      const stale = isHeartbeatStale(data.heartbeat);
      set({
        loading: false,
        refreshing: false,
        error: null,
        lastFetchedAt: Date.now(),
        heartbeat: data.heartbeat,
        marketSnapshot: data.marketSnapshot,
        opportunityQueue: data.opportunityQueue,
        paperPortfolio: data.paperPortfolio,
        researchHistory: data.researchHistory,
        isStale: stale,
      });
    } catch (err) {
      set({
        loading: false,
        refreshing: false,
        error: err instanceof Error ? err.message : "Failed to load static snapshots",
      });
    }
  },

  refresh: async () => {
    set({ refreshing: true, error: null });
    try {
      const data = await fetchAllSnapshots();
      const stale = isHeartbeatStale(data.heartbeat);
      set({
        refreshing: false,
        loading: false,
        error: null,
        lastFetchedAt: Date.now(),
        heartbeat: data.heartbeat,
        marketSnapshot: data.marketSnapshot,
        opportunityQueue: data.opportunityQueue,
        paperPortfolio: data.paperPortfolio,
        researchHistory: data.researchHistory,
        isStale: stale,
      });
    } catch (err) {
      set({
        refreshing: false,
        loading: false,
        error: err instanceof Error ? err.message : "Failed to refresh static snapshots",
      });
    }
  },

  setSnapshotsDirectly: (snapshots: Partial<AllSnapshots>) => {
    const currentHeartbeat = snapshots.heartbeat ?? get().heartbeat;
    set({
      ...snapshots,
      isStale: isHeartbeatStale(currentHeartbeat),
      lastFetchedAt: Date.now(),
      loading: false,
      error: null,
    });
  },
}));
