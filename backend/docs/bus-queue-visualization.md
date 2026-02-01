# Bus + Queue Visualization Proposal

## Goal
Provide a clear, live view of how payloads move through the message bus and queues so we can:
- See where requests are queued, delayed, or failing.
- Understand end-to-end latency from scan -> prompt -> decision -> execution.
- Diagnose backpressure, retries, and dead-letter scenarios quickly.

## Scope
- Message Bus: topic activity (publish/consume rates), per-topic error rates, event latency.
- Queues: depth, in-flight, retry counts, DLQ, age of oldest message.
- Payload Flow: per-request trace across pipeline stages with correlation IDs.
- Surfaces: a single "Bus + Queue Monitor" UI with drill-down trace views.

## Non-Goals (for v1)
- Full historical analytics or long-term storage (short retention is OK).
- External APM integration.
- Automatic remediation (alerts can be a follow-up).

## Data Model (Core)
### Event (bus-level)
- event_id, timestamp
- topic, source, status (ok/error)
- trace_id, span_id, parent_span_id
- payload_meta (ticker, interval, request_type, size_bytes)

### Queue Metric (queue-level)
- queue_name, timestamp
- depth, in_flight
- retry_count, dlq_count
- age_oldest_ms, throughput_per_min

### Worker Metric (consumer-level)
- worker_name, queue_name, timestamp
- concurrency, active, idle
- avg_latency_ms, p95_latency_ms, error_rate

### Trace (request-level)
- trace_id, request_id
- Ordered spans: ingest -> scan -> chart -> prompt -> llm -> decision -> execution
- For each span: start_ts, end_ts, duration_ms, status, error

## Instrumentation Plan
- Publish Hook: emit Event on bus publish.
- Consume Hook: emit Event on handler start/end (status + latency).
- Queue Hook: snapshot metrics on enqueue/dequeue + periodic sampler.
- Trace Propagation: carry trace_id + span_id through pipeline stages.

## Data Sources
- Existing bus/pipeline emits (automation/scanner/preview) can be extended with:
  - trace_id and span_id tags.
  - Per-stage timestamps.
- Queue stats: if in-memory, expose via a lightweight internal API; if Redis/DB-backed, read native queue stats.

## API / Realtime Surface (Proposed)
- GET /api/v1/observability/bus/metrics -> topic rates, errors, latency
- GET /api/v1/observability/queues -> queue depth, retry, DLQ, age-oldest
- GET /api/v1/observability/traces?trace_id=... -> span waterfall
- WS /ws/observability -> live stream of Event + metrics deltas

## UI Concepts
- Summary KPIs: publish/sec, consume/sec, backlog, p95 latency, error rate.
- Queue Heatmap: rows per queue, columns per metric; color for backlog/age.
- Pipeline Flow Map: stage nodes with live counters + latency badges.
- Event Stream: tail of bus events with filters (ticker, interval, topic).
- Trace Drilldown: open a request trace to see the span waterfall.
- Payload Inspector: metadata + compact payload preview (no full blobs).

## UX Behavior
- Live updates via WS with pause/resume.
- Filters: ticker, interval, topic, queue, status, time range.
- Hover to reveal counts; click to lock a trace or queue detail.

---

## UI Sketch (Wireframe)

```
+----------------------------------------------------------------------------------------------+
| Bus + Queue Monitor            [Ticker v] [Interval v] [Topic v] [Status v] [Last 15m v]     |
| KPIs: Publish/s 128 | Consume/s 124 | Backlog 32 | P95 Lat 2.4s | Errors 0.8%                |
+-------------------------------+-------------------------------------------+------------------+
| Queue Heatmap                 | Pipeline Flow Map                         | Inspector        |
| [queue] [depth] [age] [dlq]   | Ingest -> Scanner -> Chart -> Prompt -> LLM| Event/Trace Info|
| q.scanner   ###  42  3.1s  0  |   12/s     10/s     9/s      9/s   9/s    | - trace_id       |
| q.chart     ##   12  0.8s  0  |   p95 1.2s  0.9s    1.1s     2.2s  4.5s   | - topic          |
| q.prompt    ###  26  4.5s  1  |   err 0.1% 0.0%    0.2%     0.8%  0.5%    | - payload meta   |
| q.llm       #### 51  9.8s  4  | [Click node to filter events]             | [compact payload]|
+-------------------------------+-------------------------------------------+------------------+
| Event Stream (live)                                                                          |
| 18:42:10  topic=scanner.result  status=ok  ticker=BTC  interval=2h  trace=...                |
| 18:42:11  topic=chart.render    status=ok  ticker=BTC  interval=2h  trace=...                |
| 18:42:12  topic=prompt.build    status=ok  ticker=BTC  interval=2h  trace=...                |
| 18:42:14  topic=llm.request     status=err ticker=BTC  interval=2h  trace=..                 |
+----------------------------------------------------------------------------------------------+
| Trace Waterfall (selected)                                                                   |
| trace_id: 6f3c...                                                                            |
| [ingest 120ms] [scan 830ms] [chart 1.2s] [prompt 260ms] [llm 4.9s] [exec 90ms]               |
+----------------------------------------------------------------------------------------------+
```

## Next Decisions
- Confirm the route placement (new Observability page vs add to existing scanner/automation views).
- Decide retention (e.g., 15-60 min in-memory vs short-term DB storage).
- Confirm which queues/topics are in scope for v1.
