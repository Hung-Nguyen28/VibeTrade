import { Suspense, lazy, type ComponentType } from "react";
import { createHashRouter, Navigate } from "react-router";
import { Layout } from "@/components/layout/Layout";

// 7 VibeTrade v1.1 Screens
const Overview = lazy(() =>
  import("@/pages/vibetrade/Overview").then((m) => ({ default: m.Overview }))
);
const MarketScanner = lazy(() =>
  import("@/pages/vibetrade/MarketScanner").then((m) => ({ default: m.MarketScanner }))
);
const OpportunityQueue = lazy(() =>
  import("@/pages/vibetrade/OpportunityQueue").then((m) => ({ default: m.OpportunityQueue }))
);
const AIResearchRoom = lazy(() =>
  import("@/pages/vibetrade/AIResearchRoom").then((m) => ({ default: m.AIResearchRoom }))
);
const PaperPortfolio = lazy(() =>
  import("@/pages/vibetrade/PaperPortfolio").then((m) => ({ default: m.PaperPortfolio }))
);
const Performance = lazy(() =>
  import("@/pages/vibetrade/Performance").then((m) => ({ default: m.Performance }))
);
const SystemMonitor = lazy(() =>
  import("@/pages/vibetrade/SystemMonitor").then((m) => ({ default: m.SystemMonitor }))
);

function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center text-xs font-mono text-muted-foreground animate-pulse">
      Loading Quant Intelligence Terminal…
    </div>
  );
}

function wrap(Component: ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

// HashRouter ensures seamless page reload on GitHub Pages subpaths with zero 404s
export const router = createHashRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: wrap(Overview) },
      { path: "/overview", element: wrap(Overview) },
      { path: "/scanner", element: wrap(MarketScanner) },
      { path: "/queue", element: wrap(OpportunityQueue) },
      { path: "/research", element: wrap(AIResearchRoom) },
      { path: "/portfolio", element: wrap(PaperPortfolio) },
      { path: "/performance", element: wrap(Performance) },
      { path: "/monitor", element: wrap(SystemMonitor) },
      // Fallback for legacy routes
      { path: "/agent", element: <Navigate to="/" replace /> },
      { path: "/reports", element: <Navigate to="/research" replace /> },
      { path: "/paper-trading", element: <Navigate to="/portfolio" replace /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
