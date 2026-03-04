# Quant Scanner (Data Fetch + Cache)

The quant scanner is a data-only module. It fetches market data for all
monitored assets and intervals, normalizes it into a consistent snapshot,
and stores it in an in-memory cache for other modules to consume later.

## Scope
- Fetches data only (no signal classification).
- Uses the active `portfolio_exchange` connector for all market data.
- Keeps a per-symbol/per-interval cache in memory.

## Inputs
- Monitored coins/assets and intervals (shared tables).
- `limit` parameter at call time (number of candles/OI points to fetch).

## Data Fetched
- OHLCV candles via `ExchangeConnector.fetch_candles`.
- Open interest history via `ExchangeConnector.fetch_open_interest_history` (if supported by the exchange).
- CVD series calculated from candle shape (no taker volume available via CCXT OHLCV).
- Funding rate via `ExchangeConnector.fetch_funding_rate` (if supported by the exchange).
- Order book snapshot via `ExchangeConnector.fetch_order_book` (if supported by the exchange).
- Netflow data via NofXOS (optional, requires `NOFXOS_API_KEY`; timeout tunable via `NOFXOS_TIMEOUT_SECONDS`).

## Output Snapshot
Each scan builds a `QuantSnapshot` containing:
- `symbol`, `timeframe`, `timestamp`
- `candles`, `prices`
- `open_interest`
- `cvd`, `cvd_deltas`
- `price_current`, `oi_current`, `cvd_current`
- `funding_rate` (rate + timestamps)
- `order_book` (depth/OBI metrics)
- `vwap` (value, std dev, distance)
- `atr` (value, slope, z-score)
- `netflow` (institution, retail, total, regime, dominant)
- `anomalies` (price/OI/CVD z-score analysis)
- `price_slope`, `price_slope_z`
- `cvd_slope`, `cvd_slope_z`

## Notes
- ATR is skipped for timeframes below 2h to match legacy behavior.
- Netflow is optional and returns `null` when not configured or unavailable.
- Order book depth uses +/-0.5% around mid price with a 50-level snapshot.

## CLI
```bash
PYTHONPATH=backend/src python -m app.cli quant config --json
PYTHONPATH=backend/src python -m app.cli quant scan --limit 200 --json
```
