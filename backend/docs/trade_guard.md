# Trade Guard Module

The trade guard validates and adjusts execution ideas before they are passed
to the executor. It is a policy layer that enforces leverage caps, position
size rules, and SL/TP sanity checks.

## Responsibilities
- Validate required fields (action, symbol, limit price, reduce pct).
- Enforce minimum confidence thresholds.
- Apply leverage caps based on symbol tiers.
- Compute position sizing from tier + position_pct.
- Adjust stop loss and take profit based on ROE limits.
- Convert REDUCE to CLOSE when remaining value would be dust.

## Configuration (DB)
Table: `trade_guard_config`
- `min_confidence` (default 60)
- `min_position_size` (default 10 USD)
- `sl_min_roe` (default 0.03)
- `sl_max_roe` (default 0.05)
- `tp_min_roe` (default 0.05)
- `tp_max_roe` (default 0.2)
- `dust_threshold_usd` (default 10)
- `leverage_tiers` (JSON list of `{ leverage, symbols[] }`)
- `position_tier_ranges` (JSON list of `{ tier, min_pct, max_pct }`)

Leverage tiers are ordered only by their leverage value. If a symbol appears
in multiple tiers, the highest leverage wins.

## Account Setup
`portfolio_exposure_pct` is stored in `account_setup` and used to compute the
available margin for tier sizing. Default is 25%.

## CLI
```
PYTHONPATH=backend/src python -m app.cli trade-guard validate --decision-file backend/tmp/guard_decision.json
```
