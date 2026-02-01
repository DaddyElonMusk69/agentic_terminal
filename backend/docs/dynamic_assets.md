# Dynamic Assets

Dynamic assets allow the monitored list to be sourced from external feeds instead
of the manual list. When enabled, the dynamic list becomes the global truth for
all scanners and automation workflows.

## Provider
- Nofxos multi-source feeds (`ai500`, `ai300`, `oi_top`, `oi_low`).
- Sources are merged and deduplicated on each refresh.

## Config
- `enabled`: toggles dynamic list usage (requires active Binance account).
- `api_key`: stored encrypted in the database.
- `sources`: source-specific options (limits, levels, durations).
- `refresh_interval_seconds`: 60-3600 seconds (default 600 / 10 minutes).

## Refresh + Stale Policy
- The service refreshes at the configured interval.
- Last successful snapshot is reused for up to 30 minutes when refresh fails.
- After the stale window, the dynamic list is treated as unavailable.

## API
- `GET /api/v1/market/dynamic-assets`
- `PUT /api/v1/market/dynamic-assets`
- `POST /api/v1/market/dynamic-assets/test`
