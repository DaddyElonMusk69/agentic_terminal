from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional

try:
    import ccxt.async_support as ccxt
except ImportError:  # pragma: no cover
    ccxt = None

from app.domain.portfolio.interfaces import ExchangeConnector, ConnectorFactory
from app.domain.portfolio.models import (
    AccountState,
    ExchangeAccount,
    ExchangeCredentials,
    Position,
    MarketCandle,
    MarketDataPoint,
    MarketQuote,
    OrderBookLevel,
    OrderBookSnapshot,
    FundingRateSnapshot,
    DailyPnlSnapshot,
)


@dataclass
class CCXTConfig:
    exchange_id: str
    api_key: str
    api_secret: str
    passphrase: Optional[str]
    is_testnet: bool


class CCXTConnector(ExchangeConnector):
    def __init__(self, config: CCXTConfig) -> None:
        if ccxt is None:
            raise ImportError("ccxt is not installed. Add it to backend dependencies.")
        self._config = config

    async def fetch_account_state(self) -> AccountState:
        async with self._client() as client:
            balance = await client.fetch_balance()

            total = balance.get("total") or {}
            free = balance.get("free") or {}
            used = balance.get("used") or {}

            account_value = float(total.get("USDT") or total.get("USD") or 0.0)
            available = float(free.get("USDT") or free.get("USD") or 0.0)
            used_margin = float(used.get("USDT") or used.get("USD") or 0.0)

            return AccountState(
                account_value=account_value,
                available_margin=available,
                total_margin_used=used_margin,
                unrealized_pnl=0.0,
                open_positions_count=0,
                total_exposure_pct=0.0,
            )

    async def fetch_positions(self) -> List[Position]:
        async with self._client() as client:
            if not getattr(client, "has", {}).get("fetchPositions"):
                return []

            raw_positions = await client.fetch_positions()
            positions: List[Position] = []

            for raw in raw_positions or []:
                side = raw.get("side") or raw.get("direction") or "flat"
                size = float(raw.get("contracts") or raw.get("size") or 0.0)
                entry_price = _to_float(raw.get("entryPrice"))
                mark_price = _to_float(raw.get("markPrice"))
                unrealized_pnl = _to_float(raw.get("unrealizedPnl"))
                liquidation_price = _to_float(raw.get("liquidationPrice"))
                info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
                opened_at = _resolve_position_opened_at(raw, info)
                margin = (
                    _to_float(raw.get("initialMargin"))
                    or _to_float(raw.get("margin"))
                    or _to_float(info.get("initialMargin"))
                    or _to_float(info.get("margin"))
                )
                leverage = (
                    _to_float(raw.get("leverage"))
                    or _to_float(info.get("leverage"))
                    or _to_float(info.get("lever"))
                )
                if leverage is None and margin and margin > 0:
                    notional = abs(size) * (mark_price or entry_price or 0.0)
                    if notional > 0:
                        leverage = round(notional / margin, 2)

                positions.append(
                    Position(
                        symbol=_normalize_position_symbol(raw.get("symbol")),
                        direction=str(side),
                        size=size,
                        entry_price=entry_price,
                        mark_price=mark_price,
                        unrealized_pnl=unrealized_pnl,
                        liquidation_price=liquidation_price,
                        margin=margin,
                        leverage=leverage,
                        opened_at=opened_at,
                    )
                )

            return positions

    async def fetch_open_orders(self, symbols: Optional[List[str]] = None) -> List[dict]:
        async with self._client() as client:
            if not getattr(client, "has", {}).get("fetchOpenOrders"):
                return []

            orders: List[dict] = []
            if symbols:
                for symbol in symbols:
                    try:
                        fetched = await client.fetch_open_orders(symbol)
                    except Exception:
                        fetched = []
                    if fetched:
                        orders.extend([item for item in fetched if isinstance(item, dict)])
            else:
                try:
                    fetched = await client.fetch_open_orders()
                except Exception:
                    fetched = []
                if fetched:
                    orders.extend([item for item in fetched if isinstance(item, dict)])

            return orders

    async def fetch_recent_trades(self, limit: int = 10) -> List[dict]:
        limit = max(1, min(int(limit or 10), 100))
        async with self._client() as client:
            now = datetime.now(timezone.utc)
            seven_days_ms = int((now - timedelta(days=7)).timestamp() * 1000)
            exchange_id = (self._config.exchange_id or "").lower()

            if exchange_id == "binance" and hasattr(client, "fapiPrivateGetIncome"):
                trades = await _fetch_binance_income_trades(client, seven_days_ms, limit)
                if trades:
                    return trades

            return await _fetch_ccxt_recent_trades(client, seven_days_ms, limit)

    async def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> List[MarketCandle]:
        async with self._client() as client:
            candles = await client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            results: List[MarketCandle] = []
            for row in candles or []:
                if len(row) < 6:
                    continue
                results.append(
                    MarketCandle(
                        timestamp_ms=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )
            return results

    async def fetch_ticker_price(self, symbol: str) -> float | None:
        quote = await self.fetch_ticker_quote(symbol)
        return quote.price if quote else None

    async def fetch_ticker_quote(self, symbol: str) -> Optional[MarketQuote]:
        quotes = await self.fetch_ticker_quotes([symbol])
        return quotes.get(symbol)

    async def fetch_ticker_quotes(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        if not symbols:
            return {}
        async with self._client() as client:
            symbol_map: Dict[str, str] = {}
            selected_symbols: List[str] = []
            markets = getattr(client, "markets", {}) or {}

            for raw in symbols:
                candidates = _symbol_candidates(client, raw)
                chosen = None
                for candidate in candidates:
                    if candidate in markets:
                        chosen = candidate
                        break
                if not chosen and candidates:
                    chosen = candidates[0]
                if not chosen:
                    continue
                symbol_map[raw] = chosen
                if chosen not in selected_symbols:
                    selected_symbols.append(chosen)

            if not selected_symbols:
                return {}

            tickers: Dict[str, Any] = {}
            has_fetch_tickers = bool(getattr(client, "has", {}).get("fetchTickers"))
            if has_fetch_tickers:
                try:
                    result = await client.fetch_tickers(selected_symbols)
                    if isinstance(result, dict):
                        tickers = result
                    elif isinstance(result, list):
                        tickers = {item.get("symbol"): item for item in result if isinstance(item, dict)}
                except Exception:
                    tickers = {}

            if not tickers:
                for symbol in selected_symbols:
                    try:
                        tickers[symbol] = await client.fetch_ticker(symbol)
                    except Exception:
                        continue

            quotes: Dict[str, MarketQuote] = {}
            for raw, chosen in symbol_map.items():
                ticker = tickers.get(chosen)
                if ticker is None:
                    continue
                price = _extract_ticker_price(ticker)
                if price is None:
                    continue
                change_percent = _extract_ticker_change_pct(ticker, price)
                quotes[raw] = MarketQuote(price=price, change_percent=change_percent)

            return quotes

    async def fetch_open_interest_history(
        self, symbol: str, timeframe: str, limit: int
    ) -> List[MarketDataPoint]:
        async with self._client() as client:
            has = getattr(client, "has", {}) or {}
            raw: Any = None
            logger = logging.getLogger(__name__)

            if has.get("fetchOpenInterestHistory") and hasattr(client, "fetch_open_interest_history"):
                try:
                    raw = await client.fetch_open_interest_history(
                        symbol, timeframe=timeframe, limit=limit
                    )
                except Exception:
                    raw = None
                    try:
                        raw = await client.fetch_open_interest_history(symbol, limit=limit)
                    except Exception:
                        raw = None
            elif has.get("fetchOpenInterest") and hasattr(client, "fetch_open_interest"):
                try:
                    raw = await client.fetch_open_interest(symbol)
                except Exception:
                    raw = None
            else:
                logger.debug(
                    "CCXT open interest unsupported for %s (has=%s)",
                    symbol,
                    {key: has.get(key) for key in ("fetchOpenInterestHistory", "fetchOpenInterest")},
                )

            points: List[MarketDataPoint] = []
            if raw is None:
                return points

            entries = raw if isinstance(raw, list) else [raw]
            for entry in entries:
                point = _to_open_interest_point(entry)
                if point is not None:
                    points.append(point)

            return points

    async def fetch_order_book(
        self, symbol: str, limit: int = 50
    ) -> Optional[OrderBookSnapshot]:
        async with self._client() as client:
            if not getattr(client, "has", {}).get("fetchOrderBook"):
                return None
            try:
                raw = await client.fetch_order_book(symbol, limit=limit)
            except Exception:
                return None

            bids = [
                OrderBookLevel(price=float(level[0]), size=float(level[1]))
                for level in raw.get("bids", []) if len(level) >= 2
            ]
            asks = [
                OrderBookLevel(price=float(level[0]), size=float(level[1]))
                for level in raw.get("asks", []) if len(level) >= 2
            ]
            timestamp_ms = _to_timestamp_ms(raw.get("timestamp")) or int(
                datetime.now(timezone.utc).timestamp() * 1000
            )

            return OrderBookSnapshot(
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                bids=bids,
                asks=asks,
            )

    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingRateSnapshot]:
        async with self._client() as client:
            has = getattr(client, "has", {}) or {}
            raw = None
            logger = logging.getLogger(__name__)

            if has.get("fetchFundingRate") and hasattr(client, "fetch_funding_rate"):
                try:
                    raw = await client.fetch_funding_rate(symbol)
                except Exception:
                    raw = None
            elif has.get("fetchFundingRates") and hasattr(client, "fetch_funding_rates"):
                try:
                    rates = await client.fetch_funding_rates([symbol])
                except Exception:
                    rates = None
                if isinstance(rates, dict):
                    raw = rates.get(symbol) or next(iter(rates.values()), None)
            else:
                logger.debug(
                    "CCXT funding rate unsupported for %s (has=%s)",
                    symbol,
                    {key: has.get(key) for key in ("fetchFundingRate", "fetchFundingRates")},
                )

            if not raw:
                return None

            info = raw.get("info", {}) if isinstance(raw, dict) else {}
            rate = _to_float(
                raw.get("fundingRate")
                or raw.get("rate")
                or raw.get("funding_rate")
                or info.get("fundingRate")
                or info.get("rate")
                or info.get("funding_rate")
            )
            if rate is None:
                return None

            rate = max(-0.01, min(0.01, rate))
            timestamp_ms = _to_timestamp_ms(raw.get("timestamp") or raw.get("fundingTime"))
            if timestamp_ms is None:
                timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            next_funding = _to_timestamp_ms(
                raw.get("nextFundingTimestamp")
                or raw.get("nextFundingTime")
                or info.get("nextFundingTime")
                or info.get("nextFundingTimestamp")
            )
            mark_price = _to_float(
                raw.get("markPrice") or raw.get("mark_price") or info.get("markPrice") or info.get("mark_price")
            )

            return FundingRateSnapshot(
                rate=rate,
                timestamp_ms=timestamp_ms,
                next_funding_time_ms=next_funding,
                mark_price=mark_price,
            )

    async def fetch_daily_pnl(self) -> DailyPnlSnapshot:
        logger = logging.getLogger(__name__)
        try:
            async with self._client() as client:
                now = datetime.now(timezone.utc)
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_timestamp_ms = int(start_of_day.timestamp() * 1000)
                exchange_id = (self._config.exchange_id or "").lower()

                if exchange_id == "binance":
                    result = await self._get_binance_daily_pnl(client, start_timestamp_ms)
                    if result is not None:
                        return result

                if exchange_id == "okx":
                    result = await self._get_okx_daily_pnl(client, start_timestamp_ms)
                    if result is not None:
                        return result

                return await self._get_daily_pnl_from_trades(client, start_timestamp_ms)
        except Exception as exc:
            logger.warning("Failed to fetch daily PnL: %s", exc)
            return DailyPnlSnapshot(
                realized_pnl=0.0,
                trade_count=0,
                fills=[],
                exchange=self._config.exchange_id,
            )

    async def _get_binance_daily_pnl(
        self, client: Any, start_timestamp_ms: int
    ) -> Optional[DailyPnlSnapshot]:
        logger = logging.getLogger(__name__)
        if not hasattr(client, "fapiPrivateGetIncome"):
            return None
        try:
            params = {
                "incomeType": "REALIZED_PNL",
                "startTime": start_timestamp_ms,
                "limit": 1000,
            }
            income_records = await client.fapiPrivateGetIncome(params)
            if not isinstance(income_records, list):
                return None

            realized_pnl = 0.0
            closed_positions = set()
            fills = []

            for record in income_records:
                if not isinstance(record, dict):
                    continue
                income = _to_float(record.get("income")) or 0.0
                symbol = record.get("symbol") or ""
                timestamp = _to_timestamp_ms(record.get("time"))
                realized_pnl += income
                if income != 0 and symbol:
                    closed_positions.add(symbol)
                fills.append(
                    {
                        "symbol": symbol,
                        "income": income,
                        "timestamp": timestamp,
                        "type": "REALIZED_PNL",
                    }
                )

            trade_count = len(closed_positions)
            return DailyPnlSnapshot(
                realized_pnl=round(realized_pnl, 2),
                trade_count=trade_count,
                fills=fills,
                exchange=self._config.exchange_id,
            )
        except Exception as exc:
            logger.warning("Could not fetch Binance income history: %s", exc)
            return None

    async def _get_okx_daily_pnl(
        self, client: Any, start_timestamp_ms: int
    ) -> Optional[DailyPnlSnapshot]:
        logger = logging.getLogger(__name__)
        if not hasattr(client, "privateGetAccountBills"):
            return None
        try:
            params = {
                "instType": "SWAP",
                "type": "1",
                "begin": str(start_timestamp_ms),
                "limit": "100",
            }
            bills = await client.privateGetAccountBills(params)
            if not isinstance(bills, dict):
                return None

            realized_pnl = 0.0
            closed_positions = set()
            fills = []

            for bill in bills.get("data", []) or []:
                if not isinstance(bill, dict):
                    continue
                if bill.get("type") != "1":
                    continue
                pnl = _to_float(bill.get("bal")) or 0.0
                symbol = bill.get("instId") or ""
                timestamp = _to_timestamp_ms(bill.get("ts"))
                realized_pnl += pnl
                if pnl != 0 and symbol:
                    closed_positions.add(symbol)
                fills.append(
                    {
                        "symbol": symbol,
                        "income": pnl,
                        "timestamp": timestamp,
                        "type": "REALIZED_PNL",
                    }
                )

            trade_count = len(closed_positions)
            logger.info(
                "Daily PnL (OKX bills): $%.2f from %d records, %d positions closed",
                realized_pnl,
                len(fills),
                trade_count,
            )
            return DailyPnlSnapshot(
                realized_pnl=round(realized_pnl, 2),
                trade_count=trade_count,
                fills=fills,
                exchange=self._config.exchange_id,
            )
        except Exception as exc:
            logger.warning("Could not fetch OKX bills: %s", exc)
            return None

    async def _get_daily_pnl_from_trades(
        self, client: Any, start_timestamp_ms: int
    ) -> DailyPnlSnapshot:
        logger = logging.getLogger(__name__)
        has = getattr(client, "has", {}) or {}
        symbols = set()

        if has.get("fetchPositions"):
            try:
                positions = await client.fetch_positions()
            except Exception as exc:
                logger.debug("Could not fetch positions for daily PnL: %s", exc)
                positions = []
            for position in positions or []:
                symbol = position.get("symbol") if isinstance(position, dict) else None
                if symbol:
                    symbols.add(symbol)

        if has.get("fetchClosedOrders"):
            try:
                closed_orders = await client.fetch_closed_orders(since=start_timestamp_ms)
            except Exception as exc:
                logger.debug("Could not fetch closed orders for daily PnL: %s", exc)
                closed_orders = []
            for order in closed_orders or []:
                symbol = order.get("symbol") if isinstance(order, dict) else None
                if symbol:
                    symbols.add(symbol)

        if not symbols or not has.get("fetchMyTrades"):
            return DailyPnlSnapshot(
                realized_pnl=0.0,
                trade_count=0,
                fills=[],
                exchange=self._config.exchange_id,
            )

        all_trades = []
        for symbol in symbols:
            try:
                trades = await client.fetch_my_trades(symbol=symbol, since=start_timestamp_ms)
                if trades:
                    all_trades.extend(trades)
            except Exception as exc:
                logger.debug("Could not fetch trades for %s: %s", symbol, exc)

        if not all_trades:
            return DailyPnlSnapshot(
                realized_pnl=0.0,
                trade_count=0,
                fills=[],
                exchange=self._config.exchange_id,
            )

        all_trades.sort(key=lambda trade: _to_timestamp_ms(trade.get("timestamp")) or 0)

        position_tracker: Dict[str, Dict[str, float]] = {}
        realized_pnl = 0.0
        trade_count = 0
        fills = []
        epsilon = 1e-8

        for trade in all_trades:
            if not isinstance(trade, dict):
                continue
            symbol = trade.get("symbol") or ""
            side = str(trade.get("side") or "").lower()
            amount = _to_float(trade.get("amount")) or 0.0
            price = _to_float(trade.get("price")) or 0.0
            cost = _to_float(trade.get("cost")) or price * amount
            fee_cost = _extract_fee_cost(trade)

            if not symbol or amount <= 0 or price <= 0 or side not in ("buy", "sell"):
                continue

            tracker = position_tracker.setdefault(symbol, {"size": 0.0, "avg_entry": 0.0})
            size = tracker["size"]
            avg_entry = tracker["avg_entry"]

            if side == "buy":
                if size >= 0:
                    new_size = size + amount
                    if new_size > 0:
                        avg_entry = ((avg_entry * size) + (price * amount)) / new_size
                    size = new_size
                else:
                    close_amount = min(amount, abs(size))
                    fee_share = fee_cost * (close_amount / amount) if amount else 0.0
                    realized_pnl += (avg_entry - price) * close_amount - fee_share
                    remaining_size = size + close_amount
                    if abs(remaining_size) < epsilon:
                        remaining_size = 0.0
                        avg_entry = 0.0
                        trade_count += 1
                    if amount > close_amount:
                        remaining = amount - close_amount
                        size = remaining
                        avg_entry = price
                    else:
                        size = remaining_size
            else:
                if size <= 0:
                    new_abs = abs(size) + amount
                    if new_abs > 0:
                        avg_entry = ((avg_entry * abs(size)) + (price * amount)) / new_abs
                    size = -new_abs
                else:
                    close_amount = min(amount, size)
                    fee_share = fee_cost * (close_amount / amount) if amount else 0.0
                    realized_pnl += (price - avg_entry) * close_amount - fee_share
                    remaining_size = size - close_amount
                    if abs(remaining_size) < epsilon:
                        remaining_size = 0.0
                        avg_entry = 0.0
                        trade_count += 1
                    if amount > close_amount:
                        remaining = amount - close_amount
                        size = -remaining
                        avg_entry = price
                    else:
                        size = remaining_size

            tracker["size"] = size
            tracker["avg_entry"] = avg_entry

            fills.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "amount": amount,
                    "cost": cost,
                    "fee": fee_cost,
                    "timestamp": trade.get("timestamp"),
                }
            )

        logger.info(
            "Daily PnL (trade reconstruction): $%.2f from %d trades, %d completed",
            realized_pnl,
            len(all_trades),
            trade_count,
        )
        return DailyPnlSnapshot(
            realized_pnl=round(realized_pnl, 2),
            trade_count=trade_count,
            fills=fills,
            exchange=self._config.exchange_id,
        )

    def _client(self):
        return _CCXTClientContext(self._config)


