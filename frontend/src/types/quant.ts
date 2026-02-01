export type SignalAction = {
  action?: string;
  detail?: string;
};

export type SignalActions = {
  flat?: SignalAction;
  long?: SignalAction;
  short?: SignalAction;
};

export type VwapContext = {
  vwap?: number;
  vwap_state?: string;
  distance_sd?: number;
  std_dev?: number;
  candle_count?: number;
  confidence_adjustment?: number;
  modulation_reason?: string;
  sd_bands?: Record<string, number>;
  [key: string]: unknown;
};

export type FundingContext = {
  current_rate?: number;
  current_rate_pct?: string;
  regime?: string;
  regime_label?: string;
  annualized_rate_pct?: string;
  timestamp_ms?: number;
  next_funding_time_ms?: number | null;
  mark_price?: number | null;
  confidence_adjustment?: number;
  modulation_reason?: string;
  is_stale?: boolean;
  stale_reason?: string;
  [key: string]: unknown;
};

export type AtrContext = {
  current_atr?: number;
  percentile_rank?: number;
  atr_slope?: number;
  atr_z_score?: number | null;
  period?: number;
  lookback?: number;
  market_regime?: string;
  historical_average?: number;
  [key: string]: unknown;
};

export type FundInflowContext = {
  flow_regime?: string;
  dominant_flow?: string;
  total_netflow?: number;
  institution_netflow?: number;
  retail_netflow?: number;
  timeframe?: string;
  [key: string]: unknown;
};

export type AnomalyContextFactor = {
  is_significant?: boolean;
  anomaly_type?: string;
  z_score?: number;
  magnitude_pct?: number;
  baseline_mean?: number;
  baseline_std?: number;
  threshold?: number;
  current_value?: number;
  insufficient_data?: boolean;
  [key: string]: unknown;
};

export type AnomalyContext = {
  price?: AnomalyContextFactor;
  oi?: AnomalyContextFactor;
  cvd?: AnomalyContextFactor;
  [key: string]: unknown;
};

export type SpotFuturesContext = {
  coupling_state?: string;
  divergence_signal?: string;
  divergence_signals?: string[];
  display?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  z_scores?: Record<string, unknown>;
  net_flow?: Record<string, unknown>;
  [key: string]: unknown;
};

export type DepthContext = {
  bid_volume_usd?: number;
  ask_volume_usd?: number;
  net_depth_usd?: number;
  imbalance_pct?: number;
  obi_ratio?: number | null;
  mid_price?: number | null;
  range_pct?: number;
  best_bid?: number | null;
  best_ask?: number | null;
  [key: string]: unknown;
};

export type SnapshotMeta = {
  candles?: number;
  price_points?: number;
  oi_points?: number;
  cvd_points?: number;
  cvd_deltas?: number;
  [key: string]: unknown;
};

export type QuantSignal = {
  symbol: string;
  interval?: string;
  signal_type?: string;
  signal_metadata?: {
    signal_name?: string;
    direction?: string;
    category?: string;
    confidence?: number;
    base_confidence?: number;
    interpretation?: string;
    verdict?: string;
    [key: string]: unknown;
  };
  confirmation_count?: number;
  entry_price?: number;
  current_price?: number;
  entry_oi?: number;
  current_oi?: number;
  cvd_delta?: number;
  cvd_current?: number;
  net_depth_usd?: number;
  depth_regime?: string;
  depth_context?: DepthContext;
  calculated_score?: number;
  price_slope?: number;
  price_slope_z?: number | null;
  oi_slope?: number;
  oi_slope_z?: number | null;
  cvd_slope?: number;
  cvd_slope_z?: number | null;
  opened_at?: string;
  last_updated?: string;
  signal_reason?: string;
  signal_actions?: SignalActions;
  actions?: SignalActions;
  snapshot_meta?: SnapshotMeta;
  config_snapshot?: {
    profile_used?: boolean;
    profile_score?: number;
    profile_win_rate?: number;
    confidence_threshold?: number;
    interval?: string;
    timeframe?: string;
    [key: string]: unknown;
  };
  vwap_context?: VwapContext;
  funding_context?: FundingContext;
  atr_context?: AtrContext;
  fund_inflow_context?: FundInflowContext;
  anomaly_context?: AnomalyContext;
  spot_futures_context?: SpotFuturesContext;
  [key: string]: unknown;
};

export type QuantLog = {
  message: string;
  type?: string;
  timestamp?: string;
};

export type QuantStatus = {
  running?: boolean;
};
