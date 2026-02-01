from __future__ import annotations

from typing import Any, Dict

from app.domain.quant_scanner.models import QuantSnapshot


def snapshot_to_signal(snapshot: QuantSnapshot) -> Dict[str, Any]:
    cvd_delta = snapshot.cvd_deltas[-1] if snapshot.cvd_deltas else None
    depth = snapshot.order_book
    net_depth_usd = depth.net_depth_usd if depth else None
    depth_context = None
    if depth:
        depth_context = {
            "bid_volume_usd": depth.bid_volume_usd,
            "ask_volume_usd": depth.ask_volume_usd,
            "net_depth_usd": depth.net_depth_usd,
            "imbalance_pct": depth.imbalance_pct,
            "obi_ratio": depth.obi_ratio,
            "mid_price": depth.mid_price,
            "range_pct": depth.range_pct,
            "best_bid": depth.best_bid,
            "best_ask": depth.best_ask,
        }
    depth_regime = None
    if net_depth_usd is not None:
        if net_depth_usd > 0:
            depth_regime = "bid"
        elif net_depth_usd < 0:
            depth_regime = "ask"
        else:
            depth_regime = "neutral"

    vwap_context = None
    if snapshot.vwap:
        vwap_context = {
            "vwap": snapshot.vwap.value,
            "std_dev": snapshot.vwap.std_dev,
            "distance_sd": snapshot.vwap.distance,
            "candle_count": snapshot.vwap.candle_count,
        }

    funding_context = None
    if snapshot.funding_rate:
        funding_context = {
            "current_rate": snapshot.funding_rate.rate,
            "current_rate_pct": f"{snapshot.funding_rate.rate * 100:.4f}%",
            "timestamp_ms": snapshot.funding_rate.timestamp_ms,
            "next_funding_time_ms": snapshot.funding_rate.next_funding_time_ms,
            "mark_price": snapshot.funding_rate.mark_price,
        }

    atr_context = None
    if snapshot.atr:
        atr_context = {
            "current_atr": snapshot.atr.value,
            "atr_slope": snapshot.atr.slope_pct,
            "atr_z_score": snapshot.atr.z_score,
            "period": snapshot.atr.period,
            "lookback": snapshot.atr.lookback,
            "market_regime": "tracking",
        }

    fund_inflow_context = None
    if snapshot.netflow:
        fund_inflow_context = {
            "flow_regime": snapshot.netflow.flow_regime,
            "dominant_flow": snapshot.netflow.dominant_flow,
            "total_netflow": snapshot.netflow.total_netflow,
            "institution_netflow": snapshot.netflow.institution_netflow,
            "retail_netflow": snapshot.netflow.retail_netflow,
            "timeframe": snapshot.netflow.timeframe,
        }

    anomaly_context = None
    if snapshot.anomalies:
        anomaly_context = {
            "price": _anomaly_factor(snapshot.anomalies.price),
            "oi": _anomaly_factor(snapshot.anomalies.open_interest),
            "cvd": _anomaly_factor(snapshot.anomalies.cvd),
        }

    timestamp = snapshot.timestamp.isoformat()
    snapshot_meta = {
        "candles": len(snapshot.candles),
        "price_points": len(snapshot.prices),
        "oi_points": len(snapshot.open_interest),
        "cvd_points": len(snapshot.cvd),
        "cvd_deltas": len(snapshot.cvd_deltas),
    }

    return {
        "symbol": snapshot.symbol,
        "interval": snapshot.timeframe,
        "signal_type": "quant_snapshot",
        "signal_metadata": {
            "signal_name": "Quant Snapshot",
            "direction": "NEUTRAL",
            "category": "raw",
            "interpretation": "Raw quant data snapshot",
            "verdict": "tracking",
        },
        "confirmation_count": 1,
        "entry_price": snapshot.price_current,
        "current_price": snapshot.price_current,
        "entry_oi": snapshot.oi_current,
        "current_oi": snapshot.oi_current,
        "cvd_current": snapshot.cvd_current,
        "cvd_delta": cvd_delta,
        "net_depth_usd": net_depth_usd,
        "depth_context": depth_context,
        "depth_regime": depth_regime,
        "price_slope": snapshot.price_slope,
        "price_slope_z": snapshot.price_slope_z,
        "oi_slope": snapshot.oi_slope,
        "oi_slope_z": snapshot.oi_slope_z,
        "cvd_slope": snapshot.cvd_slope,
        "cvd_slope_z": snapshot.cvd_slope_z,
        "opened_at": timestamp,
        "last_updated": timestamp,
        "signal_reason": "Quant snapshot",
        "snapshot_meta": snapshot_meta,
        "vwap_context": vwap_context,
        "funding_context": funding_context,
        "atr_context": atr_context,
        "fund_inflow_context": fund_inflow_context,
        "anomaly_context": anomaly_context,
        "config_snapshot": {
            "interval": snapshot.timeframe,
            "timeframe": snapshot.timeframe,
        },
    }


def _anomaly_factor(result) -> Dict[str, Any]:
    if result is None:
        return {}
    return {
        "anomaly_type": result.anomaly_type,
        "z_score": result.z_score,
        "magnitude_pct": result.magnitude_pct,
        "baseline_mean": result.baseline_mean,
        "baseline_std": result.baseline_std,
        "threshold": result.threshold,
        "current_value": result.current_value,
        "is_significant": result.is_significant,
        "insufficient_data": result.insufficient_data,
    }
