/**
 * VibeTrade v1.1 - Static Quant Intelligence System Data Types
 * Aligned with Phase P1 -> P7 Data Schemas and contracts.
 */

export interface HeartbeatSnapshot {
  schema_version: string;
  run_id: string;
  status: "HEALTHY" | "DEGRADED" | "ERROR" | string;
  cycle_started_at_utc_ms: number;
  cycle_finished_at_utc_ms: number;
  duration_ms: number;
  schedule_drift_ms: number;
  okx_api_status: string;
  scanned_symbols_count: number;
  focus_sessions_triggered: number;
  orders_executed_count: number;
  orders_rejected_count: number;
  state_changed: boolean;
  snapshot_hashes: {
    market_snapshot_sha256?: string;
    opportunity_queue_sha256?: string;
    paper_portfolio_sha256?: string;
    research_history_sha256?: string;
    [key: string]: string | undefined;
  };
  error_summary: string | null;
}

export interface InstrumentInfo {
  inst_id: string;
  base_ccy: string;
  quote_ccy: string;
  tick_size: string;
  lot_size: string;
  min_size: string;
  state: string;
  ct_val?: string;
  ct_mult?: string;
  max_lever?: string;
  settle_ccy?: string;
}

export interface TickerInfo {
  inst_id: string;
  last: string;
  ask_px: string;
  bid_px: string;
  ask_sz: string;
  bid_sz: string;
  open_24h: string;
  high_24h: string;
  low_24h: string;
  vol_base_24h: string;
  vol_quote_24h: string;
  spread_bps: string;
  ts_utc_ms: number;
}

export interface CandleBar {
  inst_id: string;
  timeframe: string;
  candle_open_time: number;
  candle_close_time: number;
  open: string;
  high: string;
  low: string;
  close: string;
  vol_base: string;
  vol_quote: string;
  confirm: boolean;
}

export interface OrderbookDepth {
  inst_id: string;
  mid_price: string;
  best_bid: string;
  best_ask: string;
  spread_bps: string;
  bid_depth_usdt: string;
  ask_depth_usdt: string;
  imbalance_ratio: string;
  est_buy_slippage_bps: string;
  est_sell_slippage_bps: string;
  probe_notional_usdt: string;
  buy_fully_filled: boolean;
  sell_fully_filled: boolean;
  depth_levels: number;
  ts_utc_ms: number;
}

export interface MarketSnapshot {
  schema_version: string;
  generated_at_utc_ms: number;
  source: string;
  quote_ccy: string;
  inst_type: string;
  instruments: InstrumentInfo[];
  tickers: TickerInfo[];
  candles: CandleBar[];
  orderbooks: OrderbookDepth[];
}

export interface MarketRegimeInfo {
  regime: "BULL_TREND" | "RANGE_BOUND" | "HIGH_VOL_CHOP" | "BEAR_TREND" | string;
  multiplier: string;
  market_breadth_pct: string;
  btc_price: string;
  btc_ema_fast: string;
  btc_ema_slow: string;
  btc_rsi: string;
  btc_atr_pct: string;
  detected_at_utc_ms: number;
  details?: {
    atr_rank_percentile?: number;
    candles_analyzed?: number;
    is_ema_bull?: boolean;
    is_ema_bear?: boolean;
  };
}

export interface CandidateOpportunity {
  signal_id: string;
  inst_id: string;
  timeframe: string;
  candle_close_time: number;
  detected_at_utc_ms: number;
  scanner_score: string;
  regime: string;
  anomaly_types: string[];
  status: "PENDING" | "IN_FOCUS" | "EVALUATED" | "EXPIRED" | string;
  metrics: Record<string, string>;
}

export interface OpportunityQueueSnapshot {
  schema_version: string;
  generated_at_utc_ms: number;
  queue_size: number;
  market_regime: MarketRegimeInfo;
  candidates: CandidateOpportunity[];
}