class CCXTConnectorFactory(ConnectorFactory):
    def create(self, account: ExchangeAccount, credentials: ExchangeCredentials) -> ExchangeConnector:
        config = CCXTConfig(
            exchange_id=account.exchange,
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            passphrase=credentials.passphrase,
            is_testnet=account.is_testnet,
        )
        return CCXTConnector(config)


class _CCXTClientContext:
    _MARKETS_CACHE_TTL = timedelta(minutes=30)
    _MARKETS_CACHE: Dict[str, Dict[str, Any]] = {}
    _MARKETS_LOCKS: Dict[str, asyncio.Lock] = {}

    def __init__(self, config: CCXTConfig) -> None:
        self._config = config
        self._client = None

    @classmethod
    def _cache_key(cls, exchange_id: str, is_testnet: bool) -> str:
        return f"{exchange_id}:{'testnet' if is_testnet else 'main'}"

    @classmethod
    def _get_lock(cls, cache_key: str) -> asyncio.Lock:
        lock = cls._MARKETS_LOCKS.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            cls._MARKETS_LOCKS[cache_key] = lock
        return lock

    @classmethod
    def _get_cached_markets(cls, cache_key: str) -> tuple[Optional[Dict[str, Any]], bool]:
        entry = cls._MARKETS_CACHE.get(cache_key)
        if not entry:
            return None, False
        loaded_at = entry.get("loaded_at")
        if not isinstance(loaded_at, datetime):
            return entry, False
        age = datetime.now(timezone.utc) - loaded_at
        return entry, age <= cls._MARKETS_CACHE_TTL

    @classmethod
    def _apply_cached_markets(cls, client: Any, entry: Dict[str, Any]) -> None:
        for key in ("markets", "markets_by_id", "symbols", "currencies"):
            if key in entry and entry[key] is not None:
                setattr(client, key, entry[key])

    @classmethod
    def _store_markets(cls, cache_key: str, client: Any) -> None:
        markets = getattr(client, "markets", None)
        if not markets:
            return
        cls._MARKETS_CACHE[cache_key] = {
            "loaded_at": datetime.now(timezone.utc),
            "markets": markets,
            "markets_by_id": getattr(client, "markets_by_id", None),
            "symbols": getattr(client, "symbols", None),
            "currencies": getattr(client, "currencies", None),
        }

    async def __aenter__(self):
        exchange_id = self._config.exchange_id.lower()
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        options: Dict[str, Any] = {
            "defaultType": "swap",
            "fetchCurrencies": False,
        }
        if exchange_id == "binance":
            options["fetchMarkets"] = {"types": ["linear"]}

        self._client = exchange_class(
            {
                "apiKey": self._config.api_key,
                "secret": self._config.api_secret,
                "password": self._config.passphrase,
                "enableRateLimit": True,
                "timeout": 30000,
                "options": options,
            }
        )

        if isinstance(getattr(self._client, "options", None), dict):
            self._client.options["fetchCurrencies"] = False
            if exchange_id == "binance":
                self._client.options["fetchMarkets"] = {"types": ["linear"]}
        if isinstance(getattr(self._client, "has", None), dict):
            self._client.has["fetchCurrencies"] = False

        if self._config.is_testnet:
            try:
                self._client.set_sandbox_mode(True)
            except Exception:
                pass

        cache_key = self._cache_key(exchange_id, self._config.is_testnet)
        cached_entry, cache_fresh = self._get_cached_markets(cache_key)
        if cached_entry and cache_fresh:
            self._apply_cached_markets(self._client, cached_entry)
            return self._client

        lock = self._get_lock(cache_key)
        async with lock:
            cached_entry, cache_fresh = self._get_cached_markets(cache_key)
            if cached_entry and cache_fresh:
                self._apply_cached_markets(self._client, cached_entry)
                return self._client
            try:
                await self._client.load_markets()
            except Exception as exc:
                logger = logging.getLogger(__name__)
                if cached_entry:
                    self._apply_cached_markets(self._client, cached_entry)
                    logger.warning(
                        "CCXT load_markets failed for %s, using cached markets",
                        exchange_id,
                        exc_info=exc,
                    )
                    return self._client
                raise
            self._store_markets(cache_key, self._client)
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_fee_cost(trade: Any) -> float:
    if not isinstance(trade, dict):
        return 0.0
    fee = trade.get("fee")
    if isinstance(fee, dict):
        return _to_float(fee.get("cost")) or 0.0
    if isinstance(fee, list):
        total = 0.0
        for item in fee:
            if not isinstance(item, dict):
                continue
            cost = _to_float(item.get("cost"))
            if cost is not None:
                total += cost
        return total
    return 0.0


