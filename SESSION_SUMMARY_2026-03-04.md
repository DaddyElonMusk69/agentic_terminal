# Session Summary (2026-03-04)

## What Changed Today

### 1) Codex provider bridge (no API key flow)
- Added built-in `codex` provider using `codex_cli` protocol.
- Enabled provider validation/model handling for Codex without requiring an API key.
- Added runtime fallback behavior so Codex routing can still work when provider metadata is partially missing but model name indicates Codex.

### 2) Codex CLI execution in LLM pipeline
- Added local `codex exec` call path in LLM caller.
- Added compatibility handling for CLI argument differences (including fallback when unsupported flags are encountered).
- Improved timeout/error reporting and protocol visibility in logs.

### 3) Provider-aware image handling
- Added provider-aware prompt image path:
  - Non-Codex providers keep remote upload behavior.
  - Codex provider uses local temp image files for `--image`.
- Added local temp image lifecycle handling:
  - per-request cleanup on parse success
  - periodic sweeper cleanup (TTL + interval policy)

### 4) Automation pipeline and observability updates
- Extended queue worker/protocol routing for Codex path.
- Preserved richer LLM failure details in frontend/backend logs.
- Added provider/protocol fields in key automation events for easier diagnosis.

### 5) EMA/Vegas state management UX update
- Added manual clear control for managed Vegas states:
  - new backend endpoint `POST /api/v1/scanner/ema/state/clear`
  - frontend Vegas panel button: `Clear Managed States`
- Behavior remains persistent by default: states stay managed after automation stops unless manually cleared.

### 6) Template behavior fix for `resonance_refresh`
- `resonance_refresh` now reuses `new_resonance` template mapping if a dedicated `resonance_refresh` mapping is not set.
- If `resonance_refresh` mapping is explicitly set, it takes priority.

---

## Server Startup Runbook (This Instance)

Target pairing for this workspace:
- Frontend: `http://127.0.0.1:5174`
- Backend: `http://127.0.0.1:8101`

Do not interfere with the other backend instance on port `8001`.

### Terminal 1: Backend
```bash
cd backend
python3 -m pip install -e ".[test]"

# Use your dedicated DB for this instance
export BACKEND_DATABASE_URL=postgresql+asyncpg://localhost/trading_backend_8101

PYTHONPATH=src alembic -c alembic.ini upgrade head
PYTHONPATH=src uvicorn app.main:app --reload --host 127.0.0.1 --port 8101
```

### Terminal 2: Frontend
```bash
cd frontend
npm install
npm run dev
```

Vite is configured to:
- bind `5174` with `strictPort: true`
- proxy `/api`, `/socket.io`, `/realtime` to backend `8101`

### Quick Checks
```bash
curl http://127.0.0.1:8101/api/v1/health
curl 'http://127.0.0.1:8101/api/v1/automation/sessions?limit=1'
```

Note for `zsh`: quote URLs containing `?` to avoid globbing errors.

### If a port is already occupied
```bash
lsof -nP -iTCP:8101 -sTCP:LISTEN
lsof -nP -iTCP:5174 -sTCP:LISTEN
```
