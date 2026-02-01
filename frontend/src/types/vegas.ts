export type VegasIntervalCrossing = {
  in_tunnel?: boolean;
  bb_upper?: boolean;
  bb_lower?: boolean;
};

export type VegasTimers = {
  position_mgmt_remaining_sec?: number;
  position_mgmt_total_sec?: number;
  bb_rejection_remaining_sec?: number;
  bb_rejection_total_sec?: number;
  bb_touch_count?: number;
  bb_touch_direction?: "UPPER" | "LOWER" | null;
  bb_touch_required?: number;
  ema_resonance_remaining_sec?: number;
  ema_resonance_total_sec?: number;
  bb_exit_warning_remaining_sec?: number;
  bb_exit_warning_total_sec?: number;
};

export type VegasTickerState = {
  ticker: string;
  state: "IDLE" | "IN_TUNNEL" | "POSITION_ACTIVE";
  resonance_count?: number;
  active_intervals?: string[];
  interval_crossings?: Record<string, VegasIntervalCrossing>;
  entry_price?: number | null;
  entry_time?: string | null;
  direction?: string | null;
  bb_distance_pct?: number | null;
  bb_rejection_direction?: "UPPER" | "LOWER" | null;
  timers?: VegasTimers;
};

export type VegasStateUpdate = {
  states: VegasTickerState[];
};