def _extract_ticker_price(ticker: Any) -> Optional[float]:
    if not isinstance(ticker, dict):
        return None
    for key in ("last", "close", "mark", "index", "average"):
        price = _to_float(ticker.get(key))
        if price is not None and price > 0:
            return price

    info = ticker.get("info") if isinstance(ticker.get("info"), dict) else {}
    if isinstance(info, dict):
        for key in ("last", "lastPrice", "close", "markPrice", "indexPrice", "price"):
            price = _to_float(info.get(key))
            if price is not None and price > 0:
                return price

    bid = _to_float(ticker.get("bid"))
    ask = _to_float(ticker.get("ask"))
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    if bid is not None and bid > 0:
        return bid
    if ask is not None and ask > 0:
        return ask
    return None


def _extract_ticker_change_pct(ticker: Any, price: Optional[float] = None) -> Optional[float]:
    if not isinstance(ticker, dict):
        return None

    for key in ("percentage", "percent", "changePercent"):
        value = _to_float(ticker.get(key))
        if value is not None:
            return value

    change = _to_float(ticker.get("change"))
    open_price = _to_float(ticker.get("open")) or _to_float(ticker.get("previousClose"))
    if change is not None and open_price:
        return (change / open_price) * 100

    if price is None:
        price = _extract_ticker_price(ticker)
    if price is not None and open_price:
        return ((price - open_price) / open_price) * 100

    info = ticker.get("info") if isinstance(ticker.get("info"), dict) else {}
    if isinstance(info, dict):
        for key in (
            "priceChangePercent",
            "priceChangePercentage",
            "changePercent",
            "change_percent",
            "percentage",
            "percentChange",
        ):
            value = _to_float(info.get(key))
            if value is not None:
                return value

        info_change = _to_float(info.get("priceChange") or info.get("change"))
        info_open = _to_float(info.get("openPrice") or info.get("open"))
        if info_change is not None and info_open:
            return (info_change / info_open) * 100
        if price is not None and info_open:
            return ((price - info_open) / info_open) * 100

    return None


