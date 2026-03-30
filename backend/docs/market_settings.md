# Market Settings (Monitored Assets + Intervals)

This module stores the shared monitored asset list and monitored interval list
used by scanners, automation, and charting.

There are now two manual asset sources:
- Manual base assets
- US stock session assets

## Defaults
- Assets: `BTC`
- Intervals: `2h`

Defaults are inserted if the tables are empty. New installs should have these
defaults out of the box.

## API (v1)
- `GET /api/v1/market/monitored-assets`
- `GET /api/v1/market/manual-assets`
- `POST /api/v1/market/manual-assets`
- `DELETE /api/v1/market/manual-assets/{symbol}`
- `GET /api/v1/market/us-stock-assets`
- `POST /api/v1/market/us-stock-assets`
- `DELETE /api/v1/market/us-stock-assets/{symbol}`
- `POST /api/v1/market/monitored-assets`
- `DELETE /api/v1/market/monitored-assets/{symbol}`
- `GET /api/v1/market/monitored-intervals`
- `POST /api/v1/market/monitored-intervals`
- `DELETE /api/v1/market/monitored-intervals/{interval}`

## Payloads

Add asset:
```json
{
  "symbol": "BTC"
}
```

Add US stock session asset:
```json
{
  "symbol": "AAPL"
}
```

Add interval:
```json
{
  "interval": "2h"
}
```

Responses return a list of strings in the `data` field.

### Effective Assets
`GET /api/v1/market/monitored-assets` returns the effective list:
- Dynamic list when enabled and active.
- Manual list otherwise.
- US stock session assets appended during NYSE market hours.

Implementation notes:
- Uses `pandas_market_calendars` when available for holiday-aware and early-close-aware session gating.
- Falls back to a weekday `09:30-16:00` America/New_York check if that dependency is not installed.

Optional query:
- `include_positions=true` to append open positions.

## Dynamic Assets
Dynamic assets can override the manual list with a multi-source feed.
When enabled, the dynamic list becomes the global truth for monitored assets.

Rules:
- Requires an active Binance account to enable.
- Refresh interval is user-configurable (default 10 minutes, range 1-60).
- Last successful snapshot is reused for up to 30 minutes if refresh fails.

### API (v1)
- `GET /api/v1/market/dynamic-assets`
- `PUT /api/v1/market/dynamic-assets`
- `POST /api/v1/market/dynamic-assets/test`

### Payloads

Update config:
```json
{
  "enabled": true,
  "refresh_interval_seconds": 600,
  "api_key": "optional",
  "sources": {
    "ai500": { "enabled": true, "limit": 10 },
    "ai300": { "enabled": false, "limit": 20, "level": "" },
    "oi_top": { "enabled": true, "limit": 20, "duration": "1h" },
    "oi_low": { "enabled": false, "limit": 20, "duration": "1h" }
  }
}
```

Test fetch:
```json
{
  "api_key": "optional",
  "sources": {
    "ai500": { "enabled": true, "limit": 10 },
    "ai300": { "enabled": false, "limit": 20, "level": "" },
    "oi_top": { "enabled": true, "limit": 20, "duration": "1h" },
    "oi_low": { "enabled": false, "limit": 20, "duration": "1h" }
  }
}
```