export interface OpenPosition {
  position_id: string;
  inst_id: string;
  side?: "LONG" | "SHORT" | string;
  qty_base: string;
  contracts?: string;
  ct_val?: string;
  leverage?: string;
  isolated_margin_usdt?: string;
  entry_price: string;
  current_mark_price: string;
  liquidation_price?: string;
  stop_loss_price?: string;
  take_profit_price?: string;
  accumulated_funding_usdt?: string;
  notional_entry_usdt: string;
  entry_fee_usdt: string;
  candle_close_time: number;
  signal_timestamp: number;
  execution_timestamp: number;
  schedule_drift_ms: number;
  schedule_drift_bps: string;
  schedule_drift_cost_usdt: string;
  unrealized_pnl_usdt: string;
  entry_order_id: string;
}

export interface ClosedTrade {
  trade_id: string;
  position_id?: string;
  inst_id: string;
  side?: "LONG" | "SHORT" | string;
  qty_base: string;
  entry_price: string;
  exit_price: string;
  realized_pnl_usdt?: string;
  net_realized_pnl_usdt?: string;
  gross_pnl_usdt?: string;
  total_fees_usdt?: string;
  entry_fee_usdt?: string;
  exit_fee_usdt?: string;
  entry_time?: number;
  exit_time?: number;
  entry_timestamp?: number;
  exit_timestamp?: number;
  exit_reason?: "TAKE_PROFIT" | "STOP_LOSS" | "TIME_STOP" | "SIGNAL_EXIT" | "LIQUIDATED" | string;
  schedule_drift_cost_usdt?: string;
}

export interface RejectedOrder {
  order_id: string;
  signal_id?: string;
  inst_id: string;
  side?: string;
  proposed_notional_usdt?: string;
  constraint_code?: string;
  reason?: string;
  timestamp_ms?: number;
  rejected_at_utc_ms?: number;
  details?: Record<string, unknown> | string;
}

export interface PaperPortfolioSnapshot {
  schema_version: string;
  generated_at_utc_ms: number;
  initial_balance_usdt: string;
  cash_balance_usdt: string;
  total_equity_usdt: string;
  cumulative_realized_pnl_usdt: string;
  total_unrealized_pnl_usdt: string;
  total_fees_paid_usdt: string;
  total_schedule_drift_cost_usdt: string;
  total_funding_fees_usdt?: string;
  open_positions: OpenPosition[];
  closed_trades: ClosedTrade[];
  rejected_orders: RejectedOrder[];
}

export interface EvidenceItem {
  rule_id: string;
  persona: "bull_researcher" | "bear_researcher" | string;
  metric: string;
  value: string;
  threshold: string;
  weight: string;
  score_contribution: string;
  template_summary: string;
  candle_close_time: number;
}

export interface ResearchReport {
  report_id: string;
  signal_id: string;
  inst_id: string;
  timeframe: string;
  candle_close_time: number;
  evaluated_at_utc_ms: number;
  verdict: "ACTIONABLE_LONG" | "ACTIONABLE_SHORT" | "WATCHLIST_NEUTRAL" | "AVOID_BEARISH" | "INCONCLUSIVE" | string;
  score_bull: string;
  score_bear: string;
  score_raw: string;
  regime: string;
  regime_multiplier: string;
  score_net: string;
  missing_inputs: string[];
  template_summary: string;
  evidence: EvidenceItem[];
  verification?: {
    status: "VERIFIED_PASS" | "VERIFIED_FAIL" | string;
    auditor: string;
    sha256_hash?: string;
    verified_at_utc_ms?: number;
  };
}

export interface ResearchHistorySnapshot {
  schema_version: string;
  generated_at_utc_ms: number;
  total_reports: number;
  reports: ResearchReport[];
}

export interface AllSnapshots {
  heartbeat: HeartbeatSnapshot;
  marketSnapshot: MarketSnapshot;
  opportunityQueue: OpportunityQueueSnapshot;
  paperPortfolio: PaperPortfolioSnapshot;
  researchHistory: ResearchHistorySnapshot;
}
