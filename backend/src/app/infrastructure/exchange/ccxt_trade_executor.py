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


@dataclass(frozen=True)
class ProtectionOrderSnapshot:
    trigger_price: float
    order_type: str


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
            had_position_before = await self._has_open_position(symbol)
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

            protection_result = None
            if had_position_before is not True:
                protection_result = await self._maybe_set_sl_tp(symbol, decision, result)
            return _merge_entry_execution_with_protection(result, protection_result)
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
            had_position_before = await self._has_open_position(symbol)
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
                protection_result = None
                if had_position_before is not True:
                    protection_result = await self._maybe_set_sl_tp(symbol, decision, result)
                return _merge_entry_execution_with_protection(result, protection_result)
            return result
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def place_open_stop_market(
        self,
        *,
        symbol: str,
        side: str,
        size_usd: float,
        trigger_price: float,
        leverage: int,
    ) -> ExecutionResult:
        if size_usd <= 0:
            return ExecutionResult(success=False, status="invalid", error="size_usd required")
        if trigger_price <= 0:
            return ExecutionResult(success=False, status="invalid", error="trigger_price required")

        try:
            symbol = self._normalize_symbol(symbol)
            await self._set_margin_mode(symbol)
            await self._client.set_leverage(leverage, symbol)
            amount = size_usd / trigger_price
            hedge_side = "LONG" if side == "buy" else "SHORT"
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type="stop_market",
                side=side,
                amount=amount,
                params={"stopPrice": trigger_price},
                hedge_position_side=hedge_side,
            )
            order_id = str(order.get("id") or order.get("orderId") or order.get("algoId") or "")
            return ExecutionResult(
                success=True,
                status="resting",
                order_id=order_id,
                filled_size=float(order.get("filled") or 0) if order.get("filled") else None,
                raw_response=order,
            )
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
            return await self._replace_protection_order(
                symbol=symbol,
                kind="sl",
                trigger_price=trigger_price,
                cancel_action=ExecutionAction.CANCEL_SL,
                order_type="stop_market",
                success_status="sl_set",
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _update_take_profit(self, symbol: str, trigger_price: float) -> ExecutionResult:
        try:
            return await self._replace_protection_order(
                symbol=symbol,
                kind="tp",
                trigger_price=trigger_price,
                cancel_action=ExecutionAction.CANCEL_TP,
                order_type="take_profit_market",
                success_status="tp_set",
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

    async def _replace_protection_order(
        self,
        *,
        symbol: str,
        kind: str,
        trigger_price: float,
        cancel_action: ExecutionAction,
        order_type: str,
        success_status: str,
    ) -> ExecutionResult:
        position_result = await self._load_position_context(symbol)
        if position_result.error_result is not None:
            return position_result.error_result

        position = position_result.position
        assert position is not None
        assert position_result.side is not None
        assert position_result.amount is not None

        previous_order = await self._get_existing_protection_order(
            symbol=symbol,
            kind=kind,
            position=position,
        )

        cancel_result = await self._cancel_conditional_orders(symbol, cancel_action)
        if not cancel_result.success:
            label = "stop loss" if kind == "sl" else "take profit"
            return ExecutionResult(
                success=False,
                status="error",
                error=f"failed to cancel existing {label}: {cancel_result.error or cancel_result.status}",
            )

        create_result = await self._place_protection_order(
            symbol=symbol,
            position=position,
            side=position_result.side,
            order_type=order_type,
            trigger_price=trigger_price,
            success_status=success_status,
        )
        if create_result.success:
            return create_result

        if previous_order is None:
            return create_result

        restore_result = await self._place_protection_order(
            symbol=symbol,
            position=position,
            side=position_result.side,
            order_type=previous_order.order_type or order_type,
            trigger_price=previous_order.trigger_price,
            success_status=success_status,
        )
        label = "stop loss" if kind == "sl" else "take profit"
        if restore_result.success:
            return ExecutionResult(
                success=False,
                status="rolled_back",
                order_id=restore_result.order_id,
                error=(
                    f"{label} update failed; restored previous {label} at "
                    f"{previous_order.trigger_price:.5g}: {create_result.error or create_result.status}"
                ),
                raw_response={
                    "failed_update": create_result.raw_response,
                    "restored_order": restore_result.raw_response,
                },
            )

        return ExecutionResult(
            success=False,
            status="error",
            error=(
                f"{label} update failed and restore failed: "
                f"update={create_result.error or create_result.status}; "
                f"restore={restore_result.error or restore_result.status}"
            ),
            raw_response={
                "failed_update": create_result.raw_response,
                "restore_attempt": restore_result.raw_response,
            },
        )

    async def _place_protection_order(
        self,
        *,
        symbol: str,
        position: Dict[str, Any],
        side: str,
        order_type: str,
        trigger_price: float,
        success_status: str,
    ) -> ExecutionResult:
        try:
            order = await self._create_order_with_reduce_only_fallback(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=None,
                price=None,
                params=self._close_position_trigger_params(position, {"stopPrice": trigger_price}),
                hedge_position_side=self._resolve_binance_position_side(position),
            )
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

        return ExecutionResult(
            success=True,
            status=success_status,
            order_id=str(order.get("id", "")),
            raw_response=order,
        )

    async def _has_open_position(self, symbol: str) -> Optional[bool]:
        try:
            positions = await self._client.fetch_positions([symbol])
        except Exception:
            return None
        return next((p for p in positions if p.get("contracts") or p.get("size")), None) is not None

    @dataclass(frozen=True)
    class _PositionContext:
        position: Optional[Dict[str, Any]]
        side: Optional[str]
        amount: Optional[float]
        error_result: Optional[ExecutionResult]

    async def _load_position_context(self, symbol: str) -> "_PositionContext":
        try:
            positions = await self._client.fetch_positions([symbol])
        except Exception as exc:
            return self._PositionContext(
                position=None,
                side=None,
                amount=None,
                error_result=ExecutionResult(success=False, status="error", error=str(exc)),
            )

        position = next((p for p in positions if p.get("contracts") or p.get("size")), None)
        if not position:
            return self._PositionContext(
                position=None,
                side=None,
                amount=None,
                error_result=ExecutionResult(success=False, status="not_found", error=f"No open position for {symbol}"),
            )

        direction = self._resolve_position_direction(position)
        if direction is None:
            return self._PositionContext(
                position=None,
                side=None,
                amount=None,
                error_result=ExecutionResult(
                    success=False,
                    status="invalid",
                    error="Unable to resolve position side",
                ),
            )

        side = "sell" if direction == "long" else "buy"
        amount = abs(float(position.get("contracts") or position.get("size") or 0))
        if amount <= 0:
            return self._PositionContext(
                position=None,
                side=None,
                amount=None,
                error_result=ExecutionResult(
                    success=False,
                    status="invalid",
                    error=f"No open position for {symbol}",
                ),
            )

        return self._PositionContext(
            position=position,
            side=side,
            amount=amount,
            error_result=None,
        )

    async def _get_existing_protection_order(
        self,
        *,
        symbol: str,
        kind: str,
        position: Dict[str, Any],
    ) -> Optional[ProtectionOrderSnapshot]:
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

            open_orders = await self._client.fetch_open_orders(symbol)
            use_binance_algo = False
            if exchange_id == "binance" and market_id:
                params: Dict[str, Any] = {"symbol": market_id, "algoType": "CONDITIONAL"}
                try:
                    if hasattr(self._client, "fapiPrivateGetOpenAlgoOrders"):
                        algo_orders = await self._client.fapiPrivateGetOpenAlgoOrders(params)
                    else:
                        algo_orders = await self._client.request("openAlgoOrders", "fapiPrivate", "GET", params)
                except Exception:
                    algo_orders = None
                if isinstance(algo_orders, list):
                    open_orders = algo_orders
                    use_binance_algo = True

            direction = self._resolve_position_direction(position)
            mark_price = _safe_float(position.get("markPrice"))
            if mark_price is None and isinstance(position.get("info"), dict):
                mark_price = _safe_float(position["info"].get("markPrice"))

            for order in open_orders or []:
                if use_binance_algo:
                    status = str(order.get("algoStatus") or "").upper()
                    if status and not _is_open_order_status(status):
                        continue
                    order_type = str(order.get("orderType") or order.get("type") or "").lower()
                    stop_price = _safe_float(order.get("triggerPrice")) or _safe_float(order.get("stopPrice"))
                    reduce_only = bool(order.get("reduceOnly") or order.get("closePosition"))
                else:
                    status = str(order.get("status") or "").upper()
                    if status and not _is_open_order_status(status):
                        continue
                    order_type = _extract_order_type(order)
                    stop_price = _extract_stop_price(order)
                    reduce_only = _extract_reduce_only(order)

                if order_type not in ("stop", "stop_market", "take_profit", "take_profit_market") and not stop_price:
                    continue
                if not _is_trigger_order(order_type, stop_price, reduce_only):
                    continue

                order_kind = _classify_trigger_order_kind(
                    order_type=order_type,
                    stop_price=stop_price,
                    mark_price=mark_price,
                    position_side=direction,
                )
                if order_kind != kind or stop_price is None or stop_price <= 0:
                    continue

                return ProtectionOrderSnapshot(trigger_price=stop_price, order_type=order_type)
        except Exception:
            return None
        return None

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
                    if status and not _is_open_order_status(status):
                        continue
                    order_type = str(order.get("orderType") or order.get("type") or "").lower()
                    stop_price = _safe_float(order.get("triggerPrice")) or _safe_float(order.get("stopPrice"))
                    reduce_only = bool(order.get("reduceOnly") or order.get("closePosition"))
                    if order_type not in ("stop", "stop_market", "take_profit", "take_profit_market") and not stop_price:
                        continue
                    if not _is_trigger_order(order_type, stop_price, reduce_only):
                        continue

                    if action in (ExecutionAction.CANCEL_SL, ExecutionAction.CANCEL_TP):
                        order_kind = _classify_trigger_order_kind(
                            order_type=order_type,
                            stop_price=stop_price,
                            mark_price=mark_price,
                            position_side=position_side,
                        )

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
                if status and not _is_open_order_status(status):
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
                    order_kind = _classify_trigger_order_kind(
                        order_type=order_type,
                        stop_price=stop_price,
                        mark_price=mark_price,
                        position_side=position_side,
                    )

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

    def _close_position_trigger_params(
        self,
        position: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"closePosition": True}
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

    async def _maybe_set_sl_tp(
        self,
        symbol: str,
        decision: ExecutionIdea,
        result: ExecutionResult,
    ) -> Optional[ExecutionResult]:
        stop_loss_price = decision.stop_loss
        take_profit_price = decision.take_profit

        direction = _resolve_open_direction(decision.action)
        leverage = decision.leverage or 1
        reference_price = _resolve_bracket_reference_price(result, decision)

        if direction and leverage > 0 and reference_price and reference_price > 0:
            if stop_loss_price is None and decision.stop_loss_roe is not None:
                stop_loss_price = _calculate_initial_stop_loss_from_roe(
                    risk_roe=decision.stop_loss_roe,
                    entry_price=reference_price,
                    leverage=leverage,
                    direction=direction,
                )
            if take_profit_price is None and decision.take_profit_roe is not None and decision.take_profit_roe > 0:
                take_profit_price = _calculate_take_profit_from_roe(
                    target_roe=decision.take_profit_roe,
                    entry_price=reference_price,
                    leverage=leverage,
                    direction=direction,
                )

        if not stop_loss_price and not take_profit_price:
            return None

        return await self.set_sl_tp(symbol, stop_loss_price, take_profit_price)

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


def _resolve_open_direction(action: ExecutionAction) -> Optional[str]:
    if action in (ExecutionAction.OPEN_LONG, ExecutionAction.OPEN_LONG_LIMIT):
        return "long"
    if action in (ExecutionAction.OPEN_SHORT, ExecutionAction.OPEN_SHORT_LIMIT):
        return "short"
    return None


def _resolve_bracket_reference_price(result: ExecutionResult, decision: ExecutionIdea) -> Optional[float]:
    for candidate in (result.fill_price, decision.limit_price, decision.entry_price):
        try:
            if candidate is None:
                continue
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _merge_entry_execution_with_protection(
    entry_result: ExecutionResult,
    protection_result: Optional[ExecutionResult],
) -> ExecutionResult:
    if protection_result is None or (
        protection_result.success and not protection_result.error and protection_result.status != "partial"
    ):
        return entry_result

    error_parts = []
    if protection_result.status == "partial":
        error_parts.append("protection_attach_partial")
    elif not protection_result.success:
        error_parts.append("protection_attach_failed")
    if protection_result.error:
        error_parts.append(protection_result.error)

    return ExecutionResult(
        success=True,
        status=entry_result.status,
        order_id=entry_result.order_id,
        fill_price=entry_result.fill_price,
        filled_size=entry_result.filled_size,
        realized_pnl=entry_result.realized_pnl,
        error=": ".join(error_parts) if error_parts else protection_result.error,
        raw_response={
            "entry_order": entry_result.raw_response,
            "protection": protection_result.raw_response,
            "protection_status": protection_result.status,
            "protection_order_id": protection_result.order_id,
        },
    )


def _calculate_initial_stop_loss_from_roe(
    *,
    risk_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    normalized_roe = abs(float(risk_roe))
    if direction == "long":
        stop_price = entry_price * (1 - (normalized_roe / leverage))
    else:
        stop_price = entry_price * (1 + (normalized_roe / leverage))
    return float(f"{stop_price:.5g}")


def _calculate_stop_loss_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    if direction == "long":
        stop_price = entry_price * (1 + (target_roe / leverage))
    else:
        stop_price = entry_price * (1 - (target_roe / leverage))
    return float(f"{stop_price:.5g}")


def _calculate_take_profit_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> float:
    if direction == "long":
        take_profit = entry_price * (1 + (target_roe / leverage))
    else:
        take_profit = entry_price * (1 - (target_roe / leverage))
    return float(f"{take_profit:.5g}")


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_order_type(order: Dict[str, Any]) -> str:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    return str(
        order.get("type")
        or order.get("orderType")
        or info.get("type")
        or info.get("orderType")
        or params.get("type")
        or ""
    ).lower()


def _extract_stop_price(order: Dict[str, Any]) -> Optional[float]:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    for candidate in (
        order.get("stopPrice"),
        order.get("triggerPrice"),
        order.get("triggerPx"),
        info.get("stopPrice"),
        info.get("triggerPrice"),
        info.get("triggerPx"),
        params.get("stopPrice"),
        params.get("triggerPrice"),
        params.get("triggerPx"),
    ):
        parsed = _safe_float(candidate)
        if parsed is not None:
            return parsed
    return None


def _extract_reduce_only(order: Dict[str, Any]) -> bool:
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    for source in (order, info, params):
        if source.get("reduceOnly") is True:
            return True
        if source.get("closePosition") is True:
            return True
    return False


def _is_trigger_order(order_type: str, stop_price: Optional[float], reduce_only: bool) -> bool:
    normalized = str(order_type or "").lower()
    if "take_profit" in normalized or "take-profit" in normalized or normalized.startswith("tp"):
        return True
    if "stop" in normalized:
        return True
    return reduce_only and stop_price is not None and stop_price > 0


def _classify_trigger_order_kind(
    *,
    order_type: str,
    stop_price: Optional[float],
    mark_price: Optional[float],
    position_side: Optional[str],
) -> Optional[str]:
    normalized = str(order_type or "").lower()
    if "take_profit" in normalized or "take-profit" in normalized or normalized.startswith("tp"):
        return "tp"
    if "stop" in normalized and "take" not in normalized:
        return "sl"

    if (
        stop_price is None
        or stop_price <= 0
        or mark_price is None
        or mark_price <= 0
        or position_side not in ("long", "short")
    ):
        return None

    if position_side == "long":
        return "sl" if stop_price <= mark_price else "tp"
    return "sl" if stop_price >= mark_price else "tp"


def _is_open_order_status(status: str) -> bool:
    normalized = str(status or "").strip().upper()
    return normalized in {"NEW", "OPEN", "PARTIALLY_FILLED"}
