# Metric Checklist

Use this checklist after every prompt-map rollout.

## Minimum Evaluation Window

- Wait for at least `3` completed production sessions, or
- Wait for at least `150` total cycles post-change.

## Compare Baseline vs Candidate

Keep baseline and candidate windows equal in length and close in market regime.

Track:

- `total_pnl` per session
- Prompt trigger mix by vegas event
- Parser action mix by vegas event
- `new_resonance` direction-mismatch rate
- `position_management` HOLD rate and add-like action count
- LLM failure count (`automation.llm.failed`)

## Suggested Guardrails

Treat rollout as degraded if either condition is true:

- Median session `total_pnl` drops more than `20%` vs baseline window.
- `new_resonance` direction mismatch rises above baseline by `15` percentage points.

Treat rollout as suspicious if:

- `position_management` HOLD rate > `80%` and add-like actions remain `0` across the window.
- LLM/parser failure count increases materially from baseline.

## Rollback Policy

Roll back immediately when guardrails fail and there is no external operational explanation.

Rollback command:

```bash
python3 skills/vegas-prompt-ops/scripts/prompt_map_release.py rollback \
  --db trading_backend_8101 \
  --snapshot path/to/prompt-map-snapshot-YYYYMMDD-HHMMSS.json
```

## Candidate Map Template

Store candidate maps in versioned JSON files:

```json
{
  "new_resonance": 26,
  "resonance_increase": 28,
  "structure_shift": 29,
  "position_management": 27,
  "bb_exit_warning": 22,
  "bb_rejection_entry": 24
}
```
