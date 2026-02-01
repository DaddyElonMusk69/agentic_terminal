# LLM Caller

The LLM caller is a thin adapter that sends the finished prompt to a model
provider using an OpenAI-compatible `chat/completions` endpoint. It is built
to be replaceable, with the simplest possible contract for now.

## Responsibilities
- Accept a prompt string and optional image URLs.
- Format the request payload for OpenAI-compatible APIs.
- Return the raw response and extracted content to the caller.

## Request/Response Shape
The application layer uses these dataclasses:
- `LlmCallRequest`
  - `prompt_text`: string
  - `images`: list of `{ "image_url": "...", "ticker": "...", "interval": "..." }`
  - `model`: string
  - `temperature`: float
  - `max_tokens`: optional int
- `LlmCallResponse`
  - `content`: string
  - `model`: string
  - `tokens_used`: int
  - `latency_ms`: float
  - `raw_response`: optional dict

## Image Handling
Images are passed in the OpenAI multi-part content format:

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "...prompt..."},
    {"type": "image_url", "image_url": {"url": "https://..."}}
  ]
}
```

Only the `chart_snapshots` field is supported for image extraction. Each item
in `chart_snapshots` must look like this:

```json
{
  "type": "input_image",
  "image_url": "https://.../chart.png",
  "ticker": "BTC",
  "interval": "4h"
}
```

Legacy fields such as `chart_snapshots_*_interval` are not supported.

## Configuration
Environment variables (see `.env.example`):
- `BACKEND_LLM_BASE_URL` (default `https://api.openai.com/v1`)
- `BACKEND_LLM_API_KEY`
- `BACKEND_LLM_MODEL`
- `BACKEND_LLM_TEMPERATURE`
- `BACKEND_LLM_MAX_TOKENS`

## CLI Usage
Call the model with a prompt file:

```bash
python -m app.cli llm call --prompt-file backend/tmp/prompt.txt
```

Call the model using a prompt builder payload (extracts `chart_snapshots`):

```bash
python -m app.cli llm call --payload-file backend/tmp/prompt_payload.json
```

Append additional images:

```bash
python -m app.cli llm call --prompt "Hello" --images-json '[{"image_url":"https://.../chart.png"}]'
```
