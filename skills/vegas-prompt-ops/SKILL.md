---
name: vegas-prompt-ops
description: Analyze automated trading sessions for Vegas state events and iteratively improve prompt templates with safe rollouts and instant rollback.
---

# Vegas Prompt Ops

Use this skill to run a repeatable prompt-ops loop:

1. snapshot current mapping, 2) analyze a session, 3) ship candidate mapping,
2. evaluate outcome, 5) rollback fast if results degrade.

## Hard Rules

- Snapshot current mapping before every prompt rollout.
- Treat prompt templates as immutable versions; create new template IDs for edits.
- Roll back by restoring `automation_config.vegas_prompt_configs` from a snapshot.
- Compare pre/post windows with equal duration and comparable market regime.

## Quick Start

- Analyze latest session:
  - `python3 skills/vegas-prompt-ops/scripts/session_analysis.py --db trading_backend_8101`
- Snapshot active mapping:
  - `python3 skills/vegas-prompt-ops/scripts/prompt_map_release.py snapshot --db trading_backend_8101`
- Apply candidate mapping:
  - `python3 skills/vegas-prompt-ops/scripts/prompt_map_release.py apply-map --db trading_backend_8101 --map-file path/to/candidate_map.json`
- Roll back mapping:
  - `python3 skills/vegas-prompt-ops/scripts/prompt_map_release.py rollback --db trading_backend_8101 --snapshot path/to/snapshot.json`

## Workflow

## 1) Diagnose session behavior

- Run `session_analysis.py` with `--session-id` (or default latest).
- Review event/action output:
  - trigger mix
  - parser action mix by trigger
  - new-resonance direction conflicts
  - position-management HOLD dominance
  - worst realized trade
- Review `Prompt Improvement Suggestions`:
  - If session is healthy, report states no update needed.
  - If issues are detected, report includes event-level minimal-change suggestions.
- Use findings to design minimal prompt changes first.

## 2) Prepare prompt changes safely

- Insert new rows in `prompt_templates` for changed prompts.
- Keep old template IDs unchanged.
- Build a candidate event map JSON with all six keys:
  - `new_resonance`
  - `resonance_increase`
  - `structure_shift`
  - `position_management`
  - `bb_exit_warning`
  - `bb_rejection_entry`

## 3) Release with rollback ready

- Run `prompt_map_release.py snapshot` and keep the file.
- Run `prompt_map_release.py apply-map` with candidate map.
- Store snapshot + candidate map together for auditability.

## 4) Evaluate after rollout

- Wait for enough post-change sessions.
- Re-run `session_analysis.py` and compare to baseline:
  - total pnl
  - action mix by trigger
  - conflict rate on `new_resonance`
  - HOLD/add balance on `position_management`
- Follow thresholds in `references/metric_checklist.md`.

## 5) Roll back if degraded

- If metrics fail guardrails, run:
  - `prompt_map_release.py rollback --snapshot <baseline_snapshot>`
- Rollback is O(1) map switch, no row deletes/rewrites.

## Script Notes

- `scripts/session_analysis.py` writes JSON/Markdown reports via `--output-json` / `--output-md`.
- `scripts/prompt_map_release.py status` shows active mapping and recent local snapshots.

## References

- `references/metric_checklist.md` for pass/fail rules and iteration cadence.
