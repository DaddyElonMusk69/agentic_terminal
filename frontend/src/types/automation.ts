export type AutomationSession = {
  id: string;
  status: "running" | "paused" | "stopped";
  startedAt: string;
};

export type AutoAddTranche = {
  tranche_index: number;
  kind: "INITIAL" | "ADD" | string;
  status?: string | null;
  exchange_order_id?: string | null;
  trigger_price?: number | null;
  fill_price?: number | null;
  filled_quantity?: number | null;
  margin_used?: number | null;
  position_notional_usd?: number | null;
  fill_time?: string | null;
  atr_value?: number | null;
  trigger_basis_price?: number | null;
};

export type AutoAddPosition = {
  status: string;
  filled_add_count: number;
  max_tranches: number;
  next_trigger_basis_price?: number | null;
  next_trigger_price?: number | null;
  latest_atr_value?: number | null;
  original_risk_usd?: number | null;
  initial_margin_used?: number | null;
  last_error?: string | null;
  tranches: AutoAddTranche[];
};

export type AutomationPosition = {
  id?: string;
  symbol: string;
  direction?: "LONG" | "SHORT" | "long" | "short";
  side?: "long" | "short";
  size?: number;
  entry_price?: number;
  mark_price?: number;
  unrealized_pnl?: number;
  liquidation_price?: number | null;
  margin?: number;
  leverage?: number;
  opened_at?: string | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  auto_add?: AutoAddPosition | null;
};

export type AutomationTrade = {
  id?: string | number;
  symbol: string;
  direction?: "LONG" | "SHORT" | "long" | "short";
  action?: string;
  entry_price?: number;
  exit_price?: number;
  size_usd?: number;
  pnl?: number;
  pnl_pct?: number;
  status?: string;
  created_at?: string;
  closed_at?: string | null;
  account_value_after?: number | null;
};

export type AutomationLog = {
  id?: number;
  session_id?: string;
  created_at?: string;
  log_type?: string;
  cycle_number?: number;
  data?: Record<string, unknown>;
};

export type AutomationStatePayload = {
  isRunning?: boolean;
  is_running?: boolean;
  executionMode?: string;
  execution_mode?: string;
  currentCycle?: number;
  current_cycle?: number;
  sessionId?: string | null;
  session_id?: string | null;
  started_at?: string | null;
  last_cycle_at?: string | null;
  include_entry_timing_15m_chart?: boolean;
  reverse_order_enabled?: boolean;
  circuitBreakerTriggered?: boolean;
  circuit_breaker_triggered?: boolean;
  circuitBreakerReason?: string | null;
  circuit_breaker_reason?: string | null;
  positions?: AutomationPosition[];
  trades?: AutomationTrade[];
};
