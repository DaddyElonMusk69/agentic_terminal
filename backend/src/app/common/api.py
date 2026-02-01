from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ApiMeta(BaseModel):
    request_id: Optional[str] = None
    pagination: Optional[Dict[str, Any]] = None


class ApiResponse(BaseModel):
    data: Any
    meta: Optional[ApiMeta] = None


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail
    meta: Optional[ApiMeta] = None
