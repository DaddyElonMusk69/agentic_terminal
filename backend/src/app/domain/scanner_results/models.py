from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class ScannerResultRecord:
    id: int
    date: date
    ticker: str
    score: Optional[int]
    data: Optional[dict]
    created_at: Optional[datetime] = None
