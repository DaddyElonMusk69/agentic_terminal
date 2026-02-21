# Custom OI Increase/Decrease Module Plan

## Scope
- Standalone module that provides OI increase/decrease rankings for USDT‑M futures.
- On‑demand per interval (1h / 4h / 12h only).
- Persists rankings in DB with refresh + stale windows.
- Minimal changes to dynamic assets: switch OI source between nofx and custom module.

## Key requirements (confirmed)
- Refresh interval: default **30 min**, user configurable, **min 10 min**, **max 12h**.
- Persist **top 100** entries per list in DB.
- API returns **top N** entries (default 5) based on request param.
- Return **null** only if list is stale or empty.
  - If list exists + up to date (even when refreshing), return list.
- OI ranking is **increase/decrease over interval**, not raw OI size.
- Support **metric toggle** for ranking: absolute delta (USD) vs percent delta.

## Data model
### 1) `oi_rank_cache`
Stores computed list per interval/metric/direction.
- `interval` (1h/4h/12h)
- `metric` (abs/pct)
- `direction` (top/low)
- `limit` (stored max list length = 100)
- `payload` (JSON list of entries)
- `updated_at`
- `status` (ready / warming / error)
- `refresh_started_at`
- `last_error`

### 2) `oi_rank_config`
Stores refresh/stale config.
- `refresh_interval_minutes` (default 30, min 10, max 720)
- `stale_ttl_minutes` (default 90)
- `updated_at`

## Refresh vs stale rules
- **fresh**: age ≤ refresh_interval → return list (status ready)
- **soft‑stale**: refresh_interval < age ≤ stale_ttl → return list (status warming) and trigger refresh
- **hard‑stale**: age > stale_ttl → return null (status stale) and trigger refresh

## Binance fetch behavior
- Fetch USDT‑M perpetual symbols from `exchangeInfo`.
- For each symbol: `openInterestHist?period=<interval>&limit=2`.
- Compute delta = last – prev (using `sumOpenInterestValue`).
- Compute delta_pct when possible.

## Ranking strategy
- `metric=abs`: sort by delta value
- `metric=pct`: sort by delta_pct
- `direction=top`: descending
- `direction=low`: ascending

## API endpoints
- `GET /api/v1/oi-rank/top?interval=1h|4h|12h&limit=5&metric=abs|pct`
- `GET /api/v1/oi-rank/low?interval=1h|4h|12h&limit=5&metric=abs|pct`

Response:
```
{
  status: "ready|warming|stale|error",
  interval: "1h",
  metric: "abs",
  direction: "top",
  updated_at: "...",
  refresh_started_at: "...",
  data: { positions: [ { symbol, rank, delta, delta_pct, current, previous } ] } | null
}
```

## Dynamic assets integration (minimal)
- Add an internal OI dynamic‑assets client that uses this module for `oi_top` / `oi_low`.
- Keep nofx for ai500/ai300.
- Switch OI source via config/env (e.g., `BACKEND_DYNAMIC_ASSETS_OI_SOURCE=custom|nofx`).

## Notes
- Cache persisted in DB to survive restarts and multi‑process requests.
- Refresh lock uses `status` + `refresh_started_at` to avoid duplicate refreshes.

