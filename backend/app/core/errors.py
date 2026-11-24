"""Common error envelope: {"error": {"code": "...", "message": "..."}} (spec section 4 and 6)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Raise from services: raise AppError(409, "RESERVATION_CONFLICT", "...")."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


_DEFAULT_CODES = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    429: "RATE_LIMITED",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"{field}: {first.get('msg', 'Invalid request')}" if field else "Invalid request"
        return _envelope(422, "VALIDATION_ERROR", message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _DEFAULT_CODES.get(exc.status_code, "HTTP_ERROR")
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Never leak internals to the client; the details go to the server log.
        logging.getLogger("campuscore").error("Unhandled error on %s %s", request.method, request.url.path,
                                              exc_info=exc)
        return _envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.")
