from __future__ import annotations

"""Telegram Bot API client for trade alerts and automation session notifications."""

import logging
from typing import Optional

import httpx


logger = logging.getLogger(__name__)


class TelegramClient:
    API_BASE = "https://api.telegram.org/bot"

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    async def send_message(
        self,
        bot_token: str,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
    ) -> bool:
        self._last_error = None
        if not bot_token:
            self._last_error = "Missing bot token"
            return False
        if not chat_id:
            self._last_error = "Missing chat id"
            return False

        url = f"{self.API_BASE}{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
            if response.status_code >= 400:
                self._last_error = _extract_error(response)
                logger.warning("Telegram API error %s: %s", response.status_code, self._last_error)
                return False
            data = response.json()
            if isinstance(data, dict) and not data.get("ok", True):
                self._last_error = str(data.get("description") or "Telegram API error")
                logger.warning("Telegram API error: %s", self._last_error)
                return False
            return True
        except httpx.TimeoutException:
            self._last_error = "Timeout"
            logger.warning("Telegram API timeout")
            return False
        except Exception as exc:
            self._last_error = "Request failed"
            logger.warning("Telegram API request failed: %s", exc)
            return False


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text[:200] if response.text else f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        return str(payload.get("description") or payload.get("error") or payload)
    return str(payload)
