# Queue Worker Module

## Purpose
Provide a durable, serial queue for workloads that must be processed one at
a time (LLM prompts, image uploads, external rate-limited APIs). The queue is
database-backed so items survive restarts and can be retried safely.

## Use Cases
- Prompt build requests (LLM + chart uploads).
- LLM request queue (serial LLM calls).
- Order execution queue (time-urgent trade execution).
- Any workflow that needs strict ordering or single-flight execution.
- Background jobs that must not run concurrently.

## Core Components
- Queue table: `prompt_build_requests`
- Repository: `PromptBuildQueueRepository`
- Worker: `PromptBuildQueueWorker`
- Policy: `PromptQueuePolicy` (TTL + concurrency expectations)
Additional queues:
- `llm_queue_requests` / `LlmQueueRepository` / `LlmQueueWorker` (TTL 20m)
- `order_queue_requests` / `OrderQueueRepository` / `OrderQueueWorker` (TTL 5m)

## Data Model (prompt_build_requests)
- `id` (PK): request id
- `status`: queued, in_progress, done, failed, dropped
- `payload`: original request payload
- `result`: output (when done)
- `error`: failure reason (when failed/dropped)
- `created_at`, `updated_at`
- `started_at`, `completed_at`
- `expires_at`

## Lifecycle
`queued` -> `in_progress` -> `done` / `failed` / `dropped`

## Concurrency and TTL
- Concurrency is enforced at the worker level (run with a single worker).
- TTL is 20 minutes by default; stale requests are dropped on pickup.

## Stale Drop Policy
- If `expires_at` is set and current time is past it, mark as `dropped`.
- If `expires_at` is missing, derive it from `created_at + TTL`.
- Stale requests are not retried; they are finalized with `dropped`.

## Where It Lives
- Worker task: `backend/src/app/jobs/worker.py` -> `process_prompt_build_queue`
- Queue repository: `backend/src/app/infrastructure/repositories/prompt_build_queue_repository.py`
- Worker implementation: `backend/src/app/application/prompt_builder/queue_worker.py`

## Extending to Other Modules
To reuse the queue pattern:
1) Add a new queue table (or reuse `prompt_build_requests` with a type field).
2) Create a repository with `enqueue` + `claim_next`.
3) Implement a worker with TTL checks and `in_progress` lifecycle.
