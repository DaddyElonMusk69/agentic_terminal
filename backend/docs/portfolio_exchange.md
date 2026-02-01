# Portfolio and Exchange Module

This module is the single source of truth for exchange accounts, active account
selection, and portfolio data (balances and positions). All exchange access
should flow through this module to avoid hard-coded dependencies on a single
exchange.

## Responsibilities
- Store multiple exchange accounts and switch the active account.
- Provide a unified view of account state and open positions.
- Provide market data access (candles and ticker price) via the active exchange.
- Encapsulate CCXT usage so the rest of the app stays exchange-agnostic.
- Keep credentials isolated and never exposed through API responses.

## Key Components

### Domain Models
- `ExchangeAccount`: metadata for an exchange account.
- `ExchangeCredentials`: API keys and secrets for account access.
- `AccountState`: balances and margin summary.
- `Position`: normalized open position data.
- `PortfolioSnapshot`: account + state + positions.

### Interfaces
- `ExchangeRepository`: CRUD for accounts and credentials.
- `ExchangeConnector`: fetches account state, positions, candles, and ticker price.
- `ConnectorFactory`: creates connectors for a given account.

### Application Service
- `PortfolioService`: orchestrates repository + connector usage.

### Infrastructure
- `CCXTConnector`: async connector using `ccxt.async_support`.
- `CCXTConnectorFactory`: creates `CCXTConnector` instances.
- `InMemoryExchangeRepository`: temporary storage for early development.
- `PlaintextCipher`: dev-only credential handling (replace with KMS).

## Data Flow
1) Create an account via API with exchange + credentials.
2) Activate the account.
3) Fetch portfolio snapshot via API (calls CCXT under the hood).
4) Fetch market candles or live price via the active exchange connector.

## API Summary (v1)
- `GET /api/v1/portfolio/exchanges`
- `POST /api/v1/portfolio/exchanges`
- `GET /api/v1/portfolio/exchanges/{account_id}`
- `PATCH /api/v1/portfolio/exchanges/{account_id}`
- `DELETE /api/v1/portfolio/exchanges/{account_id}`
- `POST /api/v1/portfolio/exchanges/{account_id}/activate`
- `POST /api/v1/portfolio/exchanges/{account_id}/validate`
- `POST /api/v1/portfolio/exchanges/deactivate`
- `GET /api/v1/portfolio/exchanges/active`
- `GET /api/v1/portfolio/snapshot`

## Account Payload (Response)
```json
{
  "id": "uuid",
  "name": "Primary Binance",
  "exchange": "binance",
  "is_active": true,
  "is_testnet": false,
  "wallet_address": null,
  "credentials": {
    "api_key": true,
    "api_secret": true,
    "passphrase": false,
    "agent_key": false
  },
  "validation": {
    "status": "valid",
    "last_validated_at": "2026-01-28T00:00:00Z",
    "error": null
  },
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

## Usage Example

Create an account:

```json
POST /api/v1/portfolio/exchanges
{
  "name": "Primary Binance",
  "exchange": "binance",
  "is_testnet": false,
  "wallet_address": null,
  "credentials": {
    "api_key": "...",
    "api_secret": "...",
    "passphrase": null,
    "agent_key": null
  }
}
```

Activate an account:

```json
POST /api/v1/portfolio/exchanges/{account_id}/activate
```

Validate credentials (read-only check):

```json
POST /api/v1/portfolio/exchanges/{account_id}/validate
```

Fetch portfolio:

```json
GET /api/v1/portfolio/snapshot
```

## Validation Status
- `validation_status`: `unvalidated`, `valid`, `invalid`
- `last_validated_at`: timestamp of the latest validation attempt
- `validation_error`: error string (if the last attempt failed)

Validation does a read-only account fetch through CCXT. It never places orders.

## Realtime Events
The API emits outbox events for realtime delivery:
- `portfolio.exchange.created`
- `portfolio.exchange.updated`
- `portfolio.exchange.deleted`
- `portfolio.exchange.activated`
- `portfolio.exchange.deactivated`
- `portfolio.exchange.validated`

## CCXT Notes
- The connector defaults to `options.defaultType = "swap"`.
- Testnet uses `set_sandbox_mode(True)` when supported by the exchange.
- Not all exchanges support `fetch_positions`; when unavailable, the module
  returns an empty positions list.
- `agent_key` is stored but not used by CCXT (reserved for future exchange-specific adapters).

## Security
- Credentials are never returned by the API.
- Credentials are encrypted at rest using `FernetCipher`.
- The encryption key is provided via `BACKEND_CREDENTIALS_KEY` (Fernet key).
- Replace `FernetCipher` with a KMS-backed implementation for production.
- For local development, store `BACKEND_CREDENTIALS_KEY` in `backend/.env`.

## Database Persistence
- Tables: `exchange_accounts`, `exchange_credentials`
- Account setup (global): `account_setup` stores `portfolio_exposure_pct`
- SQLAlchemy models live in `backend/src/app/infrastructure/db/models/exchange.py`.
- Account setup model lives in `backend/src/app/infrastructure/db/models/account_setup.py`.
- The DB repository implementation is `SqlExchangeRepository` (see `backend/src/app/infrastructure/repositories/sql_exchange_repository.py`).
- Full schema reference: `backend/docs/database_schema.md`.

## Extending the Module
- Add exchange-specific parsing in `CCXTConnector` when needed.
- Add DB-backed repositories under `app/infrastructure/db` and wire them into
  the `get_portfolio_service()` dependency.
- Add richer account state calculations (exposure, PnL, leverage) once
  exchange-specific fields are confirmed.
