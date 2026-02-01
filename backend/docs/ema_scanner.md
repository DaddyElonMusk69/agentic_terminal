# EMA Scanner Module

The EMA scanner scans configured assets and timeframes for EMA proximity
signals. It uses the active exchange connector from the portfolio module to
fetch market data.

## Responsibilities
- Accept EMA scan configuration (assets, timeframes, EMA lengths, tolerance).
- Fetch historical candles from the active exchange.
- Fetch live price for signal checks (no candle overrides).
- Emit EMA proximity signals only.
- Emit Bollinger Band signals using BB(20, 2) with the same tolerance rules.

## Inputs
- `assets`: list of symbols (e.g., `BTC`, `ETH`, `BTC/USDT`).
- `timeframes`: list of CCXT timeframes (e.g., `15m`, `1h`).
- `ema_lengths`: list of EMA lengths (e.g., `144`, `169`).
- `tolerance_pct`: percent tolerance for proximity checks.

The default values are stored in the database tables:
`ema_scanner_config`, `ema_scanner_lines`, `monitored_coins`,
and `monitored_intervals`.

## Configuration Loading
The config repository (`SqlEmaScannerRepository`) reads scanner settings and
shared monitored data from the DB. `EmaScannerConfigService` builds the
`EmaScannerConfig` object that can be fed into the scanner service.

Optional:
- `quote_asset`: default quote asset for symbol normalization (default `USDT`).
- `min_candles`: minimum candle count for fetching (default `20`).
- `candles_multiplier`: fetch multiplier for EMA stability (default `3`).
- `max_candles`: hard cap on candle fetch count (default `1499`).
- `use_live_price`: override last close with live price (default `true`).

## Signal Logic
1) Fetch candles using `ExchangeConnector.fetch_candles`.
2) Fetch live price via `fetch_ticker_price` (required for checks).
3) Compute EMA from candle closes using SMA seed + EMA multiplier.
4) Compute Bollinger Bands (20, 2) from candle closes.
5) Emit a signal when live `price` falls within EMA ± tolerance.
6) Emit BB signals when live `price` is within tolerance of the band or breaks beyond it.

## Output
`EmaScannerSignal` entries with:
- `symbol`, `timeframe`
- `indicator` (`EMA` or `BB`)
- `parameter` (`EMA-144`, `BB-Upper`, `BB-Lower`)
- `value`, `price`, `lower_bound`, `upper_bound`
- `condition` (`proximity`, `breakout`, `breakdown`)
- `timestamp` (UTC)

## Files
- `backend/src/app/domain/ema_scanner/models.py`
- `backend/src/app/application/ema_scanner/service.py`
- Tests: `backend/tests/unit/test_ema_scanner.py`
