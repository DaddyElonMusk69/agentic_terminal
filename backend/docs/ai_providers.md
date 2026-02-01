# AI Provider Settings

This module manages LLM provider credentials, defaults, and custom
OpenAI-compatible endpoints. Provider credentials are encrypted at rest with
`BACKEND_CREDENTIALS_KEY`.

## Defaults
Built-in providers are always listed, even if not configured:
- `openai`
- `gemini`
- `claude`
- `xai`
- `deepseek`

Custom providers can be added as OpenAI-compatible endpoints.

## API (v1)
- `GET /api/v1/ai/providers`
- `POST /api/v1/ai/providers`
- `DELETE /api/v1/ai/providers/{provider}`
- `GET /api/v1/ai/providers/{provider}/models`
- `POST /api/v1/ai/providers/{provider}/validate`

## Payloads

Upsert provider:
```json
{
  "provider": "openai",
  "api_key": "sk-...",
  "default_model": "gpt-4o",
  "is_enabled": true,
  "base_url": "https://api.openai.com/v1",
  "display_name": "OpenAI",
  "protocol": "openai"
}
```

Validation request:
```json
{
  "api_key": "sk-...",
  "model": "gpt-4o"
}
```

## Notes
- `protocol` controls validation behavior (`openai`, `gemini`, `claude`).
- Custom providers default to `openai` protocol.
- `base_url` is required for custom OpenAI-compatible providers.
