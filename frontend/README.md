# Trading Dashboard Frontend

Vue 3 + TypeScript dashboard providing real-time visibility into every stage of the autonomous trading pipeline.

## Overview
- Separate frontend app served by Vite (default: http://127.0.0.1:5174)
- Backend API is expected at http://127.0.0.1:8101 in local development
- Connects to the backend over HTTP and Socket.IO for live pipeline telemetry

## Tech Stack
- Vue 3 + TypeScript
- Vite
- Tailwind CSS + Headless UI
- Pinia (state)
- socket.io-client (realtime)
- Lightweight Charts (EMA scanner result cards)

## Local Dev
```bash
cd frontend
npm install
npm run dev
```

## Build
```bash
cd frontend
npm run build
npm run preview
```

## Environment Variables
- `VITE_SOCKET_BASE` (optional)
  - Default: window origin (uses Vite proxy during dev).
  - Example: `VITE_SOCKET_BASE=http://127.0.0.1:8101`

## Project Structure
```
frontend/
  src/
    app/            # app bootstrap, router, pinia
    layouts/        # AppShell, Sidebar, TopBanner
    views/          # route-level screens
    components/     # shared UI building blocks
    stores/         # Pinia stores
    services/       # socket clients and API helpers
    styles/         # Tailwind entry + theme tokens
    types/          # domain types
```

## Layout + Scrolling
- Sidebar is fixed in place; each view manages its own scroll.
- EMA scanner columns scroll independently.
- Scrollbars are hidden via the `.scrollbar-hidden` class.

## Sockets
Socket clients live in `src/services/` and are wired in `src/layouts/AppShell.vue`.

Key Socket.IO events:
- EMA scanner: `start_scan`, `stop_scan`, `scanner_log`, `ema_scan_results`, `scan_complete`
- Quant scanner (OI/CVD): `oi_cvd_*` events
- Automation: `automation_state`, `automation_log`, `position_update`, `trade_executed`, `circuit_breaker`

Exchange selection:
- `exchangeStore.activeExchangeId` is appended as a `query` param when connecting.

## EMA Scanner Notes
- Result charts render from `result.chart_data[primaryInterval]`.
- Primary interval selection: EMA intervals first, then BB intervals, then first chart key.
- Chart component: `src/components/ScannerResultChart.vue`.

## Theming
- Tokens live in `src/styles/tokens.css`.
- Dark theme is default; `data-theme="light"` switches to light tokens.

## Views

| View | Description |
|---|---|
| **EMA Scanner** | Real-time resonance detection across monitored assets and intervals |
| **Quant Scanner** | OI, CVD, and related quant metrics ranked by signal strength |
| **Automation** | Main control panel for the pipeline: start, stop, inspect logs, and monitor decisions |
| **Agent** | Session inspector for replaying full prompt and response cycles |
| **Observability** | Queue and bus visibility for pipeline-stage monitoring |
| **Settings** | Exchange accounts, scanners, prompts, trade guard, and risk configuration |
