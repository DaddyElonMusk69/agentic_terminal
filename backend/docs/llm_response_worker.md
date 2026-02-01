# LLM Response Worker

The LLM response worker parses a raw LLM response string into structured
execution ideas. It is intentionally strict about required fields while still
robust to formatting noise (markdown, code fences, or extra text).

## Responsibilities
- Extract JSON objects or arrays from LLM responses.
- Validate required fields (`action`, `symbol`).
- Normalize values into `ExecutionIdea` records.
- Optionally extract `JSON_CONSIDER` notes for follow-up prompts.

## Supported Actions
- `OPEN_LONG`
- `OPEN_SHORT`
- `OPEN_LONG_LIMIT`
- `OPEN_SHORT_LIMIT`
- `CLOSE`
- `REDUCE`
- `HOLD`
- `UPDATE_SL`
- `UPDATE_TP`
- `CANCEL_SL`
- `CANCEL_TP`
- `CANCEL_SL_TP`

## Parsing Strategy
1) Direct JSON parse (object or array).
2) `JSON_ARRAY [...]` marker (highest priority when present).
3) ```json ...``` fenced code blocks.
4) Generic ```...``` fenced blocks.
5) First JSON array anywhere in the text.
6) First JSON object anywhere in the text.

## JSON_CONSIDER Extraction
If the response contains a `JSON_CONSIDER [...]` block, it is captured as
context for the next LLM cycle. Items must include either `asset` or `symbol`.

## CLI
```
PYTHONPATH=backend/src python -m app.cli llm parse --response-file backend/tmp/llm_response.txt
```

Sample file for quick testing:
```
backend/tmp/llm_response_example.txt
```
