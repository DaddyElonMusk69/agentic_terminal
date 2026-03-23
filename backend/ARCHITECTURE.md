# New Backend Architecture (FastAPI + Socket.IO)

This document defines the target architecture for the new standalone backend
to be built under `backend/`. It is intentionally decoupled from the current
Flask system and the existing frontend, with a clean, consistent API contract.

## Goals
- Clean, stable architecture with explicit boundaries and minimal coupling.
- First-class async support for I/O heavy workloads.
- Unified real-time channel for all streaming events.
- Clear separation between HTTP APIs, real-time APIs, and background jobs.
- Secure by default, with consistent validation and observability.

## Non-Goals
- Backward compatibility with the existing Flask backend or legacy frontend.
- One-to-one parity with legacy endpoints or payloads.
- In-process background work in the API server.

## Core Principles
- Clean architecture: domain and application logic do not depend on frameworks.
- Explicit contracts: OpenAPI for HTTP, event schemas for realtime.
- Single source of truth for data and configuration.
- Testability: pure domain logic, deterministic services, isolated I/O.

## Tech Stack
- Web framework: FastAPI (ASGI)
- Realtime: Socket.IO (python-socketio, ASGI integration)
- ORM: SQLAlchemy 2.0 (async) + Alembic migrations
- Database: PostgreSQL (primary), Redis (cache, pub/sub, task queue)
- Task queue: Taskiq (worker pool) with Redis broker (primary), or Dramatiq/Celery if needed
- Observability: structlog + OpenTelemetry + Prometheus metrics
- Auth: JWT (access + refresh), optional API keys for system integrations

## High-Level Architecture

HTTP API (FastAPI)
  - versioned REST endpoints
  - request validation via Pydantic
  - centralized error handling

Realtime API (Socket.IO)
  - single consolidated namespace and event envelope
  - server-side topic routing and authorization
  - pub/sub bridge for horizontal scaling

Background Workers
  - long-running tasks (scanner, backtests, automation)
  - scheduled tasks (cache cleanup, data refresh)
  - publish progress to realtime channel

Data Stores
  - PostgreSQL for durable state and configuration
  - Redis for caching, coordination, and realtime fanout

## Directory Layout

backend/
  src/
    app/
      main.py                  # FastAPI + Socket.IO ASGI app
      settings.py              # Pydantic settings
      api/                     # HTTP routers (versioned)
      realtime/                # Socket.IO handlers and event routing
      domain/                  # Pure domain models and logic
      application/             # Use cases / services
      infrastructure/          # DB, external providers, adapters
      jobs/                    # Background tasks and schedulers
      common/                  # Shared utilities (errors, logging, ids)
    tests/
  alembic/
  pyproject.toml

## Bounded Contexts (Initial)
- Market Data: candles, OI/CVD, cache management, snapshots
- Scanner: signal generation, profiles, resonance scoring
- Automation: orchestrator, decision engine, circuit breaker
- Backtest: simulation runs, optimization, data pipelines
- Agent: prompt/context builder, AI sessions, chat history
- Portfolio: exchange accounts, positions, PnL
- Config: global settings, user preferences, feature flags

Each context exposes:
- Domain entities and rules (pure Python)
- Application services (use cases)
- Infrastructure adapters (DB, APIs, LLMs)
- API surface (HTTP + realtime events)

## API Design

### HTTP
- Versioning: `/api/v1/...`
- Pagination: cursor-based where possible, offset for simple lists
- Request ID: `X-Request-ID` accepted and echoed
- Error schema:
  - `{ "error": { "code": "...", "message": "...", "details": {...} } }`
- Consistent response envelope:
  - `{ "data": ... , "meta": {...} }`
- Reference: `backend/docs/api_infra.md`

#### Portfolio & Exchange (v1)
- Accounts: `/api/v1/portfolio/exchanges`
- Active account: `/api/v1/portfolio/exchanges/active`
- Validate credentials: `/api/v1/portfolio/exchanges/{account_id}/validate`
- Snapshot: `/api/v1/portfolio/snapshot`
- Realtime topics: `portfolio.exchange.*`

### Realtime (Socket.IO)
- Single namespace: `/realtime`
- Unified event channel: `event`
- Event envelope:
  - `{ "v": 1, "type": "event", "topic": "scanner.signal", "payload": {...}, "ts": "...", "request_id": "..." }`
