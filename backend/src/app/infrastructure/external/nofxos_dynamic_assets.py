from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx


class NofXOSDynamicAssetsClient:
    DEFAULT_BASE_URL = "https://nofxos.ai/api"

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._base_url = base_url or os.environ.get("NOFXOS_API_URL") or self.DEFAULT_BASE_URL
        self._timeout = timeout_seconds

    async def fetch_multi_source_assets(
        self,
        sources: Dict[str, Any],
        api_key: Optional[str],
    ) -> List[str]:
        tasks: List[asyncio.Future] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if sources.get("ai500", {}).get("enabled"):
                tasks.append(
                    self._fetch_ai500(
                        client,
                        api_key,
                        limit=int(sources["ai500"].get("limit", 10)),
                    )
                )
            if sources.get("ai300", {}).get("enabled"):
                tasks.append(
                    self._fetch_ai300(
                        client,
                        api_key,
                        limit=int(sources["ai300"].get("limit", 20)),
                        level=sources["ai300"].get("level"),
                    )
                )
            if sources.get("oi_top", {}).get("enabled"):
                tasks.append(
                    self._fetch_oi_ranking(
                        client,
                        api_key,
                        ranking_type="top",
                        limit=int(sources["oi_top"].get("limit", 20)),
                        duration=sources["oi_top"].get("duration", "1h"),
                    )
                )
            if sources.get("oi_low", {}).get("enabled"):
                tasks.append(
                    self._fetch_oi_ranking(
                        client,
                        api_key,
                        ranking_type="low",
                        limit=int(sources["oi_low"].get("limit", 20)),
                        duration=sources["oi_low"].get("duration", "1h"),
                    )
                )
            if sources.get("netflow_top", {}).get("enabled"):
                tasks.append(
                    self._fetch_netflow_ranking(
                        client,
                        api_key,
                        ranking_type="top",
                        limit=int(sources["netflow_top"].get("limit", 20)),
                        duration=sources["netflow_top"].get("duration", "1h"),
                    )
                )
            if sources.get("netflow_low", {}).get("enabled"):
                tasks.append(
                    self._fetch_netflow_ranking(
                        client,
                        api_key,
                        ranking_type="low",
                        limit=int(sources["netflow_low"].get("limit", 20)),
                        duration=sources["netflow_low"].get("duration", "1h"),
                    )
                )

            if not tasks:
                return []

            results = await asyncio.gather(*tasks, return_exceptions=True)

        assets: List[str] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            assets.extend(result)

        return _dedup_preserve_order(assets)

    async def _fetch_ai500(
        self,
        client: httpx.AsyncClient,
        api_key: Optional[str],
        limit: int,
    ) -> List[str]:
        url = f"{self._base_url}/ai500/list"
        params = self._auth_params(api_key)
        data = await self._get_json(client, url, params)
        assets = self._parse_assets(data)
        return assets[:limit] if limit else assets

    async def _fetch_ai300(
        self,
        client: httpx.AsyncClient,
        api_key: Optional[str],
        limit: int,
        level: Optional[str],
    ) -> List[str]:
        url = f"{self._base_url}/ai300/list"
        params = self._auth_params(api_key)
        if level:
            params["level"] = str(level).strip().upper()
        data = await self._get_json(client, url, params)
        assets = self._parse_assets(data)
        return assets[:limit] if limit else assets

    async def _fetch_oi_ranking(
        self,
        client: httpx.AsyncClient,
        api_key: Optional[str],
        ranking_type: str,
        limit: int,
        duration: str,
    ) -> List[str]:
        endpoint = "top-ranking" if ranking_type == "top" else "low-ranking"
        url = f"{self._base_url}/oi/{endpoint}"
        params = self._auth_params(api_key)
        params.update({"limit": limit, "duration": duration})
        data = await self._get_json(client, url, params)
        return self._parse_ranking_assets(data)

    async def _fetch_netflow_ranking(
        self,
        client: httpx.AsyncClient,
        api_key: Optional[str],
        ranking_type: str,
        limit: int,
        duration: str,
    ) -> List[str]:
        endpoint = "top-ranking" if ranking_type == "top" else "low-ranking"
        url = f"{self._base_url}/netflow/{endpoint}"
        params = self._auth_params(api_key)
        params.update(
            {
                "limit": limit,
                "duration": duration,
                "type": "institution",
                "trade": "future",
            }
        )
        data = await self._get_json(client, url, params)
        return self._parse_ranking_assets(data)

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return {}
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {}
        except Exception:
            return {}

    def _parse_assets(self, data: Dict[str, Any]) -> List[str]:
        payload = data
        if isinstance(payload, dict) and "success" in payload:
            if not payload.get("success", False):
                return []
            payload = payload.get("data", payload)

        assets: List[str] = []
        if isinstance(payload, dict) and "coins" in payload:
            coins = payload.get("coins", [])
            for item in coins:
                if not isinstance(item, dict):
                    continue
                for key in ("pair", "symbol", "coin"):
                    if key in item:
                        assets.append(str(item[key]))
                        break
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    assets.append(item)
                elif isinstance(item, dict):
                    for key in ("pair", "symbol", "coin"):
                        if key in item:
                            assets.append(str(item[key]))
                            break

        cleaned = [self._clean_symbol(a) for a in assets if a]
        return _dedup_preserve_order(cleaned)

    def _parse_ranking_assets(self, data: Dict[str, Any]) -> List[str]:
        if not isinstance(data, dict):
            return []
        payload = data.get("data", data)

        if isinstance(payload, list):
            return self._extract_ranked_assets(payload)
        if not isinstance(payload, dict):
            return []

        for key in ("positions", "netflows", "rankings", "items", "rows", "coins", "list"):
            items = payload.get(key)
            if isinstance(items, list):
                return self._extract_ranked_assets(items)
        return []

    def _extract_ranked_assets(self, items: List[Any]) -> List[str]:
        ranked: List[tuple[float, int, str]] = []
        for idx, item in enumerate(items):
            if isinstance(item, str):
                cleaned = self._clean_symbol(item)
                if cleaned:
                    ranked.append((float(idx), idx, cleaned))
                continue
            if not isinstance(item, dict):
                continue

            symbol = ""
            for key in ("symbol", "pair", "coin", "asset", "baseAsset"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    symbol = value
                    break
            cleaned = self._clean_symbol(symbol)
            if not cleaned:
                continue

            rank = item.get("rank")
            rank_value = float(rank) if isinstance(rank, (int, float)) else float(idx)
            ranked.append((rank_value, idx, cleaned))

        ranked.sort(key=lambda item: (item[0], item[1]))
        return _dedup_preserve_order([symbol for _, _, symbol in ranked])

    def _clean_symbol(self, symbol: str) -> str:
        value = symbol.upper().strip()
        for suffix in ("-PERP", "PERP", "USDT", "-USD", "USD", "-USDC", "USDC"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    def _auth_params(self, api_key: Optional[str]) -> Dict[str, Any]:
        if api_key and api_key.strip():
            return {"auth": api_key.strip()}
        return {}


def _dedup_preserve_order(items: List[str]) -> List[str]:
    """Remove duplicates while preserving insertion order."""
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
