from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }
