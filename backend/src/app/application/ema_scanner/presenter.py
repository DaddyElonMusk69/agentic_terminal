from typing import Dict, List, Optional, Sequence

from app.domain.ema_scanner.models import EmaScannerSignal


def build_scan_results(
    signals: Sequence[EmaScannerSignal],
    timeframes: Sequence[str],
    chart_by_symbol: Optional[Dict[str, Dict[str, object]]] = None,
) -> List[dict]:
    grouped: Dict[str, Dict[str, object]] = {}
    for signal in signals:
        key = signal.symbol
        entry = grouped.setdefault(
            key,
            {"ema_votes": [], "bb_votes": [], "intervals": set()},
        )
        vote = {"interval": signal.timeframe, "param": signal.parameter}
        if signal.indicator == "EMA":
            entry["ema_votes"].append(vote)
            entry["intervals"].add(signal.timeframe)
        else:
            entry["bb_votes"].append(vote)

    order_index = {frame: idx for idx, frame in enumerate(timeframes)}
    results: List[dict] = []
    for symbol, entry in grouped.items():
        ema_votes = entry["ema_votes"]
        bb_votes = entry["bb_votes"]
        intervals = sorted(
            entry["intervals"],
            key=lambda frame: order_index.get(frame, 999),
        )
        results.append(
            {
                "ticker": symbol,
                "votes": len(ema_votes) + len(bb_votes),
                "intervals": intervals,
                "ema_votes": ema_votes,
                "bb_votes": bb_votes,
                "chart_data": chart_by_symbol.get(symbol) if chart_by_symbol else None,
            }
        )

    results.sort(key=lambda item: item["votes"], reverse=True)
    return results
