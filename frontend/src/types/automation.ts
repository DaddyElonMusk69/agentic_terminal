export type AutomationSession = {
  id: string;
  status: "running" | "paused" | "stopped";
  startedAt: string;
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
