import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from typing import Iterable, List

from app.application.ema_scanner.dependencies import get_ema_config_service, get_ema_scanner_service
from app.application.ema_state_manager.dependencies import get_ema_state_manager_service
from app.application.image_uploader.dependencies import get_image_uploader_config_service
from app.application.quant_scanner.dependencies import get_quant_config_service, get_quant_scanner_service
from app.application.llm_caller.dependencies import get_llm_caller_service
from app.application.llm_caller.service import extract_chart_images
from app.application.llm_pipeline.dependencies import get_llm_execution_service
from app.application.llm_response_worker.dependencies import get_llm_response_worker_service
from app.application.trade_guard.dependencies import get_trade_guard_service
from app.application.circuit_breaker.dependencies import get_circuit_breaker_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.domain.ema_scanner.models import EmaScannerConfig, EmaScannerSignal
from app.domain.ema_state_manager.models import PositionSnapshot
from app.domain.llm_caller.models import LlmCallRequest
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.quant_scanner.models import QuantScannerConfig


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_int_list(value: str | None) -> List[int]:
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_positions(value: str | None) -> List[PositionSnapshot]:
    if not value:
        return []
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("positions must be a JSON array")

    positions: List[PositionSnapshot] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("positions must be a JSON array of objects")
        symbol = item.get("symbol") or item.get("ticker")
        direction = item.get("direction") or item.get("side")
        if not symbol or not direction:
            raise ValueError("each position requires symbol and direction")
        entry_price = item.get("entry_price")
        positions.append(
            PositionSnapshot(
                symbol=str(symbol),
                direction=str(direction),
                entry_price=float(entry_price) if entry_price is not None else None,
            )
        )
    return positions


def _merge_overrides(config: EmaScannerConfig, args: argparse.Namespace) -> EmaScannerConfig:
    assets = _split_csv(getattr(args, "assets", None)) or config.assets
    timeframes = _split_csv(getattr(args, "timeframes", None)) or config.timeframes
    ema_lengths = _parse_int_list(getattr(args, "ema_lengths", None)) or config.ema_lengths
    tolerance = getattr(args, "tolerance", None)
    quote_asset = getattr(args, "quote_asset", None) or config.quote_asset

    return EmaScannerConfig(
        assets=assets,
        timeframes=timeframes,
        ema_lengths=ema_lengths,
        tolerance_pct=tolerance if tolerance is not None else config.tolerance_pct,
        quote_asset=quote_asset,
        min_candles=config.min_candles,
        candles_multiplier=config.candles_multiplier,
        max_candles=config.max_candles,
    )


def _merge_quant_overrides(config: QuantScannerConfig, args: argparse.Namespace) -> QuantScannerConfig:
    assets = _split_csv(getattr(args, "assets", None)) or config.assets
    timeframes = _split_csv(getattr(args, "timeframes", None)) or config.timeframes
    quote_asset = getattr(args, "quote_asset", None) or config.quote_asset

    return QuantScannerConfig(
        assets=assets,
        timeframes=timeframes,
        quote_asset=quote_asset,
    )


def _signals_to_json(signals: Iterable[EmaScannerSignal]) -> str:
    payload = [asdict(signal) for signal in signals]
    return json.dumps(payload, default=str, indent=2)


def _mask_key(value: str | None) -> str:
    if not value:
        return "unset"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


async def _ema_config_cmd(args: argparse.Namespace) -> int:
    service = get_ema_config_service()
    config = await service.build_config()
    if getattr(args, "json", False):
        print(json.dumps(asdict(config), indent=2))
        return 0
    print(f"assets: {', '.join(config.assets)}")
    print(f"timeframes: {', '.join(config.timeframes)}")
    print(f"ema_lengths: {', '.join(str(x) for x in config.ema_lengths)}")
    print(f"tolerance_pct: {config.tolerance_pct}")
    print(f"quote_asset: {config.quote_asset}")
    print(f"min_candles: {config.min_candles}")
    print(f"candles_multiplier: {config.candles_multiplier}")
    print(f"max_candles: {config.max_candles}")
    return 0


