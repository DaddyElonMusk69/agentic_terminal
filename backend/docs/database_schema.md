# Database Schema Overview

This document defines the high-level database structure for the new backend.
It focuses on stable boundaries and avoids coupling to any single exchange.

## Conventions
- Primary keys: UUID strings (or integer where noted).
- Timestamps: `created_at`, `updated_at` in UTC.
- JSONB: used for flexible payloads where schemas evolve.
- Soft deletes: optional for long-lived entities (add `deleted_at`).

## Exchange and Portfolio

### exchange_accounts
- `id` (PK)
- `name`
- `exchange` (e.g., binance, okx)
- `is_active`
- `is_testnet`
- `wallet_address` (optional)
- `validation_status` (`unvalidated`, `valid`, `invalid`)
- `last_validated_at` (optional)
- `validation_error` (optional)
- `created_at`, `updated_at`

### exchange_credentials
- `id` (PK)
- `account_id` (FK -> exchange_accounts.id, unique)
- `api_key_encrypted`
- `api_secret_encrypted`
- `passphrase_encrypted`
- `agent_key_encrypted` (optional)
- `created_at`, `updated_at`

### account_setup
- `id` (PK)
- `portfolio_exposure_pct`
- `created_at`, `updated_at`

### portfolio_snapshots (optional)
- `id` (PK)
- `account_id` (FK)
- `captured_at`
- `account_state` (JSONB)
- `positions` (JSONB)

## Market Data

### market_symbols
- `id` (PK)
- `symbol` (e.g., BTCUSDT)
- `exchange`
- `asset_type` (spot, perp)
- `base_asset`, `quote_asset`

### market_candles
- `id` (PK)
- `symbol_id` (FK -> market_symbols.id)
- `timeframe` (e.g., 1m, 15m)
- `timestamp`
- `open`, `high`, `low`, `close`, `volume`
- `open_interest` (optional)
- `cvd` (optional)
- Unique index: (symbol_id, timeframe, timestamp)

### funding_rates
- `id` (PK)
- `symbol_id` (FK)
- `timestamp`
- `rate`

### depth_snapshots
- `id` (PK)
- `symbol_id` (FK)
- `timestamp`
- `depth` (JSONB)

## Scanner (EMA + Quant)

### scanner_profiles
- `id` (PK)
- `name`
- `type` (ema, quant)
- `config` (JSONB)
- `is_active`

### ema_scanner_config
- `id` (PK)
- `tolerance_pct`
- `created_at`, `updated_at`

### ema_scanner_lines
- `id` (PK)
- `length`
- `created_at`, `updated_at`

### monitored_coins
- `id` (PK)
- `symbol`
- `display_order`
- `created_at`, `updated_at`

### monitored_assets
- `id` (PK)
- `symbol`
- `created_at`, `updated_at`

### monitored_intervals
- `id` (PK)
- `interval`
- `display_order`
- `created_at`, `updated_at`

### dynamic_asset_config
- `id` (PK)
- `enabled`
- `api_key_encrypted`
- `sources` (JSONB)
- `refresh_interval_seconds`
- `last_fetch_at`
- `last_success_at`
- `last_success_assets` (JSONB)
- `created_at`, `updated_at`

### scanner_runs
- `id` (PK)
- `profile_id` (FK)
- `started_at`, `finished_at`
- `status`

### scanner_signals
- `id` (PK)
- `run_id` (FK)
- `symbol_id` (FK)
- `timestamp`
- `score`
- `payload` (JSONB)

## Backtest

### backtest_runs
- `id` (PK)
- `strategy`
- `config` (JSONB)
- `started_at`, `finished_at`
- `status`

### backtest_results
- `id` (PK)
- `run_id` (FK)
- `metrics` (JSONB)
- `equity_curve` (JSONB)

### backtest_parameter_sets
- `id` (PK)
- `run_id` (FK)
- `parameters` (JSONB)
- `score`

## Automation

### automation_sessions
- `id` (PK)
- `account_id` (FK)
- `config` (JSONB)
- `started_at`, `ended_at`
- `status`

### automation_cycles
- `id` (PK)
- `session_id` (FK)
- `started_at`, `ended_at`

### automation_decisions
- `id` (PK)
- `cycle_id` (FK)
- `decision` (JSONB)
- `created_at`

### automation_trades
- `id` (PK)
- `cycle_id` (FK)
- `symbol_id` (FK)
- `action`, `size`, `price`
- `exchange_order_id`
- `status`

### automation_logs
- `id` (PK)
- `session_id` (FK)
- `level`
- `message`
- `created_at`

## AI Agent

### agent_conversations
- `id` (PK)
- `title`
- `analysis_type`
- `provider`
- `model`
- `created_at`, `updated_at`

### agent_messages
- `id` (PK)
- `conversation_id` (FK)
- `role`
- `content`
- `tokens_used`
- `latency_ms`
- `created_at`

### agent_provider_configs
- `id` (PK)
- `provider`
- `api_key_encrypted`
- `default_model`
- `is_enabled`
- `settings` (JSONB)
- `created_at`, `updated_at`

### prompt_templates
- `id` (PK)
- `name`
- `intro`
- `response_format`
- `quant_fields` (JSONB)
- `chart_defaults` (JSONB)
- `is_default`
- `created_at`, `updated_at`

### context_builder_configs
- `id` (PK)
- `name`
- `intro`, `requirements`
- `data_selections` (JSONB)
- `field_selections` (JSONB)
- `chart_config` (JSONB)

## Config and Settings

### app_settings
- `key` (PK)
- `value` (JSONB)

### trade_guard_config
- `id` (PK)
- `min_confidence`
- `min_position_size`
- `sl_min_roe`, `sl_max_roe`
- `dust_threshold_usd`
- `leverage_tiers` (JSONB)
- `created_at`, `updated_at`

### feature_flags
- `key` (PK)
- `is_enabled`
- `metadata` (JSONB)

## Background Jobs

### jobs
- `id` (PK)
- `type`
- `status` (queued, running, failed, completed)
- `payload` (JSONB)
- `result` (JSONB)
- `created_at`, `updated_at`

### prompt_build_requests
- `id` (PK)
- `status` (queued, in_progress, done, failed, dropped)
- `payload` (JSONB)
- `result` (JSONB)
- `error`
- `created_at`, `updated_at`
- `started_at`, `completed_at`
- `expires_at`

### llm_queue_requests
- `id` (PK)
- `status` (queued, in_progress, done, failed, dropped)
- `payload` (JSONB)
- `result` (JSONB)
- `error`
- `created_at`, `updated_at`
- `started_at`, `completed_at`
- `expires_at`

### order_queue_requests
- `id` (PK)
- `status` (queued, in_progress, done, failed, dropped)
- `payload` (JSONB)
- `result` (JSONB)
- `error`
- `created_at`, `updated_at`
- `started_at`, `completed_at`
- `expires_at`

### image_uploader_config
- `id` (PK)
- `provider`
- `api_key`
- `created_at`, `updated_at`

### outbox_messages
- `id` (PK)
- `message_type` (command, event)
- `topic`
- `payload` (JSONB)
- `status` (pending, processed, failed)
- `error`
- `created_at`, `processed_at`
