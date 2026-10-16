"""Logging estructurado con identificador de request y datos personales enmascarados.

Problema que resuelve: el original usaba `print`, sin forma de saber qué línea
pertenece a qué request, y llegó a imprimir filas con emails de deudores.

Tres piezas:
1. `request_id_var`: una "variable por request" (contextvar). Cada request HTTP
   recibe un id y todas las líneas de log de ese request lo llevan.
2. `PersonalDataFilter`: enmascara emails y números largos (DNI, teléfonos)
   antes de escribir la línea. Es una red de seguridad, no una excusa para
   loguear datos personales a propósito.
3. `JsonFormatter`: una línea JSON por evento, fácil de filtrar y buscar.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime

# Valor por defecto "-": fuera de un request (al arrancar, en scripts).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# 7 o más dígitos seguidos (con un + opcional): DNI, CUIT, teléfonos.
_LONG_NUMBER = re.compile(r"\+?\d{7,}")


def redact(text: str) -> str:
    """Enmascara datos personales en un texto.

    >>> redact("ana.perez@mail.com llamó desde 5491122334455")
    'a***@mail.com llamó desde [número oculto]'
    """
    text = _EMAIL.sub(r"\1***@\2", text)
    return _LONG_NUMBER.sub("[número oculto]", text)


class PersonalDataFilter(logging.Filter):
    """Filtro que enmascara el mensaje final de cada línea de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None  # el mensaje ya quedó armado y enmascarado
        return True  # True = la línea se escribe


class JsonFormatter(logging.Formatter):
    """Convierte cada evento de log en una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        # Campos extra opcionales: logger.info("...", extra={"status_code": 200})
        for key in ("method", "path", "status_code", "duration_ms", "error_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configura el logger raíz una sola vez al arrancar la app."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PersonalDataFilter())

    root = logging.getLogger()
    root.handlers = [handler]  # reemplaza handlers previos: evita líneas duplicadas
    root.setLevel(level)

    # uvicorn trae su propio log de accesos; lo reemplazamos por el nuestro
    # (ver RequestContextMiddleware), que incluye el request_id.
    logging.getLogger("uvicorn.access").disabled = True