async def _ema_scan_cmd(args: argparse.Namespace) -> int:
    config_service = get_ema_config_service()
    scanner_service = get_ema_scanner_service()

    config = await config_service.build_config()
    config = _merge_overrides(config, args)

    signals = await scanner_service.scan(config)
    if getattr(args, "json", False):
        print(_signals_to_json(signals))
        return 0

    if not signals:
        print("No EMA/BB signals found.")
        return 0

    for signal in signals:
        print(
            f"{signal.symbol} {signal.timeframe} {signal.indicator} {signal.parameter} "
            f"{signal.condition} price={signal.price:.6f} value={signal.value:.6f}"
        )
    return 0


async def _ema_state_cmd(args: argparse.Namespace) -> int:
    config_service = get_ema_config_service()
    scanner_service = get_ema_scanner_service()
    state_service = get_ema_state_manager_service()

    config = await config_service.build_config()
    config = _merge_overrides(config, args)

    signals = await scanner_service.scan(config)
    positions = _parse_positions(getattr(args, "positions", None))
    events = await state_service.process_signals(
        signals=signals,
        monitored_assets=config.assets,
        quote_asset=config.quote_asset,
        open_positions=positions,
    )

    if getattr(args, "json", False):
        payload = {
            "events": [event.to_dict() for event in events],
            "states": {symbol: state.to_dict() for symbol, state in state_service.get_all_states().items()},
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if not events:
        print("No EMA state events generated.")
    else:
        print(f"{len(events)} EMA state event(s):")
        for event in events:
            intervals = ",".join(event.active_intervals) if event.active_intervals else "-"
            bb_intervals = ",".join(event.bb_signal_intervals) if event.bb_signal_intervals else "-"
            print(
                f"{event.symbol} {event.trigger_reason.value} "
                f"resonance={event.resonance_count} intervals={intervals} "
                f"direction={event.direction_signal or '-'} bb_intervals={bb_intervals}"
            )

    states = state_service.get_all_states()
    if states:
        print("State snapshot:")
        for symbol, state in states.items():
            intervals = ",".join(sorted(state.active_intervals)) if state.active_intervals else "-"
            print(
                f"{symbol} phase={state.phase.value} resonance={state.resonance_count} "
                f"last_trigger={state.last_trigger.value} intervals={intervals}"
            )
    return 0


async def _quant_config_cmd(args: argparse.Namespace) -> int:
    service = get_quant_config_service()
    config = await service.build_config()
    if getattr(args, "json", False):
        print(json.dumps(asdict(config), indent=2))
        return 0
    print(f"assets: {', '.join(config.assets)}")
    print(f"timeframes: {', '.join(config.timeframes)}")
    print(f"quote_asset: {config.quote_asset}")
    return 0


async def _quant_scan_cmd(args: argparse.Namespace) -> int:
    config_service = get_quant_config_service()
    scanner_service = get_quant_scanner_service()

    config = await config_service.build_config()
    config = _merge_quant_overrides(config, args)
    limit = getattr(args, "limit", 200)

    snapshots = await scanner_service.scan(config, limit=limit)
    if getattr(args, "json", False):
        payload = [asdict(snapshot) for snapshot in snapshots]
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if not snapshots:
        print("No quant data fetched.")
        return 0

    for snapshot in snapshots:
        candle_count = len(snapshot.candles)
        oi_count = len(snapshot.open_interest)
        cvd_count = len(snapshot.cvd)
        price = f"{snapshot.price_current:.6f}" if snapshot.price_current is not None else "n/a"
        oi_current = f"{snapshot.oi_current:.6f}" if snapshot.oi_current is not None else "n/a"
        cvd_current = f"{snapshot.cvd_current:.6f}" if snapshot.cvd_current is not None else "n/a"
        print(
            f"{snapshot.symbol} {snapshot.timeframe} price={price} "
            f"oi={oi_current} cvd={cvd_current} "
            f"candles={candle_count} oi_points={oi_count} cvd_points={cvd_count}"
        )
    return 0


async def _image_uploader_show_cmd(args: argparse.Namespace) -> int:
    service = get_image_uploader_config_service()
    config = await service.get_config()

    from app.settings import get_settings

    settings = get_settings()
    if config:
        print("Image uploader config (DB):")
        print(f"provider: {config.provider}")
        print(f"api_key: {_mask_key(config.api_key)}")
    else:
        print("No image uploader config in DB. Using env defaults.")
        print(f"provider: {settings.prompt_image_uploader}")
        env_key = ""
        if settings.prompt_image_uploader.lower() == "imgbb":
            env_key = settings.prompt_image_imgbb_api_key
        elif settings.prompt_image_uploader.lower() in ("freeimage", "freeimage.host"):
            env_key = settings.prompt_image_freeimage_api_key
        print(f"api_key: {_mask_key(env_key)}")

    print(f"upload_concurrency: {settings.prompt_image_upload_concurrency}")
    return 0


async def _image_uploader_set_cmd(args: argparse.Namespace) -> int:
    provider = (args.provider or "").strip().lower()
    api_key = args.api_key

    if provider not in ("imgbb", "freeimage", "freeimage.host", "filesystem"):
        raise ValueError("provider must be one of: imgbb, freeimage, freeimage.host, filesystem")

    service = get_image_uploader_config_service()
    await service.set_config(provider, api_key)
    print(f"Saved image uploader config: provider={provider}")
    print(f"api_key: {_mask_key(api_key)}")
    return 0


async def _image_uploader_test_cmd(args: argparse.Namespace) -> int:
    from app.settings import get_settings
    from app.application.image_uploader.dependencies import get_image_uploader_config_service
    from app.application.image_uploader.service import ImageUploaderService

    settings = get_settings()
    service = ImageUploaderService(get_image_uploader_config_service(), settings)
    uploader = await service.get_uploader()

    # Minimal 1x1 PNG pixel
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D4948445200000001000000010806000000"
        "1F15C4890000000A49444154789C63000100000500010D0A2DB400000000"
        "49454E44AE426082"
    )

    url = await uploader.upload(png_bytes, "uploader_test")
    if hasattr(uploader, "close"):
        close = getattr(uploader, "close")
        if callable(close):
            await close()

    if not url:
        print("Upload failed (no URL returned).")
        return 1

    print(f"Upload OK: {url}")
    return 0


