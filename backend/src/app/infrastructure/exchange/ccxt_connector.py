from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
import random
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from app.settings import get_settings

_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 0.2
_RETRY_MAX_DELAY_SECONDS = 1.5
_RETRY_JITTER_SECONDS = 0.15
_RETRYABLE_ERROR_TEXT = (
    "cannot connect to host",
    "connection reset",
    "network error",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "server disconnected",
    "ssl",
)
_RETRYABLE_CCXT_ERROR_NAMES = (
    "ExchangeNotAvailable",
    "NetworkError",
    "RequestTimeout",
    "DDoSProtection",
)
T = TypeVar("T")


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
            balance = await self._with_retry("fetch_balance", client.fetch_balance)

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

            raw_positions = await self._with_retry("fetch_positions", client.fetch_positions)
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

    async def fetch_open_orders(
        self,
        symbols: Optional[List[str]] = None,
        *,
        include_conditional_orders: bool = True,
    ) -> List[dict]:
        async with self._client() as client:
            if not getattr(client, "has", {}).get("fetchOpenOrders"):
                return []

            normalized_symbols = _normalize_requested_symbols(symbols)
            orders: List[dict] = []
            if normalized_symbols:
                try:
                    fetched = await client.fetch_open_orders()
                except Exception:
                    fetched = None
                if fetched is None:
                    for symbol in normalized_symbols:
                        try:
                            market_symbol = _resolve_ccxt_market_symbol(client, symbol)
                            fetched_by_symbol = await client.fetch_open_orders(market_symbol)
                        except Exception:
                            fetched_by_symbol = []
                        if fetched_by_symbol:
                            orders.extend([item for item in fetched_by_symbol if isinstance(item, dict)])
                else:
                    all_orders = [item for item in fetched if isinstance(item, dict)]
                    orders.extend(_filter_open_orders_by_symbols(client, all_orders, normalized_symbols))
            else:
                try:
                    fetched = await client.fetch_open_orders()
                except Exception:
                    fetched = []
                if fetched:
                    orders.extend([item for item in fetched if isinstance(item, dict)])

            if include_conditional_orders and (self._config.exchange_id or "").lower() == "binance":
                algo_orders = await _fetch_binance_open_algo_orders(client, None)
                if normalized_symbols:
                    algo_orders = _filter_open_orders_by_symbols(client, algo_orders, normalized_symbols)
                if algo_orders:
                    orders.extend(algo_orders)

            return orders

    async def fetch_order(self, order_id: str, symbol: str) -> Optional[dict]:
        if not order_id or not symbol:
            return None
        async with self._client() as client:
            fetcher = getattr(client, "fetch_order", None)
            if not callable(fetcher):
                return None
            market_symbol = _resolve_ccxt_market_symbol(client, symbol)
            try:
                return await fetcher(order_id, market_symbol)
            except Exception:
                return None

    async def cancel_order(self, order_id: str, symbol: str) -> Optional[dict]:
        if not order_id or not symbol:
            return None
        async with self._client() as client:
            fetcher = getattr(client, "cancel_order", None)
            market_symbol = _resolve_ccxt_market_symbol(client, symbol)
            try:
                if callable(fetcher):
                    return await fetcher(order_id, market_symbol)
            except Exception:
                pass

            exchange_id = (self._config.exchange_id or "").lower()
            if exchange_id == "binance":
                try:
                    market = client.market(market_symbol)
                    market_id = market.get("id") if isinstance(market, dict) else None
                except Exception:
                    market_id = None
                if market_id:
                    params = {"symbol": market_id, "algoId": order_id}
                    try:
                        if hasattr(client, "fapiPrivateDeleteAlgoOrder"):
                            return await client.fapiPrivateDeleteAlgoOrder(params)
                        return await client.request("algoOrder", "fapiPrivate", "DELETE", params)
                    except Exception:
                        return None
            return None

    async def fetch_recent_trades(
        self,
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> List[dict]:
        limit = max(1, min(int(limit or 10), 1000))
        async with self._client() as client:
            now = datetime.now(timezone.utc)
            seven_days_ms = int((now - timedelta(days=7)).timestamp() * 1000)
            since_ms = _to_timestamp_ms(start_time) or seven_days_ms
            until_ms = _to_timestamp_ms(end_time)
            if until_ms is not None and until_ms < since_ms:
                since_ms, until_ms = until_ms, since_ms
            exchange_id = (self._config.exchange_id or "").lower()

            if exchange_id == "binance" and hasattr(client, "fapiPrivateGetIncome"):
                trades = await _fetch_binance_income_trades(
                    client,
                    since_ms=since_ms,
                    until_ms=until_ms,
                    limit=limit,
                )
                if trades:
                    return trades

            return await _fetch_ccxt_recent_trades(
                client,
                since_ms=since_ms,
                until_ms=until_ms,
                limit=limit,
            )

    async def fetch_recent_completed_trades(
        self,
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> List[dict]:
        limit = max(1, min(int(limit or 10), 1000))
        async with self._client() as client:
            now = datetime.now(timezone.utc)
            seven_days_ms = int((now - timedelta(days=7)).timestamp() * 1000)
            since_ms = _to_timestamp_ms(start_time) or seven_days_ms
            until_ms = _to_timestamp_ms(end_time)
            if until_ms is not None and until_ms < since_ms:
                since_ms, until_ms = until_ms, since_ms
            exchange_id = (self._config.exchange_id or "").lower()

            if exchange_id == "binance":
                positions = await _fetch_binance_recent_completed_positions(
                    client,
                    since_ms=since_ms,
                    until_ms=until_ms,
                    limit=limit,
                )
                if positions:
                    return positions

            positions = await _fetch_ccxt_recent_completed_positions(
                client,
                since_ms=since_ms,
                until_ms=until_ms,
                limit=limit,
            )
            if positions:
                return positions

            if exchange_id == "binance" and hasattr(client, "fapiPrivateGetIncome"):
                trades = await _fetch_binance_income_trades(
                    client,
                    since_ms=since_ms,
                    until_ms=until_ms,
                    limit=limit,
                )
                if trades:
                    return trades

            return await _fetch_ccxt_recent_trades(
                client,
                since_ms=since_ms,
                until_ms=until_ms,
                limit=limit,
            )

    async def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> List[MarketCandle]:
        async with self._client() as client:
            market_symbol = _resolve_ccxt_market_symbol(client, symbol)
            candles = await client.fetch_ohlcv(market_symbol, timeframe=timeframe, limit=limit)
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

    async def fetch_market_limits(self, symbol: str) -> Optional[Dict[str, Any]]:
        raw_symbol = (symbol or "").strip()
        if not raw_symbol:
            return None
        async with self._client() as client:
            markets = getattr(client, "markets", {}) or {}
            candidates = _symbol_candidates(client, raw_symbol)
            market = None
            chosen = None
            for candidate in candidates:
                if candidate in markets:
                    market = markets.get(candidate)
                    chosen = candidate
                    break
            if market is None and candidates:
                try:
                    chosen = candidates[0]
                    market = client.market(chosen)
                except Exception:
                    market = None

            if not isinstance(market, dict):
                return None

            limits = market.get("limits") if isinstance(market.get("limits"), dict) else {}
            amount_limits = limits.get("amount") if isinstance(limits.get("amount"), dict) else {}
            cost_limits = limits.get("cost") if isinstance(limits.get("cost"), dict) else {}

            min_amount = _to_float(amount_limits.get("min"))
            min_cost = _to_float(cost_limits.get("min"))
            contract_size = _to_float(market.get("contractSize") or market.get("contract_size")) or 1.0

            info = market.get("info", {}) if isinstance(market.get("info"), dict) else {}
            if min_cost is None:
                min_cost = _to_float(info.get("minNotional") or info.get("min_notional"))
            if min_amount is None:
                min_amount = _to_float(info.get("minQty") or info.get("min_qty"))

            if min_amount is None and min_cost is None:
                return None

            return {
                "symbol": raw_symbol.upper(),
                "market_symbol": chosen or market.get("symbol"),
                "min_amount": min_amount,
                "min_notional": min_cost,
                "contract_size": contract_size,
            }

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
                local_tz = _resolve_local_timezone()
                now_local = datetime.now(local_tz)
                start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                start_timestamp_ms = int(start_of_day_local.astimezone(timezone.utc).timestamp() * 1000)
                exchange_id = (self._config.exchange_id or "").lower()

                if exchange_id == "binance":
                    result = await self._get_binance_daily_pnl(client, start_timestamp_ms)
                    if _daily_pnl_has_activity(result):
                        return result
                    if result is not None:
                        logger.info(
                            "Binance income history returned no daily activity; falling back to trade reconstruction"
                        )

                if exchange_id == "okx":
                    result = await self._get_okx_daily_pnl(client, start_timestamp_ms)
                    if _daily_pnl_has_activity(result):
                        return result
                    if result is not None:
                        logger.info(
                            "OKX bills returned no daily activity; falling back to trade reconstruction"
                        )

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
            realized_records = 0
            fills = []

            for record in income_records:
                if not isinstance(record, dict):
                    continue
                income = _to_float(record.get("income")) or 0.0
                symbol = record.get("symbol") or ""
                timestamp = _to_timestamp_ms(record.get("time"))
                realized_pnl += income
                if income != 0:
                    realized_records += 1
                fills.append(
                    {
                        "symbol": symbol,
                        "income": income,
                        "timestamp": timestamp,
                        "type": "REALIZED_PNL",
                    }
                )

            trade_count = realized_records
            return DailyPnlSnapshot(
                realized_pnl=round(realized_pnl, 2),
                trade_count=trade_count,
                fills=fills,
                exchange=self._config.exchange_id,
            )
        except Exception as exc:
            if _is_restricted_location_error(exc):
                logger.warning(
                    "Binance income history unavailable due to exchange location restrictions."
                )
            else:
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
            realized_records = 0
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
                if pnl != 0:
                    realized_records += 1
                fills.append(
                    {
                        "symbol": symbol,
                        "income": pnl,
                        "timestamp": timestamp,
                        "type": "REALIZED_PNL",
                    }
                )

            trade_count = realized_records
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

        if not has.get("fetchMyTrades"):
            return DailyPnlSnapshot(
                realized_pnl=0.0,
                trade_count=0,
                fills=[],
                exchange=self._config.exchange_id,
            )

        all_trades = []
        if symbols:
            for symbol in symbols:
                try:
                    trades = await client.fetch_my_trades(symbol=symbol, since=start_timestamp_ms)
                    if trades:
                        all_trades.extend(trades)
                except Exception as exc:
                    logger.debug("Could not fetch trades for %s: %s", symbol, exc)
        else:
            try:
                trades = await client.fetch_my_trades(since=start_timestamp_ms, limit=200)
                if trades:
                    all_trades.extend(trades)
            except TypeError:
                logger.debug("Exchange requires symbol for fetch_my_trades during daily PnL reconstruction")
            except Exception as exc:
                logger.debug("Could not fetch trades without symbol for daily PnL: %s", exc)

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

    async def _with_retry(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        logger = logging.getLogger(__name__)
        for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
            try:
                return await operation()
            except Exception as exc:
                if attempt >= _RETRY_MAX_ATTEMPTS or not is_retryable_exchange_error(exc):
                    raise
                delay = _retry_delay_seconds(attempt)
                logger.warning(
                    "Transient exchange error during %s (attempt %d/%d), retrying in %.2fs: %s",
                    operation_name,
                    attempt,
                    _RETRY_MAX_ATTEMPTS,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

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
                if _is_restricted_location_error(exc):
                    logger.warning(
                        "CCXT load_markets blocked by exchange location restrictions for %s; continuing without markets",
                        exchange_id,
                    )
                    return self._client
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


def _daily_pnl_has_activity(snapshot: Optional[DailyPnlSnapshot]) -> bool:
    if snapshot is None:
        return False
    if abs(float(snapshot.realized_pnl or 0.0)) > 0:
        return True
    if int(snapshot.trade_count or 0) > 0:
        return True
    return bool(snapshot.fills)


def _resolve_local_timezone():
    configured = (get_settings().local_timezone or "").strip()
    if configured:
        try:
            return ZoneInfo(configured)
        except ZoneInfoNotFoundError:
            logging.getLogger(__name__).warning(
                "Invalid BACKEND_LOCAL_TIMEZONE=%s; falling back to system local timezone",
                configured,
            )
    return datetime.now().astimezone().tzinfo or timezone.utc


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

    if "-" in raw:
        parts = raw.split("-")
        base = parts[0]
        # Common PERP formats
        add(raw.replace("-", "/"))
        add(raw.replace("-", "/").replace("PERP", "USDT:USDT"))
        add(f"{base}/USDT:USDC")  # Hyperliquid
        add(f"{base}/USDC:USDC")  # Hyperliquid (USDC quote)
        add(f"{base}/USD:USD")    # Generic USD
        if len(parts) > 1:
            add(f"{parts[0]}/{parts[1]}")

    return candidates


def _normalize_requested_symbols(symbols: Optional[List[str]]) -> List[str]:
    if not symbols:
        return []
    normalized = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    return sorted(normalized)


def _filter_open_orders_by_symbols(client: Any, orders: List[dict], symbols: List[str]) -> List[dict]:
    if not symbols:
        return orders
    symbol_keys: set[str] = set()
    market_ids: set[str] = set()
    for symbol in symbols:
        for candidate in _symbol_candidates(client, symbol):
            symbol_keys.add(candidate.upper())
            normalized = _normalize_position_symbol(candidate)
            if normalized:
                symbol_keys.add(normalized.upper())
        market_id = _resolve_market_id(client, symbol)
        if market_id:
            market_ids.add(str(market_id).upper())

    filtered: List[dict] = []
    for order in orders:
        if _order_matches_symbol_filters(order, symbol_keys, market_ids):
            filtered.append(order)
    return filtered


def _order_matches_symbol_filters(order: Any, symbol_keys: set[str], market_ids: set[str]) -> bool:
    if not isinstance(order, dict):
        return False
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    candidates = [
        order.get("symbol"),
        order.get("marketId"),
        order.get("pair"),
        info.get("symbol"),
        info.get("pair"),
        info.get("marketId"),
        info.get("instId"),
    ]
    for raw in candidates:
        if raw is None:
            continue
        token = str(raw).strip()
        if not token:
            continue
        upper_token = token.upper()
        if upper_token in symbol_keys or upper_token in market_ids:
            return True
        normalized = _normalize_position_symbol(token)
        if normalized and normalized.upper() in symbol_keys:
            return True
    return False


def _resolve_ccxt_market_symbol(client: Any, symbol: str) -> str:
    candidates = _symbol_candidates(client, symbol)
    markets = getattr(client, "markets", {}) or {}
    for candidate in candidates:
        if candidate in markets:
            return candidate
    if candidates:
        return candidates[0]
    return str(symbol)


async def _fetch_binance_open_algo_orders(client: Any, symbols: Optional[List[str]]) -> List[dict]:
    if not hasattr(client, "fapiPrivateGetOpenAlgoOrders"):
        return []

    orders: List[dict] = []

    if symbols:
        for symbol in symbols:
            market_id = _resolve_market_id(client, symbol)
            params = {"symbol": market_id} if market_id else {}
            try:
                payload = await client.fapiPrivateGetOpenAlgoOrders(params)
            except Exception:
                payload = []
            orders.extend(_normalize_algo_orders(client, payload, market_id))
    else:
        try:
            payload = await client.fapiPrivateGetOpenAlgoOrders()
        except Exception:
            payload = []
        orders.extend(_normalize_algo_orders(client, payload, None))

    return orders


def _resolve_market_id(client: Any, symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return None
    raw = str(symbol).strip()
    if not raw:
        return None
    markets = getattr(client, "markets", {}) or {}
    for candidate in _symbol_candidates(client, raw):
        market = markets.get(candidate)
        if isinstance(market, dict) and market.get("id"):
            return str(market.get("id"))
    try:
        market = client.market(raw)
    except Exception:
        market = None
    if isinstance(market, dict):
        market_id = market.get("id")
        if market_id:
            return str(market_id)
    if "/" not in raw:
        return raw
    return None


def _normalize_algo_orders(client: Any, payload: Any, fallback_symbol: Optional[str]) -> List[dict]:
    if not payload:
        return []
    rows = payload if isinstance(payload, list) else []
    orders: List[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        raw_symbol = raw.get("symbol") or fallback_symbol
        symbol = _map_market_id_to_symbol(client, raw_symbol)
        orders.append(
            {
                "id": raw.get("algoId") or raw.get("orderId"),
                "symbol": symbol,
                "type": raw.get("orderType") or raw.get("type"),
                "stopPrice": raw.get("triggerPrice") or raw.get("stopPrice"),
                "reduceOnly": raw.get("reduceOnly") or raw.get("closePosition"),
                "status": raw.get("algoStatus") or raw.get("status") or "NEW",
                "info": raw,
            }
        )
    return orders


def _map_market_id_to_symbol(client: Any, raw_symbol: Optional[str]) -> str:
    if not raw_symbol:
        return ""
    symbol = str(raw_symbol).strip()
    if not symbol:
        return ""
    markets_by_id = getattr(client, "markets_by_id", {}) or {}
    market = markets_by_id.get(symbol)
    if isinstance(market, dict):
        mapped = market.get("symbol")
        if mapped:
            return str(mapped)
    return symbol


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


def _is_restricted_location_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "restricted location" in message or "eligibility" in message:
        return True
    if "service unavailable" in message and "451" in message:
        return True
    return False


def is_retryable_exchange_error(exc: Exception) -> bool:
    if _is_restricted_location_error(exc):
        return False

    if ccxt is not None:
        retryable_types = []
        for name in _RETRYABLE_CCXT_ERROR_NAMES:
            candidate = getattr(ccxt, name, None)
            if isinstance(candidate, type):
                retryable_types.append(candidate)
        if retryable_types and isinstance(exc, tuple(retryable_types)):
            return True

    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True

    message = str(exc).lower()
    return any(token in message for token in _RETRYABLE_ERROR_TEXT)


def _retry_delay_seconds(attempt: int) -> float:
    delay = _RETRY_BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))
    delay = min(delay, _RETRY_MAX_DELAY_SECONDS)
    return delay + random.uniform(0.0, _RETRY_JITTER_SECONDS)


async def _fetch_binance_income_trades(
    client: Any,
    since_ms: int,
    until_ms: int | None,
    limit: int,
) -> List[dict]:
    income_records = await _fetch_binance_realized_pnl_records(
        client,
        since_ms=since_ms,
        until_ms=until_ms,
    )
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
        if timestamp is not None and timestamp < since_ms:
            continue
        if until_ms is not None and timestamp is not None and timestamp > until_ms:
            continue
        trades.append(
            {
                "symbol": symbol,
                "order_id": record.get("tradeId") or record.get("tranId"),
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


async def _fetch_binance_realized_pnl_records(
    client: Any,
    since_ms: int,
    until_ms: int | None,
) -> List[dict]:
    try:
        params = {
            "incomeType": "REALIZED_PNL",
            "startTime": since_ms,
            "limit": 1000,
        }
        if until_ms is not None:
            params["endTime"] = until_ms
        income_records = await client.fapiPrivateGetIncome(params)
    except Exception:
        income_records = []
    if not isinstance(income_records, list):
        return []

    income_records.sort(key=lambda item: _to_timestamp_ms(item.get("time") or 0) or 0, reverse=True)
    return income_records


async def _fetch_binance_recent_completed_positions(
    client: Any,
    since_ms: int,
    until_ms: int | None,
    limit: int,
) -> List[dict]:
    income_records = await _fetch_binance_realized_pnl_records(
        client,
        since_ms=since_ms,
        until_ms=until_ms,
    )
    if not income_records:
        return []

    symbols: List[str] = []
    seen_symbols: set[str] = set()
    max_symbols = max(limit * 4, 12)
    for record in income_records:
        if not isinstance(record, dict):
            continue
        symbol = _normalize_income_symbol(record.get("symbol") or "")
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        symbols.append(symbol)
        if len(symbols) >= max_symbols:
            break

    trades = await _fetch_ccxt_trade_history(
        client,
        since_ms=since_ms,
        limit=max(limit * 50, 200),
        symbols=symbols or None,
    )
    positions = _aggregate_completed_positions_from_trades(
        trades,
        since_ms=since_ms,
        until_ms=until_ms,
        limit=limit,
    )
    if positions:
        return positions

    return await _fetch_binance_income_trades(
        client,
        since_ms=since_ms,
        until_ms=until_ms,
        limit=limit,
    )


async def _fetch_ccxt_recent_trades(
    client: Any,
    since_ms: int,
    until_ms: int | None,
    limit: int,
) -> List[dict]:
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

    if not has.get("fetchMyTrades"):
        return []

    all_trades: List[dict] = []
    if symbols:
        for symbol in symbols:
            try:
                trades = await client.fetch_my_trades(symbol=symbol, limit=50)
            except Exception:
                trades = []
            for trade in trades or []:
                if isinstance(trade, dict):
                    all_trades.append(trade)
    else:
        try:
            trades = await client.fetch_my_trades(since=since_ms, limit=max(limit, 50))
        except TypeError:
            trades = []
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
        timestamp = _to_timestamp_ms(trade.get("timestamp"))
        if timestamp is not None and timestamp < since_ms:
            continue
        if until_ms is not None and timestamp is not None and timestamp > until_ms:
            continue
        info = trade.get("info") if isinstance(trade.get("info"), dict) else {}
        realized_pnl = info.get("realizedPnl") or info.get("closedPnl")
        pnl_value = _to_float(realized_pnl)
        if pnl_value is None or pnl_value == 0:
            continue

        symbol = _normalize_ccxt_symbol(trade.get("symbol") or "")
        side = str(trade.get("side") or "").lower()
        amount = _to_float(trade.get("amount")) or 0.0
        price = _to_float(trade.get("price")) or 0.0

        closed_trades.append(
            {
                "symbol": symbol,
                "order_id": info.get("orderId") or trade.get("order") or trade.get("id"),
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


async def _fetch_ccxt_recent_completed_positions(
    client: Any,
    since_ms: int,
    until_ms: int | None,
    limit: int,
) -> List[dict]:
    trades = await _fetch_ccxt_trade_history(
        client,
        since_ms=since_ms,
        limit=max(limit * 50, 200),
        symbols=None,
    )
    return _aggregate_completed_positions_from_trades(
        trades,
        since_ms=since_ms,
        until_ms=until_ms,
        limit=limit,
    )


async def _fetch_ccxt_trade_history(
    client: Any,
    since_ms: int,
    limit: int,
    symbols: Optional[List[str]] = None,
) -> List[dict]:
    has = getattr(client, "has", {}) or {}
    if not has.get("fetchMyTrades"):
        return []

    fetch_limit = max(50, min(int(limit or 200), 1000))
    candidate_symbols: List[str] = []
    seen_symbols: set[str] = set()

    def add_symbol(raw_symbol: Any) -> None:
        if not raw_symbol:
            return
        symbol = str(raw_symbol).strip()
        if not symbol or symbol in seen_symbols:
            return
        seen_symbols.add(symbol)
        candidate_symbols.append(symbol)

    if symbols:
        for symbol in symbols:
            add_symbol(symbol)
    else:
        if has.get("fetchPositions"):
            try:
                positions = await client.fetch_positions()
            except Exception:
                positions = []
            for position in positions or []:
                if isinstance(position, dict):
                    add_symbol(position.get("symbol"))

        if has.get("fetchClosedOrders"):
            try:
                closed_orders = await client.fetch_closed_orders(since=since_ms)
            except Exception:
                closed_orders = []
            for order in closed_orders or []:
                if isinstance(order, dict):
                    add_symbol(order.get("symbol"))

    all_trades: List[dict] = []
    if candidate_symbols:
        for raw_symbol in candidate_symbols:
            market_symbol = _resolve_recent_trade_symbol(client, raw_symbol)
            try:
                trades = await client.fetch_my_trades(
                    symbol=market_symbol,
                    since=since_ms,
                    limit=fetch_limit,
                )
            except TypeError:
                try:
                    trades = await client.fetch_my_trades(symbol=market_symbol, limit=fetch_limit)
                except Exception:
                    trades = []
            except Exception:
                trades = []

            for trade in trades or []:
                if isinstance(trade, dict):
                    all_trades.append(trade)
    else:
        try:
            trades = await client.fetch_my_trades(since=since_ms, limit=fetch_limit)
        except TypeError:
            try:
                trades = await client.fetch_my_trades(limit=fetch_limit)
            except Exception:
                trades = []
        except Exception:
            trades = []

        for trade in trades or []:
            if isinstance(trade, dict):
                all_trades.append(trade)

    all_trades.sort(key=lambda trade: _to_timestamp_ms(trade.get("timestamp")) or 0)
    return all_trades


def _resolve_recent_trade_symbol(client: Any, raw_symbol: str) -> str:
    candidates = _symbol_candidates(client, raw_symbol)
    markets = getattr(client, "markets", {}) or {}
    for candidate in candidates:
        if candidate in markets:
            return candidate
    return candidates[0] if candidates else raw_symbol


def _aggregate_completed_positions_from_trades(
    trades: List[dict],
    *,
    since_ms: int,
    until_ms: int | None,
    limit: int,
) -> List[dict]:
    if not trades:
        return []

    epsilon = 1e-8
    states: Dict[str, Dict[str, Any]] = {}
    completed: List[dict] = []

    for trade in trades:
        if not isinstance(trade, dict):
            continue
        timestamp = _to_timestamp_ms(trade.get("timestamp"))
        if timestamp is None:
            continue
        if until_ms is not None and timestamp > until_ms:
            continue

        symbol = _normalize_ccxt_symbol(trade.get("symbol") or "")
        side = str(trade.get("side") or "").lower()
        amount = _to_float(trade.get("amount")) or 0.0
        price = _to_float(trade.get("price")) or 0.0
        if not symbol or side not in {"buy", "sell"} or amount <= 0 or price <= 0:
            continue

        delta = amount if side == "buy" else -amount
        state = states.get(symbol)

        if state is None or abs(state["size"]) < epsilon:
            states[symbol] = _new_completed_position_state(
                symbol=symbol,
                delta=delta,
                price=price,
                timestamp=timestamp,
            )
            continue

        size = float(state["size"])
        if size * delta > 0:
            _add_to_completed_position_state(state, delta=delta, price=price)
            continue

        close_qty = min(abs(size), abs(delta))
        if close_qty <= epsilon:
            continue

        state["realized_pnl"] += _extract_trade_realized_pnl(
            trade,
            avg_entry=float(state["avg_entry"]),
            exit_price=price,
            close_qty=close_qty,
            current_size=size,
            trade_amount=amount,
        )
        state["closed_qty_total"] += close_qty
        state["exit_notional_total"] += close_qty * price
        state["last_close_time"] = timestamp
        state["last_close_ref"] = _build_completed_position_close_ref(trade, symbol, timestamp)

        new_size = size + delta
        if abs(new_size) < epsilon:
            emitted = _finalize_completed_position_state(state)
            if emitted is not None and emitted.get("exit_time") is not None:
                exit_time = int(emitted["exit_time"])
                if exit_time >= since_ms and (until_ms is None or exit_time <= until_ms):
                    completed.append(emitted)
            states.pop(symbol, None)
            continue

        if size * new_size < 0:
            emitted = _finalize_completed_position_state(state)
            if emitted is not None and emitted.get("exit_time") is not None:
                exit_time = int(emitted["exit_time"])
                if exit_time >= since_ms and (until_ms is None or exit_time <= until_ms):
                    completed.append(emitted)

            remaining_delta = new_size
            states[symbol] = _new_completed_position_state(
                symbol=symbol,
                delta=remaining_delta,
                price=price,
                timestamp=timestamp,
            )
            continue

        state["size"] = new_size

    completed.sort(key=lambda item: _to_timestamp_ms(item.get("exit_time")) or 0, reverse=True)
    return completed[:limit]


def _new_completed_position_state(
    *,
    symbol: str,
    delta: float,
    price: float,
    timestamp: int,
) -> Dict[str, Any]:
    abs_delta = abs(delta)
    direction = "long" if delta > 0 else "short"
    return {
        "symbol": symbol,
        "direction": direction,
        "size": delta,
        "avg_entry": price,
        "opened_at": timestamp,
        "entry_qty_total": abs_delta,
        "entry_notional_total": abs_delta * price,
        "closed_qty_total": 0.0,
        "exit_notional_total": 0.0,
        "realized_pnl": 0.0,
        "max_abs_size": abs_delta,
        "last_close_time": None,
        "last_close_ref": None,
    }


def _add_to_completed_position_state(state: Dict[str, Any], *, delta: float, price: float) -> None:
    current_size = abs(float(state["size"]))
    add_size = abs(delta)
    new_size = current_size + add_size
    if new_size <= 0:
        return
    state["avg_entry"] = ((float(state["avg_entry"]) * current_size) + (price * add_size)) / new_size
    state["size"] = float(state["size"]) + delta
    state["entry_qty_total"] += add_size
    state["entry_notional_total"] += add_size * price
    state["max_abs_size"] = max(float(state["max_abs_size"]), abs(float(state["size"])))


def _extract_trade_realized_pnl(
    trade: dict,
    *,
    avg_entry: float,
    exit_price: float,
    close_qty: float,
    current_size: float,
    trade_amount: float,
) -> float:
    fee_cost = _extract_fee_cost(trade)
    fee_share = fee_cost * (close_qty / trade_amount) if trade_amount > 0 else fee_cost
    info = trade.get("info") if isinstance(trade.get("info"), dict) else {}
    realized = _to_float(
        info.get("realizedPnl")
        or info.get("closedPnl")
        or trade.get("realizedPnl")
        or trade.get("closedPnl")
    )
    if realized is not None:
        return realized - fee_share
    if current_size > 0:
        return ((exit_price - avg_entry) * close_qty) - fee_share
    return ((avg_entry - exit_price) * close_qty) - fee_share


def _build_completed_position_close_ref(trade: dict, symbol: str, timestamp: int) -> str:
    info = trade.get("info") if isinstance(trade.get("info"), dict) else {}
    raw_ref = (
        info.get("orderId")
        or trade.get("order")
        or trade.get("id")
        or info.get("id")
        or info.get("tradeId")
    )
    if raw_ref is None:
        return f"{symbol}:{timestamp}"
    return f"{symbol}:{raw_ref}:{timestamp}"


def _finalize_completed_position_state(state: Dict[str, Any]) -> Optional[dict]:
    closed_qty = _to_float(state.get("closed_qty_total")) or 0.0
    exit_time = _to_timestamp_ms(state.get("last_close_time"))
    if closed_qty <= 0 or exit_time is None:
        return None

    entry_qty_total = _to_float(state.get("entry_qty_total")) or 0.0
    entry_notional_total = _to_float(state.get("entry_notional_total")) or 0.0
    exit_notional_total = _to_float(state.get("exit_notional_total")) or 0.0
    max_abs_size = _to_float(state.get("max_abs_size")) or 0.0
    pnl = _to_float(state.get("realized_pnl")) or 0.0
    entry_price = (
        (entry_notional_total / entry_qty_total)
        if entry_qty_total > 0
        else _to_float(state.get("avg_entry"))
    )
    exit_price = (exit_notional_total / closed_qty) if closed_qty > 0 else None
    reference_notional = None
    if entry_price is not None and max_abs_size > 0:
        reference_notional = max_abs_size * entry_price

    roi_pct = None
    if reference_notional and reference_notional > 0:
        roi_pct = (pnl / reference_notional) * 100.0

    opened_at = _to_timestamp_ms(state.get("opened_at"))
    duration_minutes = 0
    if opened_at is not None and exit_time >= opened_at:
        duration_minutes = int((exit_time - opened_at) / 60000)

    return {
        "symbol": state.get("symbol"),
        "order_id": state.get("last_close_ref"),
        "direction": state.get("direction"),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "size": max_abs_size or closed_qty,
        "size_usd": reference_notional,
        "position_size_usd": reference_notional,
        "pnl": pnl,
        "roi_pct": roi_pct,
        "entry_time": opened_at,
        "exit_time": exit_time,
        "duration_minutes": duration_minutes,
        "is_win": pnl > 0,
    }


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
