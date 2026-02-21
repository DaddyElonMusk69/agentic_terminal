#!/usr/bin/env python3
"""
Test OI Rank Service
Usage: python test_oi_rank_service.py

Env:
  BACKEND_BASE_URL=http://127.0.0.1:8000
  OI_INTERVALS=1h,4h,12h
  OI_LIMIT=5
  OI_METRIC=abs
  OI_POLL_SECONDS=15
  OI_TIMEOUT_SECONDS=600
  OI_SKIP_CONFIG=false
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import httpx

ENV_BASE = os.environ.get("BACKEND_BASE_URL", "").strip()
BASE_CANDIDATES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8000",
]
INTERVALS = [item.strip() for item in os.environ.get("OI_INTERVALS", "1h,4h,12h").split(",") if item.strip()]
LIMIT = int(os.environ.get("OI_LIMIT", "5"))
METRIC = os.environ.get("OI_METRIC", "abs")
POLL_SECONDS = int(os.environ.get("OI_POLL_SECONDS", "15"))
TIMEOUT_SECONDS = int(os.environ.get("OI_TIMEOUT_SECONDS", "600"))
SKIP_CONFIG = os.environ.get("OI_SKIP_CONFIG", "false").lower() == "true"

DEFAULT_REFRESH_MINUTES = 30
DEFAULT_STALE_MINUTES = 90


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(dt: datetime | None) -> float | None:
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _print_error_response(prefix: str, resp: httpx.Response) -> None:
    body = resp.text
    body_preview = body[:1000] + ("..." if len(body) > 1000 else "")
    print(f"{prefix}: {resp.status_code}\n{body_preview}")


async def fetch_config(client: httpx.AsyncClient, api_base: str) -> Dict[str, Any] | None:
    url = f"{api_base}/api/v1/oi-rank/config"
    resp = await client.get(url)
    if resp.status_code != 200:
        _print_error_response("[ERROR] Config fetch failed", resp)
        return None
    payload = resp.json()
    return payload.get("data")


async def fetch_rank(
    client: httpx.AsyncClient,
    direction: str,
    interval: str,
    limit: int,
    metric: str,
    api_base: str,
) -> Dict[str, Any] | None:
    url = f"{api_base}/api/v1/oi-rank/{direction}"
    resp = await client.get(url, params={"interval": interval, "limit": limit, "metric": metric})
    if resp.status_code != 200:
        _print_error_response(f"[ERROR] {direction} fetch failed ({interval})", resp)
        return None
    payload = resp.json()
    return payload.get("data")


def summarize_rank(data: Dict[str, Any]) -> Dict[str, Any]:
    status = data.get("status")
    updated_at = _parse_dt(data.get("updated_at"))
    refresh_started_at = _parse_dt(data.get("refresh_started_at"))
    error = data.get("error")
    positions = data.get("data", {}).get("positions") if data.get("data") else None
    count = len(positions) if isinstance(positions, list) else 0
    symbols = []
    if isinstance(positions, list):
        for pos in positions:
            if isinstance(pos, dict) and isinstance(pos.get("symbol"), str):
                symbols.append(pos["symbol"])
    return {
        "status": status,
        "updated_at": updated_at,
        "refresh_started_at": refresh_started_at,
        "error": error,
        "count": count,
        "symbols": symbols,
    }


def print_snapshot(label: str, summary: Dict[str, Any]) -> None:
    updated_age = _age_seconds(summary["updated_at"])
    refresh_age = _age_seconds(summary["refresh_started_at"])
    updated_text = f"{int(updated_age)}s ago" if updated_age is not None else "n/a"
    refresh_text = f"{int(refresh_age)}s ago" if refresh_age is not None else "n/a"
    print(
        f"{label} | status={summary['status']} count={summary['count']} "
        f"updated={updated_text} refresh_started={refresh_text}"
    )
    if summary["error"]:
        print(f"  last_error: {summary['error']}")
    if summary["symbols"]:
        print(f"  symbols: {', '.join(summary['symbols'])}")


async def main() -> int:
    async with httpx.AsyncClient(timeout=15.0) as client:
        api_base = ENV_BASE.rstrip("/") if ENV_BASE else ""
        if not api_base:
            for candidate in BASE_CANDIDATES:
                try:
                    resp = await client.get(f"{candidate}/api/v1/health")
                    if resp.status_code == 200:
                        api_base = candidate
                        break
                except httpx.HTTPError:
                    continue
        if not api_base:
            api_base = BASE_CANDIDATES[0]

        print("=" * 60)
        print("OI RANK SERVICE STATUS")
        print("=" * 60)
        print(f"API base: {api_base}")
        print(f"Intervals: {', '.join(INTERVALS)} | Metric: {METRIC} | Limit: {LIMIT}")

        refresh_minutes = DEFAULT_REFRESH_MINUTES
        stale_minutes = DEFAULT_STALE_MINUTES
        config = None
        if not SKIP_CONFIG:
            config = await fetch_config(client, api_base)
        if config:
            refresh_minutes = int(config.get("refresh_interval_minutes", refresh_minutes))
            stale_minutes = int(config.get("stale_ttl_minutes", stale_minutes))
            print(f"Config: refresh={refresh_minutes} min, stale_ttl={stale_minutes} min")
        else:
            print(
                "[WARN] Using defaults (refresh 30m, stale 90m). "
                "Set OI_SKIP_CONFIG=true to silence this."
            )

        start = time.time()
        while True:
            snapshots: List[Tuple[str, Dict[str, Any]]] = []
            for interval in INTERVALS:
                top = await fetch_rank(client, "top", interval, LIMIT, METRIC, api_base)
                low = await fetch_rank(client, "low", interval, LIMIT, METRIC, api_base)
                if top is None or low is None:
                    return 1
                top_summary = summarize_rank(top)
                low_summary = summarize_rank(low)
                snapshots.append((f"{interval} top", top_summary))
                snapshots.append((f"{interval} low", low_summary))

            print("\n--- Snapshot ---")
            for label, summary in snapshots:
                print_snapshot(label, summary)

            statuses = {summary["status"] for _, summary in snapshots}
            if statuses.issubset({"ready"}):
                print("\nAll intervals ready.")
                return 0

            elapsed = time.time() - start
            if elapsed >= TIMEOUT_SECONDS:
                print("\n[ERROR] Timed out waiting for refresh to complete.")
                return 1

            max_refresh_age = 0
            for _, summary in snapshots:
                refresh_age = _age_seconds(summary["refresh_started_at"]) or 0
                max_refresh_age = max(max_refresh_age, refresh_age)

            warn_threshold = max(refresh_minutes * 2 * 60, 600)
            if max_refresh_age > warn_threshold and "warming" in statuses:
                print(
                    f"\n[WARNING] Refresh has been warming for {int(max_refresh_age)}s "
                    f"(threshold {int(warn_threshold)}s)."
                )

            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
