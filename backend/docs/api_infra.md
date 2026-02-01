# HTTP API Contract

## Base Path
- `/api/v1`
- JSON only

## Response Envelope
All successful responses use a consistent envelope:

```json
{
  "data": { },
  "meta": {
    "request_id": "uuid",
    "pagination": {
      "limit": 50,
      "next_cursor": "..."
    }
  }
}
```

Notes:
- `meta` is optional.
- `pagination` is only present for list endpoints.

## Error Envelope
All error responses use a consistent envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": { }
  },
  "meta": {
    "request_id": "uuid"
  }
}
```

## Request ID
- Client can send `X-Request-ID`.
- Server echoes it and always returns `X-Request-ID` in the response headers.
- `request_id` is also included in `meta`.

## Conventions
- Timestamps are ISO-8601 (UTC).
- IDs are UUID strings unless noted otherwise.
- `snake_case` for JSON keys.

## Error Codes (Initial)
- `validation_error`
- `http_404`, `http_401`, `http_403`, `http_409`
- `internal_error`

## Authentication (Placeholder)
- JWT access tokens will be added later.
- Initial endpoints can run without auth in development.
