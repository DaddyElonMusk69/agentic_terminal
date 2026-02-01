# Trade Executor Module

The trade executor is the final stage before sending orders to an exchange. It
wraps CCXT and uses the active account from the portfolio/exchange module.

## Responsibilities
- Convert execution ideas into CCXT orders.
- Handle market, limit, close, reduce, and SL/TP updates.
- Support leverage and isolated margin defaults (best effort).

## Supported Actions
- `OPEN_LONG`, `OPEN_SHORT` (market)
- `OPEN_LONG_LIMIT`, `OPEN_SHORT_LIMIT`
- `CLOSE`, `REDUCE`
- `UPDATE_SL`, `UPDATE_TP`
- `CANCEL_SL`, `CANCEL_TP`, `CANCEL_SL_TP`
- `HOLD` (no-op)

## CCXT Notes
- Uses `defaultType = swap` (perps).
- Attempts to set isolated margin mode and leverage.
- Uses `USDT` as the default quote asset for symbol normalization.

## CLI
```
PYTHONPATH=backend/src python -m app.cli trade-executor execute --decision-file backend/tmp/guard_decision.json --confirm
```
