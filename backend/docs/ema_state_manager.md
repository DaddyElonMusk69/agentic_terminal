# EMA State Manager

## Purpose
The EMA state manager owns the stateful logic that converts raw EMA/BB scan
signals into higher-level trigger events. It does not build prompts, fetch
quant data, or render charts. It only decides when to request a prompt and
what the prompt should include (ticker, intervals, charts, template).

## Responsibilities
- Track per-ticker EMA resonance and BB touch counts.
- Apply timers and cooldowns for each trigger type.
- Align state to the monitored assets snapshot each scan cycle.
- Emit trigger events that drive prompt building.
- Shape prompt build requests (ticker, intervals, charts, template).

## Inputs
- `signals`: EMA/BB signals from the EMA scanner (single scan cycle).
- `monitored_assets`: snapshot of monitored symbols (global truth).
- `open_positions`: snapshot of open positions (portfolio module).
- `config`: state manager configuration (DB-backed).

## Outputs
- `EmaStateEvent`:
  - `symbol`
  - `trigger_reason`
  - `resonance_count`
  - `active_intervals`
  - `bb_signal_intervals`
  - `direction_signal`
  - `previous_resonance`, `previous_intervals`
- `EmaTickerState` snapshots for UI/debugging.

## Snapshot Policy
The state manager receives a full snapshot per scan cycle and prunes any
state for symbols not in the snapshot. This avoids edge cases where monitored
assets change mid-scan. The prompt builder always uses the exact intervals
from the event snapshot.

## Trigger Types and Criteria
- NEW_RESONANCE
  - resonance_count >= min_resonance and previous_resonance < min_resonance
  - ema_resonance_cooldown_seconds elapsed
- RESONANCE_INCREASE
  - resonance_count > previous_resonance
  - ema_resonance_cooldown_seconds elapsed
- STRUCTURE_SHIFT
  - resonance_count unchanged, active_intervals changed
  - ema_resonance_cooldown_seconds elapsed
- RESONANCE_REFRESH
  - resonance_count >= min_resonance
  - ema_resonance_cooldown_seconds elapsed
- BB_REJECTION_ENTRY
  - BB touches on HTF intervals only
  - consecutive touches >= bb_rejection_min_touches
  - bb_rejection_cooldown_seconds elapsed
  - direction is SHORT for upper band, LONG for lower band
- POSITION_MANAGEMENT
  - position open
  - position_check_interval_seconds elapsed
  - no BB exit proximity
- BB_EXIT_WARNING
  - position open
  - BB exit proximity on HTF intervals
  - bb_exit_warning_cooldown_seconds elapsed

## Configuration
Defaults (from `DEFAULT_EMA_STATE_MANAGER_CONFIG`):
- min_resonance: 2
- ema_resonance_cooldown_seconds: 600
- bb_rejection_cooldown_seconds: 1200
- bb_exit_warning_cooldown_seconds: 600
- position_check_interval_seconds: 1800
- bb_rejection_min_touches: 10
- bb_htf_min_interval_minutes: 480 (8h)

Recommended ranges:
- cooldowns: 60 to 3600 seconds
- min_resonance: 1 to 5
- bb_rejection_min_touches: 1 to 30
- bb_htf_min_interval_minutes: set via interval (default 8h)

## Prompt Builder Request Contract
Templates are stored in the `prompt_templates` table. The state manager selects
the template based on trigger type and user configuration. The prompt builder
only consumes the explicit request payload; it does not infer intervals or
charts.

### Request payload schema (conceptual)
- `request_id`
- `template_id` (DB primary key, required)
- `template_version` (optional)
- `trigger_reason`
- `tickers` (explicit list)
- `intervals` (explicit list, ordered)
- `chart_requests` (list of `{interval, candles, overlays}`)
- `quant_fields` (optional list for selective packets)
- `template_context` (variables for safe formatting)
- `quant_snapshot_id` (optional, for consistent data snapshots)
- `trace_id` (optional)

### Interval Selection Rules
Intervals are always derived by the state manager:
- Resonance triggers: use the resonating intervals only.
- Position management: use all monitored intervals (global truth).
- BB triggers: use the signal interval plus all monitored intervals higher
  than the signal interval.

Higher interval calculation:
- Normalize monitored intervals to minutes.
- Include intervals strictly greater than the signal interval.
- Keep the list ordered from lower to higher.

### Prompt Queue Policy (Bus Worker)
- Prompt build requests are queued and consumed with concurrency = 1.
- Each request expires after 20 minutes (TTL).
- Stale requests are dropped when the worker picks them up.
- Requests are marked `in_progress` at start and finalized on completion.

### Request Examples
NEW_RESONANCE / RESONANCE_INCREASE / STRUCTURE_SHIFT:
```json
{
  "request_id": "7a1b5d7a-2f1a-4d8c-9a1d-7b0b0e3a9c1f",
  "template_id": 101,
  "trigger_reason": "new_resonance",
  "tickers": ["BTC"],
  "intervals": ["2h", "4h"],
  "chart_requests": [
    {"interval": "2h", "candles": 50},
    {"interval": "4h", "candles": 50}
  ],
  "template_context": {"ticker": "BTC", "resonance_count": 2}
}
```

POSITION_MANAGEMENT:
```json
{
  "request_id": "b65f5e0c-4a58-4b17-9f5d-0c2c53a9841f",
  "template_id": 201,
  "trigger_reason": "position_management",
  "tickers": ["BTC"],
  "intervals": ["2h", "4h", "8h"],
  "chart_requests": [
    {"interval": "2h", "candles": 50},
    {"interval": "4h", "candles": 50},
    {"interval": "8h", "candles": 50}
  ],
  "template_context": {"ticker": "BTC"}
}
```

BB_EXIT_WARNING (signal on 8h with monitored intervals 2h, 4h, 8h, 12h, 1d):
```json
{
  "request_id": "c4c20f3f-91f2-45b4-9d30-9ccf28c2c9b1",
  "template_id": 301,
  "trigger_reason": "bb_exit_warning",
  "tickers": ["BTC"],
  "intervals": ["8h", "12h", "1d"],
  "chart_requests": [
    {"interval": "8h", "candles": 50},
    {"interval": "12h", "candles": 50},
    {"interval": "1d", "candles": 50}
  ],
  "template_context": {"ticker": "BTC"}
}
```

BB_REJECTION_ENTRY (signal on 8h with monitored intervals 2h, 4h, 8h, 12h, 1d):
```json
{
  "request_id": "f3d33a9d-6f43-4c0d-8b5a-8f8a8a2a9a1a",
  "template_id": 401,
  "trigger_reason": "bb_rejection_entry",
  "tickers": ["BTC"],
  "intervals": ["8h", "12h", "1d"],
  "chart_requests": [
    {"interval": "8h", "candles": 50},
    {"interval": "12h", "candles": 50},
    {"interval": "1d", "candles": 50}
  ],
  "template_context": {"ticker": "BTC"}
}
```
