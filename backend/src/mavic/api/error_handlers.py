"""Traducción de errores a respuestas HTTP, en un único lugar.

Todas las respuestas de error tienen la misma forma:

    {
      "detail": "Mensaje legible para una persona",
      "code": "CODIGO_ESTABLE",
      "request_id": "id para buscar el error en los logs",
      "errors": [...]   # solo en errores de validación (422)
    }

Se mantiene la clave `detail` porque es la que FastAPI usa por defecto: así
cualquier cliente que ya lea `detail` sigue funcionando.

Regla de seguridad: un error inesperado (500) NUNCA devuelve la traza ni el
mensaje interno. Se loguea completo y al cliente le llega un texto genérico más
el `request_id` para encontrarlo en los logs.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mavic.core.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleViolationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
)
from mavic.core.logging import request_id_var

logger = logging.getLogger(__name__)

# Qué código HTTP corresponde a cada tipo de error de la aplicación.
# Se busca por herencia: una subclase de NotFoundError también devuelve 404.
_STATUS_BY_ERROR: list[tuple[type[AppError], int]] = [
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (BusinessRuleViolationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (ExternalServiceError, status.HTTP_503_SERVICE_UNAVAILABLE),
]


def _status_for(error: AppError) -> int:
    for error_type, http_status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def error_body(detail: str, code: str, **extra: Any) -> dict[str, Any]:
    return {"detail": detail, "code": code, "request_id": request_id_var.get(), **extra}


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - FastAPI solo lo llama con AppError
    http_status = _status_for(exc)
    # Errores esperables: nivel INFO (o WARNING si es una dependencia caída).
    level = logging.WARNING if isinstance(exc, ExternalServiceError) else logging.INFO
    logger.log(level, "Error de aplicación: %s", exc.message, extra={"error_code": exc.code})
    return JSONResponse(status_code=http_status, content=error_body(exc.message, exc.code))


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Datos de entrada con formato inválido (falta un campo, tipo incorrecto...)."""
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {
            # loc = ("body", "email") -> "body.email"
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_body("Los datos enviados no son válidos.", "VALIDATION_ERROR", errors=errors),
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """Errores que genera el propio framework: ruta inexistente, método no permitido."""
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    codes = {404: "ROUTE_NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(str(exc.detail), codes.get(exc.status_code, "HTTP_ERROR")),
        headers=getattr(exc, "headers", None),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Cualquier excepción no prevista: es un bug o una falla real."""
    logger.exception("Error inesperado procesando %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body("Ocurrió un error inesperado.", "INTERNAL_ERROR"),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
