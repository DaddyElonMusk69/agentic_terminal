from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TelegramRecipient:
    chat_id: str
    name: str = ""
    enabled: bool = True
    language: str = "en"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelegramRecipient":
        return cls(
            chat_id=str(data.get("chat_id", "")).strip(),
            name=str(data.get("name", "") or "").strip(),
            enabled=bool(data.get("enabled", True)),
            language=str(data.get("language", "en") or "en").strip() or "en",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "enabled": self.enabled,
            "language": self.language,
        }


@dataclass(frozen=True)
class TelegramNotifications:
    signal_open: bool = True
    signal_change: bool = True
    signal_close: bool = False
    llm_considerations: bool = False
    ema_automation: bool = True

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TelegramNotifications":
        payload = data or {}
        return cls(
            signal_open=payload.get("signal_open", True),
            signal_change=payload.get("signal_change", True),
            signal_close=bool(payload.get("signal_close", False)),
            llm_considerations=bool(payload.get("llm_considerations", False)),
            ema_automation=payload.get("ema_automation", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_open": self.signal_open,
            "signal_change": self.signal_change,
            "signal_close": self.signal_close,
            "llm_considerations": self.llm_considerations,
            "ema_automation": self.ema_automation,
        }


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    bot_token: Optional[str]
    chat_id: str
    recipients: List[TelegramRecipient] = field(default_factory=list)
    notifications: TelegramNotifications = field(default_factory=TelegramNotifications)
    parse_mode: str = "Markdown"
    disable_notification: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_enabled_chat_ids(self) -> List[str]:
        chat_ids = [recipient.chat_id for recipient in self.recipients if recipient.enabled]
        if not chat_ids and self.chat_id:
            chat_ids.append(self.chat_id)
        return chat_ids
