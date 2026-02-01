from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ImageUploaderConfig:
    provider: str
    api_key: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