def _read_text_file(path: str | None) -> str | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _read_json_file(path: str | None) -> object | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_images_json(value: str | None) -> List[dict]:
    if not value:
        return []
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("images-json must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _parse_execution_idea(payload: dict) -> ExecutionIdea:
    action = payload.get("action")
    if not action:
        raise ValueError("decision requires action")
    action_enum = ExecutionAction(str(action).upper())
    symbol = payload.get("symbol")
    if not symbol:
        raise ValueError("decision requires symbol")

    return ExecutionIdea(
        action=action_enum,
        symbol=str(symbol).upper(),
        position_size_usd=_safe_float(payload.get("position_size_usd")),
        entry_price=_safe_float(payload.get("entry_price")),
        limit_price=_safe_float(payload.get("limit_price")),
        time_in_force=_safe_str(payload.get("time_in_force")),
        stop_loss=_safe_float(payload.get("stop_loss")),
        take_profit=_safe_float(payload.get("take_profit")),
        new_stop_loss=_safe_float(payload.get("new_stop_loss")),
        new_take_profit=_safe_float(payload.get("new_take_profit")),
        reduce_pct=_safe_float(payload.get("reduce_pct")),
        confidence=_safe_float(payload.get("confidence")),
        reasoning=_safe_str(payload.get("reasoning")) or "",
        execute=bool(payload.get("execute", True)),
        leverage=_safe_int(payload.get("leverage")),
        tier=_safe_int(payload.get("tier")),
        position_pct=_safe_float(payload.get("position_pct")),
        stop_loss_roe=_safe_float(payload.get("stop_loss_roe")),
        take_profit_roe=_safe_float(payload.get("take_profit_roe")),
    )


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _build_llm_request_from_args(args: argparse.Namespace) -> LlmCallRequest:
    from app.settings import get_settings

    prompt_text = args.prompt or _read_text_file(getattr(args, "prompt_file", None))
    payload = _read_json_file(getattr(args, "payload_file", None))
    prompt_data = None

    if isinstance(payload, dict):
        if "prompt_text" in payload and not prompt_text:
            prompt_text = payload.get("prompt_text")
        if isinstance(payload.get("data"), dict):
            prompt_data = payload.get("data")
        elif "chart_snapshots" in payload or "quant_data" in payload:
            prompt_data = payload

    if not prompt_text:
        raise ValueError("prompt text is required (use --prompt, --prompt-file, or payload prompt_text)")

    images = extract_chart_images(prompt_data or {})
    images.extend(_parse_images_json(getattr(args, "images_json", None)))

    settings = get_settings()
    model = getattr(args, "model", None) or settings.llm_model
    temperature = getattr(args, "temperature", None)
    if temperature is None:
        temperature = settings.llm_temperature
    max_tokens = getattr(args, "max_tokens", None)
    if max_tokens is None:
        max_tokens = settings.llm_max_tokens

    return LlmCallRequest(
        prompt_text=prompt_text,
        images=images,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def _llm_call_cmd(args: argparse.Namespace) -> int:
    request = _build_llm_request_from_args(args)
    service = get_llm_caller_service()
    response = await service.call(request)

    if getattr(args, "json", False):
        print(json.dumps(asdict(response), indent=2, default=str))
        return 0

    print(response.content)
    print(f"\nmodel={response.model} tokens_used={response.tokens_used} latency_ms={response.latency_ms:.1f}")
    return 0


async def _llm_parse_cmd(args: argparse.Namespace) -> int:
    response_text = args.response or _read_text_file(getattr(args, "response_file", None))
    if not response_text:
        raise ValueError("response text is required (use --response or --response-file)")

    service = get_llm_response_worker_service()
    result = service.parse(response_text)

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    if not result.success:
        print(f"Parse failed: {result.error}")
        return 1

    print(f"Parsed {len(result.ideas)} execution idea(s).")
    for idea in result.ideas:
        payload = idea.to_dict()
        print(json.dumps(payload, indent=2, default=str))
    return 0


async def _llm_execute_cmd(args: argparse.Namespace) -> int:
    request = _build_llm_request_from_args(args)
    service = get_llm_execution_service()
    result = await service.execute(request)

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    if not result.parse_result.success:
        print(result.call_response.content)
        print(f"\nParse failed: {result.parse_result.error}")
        return 1

    print(result.call_response.content)
    print(f"\nParsed {len(result.parse_result.ideas)} execution idea(s).")
    for idea in result.parse_result.ideas:
        print(json.dumps(idea.to_dict(), indent=2, default=str))
    return 0


async def _trade_guard_validate_cmd(args: argparse.Namespace) -> int:
    decision_payload = None
    if args.decision_json:
        decision_payload = json.loads(args.decision_json)
    elif args.decision_file:
        decision_payload = _read_json_file(args.decision_file)

    if not isinstance(decision_payload, dict):
        raise ValueError("decision must be a JSON object")

    account_state = None
    market_data = None
    open_positions = None

    if args.account_state_json:
        account_state = json.loads(args.account_state_json)
    elif args.account_state_file:
        account_state = _read_json_file(args.account_state_file)

    if args.market_data_json:
        market_data = json.loads(args.market_data_json)
    elif args.market_data_file:
        market_data = _read_json_file(args.market_data_file)

    if args.open_positions_json:
        open_positions = json.loads(args.open_positions_json)
    elif args.open_positions_file:
        open_positions = _read_json_file(args.open_positions_file)

    if account_state is not None and not isinstance(account_state, dict):
        raise ValueError("account_state must be a JSON object")
    if market_data is not None and not isinstance(market_data, dict):
        raise ValueError("market_data must be a JSON object")
    if open_positions is not None and not isinstance(open_positions, list):
        raise ValueError("open_positions must be a JSON array")

    decision = _parse_execution_idea(decision_payload)
    service = get_trade_guard_service()
    result = await service.validate(
        decision=decision,
        account_state=account_state,
        market_data=market_data,
        open_positions=open_positions,
    )

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    if not result.is_valid:
        print("Trade guard rejected decision:")
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 1

    print("Trade guard accepted decision.")
    if result.was_modified:
        print("Modifications:")
        print(json.dumps([item.to_dict() for item in result.modifications], indent=2, default=str))
    return 0


async def _circuit_breaker_eval_cmd(args: argparse.Namespace) -> int:
    decision_payload = None
    if args.decision_json:
        decision_payload = json.loads(args.decision_json)
    elif args.decision_file:
        decision_payload = _read_json_file(args.decision_file)

    if not isinstance(decision_payload, dict):
        raise ValueError("decision must be a JSON object")

    account_state = None
    market_data = None
    open_positions = None

    if args.account_state_json:
        account_state = json.loads(args.account_state_json)
    elif args.account_state_file:
        account_state = _read_json_file(args.account_state_file)

    if args.market_data_json:
        market_data = json.loads(args.market_data_json)
    elif args.market_data_file:
        market_data = _read_json_file(args.market_data_file)

    if args.open_positions_json:
        open_positions = json.loads(args.open_positions_json)
    elif args.open_positions_file:
        open_positions = _read_json_file(args.open_positions_file)

    if account_state is not None and not isinstance(account_state, dict):
        raise ValueError("account_state must be a JSON object")
    if market_data is not None and not isinstance(market_data, dict):
        raise ValueError("market_data must be a JSON object")
    if open_positions is not None and not isinstance(open_positions, list):
        raise ValueError("open_positions must be a JSON array")

    decision = _parse_execution_idea(decision_payload)
    service = get_circuit_breaker_service()
    result = service.evaluate(
        decision=decision,
        account_state=account_state,
        market_data=market_data,
        open_positions=open_positions,
    )

    if getattr(args, "json", False):
        print(json.dumps({"allowed": result.allowed, "reasons": result.reasons}, indent=2, default=str))
        return 0

    if result.allowed:
        print("Circuit breaker allowed execution.")
        return 0

    print("Circuit breaker blocked execution:")
    print(json.dumps(result.reasons, indent=2, default=str))
    return 1


async def _trade_executor_execute_cmd(args: argparse.Namespace) -> int:
    decision_payload = None
    if args.decision_json:
        decision_payload = json.loads(args.decision_json)
    elif args.decision_file:
        decision_payload = _read_json_file(args.decision_file)

    if not isinstance(decision_payload, dict):
        raise ValueError("decision must be a JSON object")

    if not args.confirm:
        print("Refusing to execute without --confirm.")
        return 1

    decision = _parse_execution_idea(decision_payload)
    service = get_trade_executor_service()
    result = await service.execute(decision)

    if getattr(args, "json", False):
        print(json.dumps(result.__dict__, indent=2, default=str))
        return 0

    if not result.success:
        print(f"Execution failed: {result.error}")
        return 1

    print(f"Execution ok: status={result.status} order_id={result.order_id}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend-cli")
    subparsers = parser.add_subparsers(dest="command")

    ema_parser = subparsers.add_parser("ema", help="EMA scanner commands")
    ema_sub = ema_parser.add_subparsers(dest="ema_command")

    ema_config = ema_sub.add_parser("config", help="Show EMA scanner config")
    ema_config.add_argument("--json", action="store_true", help="Output JSON")
    ema_config.set_defaults(func=_ema_config_cmd)

    ema_scan = ema_sub.add_parser("scan", help="Run EMA/BB scan")
    ema_scan.add_argument("--assets", help="Comma-separated list of assets to scan")
    ema_scan.add_argument("--timeframes", help="Comma-separated list of timeframes")
    ema_scan.add_argument("--ema-lengths", dest="ema_lengths", help="Comma-separated EMA lengths")
    ema_scan.add_argument("--tolerance", type=float, help="Tolerance percentage override")
    ema_scan.add_argument("--quote-asset", help="Quote asset override (default: USDT)")
    ema_scan.add_argument("--json", action="store_true", help="Output JSON")
    ema_scan.set_defaults(func=_ema_scan_cmd)

    ema_state = ema_sub.add_parser("state", help="Run EMA scan and state manager")
    ema_state.add_argument("--assets", help="Comma-separated list of assets to scan")
    ema_state.add_argument("--timeframes", help="Comma-separated list of timeframes")
    ema_state.add_argument("--ema-lengths", dest="ema_lengths", help="Comma-separated EMA lengths")
    ema_state.add_argument("--tolerance", type=float, help="Tolerance percentage override")
    ema_state.add_argument("--quote-asset", help="Quote asset override (default: USDT)")
    ema_state.add_argument(
        "--positions",
        help='JSON array of open positions (e.g. [{"symbol":"BTC/USDT","direction":"LONG","entry_price":100000}])',
    )
    ema_state.add_argument("--json", action="store_true", help="Output JSON")
    ema_state.set_defaults(func=_ema_state_cmd)

    uploader_parser = subparsers.add_parser("image-uploader", help="Image uploader config")
    uploader_sub = uploader_parser.add_subparsers(dest="uploader_command")

    uploader_show = uploader_sub.add_parser("show", help="Show image uploader config")
    uploader_show.set_defaults(func=_image_uploader_show_cmd)

    uploader_set = uploader_sub.add_parser("set", help="Set image uploader config")
    uploader_set.add_argument("--provider", required=True, help="imgbb, freeimage, freeimage.host, filesystem")
    uploader_set.add_argument("--api-key", dest="api_key", help="API key for remote uploader")
    uploader_set.set_defaults(func=_image_uploader_set_cmd)

    uploader_test = uploader_sub.add_parser("test", help="Upload a 1x1 PNG to verify uploader")
    uploader_test.set_defaults(func=_image_uploader_test_cmd)

    quant_parser = subparsers.add_parser("quant", help="Quant scanner commands")
    quant_sub = quant_parser.add_subparsers(dest="quant_command")

    quant_config = quant_sub.add_parser("config", help="Show quant scanner config")
    quant_config.add_argument("--json", action="store_true", help="Output JSON")
    quant_config.set_defaults(func=_quant_config_cmd)

    quant_scan = quant_sub.add_parser("scan", help="Run quant data fetch")
    quant_scan.add_argument("--assets", help="Comma-separated list of assets to scan")
    quant_scan.add_argument("--timeframes", help="Comma-separated list of timeframes")
    quant_scan.add_argument("--quote-asset", help="Quote asset override (default: USDT)")
    quant_scan.add_argument("--limit", type=int, default=200, help="Candles/OI points to fetch per interval")
    quant_scan.add_argument("--json", action="store_true", help="Output JSON")
    quant_scan.set_defaults(func=_quant_scan_cmd)

    llm_parser = subparsers.add_parser("llm", help="LLM caller commands")
    llm_sub = llm_parser.add_subparsers(dest="llm_command")

    llm_call = llm_sub.add_parser("call", help="Call LLM with a prompt and optional images")
    llm_call.add_argument("--prompt", help="Prompt text (inline)")
    llm_call.add_argument("--prompt-file", help="Read prompt text from a file")
    llm_call.add_argument("--payload-file", help="Prompt builder JSON payload file")
    llm_call.add_argument("--images-json", help="JSON array of image dicts to append")
    llm_call.add_argument("--model", help="Override model name")
    llm_call.add_argument("--temperature", type=float, help="Override temperature")
    llm_call.add_argument("--max-tokens", dest="max_tokens", type=int, help="Override max tokens")
    llm_call.add_argument("--json", action="store_true", help="Output JSON response")
    llm_call.set_defaults(func=_llm_call_cmd)

    llm_execute = llm_sub.add_parser("execute", help="Call LLM and parse response")
    llm_execute.add_argument("--prompt", help="Prompt text (inline)")
    llm_execute.add_argument("--prompt-file", help="Read prompt text from a file")
    llm_execute.add_argument("--payload-file", help="Prompt builder JSON payload file")
    llm_execute.add_argument("--images-json", help="JSON array of image dicts to append")
    llm_execute.add_argument("--model", help="Override model name")
    llm_execute.add_argument("--temperature", type=float, help="Override temperature")
    llm_execute.add_argument("--max-tokens", dest="max_tokens", type=int, help="Override max tokens")
    llm_execute.add_argument("--json", action="store_true", help="Output JSON response")
    llm_execute.set_defaults(func=_llm_execute_cmd)

    llm_parse = llm_sub.add_parser("parse", help="Parse LLM response into execution ideas")
    llm_parse.add_argument("--response", help="Raw response text")
    llm_parse.add_argument("--response-file", help="Read response text from a file")
    llm_parse.add_argument("--json", action="store_true", help="Output JSON response")
    llm_parse.set_defaults(func=_llm_parse_cmd)

    guard_parser = subparsers.add_parser("trade-guard", help="Trade guard commands")
    guard_sub = guard_parser.add_subparsers(dest="guard_command")

    guard_validate = guard_sub.add_parser("validate", help="Validate an execution idea")
    guard_validate.add_argument("--decision-json", help="Execution idea JSON payload")
    guard_validate.add_argument("--decision-file", help="Execution idea JSON file")
    guard_validate.add_argument("--account-state-json", help="Account state JSON payload")
    guard_validate.add_argument("--account-state-file", help="Account state JSON file")
    guard_validate.add_argument("--market-data-json", help="Market data JSON payload")
    guard_validate.add_argument("--market-data-file", help="Market data JSON file")
    guard_validate.add_argument("--open-positions-json", help="Open positions JSON payload")
    guard_validate.add_argument("--open-positions-file", help="Open positions JSON file")
    guard_validate.add_argument("--json", action="store_true", help="Output JSON response")
    guard_validate.set_defaults(func=_trade_guard_validate_cmd)

    breaker_parser = subparsers.add_parser("circuit-breaker", help="Circuit breaker commands")
    breaker_sub = breaker_parser.add_subparsers(dest="breaker_command")

    breaker_eval = breaker_sub.add_parser("evaluate", help="Evaluate an execution idea")
    breaker_eval.add_argument("--decision-json", help="Execution idea JSON payload")
    breaker_eval.add_argument("--decision-file", help="Execution idea JSON file")
    breaker_eval.add_argument("--account-state-json", help="Account state JSON payload")
    breaker_eval.add_argument("--account-state-file", help="Account state JSON file")
    breaker_eval.add_argument("--market-data-json", help="Market data JSON payload")
    breaker_eval.add_argument("--market-data-file", help="Market data JSON file")
    breaker_eval.add_argument("--open-positions-json", help="Open positions JSON payload")
    breaker_eval.add_argument("--open-positions-file", help="Open positions JSON file")
    breaker_eval.add_argument("--json", action="store_true", help="Output JSON response")
    breaker_eval.set_defaults(func=_circuit_breaker_eval_cmd)

    executor_parser = subparsers.add_parser("trade-executor", help="Trade executor commands")
    executor_sub = executor_parser.add_subparsers(dest="executor_command")

    executor_execute = executor_sub.add_parser("execute", help="Execute an execution idea via CCXT")
    executor_execute.add_argument("--decision-json", help="Execution idea JSON payload")
    executor_execute.add_argument("--decision-file", help="Execution idea JSON file")
    executor_execute.add_argument("--confirm", action="store_true", help="Confirm trade execution")
    executor_execute.add_argument("--json", action="store_true", help="Output JSON response")
    executor_execute.set_defaults(func=_trade_executor_execute_cmd)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return asyncio.run(args.func(args))
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