- Subscriptions: `subscribe`/`unsubscribe` to topic rooms
- Topic prefixes:
  - `market.*`, `scanner.*`, `automation.*`, `backtest.*`, `agent.*`, `portfolio.*`
- Authorization:
  - token on connect + per-topic access control
- Scaling:
  - Redis pub/sub for fanout across multiple API instances
- Reference: `backend/docs/realtime_api.md`

## Background Jobs
- All heavy processing runs in workers, never in the API process.
- Workers publish progress to Socket.IO via Redis pub/sub.
- Job IDs are first-class and queryable via HTTP.
- Queue worker module reference: `backend/docs/queue_worker.md`.

## Image Uploads
- Prompt builder image uploads are handled by a pluggable uploader module.
- Provider reference: `backend/docs/image_uploader.md`.

## Dynamic Assets (Global Monitored List)
- Dynamic assets can override the manual monitored list via multi-source feeds.
- Only enabled when a Binance account is active.
- Monitored assets resolver always includes open positions to support position management.
- Module references: `backend/docs/dynamic_assets.md`, `backend/docs/market_settings.md`, `backend/docs/monitored_assets.md`.

## LLM Caller
- The LLM caller is a thin adapter for OpenAI-compatible `chat/completions`.
- It reads image URLs from `chart_snapshots` only.
- Module reference: `backend/docs/llm_caller.md`.

## LLM Response Worker
- Parses LLM responses into execution ideas.
- Handles JSON extraction and validation.
- Module reference: `backend/docs/llm_response_worker.md`.

## LLM Execution Pipeline
- Thin wrapper: LLM caller -> response worker.
- Module reference: `backend/docs/llm_pipeline.md`.

## Trade Guard
- Validates and adjusts execution ideas before trading.
- Configured via DB and portfolio exposure setup.
- Module reference: `backend/docs/trade_guard.md`.

## Circuit Breaker
- Final safety gate before execution (currently pass-through).
- Module reference: `backend/docs/circuit_breaker.md`.

## Trade Executor
- Executes orders via CCXT using the active portfolio account.
- Module reference: `backend/docs/trade_executor.md`.

## Message Bus and Outbox
- Commands and events flow through a message bus, not direct service calls.
- The outbox table persists messages for reliable delivery.
- A worker dispatches outbox messages to Redis pub/sub.
- Long-running workflows (automation) should be modeled as state transitions.

### Outbox Delivery (Reliability)
- Producers write domain state + outbox record in the same DB transaction.
- Dispatcher reads `pending` rows (FIFO, `FOR UPDATE SKIP LOCKED`), publishes, then marks `processed`.
- Failed publishes remain `pending` or are marked `failed` with error for retry.
- Consumers should be idempotent (use message id / request_id).

### Bus Worker Queue Policy (Prompt Builder)
- Prompt build requests are queued and consumed by a dedicated worker.
- Concurrency is fixed at 1 to avoid overwhelming the LLM and external services.
- Each request has a TTL of 20 minutes; stale requests are dropped on pickup.
- Requests are marked `in_progress` when work starts and finalized on completion.
- Lifecycle: `queued` -> `in_progress` -> `done` / `failed` / `dropped`.

## Automation Pipeline (BUS Architecture)
The automation pipeline is event-driven with dedicated queue workers for each
critical stage. EMA and Quant scanners run on independent intervals.

### Components
- Scheduler: emits `scanner.ema.tick` and `scanner.quant.tick` based on configured intervals.
- EMA scanner: consumes tick, publishes `scanner.ema.signals`.
- EMA state manager: consumes signals, updates state, emits `automation.prompt.requested`.
- Prompt build queue: stores requests in order (TTL 20m, concurrency=1).
- Prompt builder: consumes queue, assembles prompt (charts + quant data + template), emits `automation.prompt.completed`.
- LLM queue: stores prompts for LLM calls (TTL 20m, concurrency=1).
- LLM pipeline: consumes LLM queue, calls model, parses response, emits `automation.llm.completed`.
- Order queue: stores execution ideas (TTL 5 minutes, concurrency=1).
- Execution pipeline: trade guard -> circuit breaker -> trade executor; emits `trade.executed` / `trade.failed`.