def _symbol_candidates(client: Any, symbol: str) -> List[str]:
    raw = symbol.strip().upper()
    if not raw:
        return []

    candidates: List[str] = []
    seen = set()

    def add(candidate: Optional[str]) -> None:
        if not candidate:
            return
        if candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    add(raw)

    base = raw
    quote = None
    if "/" in raw:
        parts = raw.split("/", 1)
        base = parts[0]
        quote = parts[1].split(":", 1)[0]
        if quote:
            add(f"{base}/{quote}:{quote}")

    markets = getattr(client, "markets", {}) or {}
    if markets:
        matches = [
            market
            for market in markets.values()
            if isinstance(market, dict) and market.get("base") == base
        ]
        if matches:
            preferred_quotes = ("USDT", "USDC", "USD")
            default_type = (getattr(client, "options", {}) or {}).get("defaultType")

            def _score(market: Dict[str, Any]) -> tuple[int, int]:
                quote_symbol = market.get("quote")
                quote_rank = (
                    preferred_quotes.index(quote_symbol)
                    if quote_symbol in preferred_quotes
                    else len(preferred_quotes)
                )
                is_swap = bool(market.get("swap") or market.get("type") == "swap")
                swap_rank = 0 if (default_type == "swap" and is_swap) else 1
                return (swap_rank, quote_rank)

            matches.sort(key=_score)
            add(matches[0].get("symbol"))

    if quote:
        add(f"{base}/{quote}")

    for quote_symbol in ("USDT", "USDC", "USD"):
        add(f"{base}/{quote_symbol}")
        add(f"{base}/{quote_symbol}:{quote_symbol}")

    return candidates


