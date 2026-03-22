from typing import Any


_KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "USD",
    "BUSD",
)


def normalize_position_origin_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""

    symbol = value.strip().upper()
    if not symbol:
        return ""

    if ":" in symbol:
        symbol = symbol.split(":", 1)[0]

    if "/" in symbol:
        return symbol.split("/", 1)[0]

    for quote in _KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]

    return symbol
