# Integration Tests

These are standalone integration scripts for cross-cutting pipeline concerns.
They are designed to run against a live backend, database, and optionally a real exchange connection.

| Script | What it tests |
|---|---|
| `test_llm_pipeline.py` | End-to-end LLM flow: response parsing, trade guard, circuit breaker, and optional execution |
| `test_ccxt_executor.py` | CCXT trade execution path against a live or paper exchange account |
| `test_hyperliquid_api.py` | Hyperliquid-specific API and execution checks |
| `test_oi_rank_service.py` | OI-rank fetching and ranking behavior |
| `test_dynamic_assets.py` | Dynamic monitored-asset resolution from OI and volume data |

Backend unit and integration tests live under [backend/tests/](../backend/tests/).
These root-level scripts are for higher-level verification that requires real infrastructure.

## Running

```bash
# Example: run the LLM pipeline in dry-run mode
PYTHONPATH=backend/src python tests/test_llm_pipeline.py --skip-portfolio

# Example: replay a real response file
PYTHONPATH=backend/src python tests/test_llm_pipeline.py --response-file /path/to/response.txt
```