### Prompt Builder Internal Flow
- Charts: render requested ticker/interval charts, upload, build `chart_snapshots`.
- Quant data: wait for quant cache (retry every 10s) until all intervals are present.
- Optional portfolio/position fields: merged when available (future).
- Template: apply intro/role + response format, produce final prompt.

### Event Contracts (Minimum)
- `automation.prompt.requested`: `{request_id, ticker, intervals, template_id, chart_requests, trigger_reason, trace_id}`
- `automation.prompt.completed`: `{request_id, prompt_text, chart_snapshots, quant_data, trace_id}`
- `automation.llm.completed`: `{request_id, execution_ideas, considerations, trace_id}`
- `automation.order.queued`: `{request_id, execution_idea, trace_id}`

### Execution Modes
- `prompt_test`: stop after prompt build (no LLM enqueue).
- `dry_run`: stop before trade execution (runs trade guard + circuit breaker).
- `production`: full flow through trade execution.
- `execution_mode` is carried in queue payloads and included in automation events.

### Concurrency + Ordering
- EMA and Quant scans run independently on their own schedules.
- Prompt build, LLM, and order execution queues are single-consumer to enforce order.
- State manager uses a snapshot of monitored assets per scan to avoid mid-scan list changes.

## Data Storage
- PostgreSQL is the source of truth for all persistent data.
- Redis is used for caching, rate limiting, session state, and pub/sub.
- Time-series data can be split to a dedicated store if needed later.
- Schema reference: `backend/docs/database_schema.md`.

## Observability
- Structured logs with request_id and correlation_id.
- Metrics: API latency, job durations, queue depth, error rates.
- Tracing: HTTP + jobs + external API calls.

## Security
- Secrets via environment variables or secret manager (no plaintext in DB).
- Encryption at rest for sensitive fields when required.
- Strict input validation and rate limiting for public APIs.
- Separate service roles for API and worker runtime.
- `BACKEND_CREDENTIALS_KEY` is required for encrypting exchange credentials.

## Deployment
- ASGI server: `uvicorn` or `gunicorn -k uvicorn.workers.UvicornWorker`
- Horizontal scaling for API with Redis pub/sub
- Independent worker scale for heavy workloads

## Testing Strategy
- Unit tests for domain logic and services.
- Integration tests for API + DB + Redis.
- Contract tests for realtime event schemas.
- Prefer the test pyramid: many fast unit tests, a few integration tests, and minimal end-to-end tests.
- Treat realtime events as contracts: validate envelope + topic schemas with Pydantic models.
- Add a regression test for each bug fix.
- Mark slow realtime socket integration tests to keep the default test run fast.

## Module Inventory (Built So Far)
- Portfolio & exchange (active account + CCXT connector + DB-backed accounts)
- EMA scanner (EMA + BB signals)
- EMA state manager (signal state + trigger events)
- Quant scanner (data fetch + cached metrics)
- Market settings (monitored assets + monitored intervals API)
- Chart generator (unified renderer)
- AI providers (LLM provider settings + custom OpenAI-compatible endpoints)
- Prompt builder (templates + chart uploads + queue worker)
- Image uploader (filesystem + ImgBB + freeimage.host)
- Queue worker (prompt build queue + TTL policy)
- LLM caller (OpenAI-compatible)
- LLM response worker (JSON extraction + execution ideas)
- LLM execution pipeline (caller -> parser wrapper)
- Trade guard (rules/modifiers + DB config + portfolio exposure)
- Circuit breaker (pass-through skeleton)
- Trade executor (CCXT order execution wrapper)

## Supporting DB/Config Modules
- Prompt templates (`prompt_templates`)
- Prompt build queue (`prompt_build_requests`)
- Image uploader config (`image_uploader_config`)
- EMA scanner config (`ema_scanner_config`, `ema_scanner_lines`, monitored lists)
- Market settings (`monitored_assets`, `monitored_intervals`)
- Model provider config (`agent_provider_configs`)
- EMA state manager config (`ema_state_manager_config`)
- Account setup (`account_setup` with `portfolio_exposure_pct`)
- Trade guard config (`trade_guard_config`)

## Prompt Builder (Legacy Reference + New Design)
This section captures the legacy workflow and the redesigned workflow for the
prompt builder. The state manager will call the prompt builder with different
tickers, intervals, and chart requests based on the trigger reason.

