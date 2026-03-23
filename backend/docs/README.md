# Backend Module Docs

Design notes for backend modules and infrastructure building blocks.
These documents explain responsibilities, contracts, data flow, and implementation decisions.

## Pipeline Modules

| Doc | Module | Pipeline Stage |
|---|---|---|
| `ema_scanner.md` | EMA scanner | SCAN |
| `quant_scanner.md` | Quant scanner | SCAN |
| `dynamic_assets.md` | Dynamic monitored asset resolution | SCAN |
| `ema_state_manager.md` | Signal detection and trigger events | SIGNAL |
| `llm_caller.md` | LLM provider adapter | DECIDE |
| `llm_response_worker.md` | Response parsing into execution ideas | DECIDE |
| `llm_pipeline.md` | LLM caller + parser wrapper | DECIDE |
| `trade_guard.md` | Pre-execution validation and sizing | VALIDATE |
| `circuit_breaker.md` | Final safety gate | VALIDATE |
| `trade_executor.md` | Exchange execution via CCXT | EXECUTE |

## Infrastructure Modules

| Doc | Module |
|---|---|
| `api_infra.md` | HTTP API conventions, versioning, and error schema |
| `realtime_api.md` | Socket.IO event envelope and topic routing |
| `queue_worker.md` | Queue worker policy, TTL, and concurrency |
| `database_schema.md` | PostgreSQL schema reference |
| `image_uploader.md` | Pluggable image host adapter layer |
| `chart_generator.md` | Chart rendering and overlay pipeline |
| `portfolio_exchange.md` | Exchange account management and connector design |
| `ai_providers.md` | LLM provider configuration and OpenAI-compatible endpoints |
| `market_settings.md` | Monitored assets and interval configuration |
| `monitored_assets.md` | Asset list resolution logic |

## Architecture Plans

| Doc | Purpose |
|---|---|
| `bus-queue-visualization.md` | Event bus and queue flow diagram |
| `multi_account_router_plan.md` | Multi-account and multi-exchange routing design |
| `oi_rank_module_plan.md` | OI-rank module design |
