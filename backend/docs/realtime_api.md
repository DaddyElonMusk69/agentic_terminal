# Realtime Socket Protocol

## Endpoint
- Socket.IO path: `/realtime`
- Configured by `BACKEND_SOCKETIO_PATH`

## Unified Event Channel
All server events are emitted on the `event` channel using a single envelope:

```json
{
  "v": 1,
  "type": "event",
  "topic": "system.hello",
  "payload": { },
  "ts": "2025-01-01T00:00:00Z",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

Fields:
- `topic`: dot-delimited event name
- `payload`: event-specific data
- `request_id`: optional correlation id
- `trace_id`: optional workflow id

## System Events
Emitted by the server:
- `system.hello`: on connect
- `system.pong`: ping response
- `system.subscribed`: subscription ack
- `system.unsubscribed`: unsubscribe ack
- `system.error`: protocol or request errors

## Subscribe / Unsubscribe
Client emits:

```json
// subscribe
{ "topics": ["automation.*", "portfolio.*"] }

// unsubscribe
{ "topics": ["automation.*"] }
```

Server joins the client to per-topic rooms (`topic:<name>`) and confirms with
`system.subscribed` / `system.unsubscribed`.

Wildcard rooms use the `<prefix>.*` format and receive events under that prefix.

## Topic Conventions
Topics mirror the message bus and module names:
- `market.*`
- `scanner.*`
- `automation.*`
- `agent.*`
- `portfolio.*`

## Portfolio Exchange Events
Emitted when exchange accounts change:
- `portfolio.exchange.created`
- `portfolio.exchange.updated`
- `portfolio.exchange.deleted`
- `portfolio.exchange.activated`
- `portfolio.exchange.deactivated`
- `portfolio.exchange.validated`

## Notes
- The socket channel is intentionally thin; business logic stays in services/workers.
- Redis pub/sub will be used for fanout in multi-instance deployments.
