from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.api import ApiErrorDetail, ApiErrorResponse, ApiMeta
from app.common.errors import AppError
from app.common.ids import new_request_id


def register_request_id(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            request,
            code=exc.code,
            message=exc.message,
            details=exc.details or {},
            status_code=400,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _error_response(
            request,
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            details={},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            code="validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            request,
            code="internal_error",
            message="Internal server error",
            details={},
            status_code=500,
        )


def _error_response(
    request: Request,
    code: str,
    message: str,
    details: Dict[str, Any],
    status_code: int,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    payload = ApiErrorResponse(
        error=ApiErrorDetail(code=code, message=message, details=details),
        meta=ApiMeta(request_id=request_id),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())
