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
            await self._set_margin_mode(symbol)
            await self._client.set_leverage(leverage, symbol)
            ticker = await self._client.fetch_ticker(symbol)
            price = float(ticker.get("last") or ticker.get("close") or 0)
            if price <= 0:
                return ExecutionResult(success=False, status="invalid", error="invalid price")

            amount = size_usd / price
            order = await self._client.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
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
            await self._set_margin_mode(symbol)
            await self._client.set_leverage(leverage, symbol)
            amount = size_usd / limit_price
            tif_map = {"Gtc": "GTC", "Ioc": "IOC", "Alo": "PO"}
            ccxt_tif = tif_map.get(time_in_force, "GTC")

            order = await self._client.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=limit_price,
                params={"timeInForce": ccxt_tif},
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

            side = "sell" if position.get("side") == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._client.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params={"reduceOnly": True},
            )

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

            side = "sell" if position.get("side") == "long" else "buy"
            contracts = abs(float(position.get("contracts") or position.get("size") or 0))
            reduce_amount = contracts * (reduce_pct / 100.0)
            order = await self._client.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=reduce_amount,
                params={"reduceOnly": True},
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

            side = "sell" if position.get("side") == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._client.create_order(
                symbol=symbol,
                type="stop_market",
                side=side,
                amount=amount,
                params={"stopPrice": trigger_price, "reduceOnly": True},
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

            side = "sell" if position.get("side") == "long" else "buy"
            amount = abs(float(position.get("contracts") or position.get("size") or 0))
            order = await self._client.create_order(
                symbol=symbol,
                type="take_profit_market",
                side=side,
                amount=amount,
                params={"stopPrice": trigger_price, "reduceOnly": True},
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
            open_orders = await self._client.fetch_open_orders(symbol)
            for order in open_orders:
                order_type = str(order.get("type") or "").lower()
                if action == ExecutionAction.CANCEL_SL and "stop" not in order_type:
                    continue
                if action == ExecutionAction.CANCEL_TP and "profit" not in order_type:
                    continue
                await self._client.cancel_order(order["id"], symbol)
            return ExecutionResult(success=True, status="canceled")
        except Exception as exc:
            return ExecutionResult(success=False, status="error", error=str(exc))

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

