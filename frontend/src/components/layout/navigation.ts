import {
  LayoutDashboard,
  Search,
  Layers,
  Scale,
  WalletCards,
  TrendingUp,
  Activity,
  type LucideIcon,
} from "lucide-react";

export interface NavigationItem {
  id: string;
  to: string;
  icon: LucideIcon;
  label: string;
  description: string;
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    id: "overview",
    to: "/",
    icon: LayoutDashboard,
    label: "Overview",
    description: "$10 Equity, PnL separation, Market Regime & Top Opportunities",
  },
  {
    id: "scanner",
    to: "/scanner",
    icon: Search,
    label: "Market Scanner",
    description: "OKX Public USDT Spot monitoring, Spreads, Slippage & Anomaly flags",
  },
  {
    id: "queue",
    to: "/queue",
    icon: Layers,
    label: "Opportunity Queue",
    description: "Candidate lifecycle, Idempotent signal_id & Technical triggers",
  },
  {
    id: "research",
    to: "/research",
    icon: Scale,
    label: "AI Research Room",
    description: "Bull vs Bear Weighted Scoring, Evidence Binding & Audit Receipts",
  },
  {
    id: "portfolio",
    to: "/portfolio",
    icon: WalletCards,
    label: "Paper Portfolio",
    description: "$10 Micro account, 3 Timestamps, Drift Cost & Constraint Rejections",
  },
  {
    id: "performance",
    to: "/performance",
    icon: TrendingUp,
    label: "Performance",
    description: "Net Equity Curve vs Baselines ($10 Cash & BTC), Friction Decomposition",
  },
  {
    id: "monitor",
    to: "/monitor",
    icon: Activity,
    label: "System Monitor",
    description: "Heartbeat health, GitHub Actions schedule drift & SHA-256 Hashes",
  },
];

export const NAVIGATION_GROUPS = [
  {
    id: "vibetrade",
    items: NAVIGATION_ITEMS,
  },
];

export function isNavigationActive(to: string, pathname: string): boolean {
  if (to === "/") {
    return pathname === "/" || pathname === "/overview";
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}
