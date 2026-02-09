from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import ccxt.async_support as ccxt
except ImportError:  # pragma: no cover
    ccxt = None

from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.trade_executor.models import ExecutionResult


@dataclass(frozen=True)
class CCXTTradeConfig:
    exchange_id: str
    api_key: str
    api_secret: str
    passphrase: Optional[str]
    is_testnet: bool
    quote_asset: str = "USDT"


class CCXTTradeExecutor:
    def __init__(self, config: CCXTTradeConfig) -> None:
        if ccxt is None:
            raise ImportError("ccxt is not installed. Add it to backend dependencies.")
        self._config = config
        self._client = None

    async def __aenter__(self) -> "CCXTTradeExecutor":
        exchange_id = self._config.exchange_id.lower()
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        options: Dict[str, Any] = {
            "defaultType": "swap",
        }

        self._client = exchange_class(
            {
                "apiKey": self._config.api_key,
                "secret": self._config.api_secret,
                "password": self._config.passphrase,
                "enableRateLimit": True,
                "options": options,
            }
        )

        if self._config.is_testnet:
            try:
                self._client.set_sandbox_mode(True)
            except Exception:
                pass

        await self._client.load_markets()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def execute(self, decision: ExecutionIdea) -> ExecutionResult:
        if self._client is None:
            raise RuntimeError("CCXTTradeExecutor is not initialized")

        action = decision.action
        symbol = self._normalize_symbol(decision.symbol)

        if action == ExecutionAction.OPEN_LONG:
            return await self._open_position(
                symbol,
                "buy",
                decision.position_size_usd,
                decision.leverage or 1,
                decision,
            )
        if action == ExecutionAction.OPEN_SHORT:
            return await self._open_position(
                symbol,
                "sell",
                decision.position_size_usd,
                decision.leverage or 1,
                decision,
            )
        if action == ExecutionAction.OPEN_LONG_LIMIT:
            return await self._open_position_limit(
                symbol,
                "buy",
                decision.position_size_usd,
                decision.limit_price,
                decision.leverage or 1,
                decision.time_in_force or "Gtc",
                decision,
            )
        if action == ExecutionAction.OPEN_SHORT_LIMIT:
            return await self._open_position_limit(
                symbol,
                "sell",
                decision.position_size_usd,
                decision.limit_price,
                decision.leverage or 1,
                decision.time_in_force or "Gtc",
                decision,
            )
        if action == ExecutionAction.CLOSE:
            return await self._close_position(symbol)
        if action == ExecutionAction.REDUCE:
            return await self._reduce_position(symbol, decision.reduce_pct or 0)
        if action == ExecutionAction.HOLD:
            return ExecutionResult(success=True, status="hold")
        if action == ExecutionAction.UPDATE_SL:
            if decision.new_stop_loss is None:
                return ExecutionResult(success=False, status="invalid", error="new_stop_loss required")
            return await self._update_stop_loss(symbol, decision.new_stop_loss)
        if action == ExecutionAction.UPDATE_TP:
            if decision.new_take_profit is None:
                return ExecutionResult(success=False, status="invalid", error="new_take_profit required")
            return await self._update_take_profit(symbol, decision.new_take_profit)
        if action in (ExecutionAction.CANCEL_SL, ExecutionAction.CANCEL_TP, ExecutionAction.CANCEL_SL_TP):
            return await self._cancel_conditional_orders(symbol, action)

        return ExecutionResult(success=False, status="unsupported", error=f"Unsupported action: {action}")

    def _normalize_symbol(self, symbol: str) -> str:
        symbol = symbol.upper()
        if "/" in symbol:
            return symbol
        quote = self._config.quote_asset.upper()
        if symbol.endswith(quote):
            symbol = symbol[: -len(quote)]
        return f"{symbol}/{quote}:{quote}"

    async def _open_position(
        self,
        symbol: str,
        side: str,
        size_usd: Optional[float],
        leverage: int,
        decision: ExecutionIdea,
    ) -> ExecutionResult:
        if size_usd is None or size_usd <= 0:
            return ExecutionResult(success=False, status="invalid", error="size_usd required")

        try:
            try:
                await self._cancel_conditional_orders(symbol, ExecutionAction.CANCEL_SL_TP)
            except Exception:
                pass
            await self._set_margin_mode(symbol)
            await self._client.set_leverage(leverage, symbol)
            ticker = await self._client.fetch_ticker(symbol)
            price = float(ticker.get("last") or ticker.get("close") or 0)
            if price <= 0:
                return ExecutionResult(success=False, status="invalid", error="invalid price")

            amount = size_usd / price
            hedge_side = "LONG" if side == "buy" else "SHORT"
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                hedge_position_side=hedge_side,
            )

            result = ExecutionResult(
                success=True,
                status="filled",
                order_id=str(order.get("id", "")),
                fill_price=float(order.get("average") or price),
                filled_size=float(order.get("filled") or amount),
                raw_response=order,
            )

            await self._maybe_set_sl_tp(symbol, decision, result)
            return result
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _open_position_limit(
        self,
        symbol: str,
        side: str,
        size_usd: Optional[float],
        limit_price: Optional[float],
        leverage: int,
        time_in_force: str,
        decision: ExecutionIdea,
    ) -> ExecutionResult:
        if size_usd is None or size_usd <= 0:
            return ExecutionResult(success=False, status="invalid", error="size_usd required")
        if not limit_price or limit_price <= 0:
            return ExecutionResult(success=False, status="invalid", error="limit_price required")

        try:
            try:
                await self._cancel_conditional_orders(symbol, ExecutionAction.CANCEL_SL_TP)
            except Exception:
                pass
            await self._set_margin_mode(symbol)
            await self._client.set_leverage(leverage, symbol)
            amount = size_usd / limit_price
            tif_map = {"Gtc": "GTC", "Ioc": "IOC", "Alo": "PO"}
            ccxt_tif = tif_map.get(time_in_force, "GTC")

            hedge_side = "LONG" if side == "buy" else "SHORT"
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=limit_price,
                params={"timeInForce": ccxt_tif},
                hedge_position_side=hedge_side,
            )

            status = "filled" if order.get("status") == "closed" else "resting"
            result = ExecutionResult(
                success=True,
                status=status,
                order_id=str(order.get("id", "")),
                fill_price=float(order.get("average") or 0) if order.get("filled") else None,
                filled_size=float(order.get("filled") or 0),
                raw_response=order,
            )

            if status == "filled":
                await self._maybe_set_sl_tp(symbol, decision, result)
            return result
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _close_position(self, symbol: str) -> ExecutionResult:
        try:
            positions = await self._client.fetch_positions([symbol])
            position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
            if not position:
                return ExecutionResult(success=False, status="not_found", error=f"No open position for {symbol}")

            direction = self._resolve_position_direction(position)
            if direction is None:
                return ExecutionResult(success=False, status="invalid", error="Unable to resolve position side")
            side = "sell" if direction == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=self._reduce_only_params(position),
            )

            try:
                await self._cancel_conditional_orders(symbol, ExecutionAction.CANCEL_SL_TP)
            except Exception:
                pass

            return ExecutionResult(
                success=True,
                status="filled",
                order_id=str(order.get("id", "")),
                fill_price=float(order.get("average") or 0),
                filled_size=float(order.get("filled") or amount),
                realized_pnl=position.get("unrealizedPnl"),
                raw_response=order,
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _reduce_position(self, symbol: str, reduce_pct: float) -> ExecutionResult:
        if reduce_pct <= 0:
            return ExecutionResult(success=False, status="invalid", error="reduce_pct required")

        try:
            positions = await self._client.fetch_positions([symbol])
            position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
            if not position:
                return ExecutionResult(success=False, status="not_found", error=f"No open position for {symbol}")

            direction = self._resolve_position_direction(position)
            if direction is None:
                return ExecutionResult(success=False, status="invalid", error="Unable to resolve position side")
            side = "sell" if direction == "long" else "buy"
            contracts = abs(float(position.get("contracts") or position.get("size") or 0))
            reduce_amount = contracts * (reduce_pct / 100.0)
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="market",
                side=side,
                amount=reduce_amount,
                params=self._reduce_only_params(position),
            )

            return ExecutionResult(
                success=True,
                status="filled",
                order_id=str(order.get("id", "")),
                fill_price=float(order.get("average") or 0),
                filled_size=float(order.get("filled") or reduce_amount),
                raw_response=order,
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _update_stop_loss(self, symbol: str, trigger_price: float) -> ExecutionResult:
        try:
            await self._cancel_conditional_orders(symbol, ExecutionAction.CANCEL_SL)
            positions = await self._client.fetch_positions([symbol])
            position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
            if not position:
                return ExecutionResult(success=False, status="not_found", error=f"No open position for {symbol}")

            direction = self._resolve_position_direction(position)
            if direction is None:
                return ExecutionResult(success=False, status="invalid", error="Unable to resolve position side")
            side = "sell" if direction == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="stop_market",
                side=side,
                amount=amount,
                params=self._reduce_only_params(position, {"stopPrice": trigger_price}),
            )

            return ExecutionResult(
                success=True,
                status="sl_set",
                order_id=str(order.get("id", "")),
                raw_response=order,
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _update_take_profit(self, symbol: str, trigger_price: float) -> ExecutionResult:
        try:
            await self._cancel_conditional_orders(symbol, ExecutionAction.CANCEL_TP)
            positions = await self._client.fetch_positions([symbol])
            position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
            if not position:
                return ExecutionResult(success=False, status="not_found", error=f"No open position for {symbol}")

            direction = self._resolve_position_direction(position)
            if direction is None:
                return ExecutionResult(success=False, status="invalid", error="Unable to resolve position side")
            side = "sell" if direction == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="take_profit_market",
                side=side,
                amount=amount,
                params=self._reduce_only_params(position, {"stopPrice": trigger_price}),
            )

            return ExecutionResult(
                success=True,
                status="tp_set",
                order_id=str(order.get("id", "")),
                raw_response=order,
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _cancel_conditional_orders(self, symbol: str, action: ExecutionAction) -> ExecutionResult:
        try:
            exchange_id = self._config.exchange_id.lower()
            market_id = None
            if exchange_id == "binance":
                try:
                    market = self._client.market(symbol)
                    if isinstance(market, dict):
                        market_id = market.get("id")
                except Exception:
                    market_id = None

            async def _fetch_binance_open_algo_orders() -> Optional[list[Dict[str, Any]]]:
                if exchange_id != "binance" or not market_id:
                    return None
                params: Dict[str, Any] = {"symbol": market_id, "algoType": "CONDITIONAL"}
                try:
                    if hasattr(self._client, "fapiPrivateGetOpenAlgoOrders"):
                        response = await self._client.fapiPrivateGetOpenAlgoOrders(params)
                    else:
                        response = await self._client.request("openAlgoOrders", "fapiPrivate", "GET", params)
                except Exception:
                    return None
                if isinstance(response, list):
                    return response
                return None

            async def _cancel_binance_algo_order(algo_id: str) -> None:
                if exchange_id != "binance" or not market_id:
                    return None
                params: Dict[str, Any] = {"symbol": market_id, "algoId": algo_id}
                if hasattr(self._client, "fapiPrivateDeleteAlgoOrder"):
                    await self._client.fapiPrivateDeleteAlgoOrder(params)
                else:
                    await self._client.request("algoOrder", "fapiPrivate", "DELETE", params)

            open_orders = await self._client.fetch_open_orders(symbol)
            use_binance_algo = False
            binance_algo_orders = await _fetch_binance_open_algo_orders()
            if binance_algo_orders is not None:
                open_orders = binance_algo_orders
                use_binance_algo = True

            if not open_orders:
                return ExecutionResult(success=True, status="canceled")

            def _safe_float(value: Any) -> Optional[float]:
                try:
                    if value is None or value == "":
                        return None
                    return float(value)
                except (TypeError, ValueError):
                    return None

            def _extract_order_type(order: Dict[str, Any]) -> str:
                order_type = order.get("type")
                if not order_type and isinstance(order.get("info"), dict):
                    info = order["info"]
                    order_type = info.get("type") or info.get("orderType")
                return str(order_type or "").lower()

            def _extract_stop_price(order: Dict[str, Any]) -> Optional[float]:
                for key in ("stopPrice", "triggerPrice"):
                    value = _safe_float(order.get(key))
                    if value:
                        return value
                if isinstance(order.get("info"), dict):
                    info = order["info"]
                    for key in ("stopPrice", "triggerPrice", "triggerPx"):
                        value = _safe_float(info.get(key))
                        if value:
                            return value
                return None

            def _extract_reduce_only(order: Dict[str, Any]) -> bool:
                value = order.get("reduceOnly")
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() == "true"
                close_position = order.get("closePosition")
                if isinstance(close_position, bool):
                    return close_position
                if isinstance(close_position, str):
                    return close_position.lower() == "true"
                if isinstance(order.get("info"), dict):
                    info_value = order["info"].get("reduceOnly")
                    if isinstance(info_value, bool):
                        return info_value
                    if isinstance(info_value, str):
                        return info_value.lower() == "true"
                    close_info = order["info"].get("closePosition")
                    if isinstance(close_info, bool):
                        return close_info
                    if isinstance(close_info, str):
                        return close_info.lower() == "true"
                return False

            def _is_trigger_order(order_type: str, stop_price: Optional[float], reduce_only: bool) -> bool:
                if stop_price is not None:
                    return True
                if "stop" in order_type or "profit" in order_type:
                    return True
                return reduce_only

            position_side = None
            mark_price = None
            if action in (ExecutionAction.CANCEL_SL, ExecutionAction.CANCEL_TP):
                try:
                    positions = await self._client.fetch_positions([symbol])
                except Exception:
                    positions = []
                position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
                if position:
                    side = str(position.get("side") or "").lower()
                    if not side and isinstance(position.get("info"), dict):
                        info = position["info"]
                        side = str(info.get("positionSide") or info.get("side") or info.get("posSide") or "").lower()
                    if side in ("long", "short"):
                        position_side = side
                    mark_price = _safe_float(position.get("markPrice"))
                    if mark_price is None and isinstance(position.get("info"), dict):
                        mark_price = _safe_float(position["info"].get("markPrice"))
                if mark_price is None:
                    try:
                        ticker = await self._client.fetch_ticker(symbol)
                        mark_price = _safe_float(ticker.get("last") or ticker.get("close"))
                    except Exception:
                        mark_price = None

            if use_binance_algo:
                for order in open_orders:
                    status = str(order.get("algoStatus") or "").upper()
                    if status and status != "NEW":
                        continue
                    order_type = str(order.get("orderType") or order.get("type") or "").lower()
                    stop_price = _safe_float(order.get("triggerPrice")) or _safe_float(order.get("stopPrice"))
                    reduce_only = bool(order.get("reduceOnly") or order.get("closePosition"))
                    if order_type not in ("stop", "stop_market", "take_profit", "take_profit_market") and not stop_price:
                        continue
                    if not _is_trigger_order(order_type, stop_price, reduce_only):
                        continue

                    if action in (ExecutionAction.CANCEL_SL, ExecutionAction.CANCEL_TP):
                        order_kind = None
                        if "take_profit" in order_type or "profit" in order_type:
                            order_kind = "tp"
                        elif "stop" in order_type:
                            order_kind = "sl"
                        elif stop_price is not None and mark_price is not None and position_side in ("long", "short"):
                            if position_side == "long":
                                order_kind = "sl" if stop_price < mark_price else "tp"
                            else:
                                order_kind = "sl" if stop_price > mark_price else "tp"

                        if action == ExecutionAction.CANCEL_SL and order_kind != "sl":
                            continue
                        if action == ExecutionAction.CANCEL_TP and order_kind != "tp":
                            continue

                    algo_id = order.get("algoId") or order.get("orderId")
                    if not algo_id:
                        continue
                    await _cancel_binance_algo_order(str(algo_id))

                return ExecutionResult(success=True, status="canceled")

            for order in open_orders:
                status = str(order.get("status") or "").upper()
                if status and status != "NEW":
                    continue
                order_id = order.get("id") or order.get("orderId")
                if not order_id:
                    continue
                order_type = _extract_order_type(order)
                stop_price = _extract_stop_price(order)
                reduce_only = _extract_reduce_only(order)
                if order_type not in ("stop", "stop_market", "take_profit", "take_profit_market") and not stop_price:
                    continue
                if not _is_trigger_order(order_type, stop_price, reduce_only):
                    continue

                if action in (ExecutionAction.CANCEL_SL, ExecutionAction.CANCEL_TP):
                    order_kind = None
                    if "take_profit" in order_type or "profit" in order_type:
                        order_kind = "tp"
                    elif "stop" in order_type:
                        order_kind = "sl"
                    elif stop_price is not None and mark_price is not None and position_side in ("long", "short"):
                        if position_side == "long":
                            order_kind = "sl" if stop_price < mark_price else "tp"
                        else:
                            order_kind = "sl" if stop_price > mark_price else "tp"

                    if action == ExecutionAction.CANCEL_SL and order_kind != "sl":
                        continue
                if action == ExecutionAction.CANCEL_TP and order_kind != "tp":
                    continue

                await self._client.cancel_order(order_id, symbol)
            return ExecutionResult(success=True, status="canceled")
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    def _resolve_position_direction(self, position: Dict[str, Any]) -> Optional[str]:
        raw = str(position.get("side") or position.get("direction") or "").lower()
        info = position.get("info") if isinstance(position.get("info"), dict) else {}
        if raw not in ("long", "short") and info:
            raw = str(info.get("positionSide") or info.get("side") or info.get("posSide") or "").lower()
        if raw in ("long", "short"):
            return raw
        return None

    def _resolve_binance_position_side(self, position: Dict[str, Any]) -> Optional[str]:
        info = position.get("info") if isinstance(position.get("info"), dict) else {}
        raw = info.get("positionSide") or info.get("posSide") or position.get("positionSide") or position.get("posSide")
        if not raw:
            return None
        raw_upper = str(raw).upper()
        if raw_upper in ("LONG", "SHORT"):
            return raw_upper
        return None

    def _reduce_only_params(self, position: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"reduceOnly": True}
        if extra:
            params.update(extra)
        if (self._config.exchange_id or "").lower() == "binance":
            position_side = self._resolve_binance_position_side(position)
            if position_side:
                params["positionSide"] = position_side
        return params

    async def _create_order_with_reduce_only_fallback(self, **kwargs: Any) -> Dict[str, Any]:
        hedge_position_side = kwargs.pop("hedge_position_side", None)
        params = dict(kwargs.get("params") or {})
        for _ in range(3):
            kwargs["params"] = params
            try:
                return await self._client.create_order(**kwargs)
            except Exception as exc:
                if self._should_retry_without_reduce_only(exc) and "reduceOnly" in params:
                    params = dict(params)
                    params.pop("reduceOnly", None)
                    continue
                if self._should_retry_position_side(exc):
                    params = dict(params)
                    if "positionSide" in params:
                        params.pop("positionSide", None)
                        continue
                    if hedge_position_side:
                        params["positionSide"] = hedge_position_side
                        continue
                raise
        raise RuntimeError("create_order retries exhausted")

    def _should_retry_without_reduce_only(self, exc: Exception) -> bool:
        message = str(exc).lower()
        if "reduceonly" not in message:
            return False
        return "not required" in message or "not needed" in message

    def _should_retry_position_side(self, exc: Exception) -> bool:
        message = str(exc).lower()
        if "position side" in message or "positionside" in message:
            return True
        return "-4061" in message

    async def _set_margin_mode(self, symbol: str) -> None:
        try:
            await self._client.set_margin_mode("isolated", symbol)
        except Exception:
            return None

    async def _maybe_set_sl_tp(self, symbol: str, decision: ExecutionIdea, result: ExecutionResult) -> None:
        if not decision.stop_loss and not decision.take_profit:
            return

        await self.set_sl_tp(symbol, decision.stop_loss, decision.take_profit)

    async def set_sl_tp(
        self,
        symbol: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> ExecutionResult:
        results = []
        errors = []

        if stop_loss_price:
            sl_result = await self._update_stop_loss(symbol, stop_loss_price)
            if sl_result.success:
                results.append(f"SL: {sl_result.order_id}")
            else:
                errors.append(f"SL: {sl_result.error}")

        if take_profit_price:
            tp_result = await self._update_take_profit(symbol, take_profit_price)
            if tp_result.success:
                results.append(f"TP: {tp_result.order_id}")
            else:
                errors.append(f"TP: {tp_result.error}")

        if errors:
            return ExecutionResult(
                success=len(results) > 0,
                status="partial" if results else "failed",
                order_id=", ".join(results) if results else None,
                error="; ".join(errors),
            )

        return ExecutionResult(
            success=True,
            status="sl_tp_set",
            order_id=", ".join(results) if results else None,
        )