def _normalize_position_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip()
    if not symbol:
        return ""
    if ":" in symbol:
        return symbol.split(":", 1)[0]
    return symbol


def _to_open_interest_point(entry: Any) -> Optional[MarketDataPoint]:
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        timestamp_ms = _to_timestamp_ms(entry[0])
        value = _to_float(entry[1])
        if timestamp_ms is None or value is None:
            return None
        return MarketDataPoint(timestamp_ms=timestamp_ms, value=value)

    if not isinstance(entry, dict):
        return None

    info = entry.get("info", {}) if isinstance(entry, dict) else {}
    value = (
        entry.get("openInterest")
        or entry.get("openInterestValue")
        or entry.get("openInterestAmount")
        or entry.get("open_interest")
        or entry.get("value")
        or info.get("openInterest")
        or info.get("openInterestValue")
        or info.get("openInterestAmount")
        or info.get("open_interest")
        or info.get("value")
    )
    value = _to_float(value)
    if value is None:
        return None

    timestamp = (
        entry.get("timestamp")
        or entry.get("time")
        or entry.get("datetime")
        or info.get("timestamp")
        or info.get("time")
        or info.get("datetime")
    )
    if isinstance(timestamp, str):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            timestamp_ms = int(parsed.timestamp() * 1000)
        except ValueError:
            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    elif isinstance(timestamp, (int, float)):
        timestamp_ms = int(timestamp)
    else:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    return MarketDataPoint(timestamp_ms=timestamp_ms, value=value)


