"""Errores de la aplicación.

Problema que resuelve: en el original los servicios lanzaban `HTTPException`, o sea
que la lógica de negocio dependía de FastAPI. Además, algunos fallos se devolvían
como éxito (HTTP 200 con "status": "error").

Acá el negocio lanza errores propios, que solo dicen QUÉ pasó. La traducción a
HTTP (404, 409, ...) la hace un único lugar: `mavic.api.error_handlers`.

    dominio/aplicación  --raise ConflictError-->  manejador global  -->  HTTP 409

Cada error tiene un `code` estable (ej. "CASE_NOT_FOUND") para que el frontend
pueda reaccionar sin depender del texto del mensaje.
"""

from typing import Any


class AppError(Exception):
    """Base de todos los errores esperables de la aplicación."""

    code: str = "APP_ERROR"
    default_message: str = "Ocurrió un error en la aplicación."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """El recurso no existe, o pertenece a otra empresa (no lo revelamos)."""

    code = "NOT_FOUND"
    default_message = "El recurso no existe."


class ConflictError(AppError):
    """La operación choca con el estado actual (duplicado, ya procesado...)."""

    code = "CONFLICT"
    default_message = "La operación entra en conflicto con el estado actual."


class BusinessRuleViolationError(AppError):
    """Los datos son válidos en forma, pero una regla del negocio lo impide."""

    code = "BUSINESS_RULE_VIOLATION"
    default_message = "La operación no está permitida por las reglas del negocio."


class AuthenticationError(AppError):
    """No hay sesión válida."""

    code = "NOT_AUTHENTICATED"
    default_message = "Sesión no autenticada."


class PermissionDeniedError(AppError):
    """Hay sesión, pero el usuario no tiene permiso para esta operación."""

    code = "PERMISSION_DENIED"
    default_message = "No tenés permiso para realizar esta operación."


class ExternalServiceError(AppError):
    """Falló una dependencia externa: base de datos, proveedor de voz, email...

    `retriable` indica si tiene sentido reintentar más tarde (un timeout sí,
    una credencial inválida no).
    """

    code = "EXTERNAL_SERVICE_ERROR"
    default_message = "Un servicio externo no está disponible."

    def __init__(
        self,
        message: str | None = None,
        *,
        service: str,
        retriable: bool = True,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code, details={"service": service})
        self.service = service
        self.retriable = retriable
