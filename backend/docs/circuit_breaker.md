# Circuit Breaker Module

The circuit breaker is the last safety layer before execution. The current
implementation is a pass-through skeleton that allows all decisions that
reach it. Rules will be added over time as new edge cases are discovered.

## Responsibilities
- Evaluate execution ideas after trade guard validation.
- Provide a consistent interface for future blocking rules.

## Current Behavior
- No rules are registered.
- All decisions are allowed to pass through.

## CLI
```
PYTHONPATH=backend/src python -m app.cli circuit-breaker evaluate --decision-file backend/tmp/guard_decision.json
```