def _to_timestamp_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                return int(float(stripped))
            except ValueError:
                pass
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
                return int(parsed.timestamp() * 1000)
            except ValueError:
                return None
    return None


def _resolve_position_opened_at(raw: dict, info: dict) -> Optional[datetime]:
    timestamp = (
        raw.get("timestamp")
        or raw.get("datetime")
        or raw.get("updateTime")
        or info.get("updateTime")
        or info.get("updateTimeStamp")
        or info.get("time")
        or info.get("timestamp")
        or info.get("datetime")
    )
    timestamp_ms = _to_timestamp_ms(timestamp)
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


async def _fetch_binance_income_trades(client: Any, since_ms: int, limit: int) -> List[dict]:
    try:
        params = {
            "incomeType": "REALIZED_PNL",
            "startTime": since_ms,
            "limit": 1000,
        }
        income_records = await client.fapiPrivateGetIncome(params)
    except Exception:
        income_records = []
    if not isinstance(income_records, list):
        return []

    income_records.sort(key=lambda item: _to_timestamp_ms(item.get("time") or 0) or 0, reverse=True)
    trades: List[dict] = []
    for record in income_records:
        if len(trades) >= limit:
            break
        if not isinstance(record, dict):
            continue
        pnl = _to_float(record.get("income"))
        if pnl is None or pnl == 0:
            continue
        symbol = _normalize_income_symbol(record.get("symbol") or "")
        timestamp = _to_timestamp_ms(record.get("time"))
        trades.append(
            {
                "symbol": symbol,
                "direction": "LONG" if pnl > 0 else "SHORT",
                "entry_price": 0.0,
                "exit_price": 0.0,
                "size": 0.0,
                "pnl": pnl,
                "roi_pct": 0.0,
                "entry_time": timestamp,
                "exit_time": timestamp,
                "duration_minutes": 0,
                "is_win": pnl > 0,
            }
        )

    return trades


