# Backend (FastAPI + Socket.IO)

This backend runs independently and can be started directly from `backend/` during local development.

## What This Is

The backend is the execution engine for an autonomous crypto trading agent.
It runs a four-stage pipeline:

**SCAN -> SIGNAL -> DECIDE -> EXECUTE**

1. **Scan** — EMA and quant scanners collect market structure, OI, and related inputs
2. **Signal** — the EMA state manager detects resonance conditions and emits trigger events
3. **Decide** — the prompt builder assembles context, the LLM makes a decision, and the parser extracts structured execution ideas
4. **Execute** — the trade guard validates the idea, the circuit breaker is the final safety gate, and the CCXT executor places the order

All major stages communicate through an event bus and queue-backed workers. See [ARCHITECTURE.md](ARCHITECTURE.md) for full design details.

## Local Development

1) Create `backend/.env` from the example:

```bash
cp backend/.env.example backend/.env
```

2) Generate a Fernet key and set `BACKEND_CREDENTIALS_KEY` in `backend/.env`:

```bash
python backend/scripts/generate_fernet_key.py
```

3) Install dependencies:

```bash
python3 -m pip install -e "backend[test]"
```

4) Run migrations:

```bash
PYTHONPATH=backend/src BACKEND_DATABASE_URL=postgresql+asyncpg://localhost/trading_backend \
  alembic -c backend/alembic.ini upgrade head
```

5) Start the server:

```bash
PYTHONPATH=backend/src uvicorn app.main:app --reload --port 8101
```

6) Keep the backend process awake on macOS (run from `backend/`):
```bash
caffeinate -dimsu uvicorn --env-file .env --app-dir src app.main:app --reload --port 8101
```

7) Optional: start the frontend (run from `frontend/`):
```bash
npm run dev
```

## Required Services

- PostgreSQL is required for DB-backed modules and migrations.
- Redis is only required if you run Taskiq workers/queues.

## Production Notes

- Store `BACKEND_CREDENTIALS_KEY` in a secrets manager and inject via env var.
- Rotate encryption keys with a re-encryption migration.
- Use a managed PostgreSQL instance and Redis (separate credentials/roles).
- Run Alembic migrations as part of deployment.
- Avoid placing secrets in `.env` in production.

## Message Bus (Outbox)
- Outbox messages are stored in `outbox_messages`.
- Dispatch worker uses Taskiq and Redis.
- Example worker run:

```bash
PYTHONPATH=backend/src taskiq worker app.jobs.worker:broker
```

## CLI

Run EMA or quant scans without the API:

```bash
PYTHONPATH=backend/src python -m app.cli ema config --json
PYTHONPATH=backend/src python -m app.cli ema scan --json
PYTHONPATH=backend/src python -m app.cli quant config --json
PYTHONPATH=backend/src python -m app.cli quant scan --limit 200 --json
```