Legacy references:
- `app/domain/services/vegas_state_manager.py`
- `app/application/services/automation_workers/prompt_worker.py`
- `app/services/agent_context/prompt_builder.py`
- `app/services/agent_context/workers/vegas_charts_worker.py`

### Legacy Workflow Summary
- Prompt building is initiated by the automation worker.
- Template customization is loaded from DB (intro, requirements, data selections).
- Quant data is assembled into JSON, then charts are generated and uploaded.
- Final prompt is intro + JSON payload + response requirements.
- Vegas strategy uses a special prompt builder path that injects OI/CVD data,
  Vegas charts, and trigger-specific context.

### Legacy State Manager Trigger Policy
The Vegas state manager emits `SignalEvent` with `trigger_reason`, `active_intervals`,
and `bb_signal_intervals`. Key rules:
- Entry threshold: EMA resonance requires at least 2 distinct intervals.
- EMA resonance cooldown: 10 minutes.
- BB rejection entry: 10 consecutive touches + 20 minute cooldown.
- Position management: periodic every 30 minutes.
- BB exit warning: 10 minute cooldown.
- BB filters only consider 8h+ intervals due to `_is_interval_gte_4h` threshold
  of 480 minutes (note the legacy mismatch between comments and behavior).

### Legacy Prompt Builder Request Shaping
This is the logic that decides which intervals and charts to request based on
the trigger reason (from `PromptWorker.build_vegas_prompt`):
- NEW_RESONANCE / RESONANCE_INCREASE / STRUCTURE_SHIFT / RESONANCE_REFRESH
  - intervals_to_scan: `signal_event.active_intervals`
  - charts: none by default (entry triggers skip charts in legacy)
- POSITION_MANAGEMENT
  - intervals_to_scan: all tracked intervals (from TrackedIntervalsManager),
    fallback to `15m`, `1h`, `4h` if not available
  - charts: yes, only for the triggered ticker
  - chart configs: `{interval: 50 candles}` for each interval in `intervals_to_scan`
- BB_EXIT_WARNING
  - intervals_to_scan: `signal_interval` plus all higher tracked intervals
    (via `get_interval_and_higher`)
  - charts: yes, only for the triggered ticker
  - chart configs: `{interval: 50 candles}` for each interval in `intervals_to_scan`
- BB_REJECTION_ENTRY
  - intervals_to_scan: `signal_interval` plus all higher tracked intervals
  - charts: none by default (entry trigger)

Note: The legacy behavior above is inconsistent across flows and mixes
prompt assembly with chart generation; the new backend will use explicit
state-manager-driven requests instead of inheriting these defaults.

### New Prompt Builder (BUS-Oriented Redesign)
The new prompt builder is a stateless orchestrator that assembles prompts from
templates, quant data, and charts, without directly calling scanners or uploaders.

Core events:
- `PromptBuildRequested`
- `QuantSnapshotRequested` / `QuantSnapshotReady`
- `ChartRenderRequested` / `ChartRendered`
- `ImageUploadRequested` / `ImageUploaded`
- `PromptBuilt` / `PromptBuildFailed`

Template structure (3 parts, stored in DB):
- Intro and role
- Quant data requirements (fields + intervals + tickers)
- Response format
Multiple templates are supported, and the state manager selects which template
to use for each trigger reason.

Prompt builder request schema (conceptual):
- `request_id`
- `template_id` (DB primary key, required)
- `template_version` (optional, for rollback)
- `trigger_reason` (from state manager)
- `tickers` (explicit list, usually one ticker per trigger)
- `intervals` (explicit list, ordered)
- `chart_requests` (list of `{interval, candles, overlays}`; empty means no charts)
- `quant_fields` (optional list for selective packets)
- `template_context` (variables for safe formatting)
- `quant_snapshot_id` (optional, for consistent data snapshots)
- `trace_id` (optional, for correlation)

The concrete prompt build payload and trigger-to-interval mapping live in the
state manager doc: `backend/docs/ema_state_manager.md`.

### Notes for Implementation
- The prompt builder should never wait on scanners; it should emit a request
  for missing data and retry when `QuantSnapshotReady` arrives.
- The chart generator should only render from provided data. Uploads are handled
  by a separate image host adapter.
- The state manager owns request shaping (tickers, intervals, chart profiles),
  not the prompt builder.