async def _fetch_ccxt_recent_trades(client: Any, since_ms: int, limit: int) -> List[dict]:
    symbols = set()
    has = getattr(client, "has", {}) or {}

    if has.get("fetchPositions"):
        try:
            positions = await client.fetch_positions()
        except Exception:
            positions = []
        for position in positions or []:
            symbol = position.get("symbol") if isinstance(position, dict) else None
            if symbol:
                symbols.add(symbol)

    if has.get("fetchClosedOrders"):
        try:
            closed_orders = await client.fetch_closed_orders(since=since_ms)
        except Exception:
            closed_orders = []
        for order in closed_orders or []:
            symbol = order.get("symbol") if isinstance(order, dict) else None
            if symbol:
                symbols.add(symbol)

    if not symbols or not has.get("fetchMyTrades"):
        return []

    all_trades: List[dict] = []
    for symbol in symbols:
        try:
            trades = await client.fetch_my_trades(symbol=symbol, limit=50)
        except Exception:
            trades = []
        for trade in trades or []:
            if isinstance(trade, dict):
                all_trades.append(trade)

    all_trades.sort(key=lambda trade: _to_timestamp_ms(trade.get("timestamp")) or 0, reverse=True)

    closed_trades: List[dict] = []
    for trade in all_trades:
        if len(closed_trades) >= limit:
            break
        info = trade.get("info") if isinstance(trade.get("info"), dict) else {}
        realized_pnl = info.get("realizedPnl") or info.get("closedPnl")
        pnl_value = _to_float(realized_pnl)
        if pnl_value is None or pnl_value == 0:
            continue

        symbol = _normalize_ccxt_symbol(trade.get("symbol") or "")
        side = str(trade.get("side") or "").lower()
        amount = _to_float(trade.get("amount")) or 0.0
        price = _to_float(trade.get("price")) or 0.0
        timestamp = _to_timestamp_ms(trade.get("timestamp"))

        closed_trades.append(
            {
                "symbol": symbol,
                "direction": "long" if side == "buy" else "short",
                "entry_price": price or None,
                "exit_price": price or None,
                "size": amount or None,
                "pnl": pnl_value,
                "roi_pct": None,
                "entry_time": timestamp,
                "exit_time": timestamp,
                "duration_minutes": 0,
                "is_win": pnl_value > 0,
            }
        )

    return closed_trades


def _normalize_ccxt_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip()
    if not symbol:
        return ""
    return symbol.replace("/USDT", "").replace(":USDT", "")


def _normalize_income_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip()
    if not symbol:
        return ""
    return symbol.replace("USDT", "")
