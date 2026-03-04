# Trading Dashboard Frontend

New Vue 3 + Tailwind + Headless UI app that runs alongside the legacy Flask UI.

## Overview
- Separate frontend app served by Vite (default: http://127.0.0.1:5174).
- Backend API is expected at http://127.0.0.1:8101 in local development.
- Legacy UI remains intact; this app is for the new UI migration.

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

Current events (legacy-compatible):
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

## TODO / Next
- Wire real chart data for all results.
- Add Vegas State sidebar data to match legacy UI.
- Continue porting Quant scanner details and Agent context builder.
