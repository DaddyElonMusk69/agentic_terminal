# Monitored Assets Resolver

The monitored assets resolver provides the global list of symbols used by all
scanners and automation workflows.

## Rules
- If dynamic assets are enabled and active, the dynamic list is used.
- If dynamic assets are disabled or unavailable (stale > 30m), the manual list is used.
- Open positions are always included (to ensure position management prompts).

## Sources
1. Dynamic assets (multi-source, gated by Binance account)
2. Manual monitored assets (market settings)
3. Open positions from the active exchange

## Usage
- EMA scanner config: uses the resolved list.
- Quant scanner config: uses the same list.
- EMA state manager receives the list to avoid pruning active positions.
