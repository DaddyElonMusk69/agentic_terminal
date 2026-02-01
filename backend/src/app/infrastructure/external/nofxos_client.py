from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections import deque
from http.client import RemoteDisconnected, IncompleteRead
from typing import Any, Dict, Optional

import certifi
import httpx

logger = logging.getLogger(__name__)


class NofXOSClient:
    DEFAULT_BASE_URL = "https://nofxos.ai/api"
    DEFAULT_TIMEOUT = 10
    DEFAULT_MAX_RPS = 2
    DEFAULT_RETRY_COUNT = 2
    DEFAULT_RETRY_BASE_DELAY = 0.5
    DEFAULT_RETRY_MAX_DELAY = 4.0
    DEFAULT_RETRY_JITTER = 0.3
    DEFAULT_RATE_LIMIT_BACKOFF = 15.0
    _rate_lock = threading.Lock()
    _rate_timestamps = deque()
    _rate_configured = False
    _max_rps = DEFAULT_MAX_RPS
    _retry_count = DEFAULT_RETRY_COUNT
    _retry_base_delay = DEFAULT_RETRY_BASE_DELAY
    _retry_max_delay = DEFAULT_RETRY_MAX_DELAY
    _retry_jitter = DEFAULT_RETRY_JITTER
    _rate_limit_backoff = DEFAULT_RATE_LIMIT_BACKOFF

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("NOFXOS_API_KEY")
        self._base_url = base_url or os.environ.get("NOFXOS_API_URL") or self.DEFAULT_BASE_URL
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        verify = False if _allow_insecure_ssl() else certifi.where()
        self._client = httpx.Client(
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            verify=verify,
        )
        self._ensure_rate_config()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, api_key: Optional[str]) -> None:
        self._api_key = api_key

    def get_coin_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            logger.debug("NofXOS client not configured, skipping fetch")
            return None

        normalized = self._normalize_symbol(symbol)
        url = f"{self._base_url}/coin/{normalized}"
        params = {"include": "netflow", "auth": self._api_key}

        max_attempts = max(1, self._retry_count + 1)
        for attempt in range(1, max_attempts + 1):
            try:
                self._throttle()
                response = self._client.get(url, params=params)
                payload = response.text
                if response.status_code != 200:
                    logger.warning(
                        "NofXOS API HTTP error %s for %s payload=%s",
                        response.status_code,
                        response.url,
                        payload[:200],
                    )
                    if attempt < max_attempts and _is_retryable_http(response.status_code):
                        time.sleep(
                            self._retry_delay(
                                attempt,
                                is_rate_limit=response.status_code in {418, 429},
                            )
                        )
                        continue
                    return None
                return json.loads(payload)
            except (httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError, httpx.RequestError) as exc:
                logger.warning("NofXOS API network error for %s error=%s", url, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except (RemoteDisconnected, IncompleteRead, TimeoutError) as exc:
                logger.warning("NofXOS API network error for %s error=%s", url, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except httpx.HTTPError as exc:
                logger.warning("NofXOS API HTTP error for %s error=%s", url, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("NofXOS API invalid JSON for %s error=%s", url, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
            except Exception as exc:
                logger.warning("NofXOS API unexpected error for %s error=%s", url, exc)
                if attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt))
                    continue
                return None
        return None

    def _normalize_symbol(self, symbol: str) -> str:
        clean = (
            symbol.upper()
            .replace("-PERP", "")
            .replace("PERP", "")
            .replace("USDT", "")
            .replace("-", "")
            .replace("/", "")
            .replace(":", "")
        )
        if not clean.endswith("USDT"):
            clean = f"{clean}USDT"
        return clean

    @classmethod
    def _ensure_rate_config(cls) -> None:
        if cls._rate_configured:
            return
        cls._max_rps = max(1, int(os.environ.get("NOFXOS_MAX_RPS", cls.DEFAULT_MAX_RPS)))
        cls._retry_count = max(0, int(os.environ.get("NOFXOS_RETRY_COUNT", cls.DEFAULT_RETRY_COUNT)))
        cls._retry_base_delay = float(os.environ.get("NOFXOS_RETRY_BASE_DELAY", cls.DEFAULT_RETRY_BASE_DELAY))
        cls._retry_max_delay = float(os.environ.get("NOFXOS_RETRY_MAX_DELAY", cls.DEFAULT_RETRY_MAX_DELAY))
        cls._retry_jitter = float(os.environ.get("NOFXOS_RETRY_JITTER", cls.DEFAULT_RETRY_JITTER))
        cls._rate_limit_backoff = float(
            os.environ.get("NOFXOS_RATE_LIMIT_BACKOFF", cls.DEFAULT_RATE_LIMIT_BACKOFF)
        )
        cls._rate_configured = True

    @classmethod
    def _throttle(cls) -> None:
        if cls._max_rps <= 0:
            return
        while True:
            now = time.monotonic()
            with cls._rate_lock:
                while cls._rate_timestamps and now - cls._rate_timestamps[0] >= 1.0:
                    cls._rate_timestamps.popleft()
                if len(cls._rate_timestamps) < cls._max_rps:
                    cls._rate_timestamps.append(now)
                    return
                wait = 1.0 - (now - cls._rate_timestamps[0])
            if wait > 0:
                time.sleep(wait + random.uniform(0, cls._retry_jitter))

    @classmethod
    def _retry_delay(cls, attempt: int, is_rate_limit: bool = False) -> float:
        delay = cls._retry_base_delay * (2 ** (attempt - 1))
        delay = min(delay, cls._retry_max_delay)
        if is_rate_limit:
            delay = max(delay, cls._rate_limit_backoff)
        return delay + random.uniform(0, cls._retry_jitter)


def _is_retryable_http(status_code: int) -> bool:
    if status_code in {418, 429}:
        return True
    return 500 <= status_code <= 599


def _allow_insecure_ssl() -> bool:
    return bool(_get_env_flag("ALLOW_INSECURE_SSL"))


def _get_env_flag(name: str) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
