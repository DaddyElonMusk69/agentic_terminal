# LLM Execution Pipeline

This module is a thin wrapper that runs:
1) LLM caller (send prompt, get response)
2) LLM response worker (parse JSON into execution ideas)

It is intentionally minimal so transport logic and parsing can evolve
independently.

## Responsibilities
- Accept a `LlmCallRequest`.
- Execute the OpenAI-compatible call.
- Parse the response into execution ideas.

## CLI
```
PYTHONPATH=backend/src python -m app.cli llm execute --prompt-file backend/tmp/llm_prompt_example.txt
```
