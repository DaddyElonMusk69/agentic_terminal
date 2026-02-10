# Multi-Account Order Routing Plan

Goal: add multi-account, multi-exchange order placement with minimal disruption to existing pipeline. The new router/middleware will be the single entry point for trade execution, while the current executor becomes a per-account driver.

## Current constraints (snapshot)
- Trading uses a single active account (`exchange_accounts.is_active`).
- `TradeExecutorService` pulls only the active account and executes via CCXT.
- Portfolio snapshot, prompt builder, automation positions, and risk management all assume a single account.
- Some Binance-specific quirks are handled inside CCXT trade executor (algo orders, positionSide, reduceOnly fallbacks).

## Design principles
- Minimal invasive changes to the existing pipeline.
- Backward-compatible defaults (single-account still works with no config changes).
- Unified execution path: router orchestrates, executors perform per-account placement.
- Exchange quirks live in the router or exchange drivers, not scattered across the pipeline.
- Observability: per-account results with aggregate status.

## High-level architecture

### New module: Order Router
- Input: `ExecutionIdea` (global intent).
- Output: `AggregateExecutionResult` (per-account results + summary).
- Responsibilities:
  - Resolve active trading accounts.
  - Apply routing rules (weights, caps, exchange compatibility).
  - Split decision into per-account `ExecutionIdea` instances.
  - Execute via exchange drivers (CCXT, or exchange-specific drivers when needed).
  - Collect per-account results + errors.

### Exchange Drivers
- CCXT driver remains primary.
- Exchange-specific quirks (Binance algo endpoints, positionSide, reduceOnly fallback) are consolidated in one layer.
- Router chooses driver per account based on `account.exchange`.

### Two-phase guard
- Global guard once per trade for intent validation.
- Per-account guard for account-specific limits (margin, exposure, exchange min notional, existing positions).

## Backend changes (minimal viable scope)

### 1) Data model
Add multi-account activation while preserving a single "primary" account.

- `exchange_accounts`:
  - `is_active` = primary account (existing behavior)
  - add `is_trading_active` = included in router execution
  - optional `routing_weight` (float) or `allocation_pct`

### 2) Repository / service extensions
- Exchange repository:
  - `list_trading_accounts()`
  - keep `get_active_account()` for backward compatibility
- Portfolio service:
  - `get_portfolio_snapshot()` unchanged (primary)
  - add `get_portfolio_snapshots()` for all trading accounts

### 3) Router service
New app service, e.g. `app/application/order_router/service.py`:

Inputs:
- `ExecutionIdea` (global intent)
- optional routing policy (equal, weighted, capped)

Outputs:
- `AggregateExecutionResult`:
  - summary: `success`, `partial`, `failed`
  - list of per-account results

Behavior:
- Split sizes by routing policy.
- Normalize per-account constraints (risk config, exchange min notional).
- Execute with per-exchange driver.
- Aggregate results and errors.

### 4) Execution pipeline wiring
- `OrderQueueWorker` calls router instead of `TradeExecutorService`.
- Outbox events emit per-account results (include `account_id`, `exchange`).
- For dry_run / prompt_test, router still returns simulated per-account results.

### 5) Risk config per account
- Add `risk_management_account_config` table keyed by account_id.
- Risk management service uses account-level exposure_pct when available, else global.
- Trade guard consumes per-account exposure for per-account guard.

## Frontend changes (targeted)

### Exchange Modal
- Allow multiple accounts to be toggled as "active for trading".
- Keep a primary account selector for existing single-account UX.
- Optional weight input (default equal split).

### Automation View
- Positions card:
  - add account selector dropdown (All accounts / specific account)
  - aggregate PnL + exposure for "All accounts"

### Risk Management
- Add account selector for per-account exposure config.
- Show aggregate summary when "All accounts" is selected.

## Execution policy (100 accounts)
- Two-phase guard: global once, account-specific per account.
- Price snapshot per exchange for consistent split sizing.
- Concurrency throttling per exchange (semaphores / rate limits).
- Partial success is normal; UI should show per-account status.

## Rollout strategy
1) Add `is_trading_active` + repo API changes (no functional change).
2) Implement router with a single account path (wired but no split).
3) Extend router to multi-account split (behind feature flag).
4) Add portfolio multi-snapshot endpoint and UI account selector.
5) Add per-account risk config.
6) Enable multi-account execution and monitor results.

## Open decisions
- Routing strategy: equal split vs. weighted vs. capped by exposure.
- Primary account: keep for legacy views or fully deprecate.
- Per-account risk scope: exposure only vs. full goal/target settings.
- Exchange-specific drivers: which paths stay CCXT vs. direct API.

